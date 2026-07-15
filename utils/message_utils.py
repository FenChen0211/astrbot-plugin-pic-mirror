"""
消息解析工具模块
"""

from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse
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
                    url = MessageUtils._extract_from_image_component(component, event)
                    if url:
                        image_sources.append(url)
                        logger.debug(f"提取到图片: {url[:50]}...")

                elif isinstance(component, Comp.Reply):
                    if hasattr(component, "chain") and component.chain:
                        for reply_component in component.chain:
                            if isinstance(reply_component, Comp.Image):
                                url = MessageUtils._extract_from_image_component(
                                    reply_component, event
                                )
                                if url:
                                    image_sources.append(url)
                                    logger.debug("从回复消息提取到图片")

            logger.debug(f"总共找到 {len(image_sources)} 个图像源")
            return image_sources

        except (AttributeError, TypeError, KeyError, IndexError, ValueError) as e:
            logger.error(f"提取图像源失败: {type(e).__name__}: {e}", exc_info=True)
            return []

    @staticmethod
    def _extract_from_image_component(
        component: Comp.Image, event=None
    ) -> Optional[str]:
        """
        从Image组件提取图像URL

        Args:
            component: Image组件

        Returns:
            图像URL或数据
        """
        # AstrBot 4.26.0+ 会将媒体落到本地，并把路径放入 path/file。
        path = getattr(component, "path", None)
        if isinstance(path, str) and path:
            logger.debug("从Image组件找到path属性")
            return MessageUtils._recover_original_gif(event, path)

        file_value = getattr(component, "file", None)
        url = getattr(component, "url", None)
        if (
            isinstance(file_value, str)
            and file_value
            and (
                not isinstance(url, str)
                or not url
                or MessageUtils._is_direct_image_source(file_value)
            )
        ):
            logger.debug("从Image组件找到可直接使用的file属性")
            return MessageUtils._recover_original_gif(event, file_value)

        if isinstance(url, str) and url:
            logger.debug("从Image组件找到url属性")
            return MessageUtils._recover_original_gif(event, url)

        for attr_name in ["data", "content"]:
            if hasattr(component, attr_name):
                attr_value = getattr(component, attr_name)
                if isinstance(attr_value, str) and attr_value:
                    logger.debug(f"从Image组件找到{attr_name}属性")  # ✅ debug级别
                    return MessageUtils._recover_original_gif(event, attr_value)

        logger.debug("Image组件没有找到有效的URL属性")  # ✅ debug级别
        return None

    @staticmethod
    def _is_direct_image_source(value: str) -> bool:
        """判断 file 字段是否是可直接处理的媒体引用。"""
        if value.startswith(("http://", "https://", "base64://", "file://")):
            return True
        try:
            return MessageUtils._local_reference_to_path(value).is_file()
        except (OSError, ValueError):
            return False

    @staticmethod
    def get_trusted_event_media_paths(event) -> List[str]:
        """获取 AstrBot 为当前事件登记的临时媒体路径。"""
        paths = getattr(event, "_temporary_local_files", None)
        if not isinstance(paths, (list, tuple, set)):
            return []
        return [str(path) for path in paths if isinstance(path, (str, Path))]

    @staticmethod
    def _recover_original_gif(event, source: str) -> str:
        """在 AstrBot 4.26.0 的 JPEG 预处理结果前找回原始 GIF。"""
        if event is None:
            return source

        source_path = MessageUtils._local_reference_to_path(source)
        if (
            source_path.suffix.lower() not in {".jpg", ".jpeg"}
            or not source_path.name.startswith("media_image_")
        ):
            return source

        tracked_paths = MessageUtils.get_trusted_event_media_paths(event)
        try:
            source_resolved = source_path.resolve()
        except OSError:
            return source

        for index, tracked in enumerate(tracked_paths):
            try:
                if (
                    MessageUtils._local_reference_to_path(tracked).resolve()
                    != source_resolved
                    or index == 0
                ):
                    continue
                original_path = MessageUtils._local_reference_to_path(
                    tracked_paths[index - 1]
                ).resolve()
                if not original_path.is_file():
                    return source
                with original_path.open("rb") as file:
                    if file.read(6) in {b"GIF87a", b"GIF89a"}:
                        logger.debug("从 AstrBot 临时文件记录中恢复原始 GIF")
                        return str(original_path)
            except OSError:
                return source

        return source

    @staticmethod
    def _local_reference_to_path(value: str) -> Path:
        """将普通路径或 file URI 规范化为 Path。"""
        if not isinstance(value, str):
            raise ValueError("本地路径必须是字符串")

        parsed = urlparse(value)
        if parsed.scheme.lower() != "file":
            return Path(value)

        netloc = unquote(parsed.netloc or "")
        path = unquote(parsed.path or "")
        if len(netloc) == 2 and netloc[1] == ":":
            return Path(f"{netloc}{path}")
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        if netloc and netloc.lower() != "localhost":
            path = f"//{netloc}{path}"
        return Path(path)

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
