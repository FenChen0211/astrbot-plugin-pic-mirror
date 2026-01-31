"""
网络请求工具模块
"""

import aiohttp
import asyncio
import socket
import ipaddress
from typing import Dict, Optional, Tuple
from astrbot.api import logger

try:
    from ..constants import PLUGIN_NAME
except ImportError:
    from ..constants import PLUGIN_NAME


class FixedDNSResolver:
    """固定DNS解析器，防止DNS重绑定攻击"""

    def __init__(self, safe_resolutions: Dict[str, str]):
        """
        初始化固定DNS解析器

        Args:
            safe_resolutions: 字典，域名 -> 安全IP的映射
        """
        self._safe_resolutions = safe_resolutions
        self._resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, hostname: str, port=0, family=socket.AF_INET):
        """
        解析主机名，返回预先验证的安全IP（带地址族验证）

        Args:
            hostname: 要解析的域名
            port: 端口
            family: 地址族（AF_INET 或 AF_INET6）

        Returns:
            解析结果列表
        """
        if hostname in self._safe_resolutions:
            safe_ip = self._safe_resolutions[hostname]

            # 验证预解析IP的类型是否与请求的地址族兼容
            try:
                ip_obj = ipaddress.ip_address(safe_ip)
            except ValueError:
                # IP格式无效，返回空列表而不是回退到默认解析器
                logger.warning(f"无效的预解析IP: {safe_ip}，拒绝解析")
                return []

            # 检查地址族兼容性
            if family == socket.AF_INET and ip_obj.version != 4:
                # 请求IPv4但预解析的是IPv6
                # 安全修复：地址族不匹配时返回空列表，不回退到默认解析器
                logger.warning(
                    f"地址族不匹配: 请求IPv4但 {hostname} 预解析为IPv6 ({safe_ip})，拒绝解析"
                )
                return []
            elif family == socket.AF_INET6 and ip_obj.version != 6:
                # 请求IPv6但预解析的是IPv4
                # 安全修复：地址族不匹配时返回空列表，不回退到默认解析器
                logger.warning(
                    f"地址族不匹配: 请求IPv6但 {hostname} 预解析为IPv4 ({safe_ip})，拒绝解析"
                )
                return []

            # 返回预先验证的安全IP
            return [
                {
                    "hostname": hostname,
                    "host": safe_ip,
                    "port": port,
                    "family": family,
                    "proto": socket.IPPROTO_TCP,
                    "flags": socket.AI_NUMERICHOST,
                }
            ]
        # 其他域名使用默认解析器
        return await self._resolver.resolve(hostname, port, family)


