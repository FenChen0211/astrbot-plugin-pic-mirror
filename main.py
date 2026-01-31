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
        self._initialized = False
        self._init_task = None  # 显式初始化，避免 hasattr 隐式依赖

        logger.info("图像对称插件已加载")
        logger.info(f"当前配置: {self.config_service.get_config_summary()}")

    async def _ensure_initialized(self):
        """确保插件已初始化（延迟初始化，防竞态条件）"""
        if self._initialized:
            return
        
        init_task = self._init_task
        if init_task is not None and not init_task.done():
            await init_task
        elif init_task is None or init_task.done():
            self._init_task = asyncio.create_task(self._do_initialize())
            await self._init_task
        
        self._initialized = True

    async def _do_initialize(self):
        """实际执行初始化"""
        try:
            if hasattr(self, "image_handler") and self.image_handler:
                await self.image_handler.initialize()
            logger.info("图像对称插件初始化完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}", exc_info=True)
            self._initialized = False  # 标记为未初始化，允许重试

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
        if " @" in message_str:
            # 格式: "指令 @用户"
            parts = message_str.split("@", 1)
            actual_command = parts[0].strip()
        elif message_str.startswith("@"):
            # 格式: "@用户 指令" (指令在@之后)
            parts = message_str.split(None, 2)  # 分割成: ["@用户", "指令"]
            if len(parts) >= 2:
                actual_command = parts[1].strip()

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
        await self._ensure_initialized()

        if self.image_handler is None:
            logger.error("image_handler 未初始化")
            yield event.plain_result("❌ 插件尚未初始化完成，请稍后再试")
            return

        async for result in self.image_handler.process_mirror(event, mode):
            yield result

    @filter.command(
        "对称帮助", alias={"mirror help", "镜像帮助"}
    )
    async def mirror_help(self, event: AstrMessageEvent):
        """显示镜像插件帮助信息"""
        await self._ensure_initialized()

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

    async def terminate(self):
        """插件卸载时调用"""
        handler_cleaned = False
        termination_error = None
        
        try:
            if self._init_task is not None and not self._init_task.done():
                self._init_task.cancel()
                try:
                    await self._init_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    termination_error = f"取消初始化任务失败: {e}"

            if self.image_handler is not None:
                try:
                    await self.image_handler.cleanup()
                    handler_cleaned = True
                except AttributeError as e:
                    termination_error = f"image_handler 属性访问失败: {e}"
                except RuntimeError as e:
                    termination_error = f"image_handler 运行时错误: {e}"
                except Exception as e:
                    termination_error = f"image_handler 清理失败: {e}"
            else:
                logger.info("image_handler 未初始化，跳过清理操作")

        except asyncio.CancelledError:
            termination_error = "插件卸载被取消"
        except RuntimeError as e:
            termination_error = f"插件卸载运行时错误: {e}"
        except Exception as e:
            termination_error = f"插件卸载未知错误: {e}"
            logger.error(f"插件卸载时发生未预期异常: {e}", exc_info=True)
        finally:
            if termination_error:
                logger.warning(f"插件卸载完成（部分操作失败）: {termination_error}")
            else:
                logger.info("图像对称插件已成功卸载")
