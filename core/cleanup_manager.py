"""清理管理器"""

import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from astrbot.api import logger
from astrbot.api.star import StarTools

try:
    from ..constants import PLUGIN_NAME
except ImportError:
    from ..constants import PLUGIN_NAME


class CleanupManager:
    """清理管理器"""

    def __init__(self, config, plugin_name: str = None):
        self.config = config
        self.plugin_name = plugin_name or PLUGIN_NAME  # 默认值
        self.cleanup_queue: List[Dict[str, Any]] = []
        self._cleanup_task: Optional[asyncio.Task] = None  # 不立即创建
        self._stop_event = asyncio.Event()
        self._queue_lock = asyncio.Lock()  # ✅ 添加锁

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
                await asyncio.wait_for(self._stop_event.wait(), timeout=300)  # 5分钟检查一次
                break  # 收到停止信号，退出循环
            except asyncio.TimeoutError:
                continue  # 超时，继续下一次清理

    async def _process_cleanup_queue(self):
        """处理清理队列 - 线程安全版本"""
        current_time = time.time()
        
        async with self._queue_lock:  # ✅ 加锁
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

    def schedule_cleanup(self, file_path: Path, keep_hours: int):
        """安排文件清理 - 安全版本"""
        # 验证路径是否在插件数据目录内
        if self.plugin_name:
            try:
                plugin_data_dir = StarTools.get_data_dir(self.plugin_name)
                if not str(file_path.resolve()).startswith(str(plugin_data_dir.resolve())):
                    logger.error(f"拒绝清理外部路径: {file_path}")
                    return
            except Exception as e:
                logger.warning(f"无法验证插件数据目录: {e}")
                pass
            
        if keep_hours <= 0:
            asyncio.create_task(self._cleanup_immediately(file_path))
        else:
            expiry_time = time.time() + (keep_hours * 3600)
            
            async def _schedule():
                async with self._queue_lock:  # ✅ 加锁
                    self.cleanup_queue.append({
                        "path": file_path,
                        "expiry_time": expiry_time,
                        "scheduled_time": time.time(),
                    })
            
            asyncio.create_task(_schedule())
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
        
        # 停止清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("清理任务停止超时，强制取消")
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
        
        # 处理所有待清理的文件
        await self._process_cleanup_queue()
        
        # 清空队列
        self.cleanup_queue.clear()
        
        logger.info("清理管理器资源清理完成")