"""
头像服务
"""

import aiohttp
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
        # 尝试多个QQ头像API
        urls = [
            f"http://q1.qlogo.cn/g?b=qq&nk={qq_number}&s={size}",
            f"http://q2.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
            f"http://q4.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
        ]

        for url in urls:
            try:
                avatar_data = await self._download_avatar(url)
                if avatar_data:
                    logger.info(f"成功获取头像: {qq_number}")
                    return avatar_data
            except Exception as e:
                logger.debug(f"头像API失败 {url}: {e}")
                continue

        logger.error(f"所有头像API都失败: {qq_number}")
        return None

    async def _download_avatar(self, url: str) -> Optional[bytes]:
        """下载头像"""
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.read()
                    return None
        except Exception as e:
            logger.debug(f"下载头像失败 {url}: {e}")
            return None
