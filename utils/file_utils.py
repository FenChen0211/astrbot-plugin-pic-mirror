"""
文件处理工具模块
"""

import os
import re
import base64
import hashlib
import secrets
import time as time_module
from pathlib import Path
from typing import Optional, Tuple, List, TYPE_CHECKING
from astrbot.api import logger

if TYPE_CHECKING:
    from ..config import PluginConfig

from astrbot.api.star import StarTools


class FileUtils:
    """文件处理工具类"""

    SUPPORTED_STATIC_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    SUPPORTED_GIF_FORMAT = {".gif"}
    SUPPORTED_FORMATS = SUPPORTED_STATIC_FORMATS | SUPPORTED_GIF_FORMAT

    DEFAULT_IMAGE_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB
    DEFAULT_GIF_SIZE_LIMIT = 15 * 1024 * 1024  # 15MB

    def __init__(self, plugin_name: str = "astrbot-plugin-pic-mirror"):
        self.data_dir = FileUtils.ensure_data_dir(plugin_name)

    MAGIC_BYTES = {
        "gif": ([b"GIF87a", b"GIF89a"], 6),
        "png": (b"\x89PNG\r\n\x1a\n", 8),
        "jpeg": (b"\xff\xd8\xff", 3),
        "jpeg2000": (b"\x00\x00\x00\x0c\x6a\x50\x20\x20\x0d\x0a\x87\x0a", 12),
        "webp": (b"RIFF", 4, b"WEBP", 8),
        "bmp": (b"BM", 2),
        "avif": (b"ftyp", 4, [b"avif", b"avis"], 8),
        "ico": ([b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"], 4),
        "tiff": ([b"II\x00\x2a", b"MM\x00\x2a"], 4),
    }

    @staticmethod
    def ensure_data_dir(plugin_name: str) -> Path:
        """
        确保插件数据目录存在

        Args:
            plugin_name: 插件名称

        Returns:
            Path: 数据目录路径
        """
        data_dir = StarTools.get_data_dir(plugin_name)
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @staticmethod
    def get_file_extension(url_or_path: str) -> Optional[str]:
        """
        从URL或路径中提取文件扩展名（改进版）

        Args:
            url_or_path: URL或文件路径

        Returns:
            小写的文件扩展名，如'.jpg'、'.gif'
        """
        # 移除查询参数
        path = url_or_path.split("?")[0]

        # 提取扩展名
        match = re.search(r"\.([a-zA-Z0-9]+)$", path)
        if match:
            ext = f".{match.group(1).lower()}"
            # 确保扩展名是我们支持的格式
            return ext
        return None

    @staticmethod
    def is_image_url(url: str) -> bool:
        """
        检查URL是否是支持的图像格式

        Args:
            url: 要检查的URL

        Returns:
            bool: 是否支持
        """
        ext = FileUtils.get_file_extension(url)
        return ext in FileUtils.SUPPORTED_FORMATS if ext else False

    def generate_filename(self, original_url: str, mode: str) -> str:
        """
        生成唯一的文件名（Base64优化版）

        Args:
            original_url: 原始图像URL或Base64数据
            mode: 对称模式

        Returns:
            str: 生成的文件名
        """
        # Base64数据优化：避免处理完整大型数据
        if len(original_url) > 1000:
            # 大型数据：使用MD5摘要代替完整字符串
            content_hash = hashlib.md5(original_url.encode()).hexdigest()[:16]
            hash_input = f"{content_hash}_{mode}"
        else:
            hash_input = f"{original_url}_{mode}"

        # 添加熵确保唯一性
        timestamp = int(time_module.time())
        random_token = secrets.token_hex(4)

        hash_input = f"{hash_input}_{timestamp}_{random_token}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]

        # 尝试从原始URL获取扩展名
        ext = FileUtils.get_file_extension(original_url)

        if not ext:
            # 如果没有扩展名，根据原始URL判断
            if "qq_" in original_url or "avatar_" in original_url:
                ext = ".jpg"
            else:
                ext = ".png"

        filename = f"mirror_{mode}_{file_hash}{ext}"
        # 检测碰撞
        counter = 0
        original_filename = filename
        while (self.data_dir / filename).exists():
            counter += 1
            filename = f"mirror_{mode}_{file_hash}_{counter}{ext}"
        return filename

    @staticmethod
    def validate_image_size(
        image_path: str, config: Optional["PluginConfig"] = None
    ) -> Tuple[bool, str]:
        """
        验证图像文件大小（支持配置）

        Args:
            image_path: 图像文件路径
            config: 插件配置

        Returns:
            Tuple[bool, str]: (是否通过验证, 错误信息)
        """
        try:
            file_size = os.path.getsize(image_path)

            # 获取文件扩展名
            ext = FileUtils.get_file_extension(image_path)

            # 获取大小限制
            if config:
                if ext == ".gif":
                    max_size = config.max_gif_size_bytes
                    max_size_mb = config.gif_size_limit_mb
                else:
                    max_size = config.max_image_size_bytes
                    max_size_mb = config.image_size_limit_mb
            else:
                if ext == ".gif":
                    max_size = FileUtils.DEFAULT_GIF_SIZE_LIMIT
                    max_size_mb = 15
                else:
                    max_size = FileUtils.DEFAULT_IMAGE_SIZE_LIMIT
                    max_size_mb = 10

            if file_size > max_size:
                file_size_mb = file_size / 1024 / 1024
                return (
                    False,
                    f"文件过大（{file_size_mb:.1f}MB），最大允许：{max_size_mb}MB",
                )

            return True, ""
        except Exception as e:
            return False, f"无法获取文件大小: {str(e)}"

    @staticmethod
    def is_base64_image(data: str) -> bool:
        """检查是否为base64格式的图像数据"""
        return isinstance(data, str) and data.startswith("base64://")

    @staticmethod
    def decode_base64_image(base64_data: str) -> Optional[bytes]:
        """解码base64图像数据"""
        try:
            if base64_data.startswith("base64://"):
                base64_data = base64_data[len("base64://") :]
            # 添加validate=True进行严格的Base64验证
            return base64.b64decode(base64_data, validate=True)
        except Exception as e:
            logger.error(f"Base64解码失败: {e}")
            return None

    @staticmethod
    def cleanup_temp_files(data_dir: Path, pattern: str = "*"):
        """
        清理临时文件

        Args:
            data_dir: 数据目录
            pattern: 文件匹配模式
        """
        try:
            for file_path in data_dir.glob(pattern):
                if file_path.is_file():
                    if any(
                        keyword in file_path.name
                        for keyword in ["tmp", "avatar", "downloaded"]
                    ):
                        try:
                            file_path.unlink()
                        except (OSError, PermissionError) as e:
                            logger.debug(f"无法删除临时文件 {file_path.name}: {e}")
        except (OSError, PermissionError) as e:
            logger.debug(f"清理临时文件时出错: {e}")

    @staticmethod
    def detect_image_format_by_magic(data: bytes) -> Optional[str]:
        """
        通过魔数检测图像格式（增强版）

        Args:
            data: 图像数据

        Returns:
            扩展名，如 '.jpg', '.png', '.gif', '.webp', '.bmp'
        """
        if len(data) < 12:
            return None

        magic = FileUtils.MAGIC_BYTES

        if data[:6] in magic["gif"][0]:
            if len(data) > 13:
                image_descriptor_count = data.count(b'\x2C')
                if image_descriptor_count > 1:
                    logger.debug(f"检测到动态GIF，包含 {image_descriptor_count} 帧")
            return ".gif"

        if data[:8] == magic["png"][0]:
            return ".png"

        if data[:12] == magic["jpeg2000"][0]:
            return ".jp2"

        if data[:3] == magic["jpeg"][0]:
            return ".jpg"

        if data[:4] == magic["webp"][0] and data[8:12] == magic["webp"][2]:
            return ".webp"

        if data[:2] == magic["bmp"][0]:
            return ".bmp"

        if len(data) > 12 and data[4:8] == magic["avif"][0] and data[8:12] in magic["avif"][2]:
            return ".avif"

        if data[:4] in magic["ico"][0]:
            return ".ico"

        if data[:4] in magic["tiff"][0]:
            return ".tiff"

        return None
