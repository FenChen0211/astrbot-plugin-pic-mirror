"""
配置服务
"""

from typing import Dict, Any
from astrbot.api import logger
from ..config import PluginConfig


class ConfigService:
    """配置服务类"""

    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self.config = self._load_config()

    def _load_config(self) -> PluginConfig:
        """加载插件配置"""
        try:
            # 尝试获取配置，如果失败则使用默认值
            config_dict = {}

            # 方法优先级：get_plugin_config > get_config > .config > context.config
            methods_to_try = [
                ("get_plugin_config", "调用 get_plugin_config() 方法"),
                ("get_config", "调用 get_config() 方法"),
                ("config", "访问 .config 属性"),
            ]

            for method_name, description in methods_to_try:
                if hasattr(self.plugin, method_name):
                    try:
                        attr = getattr(self.plugin, method_name)
                        if callable(attr):
                            config_dict = attr()  # 调用方法
                        else:
                            config_dict = attr  # 访问属性

                        logger.info(f"{description} 成功")
                        break
                    except Exception as e:
                        logger.debug(f"{description} 失败: {e}")
                        continue

            # 如果上述方法都失败，尝试从context获取
            if not config_dict and hasattr(self.plugin, "context"):
                try:
                    context = self.plugin.context
                    if hasattr(context, "config"):
                        config_dict = context.config
                        logger.info("从 context.config 获取配置成功")
                except Exception as e:
                    logger.debug(f"从context获取配置失败: {e}")

            # 如果还是没有配置，使用空字典（将使用默认值）
            if not config_dict:
                logger.info("使用空配置字典，将应用默认值")
                config_dict = {}

            logger.info(f"配置字典内容: {config_dict}")

            # 加载配置
            config = PluginConfig.load_from_dict(config_dict)
            logger.info("插件配置加载成功")
            return config

        except Exception as e:
            logger.error(f"配置加载失败，使用默认配置: {e}")
            # 返回默认配置，确保插件能正常运行
            return PluginConfig()

    def get_config_summary(self) -> str:
        """获取配置摘要"""
        config = self.config
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
            return f"""📷 图像对称插件使用说明 v1.2.0

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
        return self.config
