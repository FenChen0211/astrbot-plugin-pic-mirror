"""
网络请求工具模块
"""

import aiohttp
import asyncio
import socket           # ✅ 添加这行
import ipaddress       # ✅ 添加这行
from typing import Optional
from astrbot.api import logger

try:
    from ..constants import PLUGIN_NAME
except ImportError:
    from ..constants import PLUGIN_NAME


class NetworkUtils:
    """网络请求工具类"""
    
    # 类常量
    DANGEROUS_PATTERNS = [
        'localhost', '127.0.0.1', '0.0.0.0', '::1',
        '169.254.', 'metadata.',
        '.internal', '.local', '.localdomain',
    ]
    
    PRIVATE_IP_PREFIXES = ['192.168.', '10.', '172.16.']
    
    def __init__(self, timeout: int = 30, config=None):
        self.timeout = timeout
        self.session = None
        self.config = config
        
        
        
        # 从配置获取大小限制，或使用默认值
        if config and hasattr(config, 'max_image_size_bytes'):
            self.max_download_size = config.max_image_size_bytes
        else:
            self.max_download_size = 10 * 1024 * 1024  # 10MB默认
    
    async def _resolve_hostname(self, hostname: str) -> str:
        """异步解析域名获取IP地址"""
        try:
            loop = asyncio.get_running_loop()
            # 使用getaddrinfo进行DNS解析
            addrinfo = await loop.getaddrinfo(
                hostname, None, 
                family=socket.AF_UNSPEC, 
                type=socket.SOCK_STREAM
            )
            if addrinfo:
                # 返回第一个解析到的IP地址
                return addrinfo[0][4][0]
        except (socket.gaierror, asyncio.CancelledError, Exception) as e:
            logger.debug(f"DNS解析失败 {hostname}: {e}")
        return None
    
    def _is_private_ip(self, ip_str: str) -> bool:
        """检查IP是否为私有地址"""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return False
    
    async def get_session(self):
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _is_safe_url(self, url: str) -> bool:
        """真正的SSRF防护 - 包含DNS解析检查"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            
            # 基础检查
            if parsed.scheme not in ('http', 'https'):
                return False
            
            hostname = parsed.hostname
            if not hostname:
                return False
            
            # 1. 快速字符串检查（黑名单）- 使用类常量
            for pattern in self.DANGEROUS_PATTERNS:
                # 统一处理：如果pattern以点开头，去掉点
                clean_pattern = pattern[1:] if pattern.startswith('.') else pattern
                if hostname == pattern or hostname.endswith('.' + clean_pattern) or hostname.startswith(pattern):
                    return False
            
            # 2. DNS解析检查
            resolved_ip = await self._resolve_hostname(hostname)
            
            # ❌ 修改前（危险）：
            # if '.' in hostname and not any(hostname.startswith(p) for p in ['192.168.', '10.', '172.16.']):
            #     logger.info(f"允许未解析域名（可能是公网）: {hostname}")
            #     return True
            
            # ✅ 修改后（安全）：
            if not resolved_ip:
                logger.warning(f"DNS解析失败，拒绝访问: {hostname}")
                return False  # 解析失败就拒绝！
            
            # IP地址检查
            if self._is_private_ip(resolved_ip):
                logger.warning(f"域名解析到私有IP: {hostname} -> {resolved_ip}")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"URL安全检查失败 {url}: {e}")
            return False  # 有疑问就拒绝
    
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
        is_safe = await self._is_safe_url(url)
        if not is_safe:
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
