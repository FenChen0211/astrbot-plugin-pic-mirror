"""
图像对称插件主入口模块
"""

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import asyncio

try:
    from .constants import PLUGIN_NAME
except ImportError:
    from .constants import PLUGIN_NAME

from .services.config_service import ConfigService
from .core.image_handler import ImageHandler


class PicMirrorPlugin(Star):
    """图像对称处理插件"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 旧版初始化方式
        self.config_service = ConfigService(self)
        self.image_handler = ImageHandler(self.config_service)
        
        logger.info("图像对称插件已加载")
        logger.info(f"当前配置: {self.config_service.get_config_summary()}")

    # 独立指令定义
    async def _handle_mirror_command(self, event: AstrMessageEvent, mode: str):
        """统一处理镜像命令"""
        if self.image_handler is None:
            logger.error("image_handler 未初始化")
            yield event.plain_result("❌ 插件尚未初始化完成，请稍后再试")
            return
            
        async for result in self.image_handler.process_mirror(event, mode):
            yield result

    @filter.command("左对称", alias={"mirror left", "left", "左右对称"})
    async def mirror_left(self, event: AstrMessageEvent):
        """左半边图像对称到右边"""
        async for result in self._handle_mirror_command(event, "left_to_right"):
            yield result

    @filter.command("右对称", alias={"mirror right", "right", "右左对称"})
    async def mirror_right(self, event: AstrMessageEvent):
        """右半边图像对称到左边"""
        async for result in self._handle_mirror_command(event, "right_to_left"):
            yield result

    @filter.command("上对称", alias={"mirror top", "top", "上下对称"})
    async def mirror_top(self, event: AstrMessageEvent):
        """上半边图像对称到下面"""
        async for result in self._handle_mirror_command(event, "top_to_bottom"):
            yield result

    @filter.command("下对称", alias={"mirror bottom", "bottom", "下上对称"})
    async def mirror_bottom(self, event: AstrMessageEvent):
        """下半边图像对称到上面"""
        async for result in self._handle_mirror_command(event, "bottom_to_top"):
            yield result

    @filter.command("对称帮助", alias={"mirror help", "镜像帮助"})  # ✅ 移除重复的"对称帮助"
    async def mirror_help(self, event: AstrMessageEvent):
        """显示镜像插件帮助信息"""
        if self.config_service is None:
            logger.error("config_service 未初始化")
            yield event.plain_result("❌ 插件尚未初始化完成，请稍后再试")
            return
            
        help_text = self.config_service.get_help_text()
        yield event.plain_result(help_text)

    async def initialize(self):
        """插件异步初始化"""
        try:
            if hasattr(self, 'image_handler') and self.image_handler:
                await self.image_handler.initialize()
            logger.info("图像对称插件初始化完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}", exc_info=True)

    async def terminate(self):
        """插件卸载时调用"""
        try:
            if hasattr(self, 'image_handler') and self.image_handler is not None:
                await self.image_handler.cleanup()
            else:
                logger.warning("image_handler 未初始化，跳过清理操作")
        except (AttributeError, RuntimeError, asyncio.CancelledError) as e:
            logger.error(f"插件卸载时发生异常: {e}", exc_info=True)
        except Exception as e:
            # 其他未知异常也记录，但更详细
            logger.critical(f"插件卸载时发生未知异常: {e}", exc_info=True)
            raise  # 重新抛出让框架处理
        finally:
            logger.info("图像对称插件正在卸载...")
