"""插件常量定义"""

import yaml
from pathlib import Path

PLUGIN_NAME = "astrbot-plugin-pic-mirror"
PLUGIN_AUTHOR = "FenChen0211"
PLUGIN_DESCRIPTION = "图像对称处理插件"

# 从 metadata.yaml 读取版本号
def _load_version() -> str:
    try:
        metadata_path = Path(__file__).parent / "metadata.yaml"
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = yaml.safe_load(f)
                version = metadata.get("version", "v1.2.0")
                # 去除可能的前缀 "v"，只保留版本号部分
                if version.startswith("v"):
                    version = version[1:]
                return version
    except Exception:
        pass
    return "1.2.0"

PLUGIN_VERSION = _load_version()
