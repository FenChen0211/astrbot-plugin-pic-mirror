"""清理管理器"""

import asyncio
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from astrbot.api import logger
from astrbot.api.star import StarTools

from ..constants import PLUGIN_NAME


class CleanupManager:
    """清理管理器"""

    TEMP_FILE_PREFIXES = [
        "mirror_tmp_",
        "mirror_temp_",
        "mirror_avatar_",
        "mirror_downloaded_",
        "mirror_base64_",
    ]

    def __init__(self, config, plugin_name: str = None):
        self.config = config
        self.plugin_name = plugin_name or PLUGIN_NAME  # 默认值
        self.cleanup_queue: List[Dict[str, Any]] = []
        self._pending_tasks: Set[asyncio.Task] = set()  # 跟踪所有挂起任务
        self._cleanup_task: Optional[asyncio.Task] = None  # 不立即创建
        self._stop_event = asyncio.Event()
        self._queue_lock = threading.Lock()  # 使用线程锁而非异步锁（操作轻量）

    def _track_task(self, task: asyncio.Task):
        """跟踪异步任务，确保cleanup_all时能正确取消"""
        def done_callback(t: asyncio.Task):
            self._pending_tasks.discard(t)
        
        # 如果任务已完成，直接从集合中移除（避免竞态条件）
        if task.done():
            return
        
        self._pending_tasks.add(task)
        task.add_done_callback(done_callback)

    async def start(self):
        """手动启动清理任务"""
        if self.config.enable_auto_cleanup and not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """清理任务"""
        while not self._stop_event.is_set():
            try:
                await self._process_cleanup_queue()
            except (OSError, PermissionError) as e:
                logger.error(f"清理任务文件操作异常: {e}")
            except Exception as e:
                logger.error(f"清理任务未知异常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 异常后等待

            # 使用 wait_for 来响应停止信号
            try:
                timeout = (
                    self.config.cleanup_loop_interval
                    if hasattr(self.config, "cleanup_loop_interval")
                    else 300
                )
                await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
                break  # 收到停止信号，退出循环
            except asyncio.TimeoutError:
                continue  # 超时，继续下一次清理

    async def _process_cleanup_queue(self):
        """处理清理队列 - 线程安全版本"""
        current_time = time.time()

        with self._queue_lock:  # 使用线程锁
            items_to_remove = []

            for item in self.cleanup_queue:
                file_path = item.get("path")
                expiry_time = item.get("expiry_time")

                if not file_path or not expiry_time or not file_path.exists():
                    items_to_remove.append(item)
                    continue

                if current_time >= expiry_time:
                    try:
                        file_path.unlink()
                        logger.info(f"定时清理文件: {file_path.name}")
                        items_to_remove.append(item)
                    except Exception as e:
                        logger.warning(f"清理文件失败 {file_path}: {e}")

            # 批量移除
            for item in items_to_remove:
                if item in self.cleanup_queue:
                    self.cleanup_queue.remove(item)

    def _validate_cleanup_path(self, file_path: Path) -> bool:
        """
        验证清理路径的安全性

        Args:
            file_path: 待验证的文件路径

        Returns:
            bool: 路径是否安全
        """
        if not self.plugin_name:
            return True

        try:
            plugin_data_dir = StarTools.get_data_dir(self.plugin_name)
            safe_path = (plugin_data_dir / file_path).resolve()
            data_dir_resolved = plugin_data_dir.resolve()

            if not safe_path.is_relative_to(data_dir_resolved):
                logger.error(
                    f"[清理管理器] 拒绝清理外部路径（路径遍历攻击尝试）: {file_path}"
                )
                return False

            if safe_path.is_symlink():
                try:
                    real_path = safe_path.resolve(strict=True)
                    if not real_path.is_relative_to(data_dir_resolved):
                        logger.error(f"拒绝清理符号链接指向的外部路径: {file_path}")
                        return False
                except (FileNotFoundError, RuntimeError) as e:
                    logger.error(f"符号链接解析失败: {e}")
                    return False

            return True
        except Exception as e:
            logger.error(
                f"[清理管理器] 路径校验失败（原因: {type(e).__name__}: {e}），拒绝执行清理以确保安全",
                exc_info=True,
            )
            return False

    def schedule_cleanup(self, file_path: Path, keep_hours: int):
        """安排文件清理 - 安全版本"""
        if not self._validate_cleanup_path(file_path):
            return

        if keep_hours <= 0:
            task = asyncio.create_task(self._cleanup_immediately(file_path))
            self._track_task(task)
        else:
            expiry_time = time.time() + (keep_hours * 3600)
            # 直接执行（操作轻量，使用线程锁）
            with self._queue_lock:
                self.cleanup_queue.append(
                    {
                        "path": file_path,
                        "expiry_time": expiry_time,
                        "scheduled_time": time.time(),
                    }
                )
            logger.info(f"已安排清理 {file_path.name}, {keep_hours}小时后删除")

    async def _cleanup_immediately(self, file_path: Path):
        """立即清理"""
        await asyncio.sleep(0.5)  # 确保发送完成
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"立即清理文件: {file_path.name}")
        except Exception as e:
            logger.warning(f"立即清理失败 {file_path}: {e}")

    async def cleanup_all(self):
        """清理所有资源"""
        logger.info("开始清理清理管理器资源...")

        if self._cleanup_task and not self._cleanup_task.done():
            self._stop_event.set()
            timeout = (
                self.config.cleanup_timeout
                if hasattr(self.config, "cleanup_timeout")
                else 5.0
            )
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    f"清理任务在{timeout}秒内未响应（可能正在处理文件或卡住），强制取消"
                )
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

        # 取消所有挂起的清理任务
        for task in list(self._pending_tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._pending_tasks.clear()

        # 处理所有待清理的文件
        await self._process_cleanup_queue()

        # 清空队列
        self.cleanup_queue.clear()

        logger.info("清理管理器资源清理完成")

    def cleanup_temp_dirs(self):
        """清理临时目录"""
        try:
            temp_dir = Path(tempfile.gettempdir())
            cleaned_count = 0

            for prefix in self.TEMP_FILE_PREFIXES:
                pattern = f"{prefix}*"
                for temp_file in temp_dir.glob(pattern):
                    if temp_file.is_file():
                        try:
                            temp_file.unlink()
                            cleaned_count += 1
                        except Exception as e:
                            logger.debug(f"无法删除临时文件 {temp_file.name}: {e}")

            if cleaned_count > 0:
                logger.info(f"清理临时目录完成，共清理 {cleaned_count} 个文件")
        except Exception as e:
            logger.warning(f"清理临时目录时出错: {e}")
