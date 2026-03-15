"""
pytest 配置文件

在测试运行前加载 .env 文件中的环境变量。
"""

import os
from pathlib import Path

# 尝试加载 python-dotenv
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def pytest_configure(config):
    """
    pytest 配置钩子
    
    在所有测试运行前加载 .env 文件
    """
    # 查找 .env 文件路径（项目根目录）
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        if HAS_DOTENV:
            # 使用 python-dotenv 加载 .env 文件
            load_dotenv(env_file, override=True)
            print(f"\n[conftest] 已从 {env_file} 加载环境变量")
        else:
            # 如果没有 python-dotenv，手动解析 .env 文件
            _load_env_manually(env_file)
            print(f"\n[conftest] 已手动从 {env_file} 加载环境变量")


def _load_env_manually(env_file: Path) -> None:
    """
    手动解析 .env 文件
    
    Args:
        env_file: .env 文件路径
    """
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            
            # 解析 KEY=VALUE 格式
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                
                # 移除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # 设置环境变量（不覆盖已存在的）
                if key and not os.environ.get(key):
                    os.environ[key] = value
