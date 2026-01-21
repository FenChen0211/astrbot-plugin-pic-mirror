"""
图像对称插件工具模块
处理文件操作、验证和路径管理
"""

import os
import re
import hashlib
import base64
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image
import astrbot.api.message_components as Comp


class FileUtils:
    """文件处理工具类"""

    # 支持的图像格式
    SUPPORTED_STATIC_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    SUPPORTED_GIF_FORMAT = {".gif"}
    SUPPORTED_FORMATS = SUPPORTED_STATIC_FORMATS | SUPPORTED_GIF_FORMAT

    # 文件大小限制（10MB）
    MAX_FILE_SIZE = 10 * 1024 * 1024

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
        path = url_or_path.split("?")[0]
        # 提取扩展名
        match = re.search(r"\.([a-zA-Z0-9]+)$", path)
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

        ext = FileUtils.get_file_extension(original_url) or ".png"
        return f"mirror_{mode}_{file_hash}{ext}"

    @staticmethod
    def validate_image_size(image_path: str) -> Tuple[bool, str]:
        """
        验证图像文件大小

        Args:
            image_path: 图像文件路径

        Returns:
            Tuple[bool, str]: (是否通过验证, 错误信息)
        """
        try:
            file_size = os.path.getsize(image_path)
            if file_size > FileUtils.MAX_FILE_SIZE:
                return (
                    False,
                    f"图像文件过大（{file_size / 1024 / 1024:.1f}MB），请使用小于10MB的图像",
                )
            return True, ""
        except Exception as e:
            return False, f"无法获取文件大小: {str(e)}"

    @staticmethod
    def extract_image_urls_from_event(event) -> List[str]:
        """
        从消息事件中提取所有图像URL（修复版）

        关键修复：优先使用url属性，正确处理Reply组件的chain属性
        """
        image_urls = []

        try:
            # 使用event.get_messages()获取消息链
            messages = event.get_messages()
        except AttributeError:
            # 如果get_messages()不存在，使用message_obj.message
            messages = event.message_obj.message

        for component in messages:
            # 处理普通Image组件
            if isinstance(component, Comp.Image):
                # 关键修复：优先检查url属性
                if hasattr(component, "url") and component.url:
                    image_urls.append(component.url)
                    continue

                # 其次检查file属性
                if hasattr(component, "file") and component.file:
                    # 如果是base64数据，直接使用
                    if isinstance(component.file, str) and component.file.startswith(
                        "base64://"
                    ):
                        image_urls.append(component.file)
                    # 如果是普通字符串，可能是本地路径
                    elif isinstance(component.file, str):
                        image_urls.append(component.file)

            # 处理Reply组件
            elif isinstance(component, Comp.Reply):
                # 关键修复：使用chain属性获取被回复的内容
                if hasattr(component, "chain") and component.chain:
                    for reply_component in component.chain:
                        if isinstance(reply_component, Comp.Image):
                            if hasattr(reply_component, "url") and reply_component.url:
                                image_urls.append(reply_component.url)
                            elif (
                                hasattr(reply_component, "file")
                                and reply_component.file
                            ):
                                if isinstance(
                                    reply_component.file, str
                                ) and reply_component.file.startswith("base64://"):
                                    image_urls.append(reply_component.file)

        return image_urls

    @staticmethod
    def is_base64_image(data: str) -> bool:
        """检查是否为base64格式的图像数据"""
        return isinstance(data, str) and data.startswith("base64://")

    @staticmethod
    def decode_base64_image(base64_data: str) -> Optional[bytes]:
        """解码base64图像数据"""
        try:
            if base64_data.startswith("base64://"):
                base64_data = base64_data[len("base64://") :]
            return base64.b64decode(base64_data)
        except Exception as e:
            return None
