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
        self.session = None  # 添加session缓存
        # URL白名单 - 只允许特定的域名
        self.allowed_domains = [
            'q1.qlogo.cn',
            'q2.qlogo.cn', 
            'q4.qlogo.cn',
            'q.qlogo.cn',
            # 可以根据需要添加其他允许的域名
        ]
        # 下载大小限制 (10MB)
        self.max_download_size = 10 * 1024 * 1024
    
    async def get_session(self):
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _is_safe_url(self, url: str) -> bool:
        """
        检查URL是否安全（防止SSRF攻击）
        
        Args:
            url: 要检查的URL
            
        Returns:
            bool: URL是否安全
        """
        try:
            from urllib.parse import urlparse
            
            parsed = urlparse(url)
            
            # 检查协议
            if parsed.scheme not in ['https', 'http']:
                logger.warning(f"不支持的协议: {parsed.scheme}")
                return False
            
            # 检查域名是否在白名单中
            if parsed.netloc not in self.allowed_domains:
                logger.warning(f"域名不在白名单中: {parsed.netloc}")
                return False
            
            # 检查是否为内网地址
            hostname = parsed.netloc.split(':')[0]  # 移除端口
            if hostname in ['localhost', '127.0.0.1'] or hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.'):
                logger.warning(f"检测到内网地址: {hostname}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"URL安全检查失败: {e}")
            return False
    
    async def cleanup(self):
        """清理资源，关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        下载图片

        Args:
            url: 图片URL

        Returns:
            图片字节数据，失败返回None
        """
        # 添加URL安全检查
        if not self._is_safe_url(url):
            logger.warning(f"拒绝不安全的URL: {url}")
            return None
        
        try:
            session = await self.get_session()
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    logger.error(f"下载失败，状态码: {response.status}")
                    return None

                # 流式读取+大小限制
                data = b''
                async for chunk in response.content.iter_chunked(8192):
                    data += chunk
                    if len(data) > self.max_download_size:
                        logger.error(f"图片超过大小限制: {len(data)} bytes")
                        return None

                logger.info(f"成功下载图片，大小: {len(data)} bytes")
                return data

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
        # QQ头像API列表（只使用HTTPS）
        avatar_urls = [
            f"https://q1.qlogo.cn/g?b=qq&nk={qq_number}&s={size}",
            f"https://q2.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
            f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq_number}&spec={size}",
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
        session = await self.get_session()
        for attempt in range(retries + 1):
            try:
                # 设置超时和headers
                timeout = aiohttp.ClientTimeout(total=10)
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }

                async with session.get(
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
            session = await self.get_session()
            async with session.head(url, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False
