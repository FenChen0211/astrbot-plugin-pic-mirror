"""
头像服务
"""

from typing import Optional
from astrbot.api import logger


class AvatarService:
    """头像服务类"""

    def __init__(self, network_utils):
        self.network_utils = network_utils

    async def get_avatar(self, qq_number: str, size: int = 640) -> Optional[bytes]:
        """
        获取QQ用户头像

        Args:
            qq_number: QQ号码
            size: 头像尺寸

        Returns:
            头像图片字节数据
        """
        # 使用传入的 network_utils 来获取头像，避免重复实现
        try:
            avatar_data = await self.network_utils.get_qq_avatar(qq_number, size)
            if avatar_data:
                logger.info(f"成功获取头像: {qq_number}")
                return avatar_data
            else:
                logger.error(f"获取头像失败: {qq_number}")
                return None
        except Exception as e:
            logger.error(f"获取头像异常 {qq_number}: {e}")
            return None

    