class NetworkUtils:
    """网络请求工具类"""

    # 类常量
    DANGEROUS_PATTERNS = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.",
        "metadata.",
        ".internal",
        ".local",
        ".localdomain",
    ]

    PRIVATE_IP_PREFIXES = ["192.168.", "10.", "172.16."]

    def __init__(self, timeout: int = 30, config=None):
        self.timeout = timeout
        self.config = config  # 保存配置引用
        self.session = None
        self._session_lock = asyncio.Lock()  # Session创建锁

        # 从配置获取大小限制，或使用默认值
        if config and hasattr(config, "max_image_size_bytes"):
            self.max_download_size = config.max_image_size_bytes
        else:
            self.max_download_size = 10 * 1024 * 1024  # 10MB默认

    async def _resolve_hostname(self, hostname: str) -> str:
        """异步解析域名获取IP地址（优先IPv4）"""
        try:
            loop = asyncio.get_running_loop()

            # 第一步：优先尝试解析IPv4（HTTP/HTTPS通常使用IPv4）
            try:
                addrinfo = await loop.getaddrinfo(
                    hostname, None, family=socket.AF_INET, type=socket.SOCK_STREAM
                )
                if addrinfo:
                    return addrinfo[0][4][0]
            except socket.gaierror:
                pass  # IPv4失败，继续尝试IPv6

            # 第二步：回退到IPv6（仅当IPv4不可用时）
            try:
                addrinfo = await loop.getaddrinfo(
                    hostname, None, family=socket.AF_INET6, type=socket.SOCK_STREAM
                )
                if addrinfo:
                    return addrinfo[0][4][0]
            except socket.gaierror:
                pass  # IPv6也失败

            # 第三步：最后尝试任意地址族
            try:
                addrinfo = await loop.getaddrinfo(
                    hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
                )
                if addrinfo:
                    # 优先选择IPv4地址
                    for entry in addrinfo:
                        ip = entry[4][0]
                        try:
                            ip_obj = ipaddress.ip_address(ip)
                            if ip_obj.version == 4:
                                return ip
                        except ValueError:
                            continue
                    # 没有IPv4，返回第一个
                    return addrinfo[0][4][0]
            except socket.gaierror:
                pass

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

    def _is_ip_format(self, hostname: str) -> bool:
        """
        检查是否为IP格式（支持各种表示法）
        - IPv4: 192.168.1.1, 127.0.0.1
        - IPv6: ::1, 2001:db8::1, [::1]
        - 整数表示: 2130706433 (0x7F000001)
        """
        try:
            # 检查原始字符串
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass

        # 检测整数格式的IPv4
        try:
            ip_int = int(hostname)
            if 0 <= ip_int <= 0xFFFFFFFF:  # 32位整数范围
                ipaddress.ip_address(ip_int)
                return True
        except (ValueError, ipaddress.AddressValueError):
            pass

        return False

    def _is_link_local_ip(self, ip_str: str) -> bool:
        """检查是否为链路本地地址 (169.254.x.x)"""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_link_local
        except ValueError:
            return False

    async def _is_safe_url_with_ip(self, url: str) -> Optional[Tuple[str, str]]:
        """
        增强版安全URL检查 + DNS解析，返回安全IP和主机名

        改进点：
        - 对IP格式的URL直接检查，绕过DNS解析
        - 检测整数格式的IPv4表示（如 2130706433）
        - 链路本地地址检查 (169.254.x.x)

        Args:
            url: 完整URL

        Returns:
            (安全IP, 主机名) 或 None（如果不安全）
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)

            # 基础检查
            if parsed.scheme not in ("http", "https"):
                return None

            hostname = parsed.hostname
            if not hostname:
                return None

            # 1. 如果是IP格式（包含IPv4/IPv6），直接检查
            if self._is_ip_format(hostname):
                # 检查是否为私有/本地/链路本地IP
                if self._is_private_ip(hostname):
                    logger.warning(f"IP格式危险（私有/回环）: {hostname}")
                    return None
                # 对于IP格式，直接返回IP作为主机名
                return (hostname, hostname)

            # 移除IPv6方括号（如果存在）
            if hostname.startswith("[") and hostname.endswith("]"):
                hostname_clean = hostname[1:-1]
                if self._is_ip_format(hostname_clean):
                    if self._is_private_ip(hostname_clean):
                        logger.warning(f"IPv6格式危险: {hostname}")
                        return None
                    return (hostname_clean, hostname)

            # 2. 原有字符串检查（黑名单）- 带通配符支持
            for pattern in self.DANGEROUS_PATTERNS:
                clean_pattern = pattern[1:] if pattern.startswith(".") else pattern
                if (
                    hostname == pattern
                    or hostname.endswith("." + clean_pattern)
                    or hostname.startswith(pattern)
                ):
                    return None

            # 3. DNS解析并验证IP
            resolved_ip = await self._resolve_hostname(hostname)

            if not resolved_ip:
                logger.warning(f"DNS解析失败，拒绝访问: {hostname}")
                return None

            # IP地址检查
            if self._is_private_ip(resolved_ip):
                logger.warning(f"域名解析到私有IP: {hostname} -> {resolved_ip}")
                return None

            # 返回安全IP和主机名
            return (resolved_ip, hostname)

        except Exception as e:
            logger.warning(f"URL安全检查失败 {url}: {e}")
            return None

    async def get_session(self):
        """获取或创建HTTP会话（线程安全）"""
        if self.session is None or self.session.closed:
            async with self._session_lock:
                if self.session is None or self.session.closed:
                    self.session = aiohttp.ClientSession()
        return self.session

    async def _is_safe_url(self, url: str) -> bool:
        """真正的SSRF防护 - 包含DNS解析检查"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)

            # 基础检查
            if parsed.scheme not in ("http", "https"):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            # 1. 快速字符串检查（黑名单）- 使用类常量
            for pattern in self.DANGEROUS_PATTERNS:
                # 统一处理：如果pattern以点开头，去掉点
                clean_pattern = pattern[1:] if pattern.startswith(".") else pattern
                if (
                    hostname == pattern
                    or hostname.endswith("." + clean_pattern)
                    or hostname.startswith(pattern)
                ):
                    return False

            # 2. DNS解析检查（返回带IP的安全检查）
            safe_info = await self._is_safe_url_with_ip(url)
            if not safe_info:
                return False

            return True
        except Exception as e:
            logger.warning(f"URL安全检查失败 {url}: {e}")
            return False

    async def cleanup(self):
        """清理资源，关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        下载图片（防DNS Rebinding版本 - 使用固定DNS解析器解决SSL证书问题）

        通过自定义DNS解析器将域名固定解析到预先验证的安全IP，
        保持原始URL进行连接，避免HTTPS证书验证失败。

        Args:
            url: 图片URL

        Returns:
            图片字节数据，失败返回None
        """
        # 1. 安全检查 + DNS解析（获取固定安全IP）
        safe_info = await self._is_safe_url_with_ip(url)
        if not safe_info:
            logger.warning(f"拒绝不安全的URL: {url}")
            return None

        safe_ip, hostname = safe_info

        # 2. 使用自定义DNS解析器（保持原始URL，避免SSL证书问题）
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)

            # 创建固定DNS解析器，强制域名解析到安全IP
            resolver = FixedDNSResolver({hostname: safe_ip})

            # 使用自定义解析器的连接器
            connector = aiohttp.TCPConnector(
                resolver=resolver,
                limit_per_host=3,
                ttl_dns_cache=300,
            )

            timeout = aiohttp.ClientTimeout(total=self.timeout)

            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                # 使用原始URL（域名），DNS解析被FixedDNSResolver控制
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"下载失败，状态码: {response.status}")
                        return None

                    # 流式读取+大小限制
                    buffer = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        buffer.extend(chunk)
                        if len(buffer) > self.max_download_size:
                            logger.error(f"图片超过大小限制: {len(buffer)} bytes")
                            return None

                    logger.info(f"成功下载图片，大小: {len(buffer)} bytes")
                    return bytes(buffer)

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
                await asyncio.sleep(0.5 * (2**attempt))  # 指数退避: 0.5s, 1s, 2s

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
