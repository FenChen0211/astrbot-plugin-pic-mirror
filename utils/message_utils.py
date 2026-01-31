"""
消息解析工具模块
"""

from typing import List, Optional
import astrbot.api.message_components as Comp
from astrbot.api import logger


class MessageUtils:
    """消息解析工具类"""

    @staticmethod
    def extract_at_qq(event) -> Optional[str]:
        """提取@的QQ号 - 减少日志版本"""
        try:
            messages = event.get_messages()
        except AttributeError:
            messages = event.message_obj.message

        for component in messages:
            if isinstance(component, Comp.At):
                # At组件可能有qq属性
                if hasattr(component, "qq"):
                    qq_value = component.qq
                    if qq_value:
                        logger.debug(f"提取到@QQ号: {qq_value}")  # ✅ debug级别
                        return str(qq_value)

                # 或者检查其他可能的属性名
                for attr_name in ["target", "user_id", "id"]:
                    if hasattr(component, attr_name):
                        attr_value = getattr(component, attr_name)
                        if attr_value:
                            logger.debug(f"提取到@QQ号: {attr_value}")  # ✅ debug级别
                            return str(attr_value)

        return None

    @staticmethod
    def extract_image_sources(event) -> List[str]:
        """提取图像源 - 使用标准API"""
        image_sources = []

        try:
            messages = event.get_messages()

            if not messages:
                logger.debug("event.get_messages() 返回空")
                return image_sources

            logger.debug(f"从get_messages()获取到消息链，长度: {len(messages)}")

            for component in messages:
                if isinstance(component, Comp.Image):
                    url = MessageUtils._extract_from_image_component(component)
                    if url:
                        image_sources.append(url)
                        logger.debug(f"提取到图片: {url[:50]}...")

                elif isinstance(component, Comp.Reply):
                    if hasattr(component, 'chain') and component.chain:
                        for reply_component in component.chain:
                            if isinstance(reply_component, Comp.Image):
                                url = MessageUtils._extract_from_image_component(reply_component)
                                if url:
                                    image_sources.append(url)
                                    logger.debug(f"从回复消息提取到图片")

            logger.debug(f"总共找到 {len(image_sources)} 个图像源")
            return image_sources

        except Exception as e:
            logger.error(f"提取图像源失败: {e}", exc_info=True)
            return []

    @staticmethod
    def _extract_from_messages(messages) -> List[str]:
        """从消息链中提取图像源"""
        image_sources = []

        if not messages or not isinstance(messages, list):
            return image_sources

        for component in messages:
            if isinstance(component, Comp.Image):
                url = MessageUtils._extract_from_image_component(component)
                if url:
                    image_sources.append(url)
                    logger.debug(f"从消息链提取到图片: {url[:50]}...")

            elif isinstance(component, Comp.Reply):
                reply_messages = None

                if hasattr(component, 'chain') and component.chain:
                    reply_messages = component.chain
                    logger.debug(f"Reply 组件有 chain 属性，长度: {len(reply_messages)}")

    @staticmethod
    def _extract_from_image_component(component: Comp.Image) -> Optional[str]:
        """
        从Image组件提取图像URL

        Args:
            component: Image组件

        Returns:
            图像URL或数据
        """
        # 优先检查url属性
        if hasattr(component, "url") and component.url:
            logger.debug(f"从Image组件找到url属性")  # ✅ debug级别
            return component.url

        # 其次检查file属性
        if hasattr(component, "file") and component.file:
            logger.debug(f"从Image组件找到file属性")  # ✅ debug级别

            # 如果是base64格式
            if isinstance(component.file, str) and component.file.startswith(
                "base64://"
            ):
                return component.file
            # 如果是普通字符串
            elif isinstance(component.file, str):
                return component.file

        # 检查其他可能的属性
        for attr_name in ["data", "path", "content"]:
            if hasattr(component, attr_name):
                attr_value = getattr(component, attr_name)
                if attr_value:
                    logger.debug(f"从Image组件找到{attr_name}属性")  # ✅ debug级别
                    if isinstance(attr_value, str):
                        return attr_value

        logger.debug(f"Image组件没有找到有效的URL属性")  # ✅ debug级别
        return None

    @staticmethod
    def _extract_from_reply_component(component: Comp.Reply) -> List[str]:
        """
        从Reply组件提取图像

        Args:
            component: Reply组件

        Returns:
            图像URL列表
        """
        image_sources = []

        if hasattr(component, 'chain') and component.chain:
            for reply_component in component.chain:
                if isinstance(reply_component, Comp.Image):
                    url = MessageUtils._extract_from_image_component(reply_component)
                    if url:
                        image_sources.append(url)

        return image_sources

    @staticmethod
    def extract_command_text(event) -> Optional[str]:
        """
        提取纯文本指令

        Args:
            event: 消息事件

        Returns:
            指令文本
        """
        try:
            messages = event.get_messages()
        except AttributeError:
            messages = event.message_obj.message

        for component in messages:
            if isinstance(component, Comp.Plain):
                text = component.text.strip()
                if text:
                    return text

        return None

    @staticmethod
    def has_image_in_message(event) -> bool:
        """
        检查消息中是否包含图像

        Args:
            event: 消息事件

        Returns:
            是否包含图像
        """
        try:
            messages = event.get_messages()
        except AttributeError:
            messages = event.message_obj.message

        for component in messages:
            if isinstance(component, Comp.Image):
                return True
            elif isinstance(component, Comp.Reply):
                # 检查回复中是否有图像
                if hasattr(component, "chain") and component.chain:
                    for reply_component in component.chain:
                        if isinstance(reply_component, Comp.Image):
                            return True

        return False
