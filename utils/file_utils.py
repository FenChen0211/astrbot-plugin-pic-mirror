"""
文件处理工具模块
"""
import os
import re
import hashlib
import base64
from pathlib import Path
from typing import Optional, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from config import PluginConfig


class FileUtils:
    """文件处理工具类"""
    
    # 支持的图像格式
    SUPPORTED_STATIC_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    SUPPORTED_GIF_FORMAT = {'.gif'}
    SUPPORTED_FORMATS = SUPPORTED_STATIC_FORMATS | SUPPORTED_GIF_FORMAT
    
    # 默认文件大小限制（会被配置覆盖）
    DEFAULT_IMAGE_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB
    DEFAULT_GIF_SIZE_LIMIT = 15 * 1024 * 1024    # 15MB
    
    @staticmethod
    def ensure_data_dir(plugin_name: str) -> Path:
        """
        确保插件数据目录存在
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Path: 数据目录路径
        """
        data_dir = Path(f"data/plugins/{plugin_name}")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    @staticmethod
    def get_file_extension(url_or_path: str) -> Optional[str]:
        """
        从URL或路径中提取文件扩展名
        
        Args:
            url_or_path: URL或文件路径
            
        Returns:
            小写的文件扩展名，如'.jpg'、'.gif'
        """
        # 移除查询参数
        path = url_or_path.split('?')[0]
        # 提取扩展名
        match = re.search(r'\.([a-zA-Z0-9]+)$', path)
        return f".{match.group(1).lower()}" if match else None
    
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
    
    @staticmethod
    def generate_filename(original_url: str, mode: str) -> str:
        """
        生成唯一的文件名
        
        Args:
            original_url: 原始图像URL
            mode: 对称模式
            
        Returns:
            str: 生成的文件名
        """
        # 创建哈希值确保唯一性
        hash_input = f"{original_url}_{mode}"
        file_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        ext = FileUtils.get_file_extension(original_url) or '.png'
        return f"mirror_{mode}_{file_hash}{ext}"
    
    @staticmethod
    def validate_image_size(image_path: str, config: Optional["PluginConfig"] = None) -> Tuple[bool, str]:
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
                if ext == '.gif':
                    max_size = config.max_gif_size_bytes
                    max_size_mb = config.gif_size_limit_mb
                else:
                    max_size = config.max_image_size_bytes
                    max_size_mb = config.image_size_limit_mb
            else:
                if ext == '.gif':
                    max_size = FileUtils.DEFAULT_GIF_SIZE_LIMIT
                    max_size_mb = 15
                else:
                    max_size = FileUtils.DEFAULT_IMAGE_SIZE_LIMIT
                    max_size_mb = 10
            
            if file_size > max_size:
                file_size_mb = file_size / 1024 / 1024
                return False, f"文件过大（{file_size_mb:.1f}MB），最大允许：{max_size_mb}MB"
            
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
                base64_data = base64_data[len("base64://"):]
            return base64.b64decode(base64_data)
        except Exception as e:
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
                    try:
                        if any(keyword in file_path.name for keyword in ["tmp", "avatar", "downloaded"]):
                            file_path.unlink()
                    except:
                        pass
        except Exception as e:
            pass