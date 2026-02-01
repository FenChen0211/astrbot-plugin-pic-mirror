"""
插件配置管理模块
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from astrbot.api import logger


@dataclass
class PluginConfig:
    """插件配置数据类"""

    # ============ 验证常量 ============
    # 文件大小限制范围 (MB)
    MIN_IMAGE_SIZE_MB = 1
    MAX_IMAGE_SIZE_MB = 100
    MIN_GIF_SIZE_MB = 1
    MAX_GIF_SIZE_MB = 200
    
    # 处理参数范围
    MIN_PROCESSING_TIMEOUT = 5   # 秒
    MAX_PROCESSING_TIMEOUT = 300  # 秒
    MIN_OUTPUT_QUALITY = 1
    MAX_OUTPUT_QUALITY = 100
    
    # 文件保留时间范围 (小时)
    MIN_KEEP_FILES_HOURS = 0
    MAX_KEEP_FILES_HOURS = 168  # 7天
    
    # 频率限制范围 (次/分钟)
    MIN_RATE_LIMIT = 0
    MAX_RATE_LIMIT = 60
    
    # GIF帧数限制范围
    MIN_GIF_FRAMES = 10
    MAX_GIF_FRAMES = 1000
    
    # 清理超时范围 (秒)
    MIN_CLEANUP_TIMEOUT = 1.0
    MAX_CLEANUP_TIMEOUT = 30.0
    
    # 清理循环间隔范围 (秒)
    MIN_CLEANUP_LOOP_INTERVAL = 60
    MAX_CLEANUP_LOOP_INTERVAL = 1800  # 30分钟
    
    cleanup_loop_interval: int = 300  # 清理循环间隔时间（秒）
    
    # 文件大小限制
    image_size_limit_mb: int = 10  # 图像文件大小限制 (MB)
    gif_size_limit_mb: int = 15  # GIF文件大小限制 (MB)

    # 预检查文件大小限制 (MB)
    MIN_PRECHECK_FILE_SIZE_MB = 10
    MAX_PRECHECK_FILE_SIZE_MB = 500
    precheck_file_size_mb: int = 100  # 预检查阶段文件大小限制 (MB)

    # 压缩参数限制
    MIN_MAX_DIMENSION = 512
    MAX_MAX_DIMENSION = 8192
    max_compression_dimension: int = 2048  # 压缩最大尺寸 (像素)

    # GIF总像素限制
    MIN_MAX_TOTAL_PIXELS = 500 * 500  # 2500万像素
    MAX_MAX_TOTAL_PIXELS = 10000 * 10000  # 1亿像素
    max_total_pixels: int = 4000 * 4000  # GIF总像素限制 (约16亿像素)

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
    def precheck_file_size_bytes(self) -> int:
        """获取预检查文件大小限制 (字节)"""
        return self.precheck_file_size_mb * 1024 * 1024

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

            config = cls()
            config = cls(
                image_size_limit_mb=safe_get("image_size_limit_mb", config.image_size_limit_mb, int),
                gif_size_limit_mb=safe_get("gif_size_limit_mb", config.gif_size_limit_mb, int),
                precheck_file_size_mb=safe_get("precheck_file_size_mb", config.precheck_file_size_mb, int),
                max_compression_dimension=safe_get("max_compression_dimension", config.max_compression_dimension, int),
                max_total_pixels=safe_get("max_total_pixels", config.max_total_pixels, int),
                cleanup_loop_interval=safe_get("cleanup_loop_interval", config.cleanup_loop_interval, int),
                processing_timeout=safe_get("processing_timeout", config.processing_timeout, int),
                output_quality=safe_get("output_quality", config.output_quality, int),
                enable_gif=safe_get("enable_gif", config.enable_gif, bool),
                enable_compression=safe_get("enable_compression", config.enable_compression, bool),
                silent_mode=safe_get("silent_mode", config.silent_mode, bool),
                enable_auto_cleanup=safe_get("enable_auto_cleanup", config.enable_auto_cleanup, bool),
                keep_files_hours=safe_get("keep_files_hours", config.keep_files_hours, int),
                enable_at_avatar=safe_get("enable_at_avatar", config.enable_at_avatar, bool),
                rate_limit_per_minute=safe_get("rate_limit_per_minute", config.rate_limit_per_minute, int),
                max_gif_frames=safe_get("max_gif_frames", config.max_gif_frames, int),
                cleanup_timeout=safe_get("cleanup_timeout", config.cleanup_timeout, float),
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
        if not (self.MIN_IMAGE_SIZE_MB <= self.image_size_limit_mb <= self.MAX_IMAGE_SIZE_MB):
            raise ValueError(f"image_size_limit_mb must be between {self.MIN_IMAGE_SIZE_MB}-{self.MAX_IMAGE_SIZE_MB} MB")
        if not (self.MIN_GIF_SIZE_MB <= self.gif_size_limit_mb <= self.MAX_GIF_SIZE_MB):
            raise ValueError(f"gif_size_limit_mb must be between {self.MIN_GIF_SIZE_MB}-{self.MAX_GIF_SIZE_MB} MB")
        if not (self.MIN_PRECHECK_FILE_SIZE_MB <= self.precheck_file_size_mb <= self.MAX_PRECHECK_FILE_SIZE_MB):
            raise ValueError(f"precheck_file_size_mb must be between {self.MIN_PRECHECK_FILE_SIZE_MB}-{self.MAX_PRECHECK_FILE_SIZE_MB} MB")
        if not (self.MIN_MAX_DIMENSION <= self.max_compression_dimension <= self.MAX_MAX_DIMENSION):
            raise ValueError(f"max_compression_dimension must be between {self.MIN_MAX_DIMENSION}-{self.MAX_MAX_DIMENSION} pixels")
        if not (self.MIN_MAX_TOTAL_PIXELS <= self.max_total_pixels <= self.MAX_MAX_TOTAL_PIXELS):
            raise ValueError(f"max_total_pixels must be between {self.MIN_MAX_TOTAL_PIXELS}-{self.MAX_MAX_TOTAL_PIXELS}")
        if not (self.MIN_CLEANUP_TIMEOUT <= self.cleanup_timeout <= self.MAX_CLEANUP_TIMEOUT):
            raise ValueError(f"cleanup_timeout must be between {self.MIN_CLEANUP_TIMEOUT}-{self.MAX_CLEANUP_TIMEOUT} seconds")
        if not (self.MIN_CLEANUP_LOOP_INTERVAL <= self.cleanup_loop_interval <= self.MAX_CLEANUP_LOOP_INTERVAL):
            raise ValueError(f"cleanup_loop_interval must be between {self.MIN_CLEANUP_LOOP_INTERVAL}-{self.MAX_CLEANUP_LOOP_INTERVAL} seconds")
        if not (self.MIN_PROCESSING_TIMEOUT <= self.processing_timeout <= self.MAX_PROCESSING_TIMEOUT):
            raise ValueError(f"processing_timeout must be between {self.MIN_PROCESSING_TIMEOUT}-{self.MAX_PROCESSING_TIMEOUT} seconds")
        if not (self.MIN_OUTPUT_QUALITY <= self.output_quality <= self.MAX_OUTPUT_QUALITY):
            raise ValueError(f"output_quality must be between {self.MIN_OUTPUT_QUALITY}-{self.MAX_OUTPUT_QUALITY}")
        if not (self.MIN_KEEP_FILES_HOURS <= self.keep_files_hours <= self.MAX_KEEP_FILES_HOURS):
            raise ValueError(f"keep_files_hours must be between {self.MIN_KEEP_FILES_HOURS}-{self.MAX_KEEP_FILES_HOURS} hours")
        if not (self.MIN_RATE_LIMIT <= self.rate_limit_per_minute <= self.MAX_RATE_LIMIT):
            raise ValueError(f"rate_limit_per_minute must be between {self.MIN_RATE_LIMIT}-{self.MAX_RATE_LIMIT}")
        if not (self.MIN_GIF_FRAMES <= self.max_gif_frames <= self.MAX_GIF_FRAMES):
            raise ValueError(f"max_gif_frames must be between {self.MIN_GIF_FRAMES}-{self.MAX_GIF_FRAMES}")
