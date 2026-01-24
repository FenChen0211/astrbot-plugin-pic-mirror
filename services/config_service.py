"""
配置服务
"""

from typing import Dict, Any
from astrbot.api import logger

# 修复：使用和 image_processor.py 相同的智能导入
try:
    from config import PluginConfig  # 先尝试绝对导入
except ImportError:
    from ..config import PluginConfig  # 失败再尝试相对导入


class ConfigService:
    """配置服务类"""

    def __init__(self, plugin_instance, config_dict=None):
        self.plugin = plugin_instance
        self._config = None  # 延迟加载
        # 保存可能传入的配置字典，但_load_config会优先使用
        self._config_dict = config_dict

    def _load_config(self) -> PluginConfig:
        """简化版本 - 只用标准方式"""
        try:
            # 直接使用context.config
            if hasattr(self.plugin, 'context') and hasattr(self.plugin.context, 'config'):
                config_dict = self.plugin.context.config
                return PluginConfig.load_from_dict(config_dict)
            # 否则返回默认
            return PluginConfig()
        except Exception as e:
            logger.error(f"配置加载失败，使用默认配置: {e}")
            return PluginConfig()

    def get_config_summary(self) -> str:
        """获取配置摘要"""
        # 确保配置已加载
        config = self.config_obj  # 使用config_obj属性确保加载
        
        return (
            f"图像限制={config.image_size_limit_mb}MB, "
            f"GIF限制={config.gif_size_limit_mb}MB, "
            f"自动清理={'启用' if config.enable_auto_cleanup else '禁用'}, "
            f"@头像功能={'启用' if config.enable_at_avatar else '禁用'}"
        )

    def get_help_text(self) -> str:
        """获取帮助文本"""
        config = self.config

        if config.silent_mode:
            return """📷 图像对称插件使用说明

可用指令:
• 左对称 / mirror left - 左半边对称到右边
• 右对称 / mirror right - 右半边对称到左边  
• 上对称 / mirror top - 上半边对称到下面
• 下对称 / mirror bottom - 下半边对称到上面

使用方法:
1. 回复一条包含图像的消息，然后发送指令
2. 发送指令并@一个用户 (处理该用户头像)
3. 直接发送图像和指令在同一消息中

支持格式: PNG, JPG, GIF, BMP, WebP

示例:
回复图片消息后发送: 左对称
@用户 并发送: 右对称
图片 + 右对称"""
        else:
            return f"""📷 图像对称插件使用说明 v1.1.1

当前配置:
• 图像大小限制: {config.image_size_limit_mb}MB
• GIF大小限制: {config.gif_size_limit_mb}MB
• GIF处理: {"✅ 已启用" if config.enable_gif else "❌ 已禁用"}
• 自动清理: {"✅ 已启用" if config.enable_auto_cleanup else "❌ 已禁用"}
• @头像功能: {"✅ 已启用" if config.enable_at_avatar else "❌ 已禁用"}

可用指令:
• 左对称 / mirror left - 左半边对称到右边
• 右对称 / mirror right - 右半边对称到左边  
• 上对称 / mirror top - 上半边对称到下面
• 下对称 / mirror bottom - 下半边对称到上面

使用方法:
1. 回复一条包含图像的消息，然后发送指令
2. 发送指令并@一个用户 (处理该用户头像)
3. 直接发送图像和指令在同一消息中

支持格式: PNG, JPG, GIF, BMP, WebP
大小限制: 图像<{config.image_size_limit_mb}MB, GIF<{config.gif_size_limit_mb}MB

示例:
回复图片消息后发送: 左对称
@用户 并发送: 右对称
图片 + 右对称

GitHub: https://github.com/FenChen0211/astrbot-plugin-pic-mirror"""

    @property
    def config_obj(self) -> PluginConfig:
        """获取配置对象"""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    @property 
    def config(self):
        """配置对象别名"""
        return self.config_obj
