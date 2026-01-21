"""
网络请求工具模块
"""

import aiohttp
import asyncio
from typing import Optional
from astrbot.api import logger


class NetworkUtils:
    """网络请求工具类"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        下载图片

        Args:
            url: 图片URL

        Returns:
            图片字节数据，失败返回None
        """
        # QQ图片需要将https替换为http
        url = url.replace("https://", "http://")

        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        logger.error(f"下载失败，状态码: {response.status}")
                        return None

                    content = await response.read()
                    logger.info(f"成功下载图片，大小: {len(content)} bytes")
                    return content

        except asyncio.TimeoutError:
            logger.error(f"下载超时: {url}")
            return None
        except Exception as e:
            logger.error(f"下载图片失败 {url}: {str(e)}")
            return None

    async def get_qq_avatar(self, qq_number: str, size: int = 640) -> Optional[bytes]:
        """
        获取QQ用户头像

        Args:
            qq_number: QQ号码
            size: 头像尺寸 (默认640)

        Returns:
            头像图片字节数据，失败返回None
        """
        # QQ头像API列表（多个备用地址）
        avatar_urls = [
            f"http://q1.qlogo.cn/g?b=qq&nk={qq_number}&s={size}",
            f"http://q2.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
            f"http://q4.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
            f"https://q.qlogo.cn/g?b=qq&nk={qq_number}&s={size}",
        ]

        for url in avatar_urls:
            try:
                avatar_data = await self._download_with_retry(url)
                if avatar_data:
                    logger.info(f"成功获取QQ头像: {qq_number}")
                    return avatar_data
            except Exception as e:
                logger.debug(f"头像API失败 {url}: {e}")
                continue

        logger.error(f"所有头像API都失败: {qq_number}")
        return None

    async def _download_with_retry(self, url: str, retries: int = 2) -> Optional[bytes]:
        """
        带重试的下载

        Args:
            url: 下载地址
            retries: 重试次数

        Returns:
            下载的数据
        """
        for attempt in range(retries + 1):
            try:
                async with aiohttp.ClientSession() as client:
                    # 设置超时和headers
                    timeout = aiohttp.ClientTimeout(total=10)
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }

                    async with client.get(
                        url, timeout=timeout, headers=headers
                    ) as response:
                        if response.status == 200:
                            return await response.read()
                        elif response.status == 404:
                            # 404不需要重试
                            return None
            except Exception as e:
                if attempt == retries:
                    logger.debug(f"下载失败 {url} (尝试{attempt + 1}次): {e}")
                await asyncio.sleep(0.5)  # 重试前等待

        return None

    async def validate_url(self, url: str) -> bool:
        """
        验证URL是否有效

        Args:
            url: 要验证的URL

        Returns:
            bool: 是否有效
        """
        try:
            async with aiohttp.ClientSession() as client:
                async with client.head(url, timeout=5) as response:
                    return response.status == 200
        except Exception:
            return False
