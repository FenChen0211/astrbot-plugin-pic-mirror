"""
清理管理器
"""
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any
from astrbot.api import logger


class CleanupManager:
    """清理管理器"""
    
    def __init__(self, config):
        self.config = config
        self.cleanup_queue: List[Dict[str, Any]] = []
        
        if config.enable_auto_cleanup:
            asyncio.create_task(self._cleanup_task())
    
    async def _cleanup_task(self):
        """清理任务"""
        while True:
            try:
                await self._process_cleanup_queue()
            except Exception as e:
                logger.error(f"清理任务异常: {e}")
            
            await asyncio.sleep(300)  # 5分钟检查一次
    
    async def _process_cleanup_queue(self):
        """处理清理队列"""
        current_time = time.time()
        
        for item in self.cleanup_queue[:]:
            file_path = item.get("path")
            expiry_time = item.get("expiry_time")
            
            if not file_path or not expiry_time or not file_path.exists():
                self.cleanup_queue.remove(item)
                continue
            
            if current_time >= expiry_time:
                try:
                    file_path.unlink()
                    logger.info(f"定时清理文件: {file_path.name}")
                    self.cleanup_queue.remove(item)
                except Exception as e:
                    logger.warning(f"清理文件失败 {file_path}: {e}")
    
    def schedule_cleanup(self, file_path: Path, keep_hours: int):
        """安排文件清理"""
        if keep_hours <= 0:
            # 立即清理
            asyncio.create_task(self._cleanup_immediately(file_path))
        else:
            # 延迟清理
            expiry_time = time.time() + (keep_hours * 3600)
            self.cleanup_queue.append({
                "path": file_path,
                "expiry_time": expiry_time,
                "scheduled_time": time.time()
            })
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
        """清理所有文件"""
        # 这里可以添加全局清理逻辑
        pass