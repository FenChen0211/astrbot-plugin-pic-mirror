"""
图像处理主逻辑
"""

import asyncio
import base64
import contextlib
import hashlib
import tempfile
import time
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse
from astrbot.api import logger
from astrbot.api.star import StarTools
import astrbot.api.message_components as Comp

from ..constants import PLUGIN_NAME

# 统一使用相对导入
from ..utils.network_utils import NetworkUtils
from ..utils.message_utils import MessageUtils
from ..utils.file_utils import FileUtils
from ..core.avatar_service import AvatarService
from ..core.cleanup_manager import CleanupManager
from ..image_processor import MirrorProcessor


class ImageHandler:
    """图像处理器"""

    TEMP_FILE_PREFIXES = [
        "mirror_tmp_",
        "mirror_temp_",
        "mirror_avatar_",
        "mirror_downloaded_",
        "mirror_base64_",
    ]

    RATE_LIMIT_WINDOW_SECONDS = 60  # 频率限制时间窗口（秒）

    def __init__(self, config_service, plugin_name: str = None):
        self.config_service = config_service
        self.config = config_service.config  # ✅ 直接使用

        # 初始化组件
        self.network_utils = NetworkUtils(timeout=self.config.processing_timeout)
        self.message_utils = MessageUtils()
        self.file_utils = FileUtils()
        self.avatar_service = AvatarService(self.network_utils)
        # 传递插件名给CleanupManager
        self.plugin_name = plugin_name or PLUGIN_NAME
        self.cleanup_manager = CleanupManager(self.config, self.plugin_name)
        self._last_prepare_error: Optional[str] = None

        # 数据目录
        self.data_dir = StarTools.get_data_dir(self.plugin_name)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 频率限制相关初始化
        self._user_request_times = {}  # 格式: {user_id: [timestamp1, timestamp2...]}
        self._rate_limit_lock = asyncio.Lock()
        self._processing_semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)

        # 初始化清理任务
        self._cleanup_task = None

    @property
    def rate_limit_lock(self):
        """获取频率限制锁"""
        return self._rate_limit_lock

    async def initialize(self):
        """异步初始化清理管理器"""
        try:
            await self.cleanup_manager.start()
            # 启动定期清理频率限制记录的任务
            self._cleanup_task = asyncio.create_task(
                self._periodic_cleanup_rate_limits()
            )
            # 使用cleanup_manager跟踪任务，确保卸载时能正确取消
            self.cleanup_manager._track_task(self._cleanup_task)
            logger.info("清理管理器已启动")
        except Exception as e:
            logger.error(f"清理管理器启动失败: {e}", exc_info=True)
            # 即使启动失败，插件仍可运行，只是没有定时清理

    async def _periodic_cleanup_rate_limits(self):
        """定期清理过期的频率限制记录"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                self._cleanup_old_rate_limit_records()
            except asyncio.CancelledError:
                logger.info("频率限制清理任务已取消")
                break
            except Exception as e:
                logger.error(f"频率限制清理任务异常: {e}", exc_info=True)

    async def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """检查用户请求频率限制"""
        if not self.config.rate_limit_enabled:
            return True, None

        current_time = time.time()
        window_start = current_time - self.RATE_LIMIT_WINDOW_SECONDS

        async with self._rate_limit_lock:
            user_requests = self._user_request_times.get(user_id, [])

            recent_requests = [
                req_time for req_time in user_requests if req_time >= window_start
            ]
            self._user_request_times[user_id] = recent_requests

            if len(recent_requests) >= self.config.rate_limit_per_minute:
                remaining_time = self.RATE_LIMIT_WINDOW_SECONDS - (current_time - min(recent_requests))
                return False, f"请求过于频繁，请{int(remaining_time)}秒后再试"

            self._user_request_times[user_id].append(current_time)
            return True, None

    def _cleanup_old_rate_limit_records(self):
        """清理过期的频率限制记录"""
        current_time = time.time()
        window_start = current_time - self.RATE_LIMIT_WINDOW_SECONDS

        with contextlib.suppress(Exception):
            new_user_requests = {}
            for user_id, requests in self._user_request_times.items():
                recent_requests = [
                    req_time for req_time in requests if req_time >= window_start
                ]
                if recent_requests:
                    new_user_requests[user_id] = recent_requests

            self._user_request_times = new_user_requests

    async def process_mirror(self, event, mode: str):
        """
        处理图像对称请求

        Args:
            event: 消息事件
            mode: 对称模式
        """
        try:
            user_id = event.get_sender_id()
            allowed, error_msg = await self.check_rate_limit(user_id)

            if not allowed:
                logger.warning(f"用户 {user_id} 触发频率限制")
                yield self._get_error_message(event, error_msg)
                return

            async with self._processing_semaphore:
                logger.info(f"开始处理图像对称请求，用户: {user_id}, 模式: {mode}")

                # 1. 尝试获取@的用户头像
                if self.config.enable_at_avatar:
                    at_qq = self.message_utils.extract_at_qq(event)
                    if at_qq and self._can_process_qq_avatar(event, at_qq):
                        async for result in self._process_avatar(event, at_qq, mode):
                            yield result
                        return

                # 2. 提取图像源
                image_sources = self.message_utils.extract_image_sources(event)
                trusted_local_paths = set(
                    self.message_utils.get_trusted_event_media_paths(event)
                )
                logger.info(f"找到的图像源: {len(image_sources)}个")

                if not image_sources:
                    yield self._get_error_message(event, "未找到图像")
                    return

                # 3. 发送处理中提示（非静默模式）
                if not self.config.silent_mode:
                    processing_msg = MirrorProcessor.get_mode_description(mode)
                    yield event.plain_result(f"🔄 正在处理图像: {processing_msg}...")

                # 4. 处理图像源
                processed = False
                prepare_errors = []

                for image_source in image_sources:
                    try:
                        input_path = await self._prepare_image_file(
                            image_source, trusted_local_paths
                        )
                        if not input_path:
                            if self._last_prepare_error:
                                prepare_errors.append(self._last_prepare_error)
                                self._last_prepare_error = None
                            continue

                        async for result in self._process_single_image(
                            event, input_path, mode, str(image_source)
                        ):
                            yield result
                            processed = True

                    except Exception as e:
                        logger.error(
                            f"处理图像源失败 {image_source}: {str(e)}", exc_info=True
                        )
                        continue

                if not processed:
                    message = prepare_errors[-1] if prepare_errors else "未能处理任何图像"
                    yield self._get_error_message(event, "处理失败", message)

        except Exception as e:
            logger.error(f"处理指令异常: {str(e)}", exc_info=True)
            yield self._get_error_message(event, "处理失败", str(e))

    @staticmethod
    def _can_process_qq_avatar(event, target: str) -> bool:
        """仅在 OneBot 消息中将 @目标解释为可查询的 QQ 头像。"""
        platform_name = ""
        try:
            platform_name = str(event.get_platform_name()).lower()
        except (AttributeError, TypeError):
            pass

        if platform_name != "aiocqhttp":
            logger.debug(
                f"跳过 @头像处理: {platform_name or '未知'} 平台的 At 目标不是可用于 qlogo 的 QQ 号"
            )
            return False

        # qlogo 接口只接受真实 QQ UIN。避免将平台自身的唤醒标记或 OpenID 当作 QQ 号。
        if not re.fullmatch(r"[1-9]\d{4,11}", str(target)):
            logger.debug(f"跳过无效 QQ 头像目标: {target}")
            return False

        return True

    async def _process_avatar(self, event, qq_number: str, mode: str):
        """处理用户头像"""
        logger.info(f"处理用户头像: {qq_number}")

        avatar_data = await self.avatar_service.get_avatar(qq_number)
        if not avatar_data:
            yield self._get_error_message(event, "获取头像失败")
            return

        # 保存头像临时文件
        input_path = await self._save_temp_file(
            avatar_data, f"avatar_{qq_number}", ".jpg"
        )
        if not input_path:
            yield self._get_error_message(event, "保存头像失败")
            return

        # 处理头像
        async for result in self._process_single_image(
            event, input_path, mode, f"qq_{qq_number}"
        ):
            yield result

    async def _process_single_image(
        self, event, input_path: Path, mode: str, source_info: str
    ):
        """处理单个图像"""
        try:
            # 从实际输入文件获取扩展名，确保 GIF 保持 .gif 扩展名
            input_ext = input_path.suffix.lower() if input_path.suffix else None
            output_filename = self.file_utils.generate_filename(source_info, mode, input_ext)
            output_path = self.data_dir / output_filename

            logger.info(f"处理图像: {input_path} -> {output_path}")

            # 处理图像
            success, message = await MirrorProcessor.process_image(
                str(input_path),
                str(output_path),
                mode,
                self.config,
            )

            # 清理输入文件
            self._cleanup_input_file(input_path)

            if success:
                # 发送结果
                yield self._get_result_message(event, output_path, mode)

                # 安排清理
                if self.config.enable_auto_cleanup:
                    self.cleanup_manager.schedule_cleanup(
                        output_path, self.config.keep_files_hours
                    )

            else:
                logger.warning(f"图像处理失败: {message}")
                yield self._get_error_message(event, "处理失败", message)

        except Exception as e:
            logger.error(f"处理单图像失败: {str(e)}", exc_info=True)
            yield self._get_error_message(event, "处理失败")

    async def _prepare_image_file(
        self,
        image_source: str,
        trusted_local_paths=None,
    ) -> Optional[Path]:
        """准备图像文件 - 优化版"""
        self._last_prepare_error = None

        # 如果是URL，下载
        if image_source.startswith(("http://", "https://")):
            path = await self._download_image(image_source)
            if not path:
                self._last_prepare_error = "图片下载失败或图片格式不受支持"
            return path

        # 如果是base64，提前计算摘要传递
        elif image_source.startswith("base64://"):
            source_hash = hashlib.md5(image_source.encode()).hexdigest()[:16]
            path = await self._decode_base64_image(image_source, source_hash)
            if not path:
                self._last_prepare_error = "Base64 图片解析失败或图片超过大小限制"
            return path

        # 本地文件
        else:
            return self._get_local_file(image_source, trusted_local_paths)

    async def _download_image(self, url: str) -> Optional[Path]:
        """下载图像并正确识别格式"""
        logger.info(f"下载网络图片: {url}")

        image_data = await self.network_utils.download_image(url)
        if not image_data:
            return None

        # 优先使用魔数检测，回退到URL扩展名
        ext = self.file_utils.detect_image_format_by_magic(image_data)
        if not ext:
            # 魔数检测失败时使用URL扩展名
            ext = self.file_utils.get_file_extension(url) or ".jpg"

        return await self._save_temp_file(image_data, "downloaded", ext)

    async def _decode_base64_image(
        self, base64_data: str, data_hash: str = None
    ) -> Optional[Path]:
        """解码base64图像 - 优化版，使用预计算摘要"""
        try:
            if base64_data.startswith("base64://"):
                base64_data = base64_data[len("base64://") :]

            max_size = (
                self.config.max_image_size_bytes if self.config else 10 * 1024 * 1024
            )
            max_base64_length = min(
                int(max_size * 4 / 3) + 100,  # Base64编码会增加约33%长度，加100缓冲
                20 * 1024 * 1024  # 限制最大20MB Base64字符串
            )
            if len(base64_data) > max_base64_length:
                logger.error(f"Base64数据过长: {len(base64_data)}字符 > {max_base64_length}字符")
                return None

            loop = asyncio.get_running_loop()

            def decode_in_thread():
                return base64.b64decode(base64_data, validate=True)

            image_data = await loop.run_in_executor(None, decode_in_thread)

            if len(image_data) > max_size:
                logger.error(f"解码后图像过大: {len(image_data)}字节 > {max_size}字节")
                return None

            source_info = data_hash if data_hash else f"base64_{len(base64_data)}"
            ext = self.file_utils.detect_image_format_by_magic(image_data) or ".png"
            return await self._save_temp_file(image_data, source_info, ext)

        except Exception as e:
            logger.error(f"base64解码失败: {e}")
            return None

    def _get_local_file(
        self, file_path: str, trusted_local_paths=None
    ) -> Optional[Path]:
        """获取本地文件 - 安全版本（防路径遍历）"""
        try:
            clean_path = self._local_reference_to_path(file_path)

            # 仅接受 AstrBot 为当前事件登记过的绝对路径。
            if clean_path.is_absolute():
                trusted_resolved = set()
                for trusted_path in trusted_local_paths or ():
                    try:
                        trusted_resolved.add(
                            self._local_reference_to_path(trusted_path).resolve()
                        )
                    except (OSError, ValueError):
                        continue

                resolved_path = clean_path.resolve()
                if resolved_path not in trusted_resolved:
                    logger.warning(f"拒绝未受信任的绝对路径: {file_path}")
                    self._last_prepare_error = (
                        "已拒绝未由 AstrBot 当前消息提供的绝对路径。"
                        "请回复/发送图片，或使用插件数据目录内的相对文件名。"
                    )
                    return None
                if not resolved_path.is_file():
                    self._last_prepare_error = f"本地媒体文件不存在: {clean_path}"
                    return None
                return resolved_path

            # 构建安全路径
            safe_path = (self.data_dir / clean_path).resolve()

            # 使用 is_relative_to 进行严格的路径层级检查（Python 3.9+）
            # 防止路径遍历攻击，如 ../../../etc/passwd
            data_dir_resolved = self.data_dir.resolve()
            if safe_path.is_relative_to(data_dir_resolved):
                if safe_path.exists():
                    return safe_path
                self._last_prepare_error = f"本地文件不存在: {clean_path}"
            else:
                logger.warning(f"路径越界: {file_path}")
                self._last_prepare_error = (
                    "路径超出插件数据目录，已拒绝读取。请使用插件数据目录内的相对路径。"
                )

        except Exception as e:
            logger.warning(f"本地路径解析失败 {file_path}: {e}")
            self._last_prepare_error = f"本地路径解析失败: {e}"

        return None

    @staticmethod
    def _local_reference_to_path(file_path: str) -> Path:
        """将普通路径或 file URI 转换为本地路径。"""
        if not isinstance(file_path, str):
            raise ValueError("本地路径必须是字符串")

        parsed = urlparse(file_path)
        if parsed.scheme.lower() != "file":
            return Path(file_path)

        netloc = unquote(parsed.netloc or "")
        path = unquote(parsed.path or "")
        if re.fullmatch(r"[A-Za-z]:", netloc):
            return Path(f"{netloc}{path}")
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        if netloc and netloc.lower() != "localhost":
            path = f"//{netloc}{path}"
        return Path(path)

    async def _save_temp_file(
        self, data: bytes, prefix: str, extension: str
    ) -> Optional[Path]:
        """保存临时文件 - 使用独特前缀避免误删"""
        try:
            # 使用独特前缀：mirror_ + 原前缀 +
            unique_prefix = f"mirror_{prefix}_"
            with tempfile.NamedTemporaryFile(
                prefix=unique_prefix,
                suffix=extension,
                delete=False,
                dir=str(self.data_dir),
            ) as tmp:
                tmp.write(data)
                return Path(tmp.name)
        except Exception as e:
            logger.error(f"保存临时文件失败: {e}")
            return None

    def _cleanup_input_file(self, file_path: Path):
        """清理输入文件 - 使用前缀列表确保安全"""
        if not file_path or not file_path.exists():
            return

        try:
            if file_path.parent == self.data_dir:
                filename = file_path.name.lower()
                # 使用前缀列表检查，灵活可控
                for prefix in self.TEMP_FILE_PREFIXES:
                    if filename.startswith(prefix):
                        file_path.unlink()
                        logger.info(f"清理临时输入文件: {file_path.name}")
                        return
        except Exception as e:
            logger.warning(f"清理输入文件失败 {file_path}: {e}")

    def _get_result_message(self, event, output_path: Path, mode: str):
        """
        获取结果消息

        Args:
            event: 消息事件对象
            output_path: 输出文件路径
            mode: 对称模式
        """
        if self.config.silent_mode:
            return event.chain_result([Comp.Image(file=str(output_path))])
        else:
            description = MirrorProcessor.get_mode_description(mode)
            return event.chain_result(
                [
                    Comp.Plain(text=f"✅ {description}\n"),
                    Comp.Image(file=str(output_path)),
                ]
            )

    def _get_error_message(self, event, message: str, detail: str = None):
        """
        获取错误消息

        Args:
            event: 消息事件对象
            message: 简要错误消息
            detail: 详细错误信息（非静默模式时显示）
        """
        if self.config.silent_mode:
            return event.plain_result(f"❌ {message}")
        else:
            full_msg = f"❌ {message}"
            if detail:
                full_msg += f"\n详情: {detail}"
            return event.plain_result(full_msg)

    async def cleanup(self):
        await self.cleanup_manager.cleanup_all()

        self.cleanup_manager.cleanup_temp_dirs()

        if hasattr(self.network_utils, "cleanup"):
            await self.network_utils.cleanup()

        if hasattr(self.avatar_service, "cleanup"):
            await self.avatar_service.cleanup()

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("ImageHandler 资源清理完成")
