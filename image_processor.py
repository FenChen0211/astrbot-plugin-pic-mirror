"""
图像对称处理模块
"""

import asyncio
import io
import os
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageSequence

# 注意：PIL全局设置已移除，避免影响其他插件

# 统一使用相对导入
from .utils.file_utils import FileUtils
from .config import PluginConfig
from astrbot.api import logger


class MirrorProcessor:
    """图像对称处理器"""

    @staticmethod
    def _check_image_size(img: Image.Image) -> bool:
        """
        检查图像尺寸，防止解压炸弹 - 简化版

        Args:
            img: PIL图像对象

        Returns:
            bool: 图像尺寸是否在安全范围内
        """
        pixels = img.width * img.height

        # 1亿像素硬限制
        if pixels > 10000 * 10000:
            return False

        # 2500万像素警告
        if pixels > 5000 * 5000:
            logger.warning(f"处理大图像: {pixels}像素 ({img.width}x{img.height})")

        return True

    @staticmethod
    def _check_image_before_open(file_path: str) -> Tuple[bool, str]:
        """
        打开图像前进行安全检查（解压炸弹防护）

        检查项:
        - 文件大小限制（硬限制100MB）
        - 文件头校验
        - 文件是否为空

        Args:
            file_path: 文件路径

        Returns:
            Tuple[bool, str]: (是否安全, 错误信息)
        """
        try:
            # 检查文件大小（防止超大文件）
            max_size = 100 * 1024 * 1024  # 100MB硬限制
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                return False, f"文件过大 ({file_size / 1024 / 1024:.1f}MB > 100MB)"

            # 检查文件头
            with open(file_path, "rb") as f:
                header = f.read(100)
                if not header:
                    return False, "文件为空或无法读取"

            return True, ""
        except Exception as e:
            logger.error(f"图像预检查异常: {e}")
            return False, "文件检查失败"

    @staticmethod
    async def process_image(
        input_path: str,
        output_path: str,
        mode: str,
        config: Optional[PluginConfig] = None,
    ) -> Tuple[bool, str]:
        """
        处理图像的主函数

        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            mode: 对称模式
            config: 插件配置

        Returns:
            Tuple[bool, str]: (是否成功, 错误信息或成功信息)
        """
        try:
            # 验证文件存在
            if not Path(input_path).exists():
                return False, f"输入文件不存在: {input_path}"

            # 1. 解压炸弹预检查（文件大小和文件头）
            is_safe, msg = MirrorProcessor._check_image_before_open(input_path)
            if not is_safe:
                return False, msg

            # 验证文件大小（使用配置）
            is_valid, error_msg = FileUtils.validate_image_size(input_path, config)
            if not is_valid:
                return False, error_msg

            # 获取文件扩展名
            ext = FileUtils.get_file_extension(input_path)
            if not ext:
                return False, "无法识别图像格式"

            # 检查GIF支持
            if ext == ".gif":
                if config and not config.enable_gif:
                    return False, "GIF处理功能已禁用"

            # 处理GIF
            if ext in FileUtils.SUPPORTED_GIF_FORMAT:
                return await MirrorProcessor._process_gif(
                    input_path, output_path, mode, config
                )
            # 处理静态图像
            elif ext in FileUtils.SUPPORTED_STATIC_FORMATS:
                return await MirrorProcessor._process_static_image(
                    input_path, output_path, mode, config
                )
            else:
                return False, f"不支持的图像格式: {ext}"

        except Exception as e:
            return False, f"图像处理失败: {str(e)}"

    @staticmethod
    async def _process_static_image(
        input_path: str,
        output_path: str,
        mode: str,
        config: Optional[PluginConfig] = None,
    ) -> Tuple[bool, str]:
        """
        处理静态图像（全异步，避免阻塞）
        """
        try:
            loop = asyncio.get_running_loop()

            # 将所有图像处理放入executor执行
            def process_in_thread():
                with Image.open(input_path) as img:
                    # 检查图像尺寸安全性（防止解压炸弹）
                    if not MirrorProcessor._check_image_size(img):
                        return (
                            None,
                            f"图像尺寸过大，可能存在安全风险: {img.width}x{img.height}像素",
                        )

                    # 转换模式（确保透明度处理正确）
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    elif img.mode == "LA":
                        img = img.convert("RGBA")

                    # 应用对称变换
                    mirrored = MirrorProcessor._apply_mirror(img, mode)

                    # 应用压缩（如果启用）
                    if config and config.enable_compression:
                        mirrored = MirrorProcessor._compress_image(mirrored, config)

                    # 保存图像（使用配置的质量设置）
                    quality = config.output_quality if config else 85

                    # 根据输出路径扩展名判断保存格式
                    output_ext = Path(output_path).suffix.lower()

                    # === JPEG格式特殊处理：确保RGB模式 ===
                    if output_ext in [".jpg", ".jpeg"] and mirrored.mode == "RGBA":
                        try:
                            # 创建一个白色背景，合成不透明图像
                            background = Image.new(
                                "RGB", mirrored.size, (255, 255, 255)
                            )
                            background.paste(mirrored, mask=mirrored.split()[3])
                            mirrored = background
                        except Exception as e:
                            logger.warning(f"JPEG图像RGBA转RGB失败: {e}")
                            mirrored = mirrored.convert("RGB")
                    elif output_ext not in [".png"] and mirrored.mode not in (
                        "RGB",
                        "L",
                        "P",
                    ):
                        # 其他格式确保至少是RGB或兼容模式
                        try:
                            mirrored = mirrored.convert("RGB")
                        except Exception as e:
                            logger.warning(f"图像模式转换失败: {e}")

                    # 保存图像
                    if output_ext == ".png":
                        mirrored.save(output_path, optimize=True)
                    elif output_ext == ".webp":
                        mirrored.save(output_path, quality=quality, method=6)
                    else:
                        mirrored.save(output_path, quality=quality, optimize=True)

                    return mirrored, quality

            result = await loop.run_in_executor(None, process_in_thread)

            if result[0] is None:
                return False, result[1]

            return True, "图像处理成功"

        except Exception as e:
            return False, f"静态图像处理失败: {str(e)}"

    @staticmethod
    def _compress_image(image: Image.Image, config: PluginConfig) -> Image.Image:
        """
        压缩图像

        Args:
            image: PIL图像对象
            config: 插件配置

        Returns:
            压缩后的图像
        """
        try:
            if image.mode == "RGBA":
                try:
                    alpha = image.getchannel("A")
                    if alpha.getextrema() == (255, 255):
                        image = image.convert("RGB")
                except (ValueError, KeyError) as e:
                    logger.debug(f"无法获取alpha通道或检查透明度: {e}")

            width, height = image.size
            max_dimension = 2048

            if width > max_dimension or height > max_dimension:
                ratio = min(max_dimension / width, max_dimension / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            return image
        except (ValueError, OSError, MemoryError) as e:
            logger.warning(f"图像压缩失败，返回原图: {type(e).__name__}: {e}")
            return image

    @staticmethod
    async def _process_gif(
        input_path: str,
        output_path: str,
        mode: str,
        config: Optional[PluginConfig] = None,
    ) -> Tuple[bool, str]:
        """
        处理GIF动画（全异步，避免阻塞）
        """
        try:
            loop = asyncio.get_running_loop()

            # 将整个GIF处理放入executor执行
            def process_gif_in_thread():
                frames = []
                durations = []

                with Image.open(input_path) as img:
                    # 检查GIF整体尺寸安全性
                    if not MirrorProcessor._check_image_size(img):
                        return (
                            None,
                            f"GIF尺寸过大，可能存在安全风险: {img.width}x{img.height}像素",
                        )

                    MAX_FRAMES = (
                        config.max_gif_frames if config else 200
                    )  # GIF最大帧数限制，防止解压炸弹

                    # 一次遍历同时统计和处理帧
                    frame_count = 0
                    for frame in ImageSequence.Iterator(img):
                        frame_count += 1

                        if frame_count > MAX_FRAMES:
                            logger.error(
                                f"GIF帧数过多，可能存在解压炸弹风险: {frame_count}帧"
                            )
                            return (
                                None,
                                f"GIF帧数过多（{frame_count} > {MAX_FRAMES}），可能存在安全风险",
                            )

                        # 记录每帧持续时间
                        durations.append(frame.info.get("duration", 100))

                        # 处理当前帧
                        if frame.mode == "P":
                            frame = frame.convert("RGBA")
                        elif frame.mode == "LA":
                            frame = frame.convert("RGBA")

                        # 应用对称变换
                        mirrored_frame = MirrorProcessor._apply_mirror(frame, mode)

                        # 应用压缩（如果启用）
                        if config and config.enable_compression:
                            mirrored_frame = MirrorProcessor._compress_image(
                                mirrored_frame, config
                            )

                        frames.append(mirrored_frame)

                    # 帧数过多时提示
                    if frame_count > 100:
                        logger.warning(
                            f"处理大型GIF: {frame_count}帧，可能需要较长时间"
                        )

                # 保存GIF
                if len(frames) > 0:
                    frames[0].save(
                        output_path,
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=0,
                        optimize=True,
                    )
                    return frames, None

                return None, "GIF没有帧数据"

            result = await loop.run_in_executor(None, process_gif_in_thread)

            if result[0] is None:
                return False, result[1]

            return True, "GIF处理成功"

        except Exception as e:
            return False, f"GIF处理失败: {str(e)}"

    @staticmethod
    def _apply_mirror(image: Image.Image, mode: str) -> Image.Image:
        """
        应用对称变换

        Args:
            image: PIL图像对象
            mode: 对称模式

        Returns:
            Image.Image: 变换后的图像
        """
        width, height = image.size

        # 创建新图像
        result = Image.new(image.mode, (width, height))

        if mode == "left_to_right":
            # 左半边对称到右边（处理奇数宽度）
            half_width = (width + 1) // 2
            other_half = width - half_width
            left_half = image.crop((0, 0, half_width, height))
            right_half = left_half.transpose(Image.FLIP_LEFT_RIGHT)
            result.paste(left_half, (0, 0))
            # 只粘贴右侧需要的列数（防止越界）
            if other_half > 0:
                right_piece = right_half.crop(
                    (right_half.width - other_half, 0, right_half.width, height)
                )
                result.paste(right_piece, (half_width, 0))

        elif mode == "right_to_left":
            # 右半边对称到左边（处理奇数宽度）
            half_width = (width + 1) // 2
            other_half = width - half_width
            # 右侧包含上取整的一半（确保中间像素被正确处理）
            right_half = image.crop((other_half, 0, width, height))
            left_half = right_half.transpose(Image.FLIP_LEFT_RIGHT)
            # 只粘贴左侧需要的列数
            if other_half > 0:
                left_piece = left_half.crop((0, 0, other_half, height))
                result.paste(left_piece, (0, 0))
            result.paste(right_half, (other_half, 0))

        elif mode == "top_to_bottom":
            # 上半边对称到下面（处理奇数高度）
            half_height = (height + 1) // 2
            other_half = height - half_height
            top_half = image.crop((0, 0, width, half_height))
            bottom_half = top_half.transpose(Image.FLIP_TOP_BOTTOM)
            result.paste(top_half, (0, 0))
            if other_half > 0:
                bottom_piece = bottom_half.crop(
                    (0, bottom_half.height - other_half, width, bottom_half.height)
                )
                result.paste(bottom_piece, (0, half_height))

        elif mode == "bottom_to_top":
            # 下半边对称到上面（处理奇数高度）
            half_height = (height + 1) // 2
            other_half = height - half_height
            bottom_half = image.crop((0, other_half, width, height))
            top_half = bottom_half.transpose(Image.FLIP_TOP_BOTTOM)
            if other_half > 0:
                top_piece = top_half.crop((0, 0, width, other_half))
                result.paste(top_piece, (0, 0))
            result.paste(bottom_half, (0, other_half))

        else:
            # 默认不处理
            return image.copy()

        return result

    @staticmethod
    def get_mode_description(mode: str) -> str:
        """
        获取对称模式的描述

        Args:
            mode: 对称模式

        Returns:
            str: 模式描述
        """
        descriptions = {
            "left_to_right": "左半边图像对称到右边",
            "right_to_left": "右半边图像对称到左边",
            "top_to_bottom": "上半边图像对称到下面",
            "bottom_to_top": "下半边图像对称到上面",
        }
        return descriptions.get(mode, "未知对称模式")
