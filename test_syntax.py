# test_syntax.py - 放在插件目录中运行
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== 测试所有文件语法 ===")

files_to_test = [
    "main.py",
    "config.py",
    "image_processor.py",
    "core/image_handler.py",
    "services/config_service.py",
    "utils/file_utils.py",
    "utils/network_utils.py",
    "core/cleanup_manager.py"
]

for file in files_to_test:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 尝试编译
        compile(content, file, 'exec')
        print(f"✓ {file} 语法正确")
    except SyntaxError as e:
        print(f"✗ {file} 语法错误: {e}")
    except Exception as e:
        print(f"✗ {file} 读取失败: {e}")

print("\n=== 测试关键导入 ===")

try:
    print("1. 测试导入 config...")
    from config import PluginConfig
    print("   ✓ config 导入成功")
except ImportError as e:
    print(f"   ✗ config 导入失败: {e}")

try:
    print("2. 测试导入 utils.file_utils...")
    from utils.file_utils import FileUtils
    print("   ✓ file_utils 导入成功")
except ImportError as e:
    print(f"   ✗ file_utils 导入失败: {e}")

try:
    print("3. 测试导入 image_processor...")
    from image_processor import MirrorProcessor
    print("   ✓ image_processor 导入成功")
except ImportError as e:
    print(f"   ✗ image_processor 导入失败: {e}")

print("\n=== 测试PIL依赖 ===")
try:
    from PIL import Image
    print("✓ PIL/Pillow 已安装")
except ImportError:
    print("✗ PIL/Pillow 未安装 - 需要运行: pip install Pillow")