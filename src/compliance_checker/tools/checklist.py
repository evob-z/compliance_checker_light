"""
load_checklist 工具实现
支持从文件或 YAML 字符串加载审核清单
"""

import os
from typing import Optional

from compliance_checker.core.checklist_model import Checklist, ProjectPeriod
from compliance_checker.core.yaml_compat import safe_load

# 导入配置
try:
    import sys
    from pathlib import Path
    config_path = Path(__file__).parent.parent.parent.parent / "config"
    if str(config_path) not in sys.path:
        sys.path.insert(0, str(config_path))
    from settings import (
        get_default_checklist_path,
        get_default_checklist_id,
        is_user_yaml_allowed
    )
except ImportError:
    # 配置不可用时的默认值
    def get_default_checklist_path():
        return "/home/evob/.openclaw/workspace/compliance-checker/config/checklists"
    def get_default_checklist_id():
        return "default"
    def is_user_yaml_allowed():
        return True


# 配置文件目录（向后兼容）
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "checklists")


async def load_checklist(
    checklist_id: Optional[str] = None,
    yaml_content: Optional[str] = None,
    yaml_file_path: Optional[str] = None,
    project_period: Optional[dict] = None
) -> dict:
    """
    加载审核清单配置。
    
    支持三种方式：
    1. 从配置文件加载：提供 checklist_id（如 "default" 会加载 default.yaml）
    2. 从 YAML 字符串加载：直接提供 yaml_content
    3. 从 YAML 文件路径加载：提供 yaml_file_path（绝对路径）
    
    优先级：yaml_file_path > yaml_content > checklist_id > 默认配置
    
    Args:
        checklist_id: 清单配置文件ID
        yaml_content: YAML 格式字符串
        yaml_file_path: YAML 文件的绝对路径
        project_period: 可选，覆盖或设置项目周期
    
    Returns:
        结构化的清单字典
    
    Raises:
        ValueError: 参数无效或配置文件不存在
    """
    # 确定清单目录（优先使用配置中的路径）
    checklist_dir = get_default_checklist_path()
    
    raw_data = None
    source_info = ""
    
    # 方式1：从 YAML 文件路径加载（最高优先级）
    if yaml_file_path:
        if not os.path.exists(yaml_file_path):
            raise ValueError(f"YAML 文件不存在: {yaml_file_path}")
        
        with open(yaml_file_path, "r", encoding="utf-8") as f:
            raw_data = safe_load(f.read())
        source_info = f"文件: {yaml_file_path}"
    
    # 方式2：从 YAML 字符串加载
    elif yaml_content:
        if not is_user_yaml_allowed():
            raise ValueError("当前配置不允许用户传入 YAML 内容")
        raw_data = safe_load(yaml_content)
        source_info = "YAML 字符串"
    
    # 方式3：从配置文件加载
    elif checklist_id:
        config_path = os.path.join(checklist_dir, f"{checklist_id}.yaml")
        if not os.path.exists(config_path):
            # 尝试向后兼容查找旧路径
            config_path = os.path.join(CONFIG_DIR, f"{checklist_id}.yaml")
        
        if not os.path.exists(config_path):
            raise ValueError(f"清单配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = safe_load(f.read())
        source_info = f"配置文件: {checklist_id}"
    
    # 方式4：使用默认配置
    else:
        default_id = get_default_checklist_id()
        config_path = os.path.join(checklist_dir, f"{default_id}.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(CONFIG_DIR, f"{default_id}.yaml")
        
        if not os.path.exists(config_path):
            raise ValueError(f"默认清单配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = safe_load(f.read())
        source_info = f"默认配置: {default_id}"
    
    if not raw_data:
        raise ValueError("无法解析清单数据")
    
    # 字段映射：checklist_id -> id
    if "checklist_id" in raw_data and "id" not in raw_data:
        raw_data["id"] = raw_data.pop("checklist_id")
    
    # 如果提供了 project_period，覆盖或设置
    if project_period:
        raw_data["project_period"] = project_period
    
    # 转换为数据模型 (Pydantic v2)
    checklist = Checklist.model_validate(raw_data)
    
    # 返回字典格式，将 id 映射回 checklist_id
    result = checklist.model_dump()
    result["checklist_id"] = result.pop("id")
    result["_source"] = source_info  # 添加来源信息（调试用）
    return result


def list_available_checklists() -> list:
    """
    列出所有可用的清单配置文件。
    
    Returns:
        清单ID列表
    """
    checklists = []
    
    # 从配置路径查找
    checklist_dir = get_default_checklist_path()
    if os.path.exists(checklist_dir):
        for filename in os.listdir(checklist_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                checklist_id = filename.rsplit(".", 1)[0]
                checklists.append(checklist_id)
    
    # 从旧路径查找（向后兼容）
    if os.path.exists(CONFIG_DIR):
        for filename in os.listdir(CONFIG_DIR):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                checklist_id = filename.rsplit(".", 1)[0]
                if checklist_id not in checklists:
                    checklists.append(checklist_id)
    
    return sorted(checklists)
