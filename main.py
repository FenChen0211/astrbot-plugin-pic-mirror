"""
图像对称插件主入口模块
"""

import asyncio

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.api.star import Context, Star

from .constants import PLUGIN_NAME

from astrbot.api import logger
from .services.config_service import ConfigService
from .core.image_handler import ImageHandler


# 根据 AstrBot v3.5.20+ 最佳实践: @register 装饰器已废弃
# AstrBot 可自动识别继承自 Star 的类，无需显式注册
# 为保持代码简洁和符合新版本规范，此处移除 @register 装饰器
class PicMirrorPlugin(Star):
    """图像对称处理插件"""

    def __init__(self, context: Context):
        super().__init__(context)

        self.config_service = ConfigService(self)
        self.image_handler = ImageHandler(self.config_service)

        logger.info("图像对称插件已加载")
        logger.info(f"当前配置: {self.config_service.get_config_summary()}")

        self._init_task = asyncio.create_task(self.initialize())

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_all_mirror_commands(self, event: AstrMessageEvent):
        """
        处理无斜杠的镜像指令
        格式: "指令名 @用户" (如: "左对称 @张三")
        """
        message_str = event.message_str.strip()

        plain_commands = {
            "左对称": "left_to_right",
            "右对称": "right_to_left",
            "上对称": "top_to_bottom",
            "下对称": "bottom_to_top",
            "对称帮助": "help",
            "镜像帮助": "help",
        }

        actual_command = message_str
        if " @" in message_str or message_str.startswith("@"):
            parts = message_str.split("@", 1)
            actual_command = parts[0].strip()

        if actual_command in plain_commands:
            mode = plain_commands[actual_command]
            logger.info(f"收到无斜杠指令: {actual_command} -> 模式: {mode}")

            if mode == "help":
                async for result in self.mirror_help(event):
                    yield result
            else:
                async for result in self.handle_mirror_with_mode(event, mode):
                    yield result

    async def handle_mirror_with_mode(self, event: AstrMessageEvent, mode: str):
        """处理镜像请求的统一入口"""
        # 审核说明: 根据审核要求等待初始化完成，避免竞态条件
        if (
            hasattr(self, "_init_task")
            and self._init_task
            and not self._init_task.done()
        ):
            await self._init_task

        if self.image_handler is None:
            logger.error("image_handler 未初始化")
            yield event.plain_result("❌ 插件尚未初始化完成，请稍后再试")
            return

        async for result in self.image_handler.process_mirror(event, mode):
            yield result

    @filter.command("左对称", alias={"mirror left", "left", "左右对称"})
    async def mirror_left(self, event: AstrMessageEvent):
        """左半边图像对称到右边"""
        async for result in self.handle_mirror_with_mode(event, "left_to_right"):
            yield result

    @filter.command("右对称", alias={"mirror right", "right", "右左对称"})
    async def mirror_right(self, event: AstrMessageEvent):
        """右半边图像对称到左边"""
        async for result in self.handle_mirror_with_mode(event, "right_to_left"):
            yield result

    @filter.command("上对称", alias={"mirror top", "top", "上下对称"})
    async def mirror_top(self, event: AstrMessageEvent):
        """上半边图像对称到下面"""
        async for result in self.handle_mirror_with_mode(event, "top_to_bottom"):
            yield result

    @filter.command("下对称", alias={"mirror bottom", "bottom", "下上对称"})
    async def mirror_bottom(self, event: AstrMessageEvent):
        """下半边图像对称到上面"""
        async for result in self.handle_mirror_with_mode(event, "bottom_to_top"):
            yield result

    @filter.command(
        "对称帮助", alias={"mirror help", "镜像帮助"}
    )  # ✅ 移除重复的"对称帮助"
    async def mirror_help(self, event: AstrMessageEvent):
        """显示镜像插件帮助信息"""
        if self.config_service is None:
            logger.error("config_service 未初始化")
            yield event.plain_result("❌ 插件尚未初始化完成，请稍后再试")
            return

        help_text = self.config_service.get_help_text()
        yield event.plain_result(help_text)

    # @filter.on_astrbot_loaded
    # async def on_loaded(self):
    #     """Bot加载完成时自动调用初始化"""
    #     await self.initialize()

    async def initialize(self):
        """插件异步初始化"""
        try:
            if hasattr(self, "image_handler") and self.image_handler:
                await self.image_handler.initialize()
            logger.info("图像对称插件初始化完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}", exc_info=True)

    async def terminate(self):
        """插件卸载时调用"""
        try:
            if (
                hasattr(self, "_init_task")
                and self._init_task
                and not self._init_task.done()
            ):
                self._init_task.cancel()
                try:
                    await self._init_task
                except asyncio.CancelledError:
                    pass

            if hasattr(self, "image_handler") and self.image_handler is not None:
                await self.image_handler.cleanup()
            else:
                logger.warning("image_handler 未初始化，跳过清理操作")
        except (AttributeError, RuntimeError, asyncio.CancelledError) as e:
            logger.error(f"插件卸载时发生异常: {e}", exc_info=True)
        finally:
            logger.info("图像对称插件正在卸载...")
