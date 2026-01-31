"""
插件配置管理模块
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from astrbot.api import logger


@dataclass
class PluginConfig:
    """插件配置数据类"""

    # 文件大小限制
    image_size_limit_mb: int = 10  # 图像文件大小限制 (MB)
    gif_size_limit_mb: int = 15  # GIF文件大小限制 (MB)

    # 处理参数
    processing_timeout: int = 30  # 处理超时时间 (秒)
    output_quality: int = 85  # 输出图像质量 (1-100)

    # 功能开关
    enable_gif: bool = True  # 是否启用GIF处理
    enable_compression: bool = True  # 是否启用自动压缩
    silent_mode: bool = True  # 是否启用静默模式
    enable_auto_cleanup: bool = True  # 是否启用自动清理
    enable_at_avatar: bool = True  # 是否启用@用户头像功能

    # 清理设置
    keep_files_hours: int = 1  # 文件保留时间 (小时)

    # 频率限制
    rate_limit_per_minute: int = 10  # 每个用户每分钟最多请求次数

    # GIF设置
    max_gif_frames: int = 200  # GIF最大帧数限制

    # 清理设置
    cleanup_timeout: float = 5.0  # 清理任务超时时间（秒）

    @property
    def max_image_size_bytes(self) -> int:
        """获取最大图像文件大小 (字节)"""
        return self.image_size_limit_mb * 1024 * 1024

    @property
    def max_gif_size_bytes(self) -> int:
        """获取最大GIF文件大小 (字节)"""
        return self.gif_size_limit_mb * 1024 * 1024

    @property
    def rate_limit_enabled(self) -> bool:
        """是否启用了频率限制"""
        return self.rate_limit_per_minute > 0

    @classmethod
    def load_from_dict(cls, config_dict: Optional[Dict[str, Any]]) -> "PluginConfig":
        """
        从配置字典加载配置

        Args:
            config_dict: 配置字典，来自AstrBot的get_config()

        Returns:
            PluginConfig实例
        """
        if not config_dict:
            # 返回默认配置
            return cls()

        try:
            # 类型转换辅助函数
            def safe_get(key: str, default, type_):
                """安全获取并转换配置值"""
                value = config_dict.get(key, default)
                if value is None:
                    return default
                try:
                    # bool 类型需要特殊处理
                    if type_ == bool:
                        if isinstance(value, str):
                            return value.lower() in ("true", "1", "yes")
                        return bool(value)
                    return type_(value)
                except (ValueError, TypeError):
                    logger.warning(
                        f"配置项 [{key}] 类型错误: {value} ({type_.__name__})，使用默认值: {default}"
                    )
                    return default

            config = cls(
                image_size_limit_mb=safe_get("image_size_limit_mb", 10, int),
                gif_size_limit_mb=safe_get("gif_size_limit_mb", 15, int),
                processing_timeout=safe_get("processing_timeout", 30, int),
                output_quality=safe_get("output_quality", 85, int),
                enable_gif=safe_get("enable_gif", True, bool),
                enable_compression=safe_get("enable_compression", True, bool),
                silent_mode=safe_get("silent_mode", True, bool),
                enable_auto_cleanup=safe_get("enable_auto_cleanup", True, bool),
                keep_files_hours=safe_get("keep_files_hours", 1, int),
                enable_at_avatar=safe_get("enable_at_avatar", True, bool),
                rate_limit_per_minute=safe_get("rate_limit_per_minute", 10, int),
            )
            config.validate()
            return config
        except Exception as e:
            # 配置解析失败时使用默认值
            # 重要：使用框架的logger，而不是print
            logger.error(f"配置解析失败，使用默认配置: {e}", exc_info=True)
            return cls()

    def validate(self):
        """
        验证配置值是否在有效范围内
        如果配置无效则抛出 ValueError
        """
        if not (1 <= self.image_size_limit_mb <= 100):
            raise ValueError("image_size_limit_mb must be between 1-100 MB")
        if not (1 <= self.gif_size_limit_mb <= 200):
            raise ValueError("gif_size_limit_mb must be between 1-200 MB")
        if not (5 <= self.processing_timeout <= 300):
            raise ValueError("processing_timeout must be between 5-300 seconds")
        if not (1 <= self.output_quality <= 100):
            raise ValueError("output_quality must be between 1-100")
        if self.keep_files_hours < 0:
            raise ValueError("keep_files_hours cannot be negative")
        if not (0 <= self.rate_limit_per_minute <= 60):
            raise ValueError("rate_limit_per_minute must be between 0-60")
        # 布尔值不需要验证
