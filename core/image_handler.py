"""
图像处理主逻辑
"""

import asyncio
import base64
import hashlib
import tempfile
from pathlib import Path
from typing import List, Optional
from astrbot.api import logger
from astrbot.api.star import StarTools
import astrbot.api.message_components as Comp

try:
    from ..constants import PLUGIN_NAME
except ImportError:
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

        # 数据目录
        self.data_dir = StarTools.get_data_dir(self.plugin_name)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """异步初始化清理管理器"""
        try:
            await self.cleanup_manager.start()
            logger.info("清理管理器已启动")
        except Exception as e:
            logger.error(f"清理管理器启动失败: {e}", exc_info=True)
            # 即使启动失败，插件仍可运行，只是没有定时清理

    async def process_mirror(self, event, mode: str):
        """
        处理图像对称请求

        Args:
            event: 消息事件
            mode: 对称模式
        """
        try:
            logger.info(f"开始处理图像对称请求，模式: {mode}")

            # 1. 尝试获取@的用户头像
            if self.config.enable_at_avatar:
                at_qq = self.message_utils.extract_at_qq(event)
                if at_qq:
                    async for result in self._process_avatar(event, at_qq, mode):
                        yield result
                    return

            # 2. 提取图像源
            image_sources = self.message_utils.extract_image_sources(event)
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

            for image_source in image_sources:
                try:
                    input_path = await self._prepare_image_file(image_source)
                    if not input_path:
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
                yield self._get_error_message(event, "处理失败")

        except Exception as e:
            logger.error(f"处理指令异常: {str(e)}", exc_info=True)
            yield self._get_error_message(event, "处理失败")

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
            # 生成输出文件
            output_filename = self.file_utils.generate_filename(source_info, mode)
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
                yield self._get_error_message(event, "处理失败")

        except Exception as e:
            logger.error(f"处理单图像失败: {str(e)}", exc_info=True)
            yield self._get_error_message(event, "处理失败")

    async def _prepare_image_file(self, image_source: str) -> Optional[Path]:
        """准备图像文件 - 优化版"""
        # 如果是URL，下载
        if image_source.startswith(("http://", "https://")):
            return await self._download_image(image_source)

        # 如果是base64，提前计算摘要传递
        elif image_source.startswith("base64://"):
            source_hash = hashlib.md5(image_source.encode()).hexdigest()[:16]
            return await self._decode_base64_image(image_source, source_hash)

        # 本地文件
        else:
            return self._get_local_file(image_source)

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

    async def _decode_base64_image(self, base64_data: str, data_hash: str = None) -> Optional[Path]:
        """解码base64图像 - 优化版，使用预计算摘要"""
        try:
            # 移除base64前缀
            if base64_data.startswith("base64://"):
                base64_data = base64_data[len("base64://") :]

            # 1. 检查base64字符串长度
            MAX_BASE64_LENGTH = 20 * 1024 * 1024 * 4 // 3  # 对应20MB原始数据
            if len(base64_data) > MAX_BASE64_LENGTH:
                logger.error(f"Base64数据过长: {len(base64_data)}字符")
                return None

            # 将解码操作放入线程池避免阻塞
            loop = asyncio.get_running_loop()

            def decode_in_thread():
                return base64.b64decode(base64_data, validate=True)

            image_data = await loop.run_in_executor(None, decode_in_thread)

            # 3. 检查解码后大小
            max_size = (
                self.config.max_image_size_bytes if self.config else 10 * 1024 * 1024
            )
            if len(image_data) > max_size:
                logger.error(f"解码后图像过大: {len(image_data)}字节 > {max_size}字节")
                return None

            # 4. 保存：使用预计算的数据hash而不是完整base64字符串
            source_info = data_hash if data_hash else f"base64_{len(base64_data)}"
            ext = self.file_utils.detect_image_format_by_magic(image_data) or ".png"
            return await self._save_temp_file(image_data, source_info, ext)

        except Exception as e:
            logger.error(f"base64解码失败: {e}")
            return None

    def _get_local_file(self, file_path: str) -> Optional[Path]:
        """获取本地文件 - 安全版本（防路径遍历）"""
        try:
            # 只允许相对路径，且必须在data_dir内
            clean_path = Path(file_path)

            # 检查是否为相对路径（不允许绝对路径）
            if clean_path.is_absolute():
                logger.warning(f"拒绝绝对路径: {file_path}")
                return None

            # 构建安全路径
            safe_path = (self.data_dir / clean_path).resolve()

            # 使用 is_relative_to 进行严格的路径层级检查（Python 3.9+）
            # 防止路径遍历攻击，如 ../../../etc/passwd
            data_dir_resolved = self.data_dir.resolve()
            if safe_path.is_relative_to(data_dir_resolved):
                if safe_path.exists():
                    return safe_path
            else:
                logger.warning(f"路径越界: {file_path}")

        except Exception as e:
            logger.warning(f"本地路径解析失败 {file_path}: {e}")

        return None

    async def _save_temp_file(
        self, data: bytes, prefix: str, extension: str
    ) -> Optional[Path]:
        """保存临时文件"""
        try:
            with tempfile.NamedTemporaryFile(
                prefix=prefix, suffix=extension, delete=False, dir=str(self.data_dir)
            ) as tmp:
                tmp.write(data)
                return Path(tmp.name)
        except Exception as e:
            logger.error(f"保存临时文件失败: {e}")
            return None

    def _cleanup_input_file(self, file_path: Path):
        """清理输入文件 - 更安全版本"""
        if not file_path or not file_path.exists():
            return

        try:
            # 更精确的判断：文件在插件数据目录内且是临时文件
            if file_path.parent == self.data_dir:
                filename = file_path.name.lower()
                # 修复前缀匹配：匹配"downloaded"和"downloaded_"等多种前缀
                temp_prefixes = [
                    "tmp",
                    "temp",
                    "avatar_",
                    "avatar",
                    "downloaded",
                    "downloaded_",
                    "base64",
                    "base64_",
                ]

                if any(filename.startswith(prefix) for prefix in temp_prefixes):
                    file_path.unlink()
                    logger.info(f"清理临时输入文件: {file_path.name}")
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

    def _get_error_message(self, event, message: str):
        """
        获取错误消息

        Args:
            event: 消息事件对象
            message: 错误消息
        """
        if self.config.silent_mode:
            return event.plain_result(f"❌ {message}")
        else:
            return event.plain_result(f"❌ {message}")

    async def cleanup(self):
        await self.cleanup_manager.cleanup_all()

        # 关闭网络连接
        if hasattr(self.network_utils, "cleanup"):
            await self.network_utils.cleanup()

        self.network_utils = None
        self.message_utils = None
        self.file_utils = None
        self.avatar_service = None
