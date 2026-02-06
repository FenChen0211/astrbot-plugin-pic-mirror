"""插件常量定义"""

import yaml
from pathlib import Path

PLUGIN_NAME = "astrbot-plugin-pic-mirror"
PLUGIN_AUTHOR = "FenChen0211"
PLUGIN_DESCRIPTION = "图像对称处理插件"


def _load_version() -> str:
    """
    从 metadata.yaml 读取版本号
    版本号只能来源于 metadata.yaml 文件，不允许硬编码
    """
    try:
        metadata_path = Path(__file__).parent / "metadata.yaml"
        if not metadata_path.exists():
            from astrbot.api import logger
            logger.error(f"[{PLUGIN_NAME}] 插件元数据文件不存在: {metadata_path}")
            return "unknown"

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = yaml.safe_load(f)

        version = metadata.get("version")
        if not version:
            from astrbot.api import logger
            logger.error(f"[{PLUGIN_NAME}] metadata.yaml 中未找到 version 字段")
            return "unknown"

        if version.startswith("v"):
            version = version[1:]

        return version

    except FileNotFoundError:
        from astrbot.api import logger
        logger.error(f"[{PLUGIN_NAME}] 插件元数据文件不存在")
        return "unknown"
    except (yaml.YAMLError, PermissionError) as e:
        from astrbot.api import logger
        logger.error(f"[{PLUGIN_NAME}] 解析 metadata.yaml 失败: {e}")
        return "unknown"


PLUGIN_VERSION = _load_version()
