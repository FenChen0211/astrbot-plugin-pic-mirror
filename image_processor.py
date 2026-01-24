"""
图像对称处理模块
"""

import asyncio
import io
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
    async def process_image(
        input_path: str,
        output_path: str,
        mode: str,
        plugin_name: str = "astrbot-plugin-pic-mirror",
        config: Optional[PluginConfig] = None,
    ) -> Tuple[bool, str]:
        """
        处理图像的主函数

        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            mode: 对称模式
            plugin_name: 插件名称（用于数据目录）
            config: 插件配置

        Returns:
            Tuple[bool, str]: (是否成功, 错误信息或成功信息)
        """
        try:
            # 验证文件存在
            if not Path(input_path).exists():
                return False, f"输入文件不存在: {input_path}"

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
        处理静态图像
        """
        try:
            with Image.open(input_path) as img:
                # 检查图像尺寸安全性（防止解压炸弹）
                if not MirrorProcessor._check_image_size(img):
                    return False, f"图像尺寸过大，可能存在安全风险: {img.width}x{img.height}像素"
                
                # 转换模式（确保透明度处理正确）
                if img.mode == "P":
                    img = img.convert("RGBA")
                elif img.mode == "LA":
                    img = img.convert("RGBA")

                # 应用对称变换
                loop = asyncio.get_running_loop()
                mirrored = await loop.run_in_executor(
                    None,
                    MirrorProcessor._apply_mirror,
                    img,
                    mode
                )

                # 应用压缩（如果启用）
                if config and config.enable_compression:
                    mirrored = await loop.run_in_executor(
                        None,
                        MirrorProcessor._compress_image,
                        mirrored,
                        config
                    )

                # 保存图像（使用配置的质量设置）
                quality = config.output_quality if config else 85
                
                # 将保存操作放到线程池中执行
                def save_image():
                    if input_path.lower().endswith(".png"):
                        mirrored.save(output_path, optimize=True)
                    elif input_path.lower().endswith(".webp"):
                        mirrored.save(
                            output_path, quality=quality, method=6
                        )  # method=6为默认平衡模式
                    else:
                        mirrored.save(output_path, quality=quality, optimize=True)
                
                await loop.run_in_executor(None, save_image)

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
            # 如果是PNG，尝试转换为更小的颜色模式
            if image.mode == "RGBA":
                # 检查是否真的需要透明度
                try:
                    alpha = image.getchannel("A")
                    if alpha.getextrema() == (255, 255):  # 完全不透明
                        image = image.convert("RGB")
                except:
                    pass

            # 如果是大图像，可以适当缩小尺寸
            width, height = image.size
            max_dimension = 2048  # 最大尺寸限制

            if width > max_dimension or height > max_dimension:
                ratio = min(max_dimension / width, max_dimension / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            return image
        except Exception:
            # 压缩失败时返回原图
            return image

    @staticmethod
    async def _process_gif(
        input_path: str,
        output_path: str,
        mode: str,
        config: Optional[PluginConfig] = None,
    ) -> Tuple[bool, str]:
        """
        处理GIF动画
        """
        try:
            # 读取GIF
            loop = asyncio.get_running_loop()
            frames = []
            durations = []

            with Image.open(input_path) as img:
                # 检查GIF整体尺寸安全性
                if not MirrorProcessor._check_image_size(img):
                    return False, f"GIF尺寸过大，可能存在安全风险: {img.width}x{img.height}像素"
                
                # 计算帧数
                frame_count = 0
                for _ in ImageSequence.Iterator(img):
                    frame_count += 1
                
                # 帧数过多时提示
                if frame_count > 100:
                    logger.warning(f"处理大型GIF: {frame_count}帧，可能需要较长时间")
                
                for frame in ImageSequence.Iterator(img):
                    # 记录每帧持续时间
                    durations.append(frame.info.get("duration", 100))

                    # 处理当前帧
                    if frame.mode == "P":
                        frame = frame.convert("RGBA")
                    elif frame.mode == "LA":
                        frame = frame.convert("RGBA")

                    # 将CPU密集型的图像处理操作放到线程池中执行
                    mirrored_frame = await loop.run_in_executor(
                        None,
                        MirrorProcessor._apply_mirror,
                        frame,
                        mode
                    )

                    # 应用压缩（如果启用）
                    if config and config.enable_compression:
                        mirrored_frame = await loop.run_in_executor(
                            None,
                            MirrorProcessor._compress_image,
                            mirrored_frame,
                            config
                        )

                    frames.append(mirrored_frame)

            # 保存GIF
            if len(frames) > 0:
                # 将保存操作放到线程池中执行
                def save_gif():
                    frames[0].save(
                        output_path,
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=0,
                        optimize=True,
                    )
                
                await loop.run_in_executor(None, save_gif)
                return True, "GIF处理成功"
            else:
                return False, "GIF没有帧数据"

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
            # 左半边对称到右边
            left_half = image.crop((0, 0, width // 2, height))
            right_half = left_half.transpose(Image.FLIP_LEFT_RIGHT)
            result.paste(left_half, (0, 0))
            result.paste(right_half, (width // 2, 0))

        elif mode == "right_to_left":
            # 右半边对称到左边
            right_half = image.crop((width // 2, 0, width, height))
            left_half = right_half.transpose(Image.FLIP_LEFT_RIGHT)
            result.paste(left_half, (0, 0))
            result.paste(right_half, (width // 2, 0))

        elif mode == "top_to_bottom":
            # 上半边对称到下面
            top_half = image.crop((0, 0, width, height // 2))
            bottom_half = top_half.transpose(Image.FLIP_TOP_BOTTOM)
            result.paste(top_half, (0, 0))
            result.paste(bottom_half, (0, height // 2))

        elif mode == "bottom_to_top":
            # 下半边对称到上面
            bottom_half = image.crop((0, height // 2, width, height))
            top_half = bottom_half.transpose(Image.FLIP_TOP_BOTTOM)
            result.paste(top_half, (0, 0))
            result.paste(bottom_half, (0, height // 2))

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
