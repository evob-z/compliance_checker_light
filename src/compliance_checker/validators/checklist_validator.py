"""
清单 YAML 验证器

用于验证外部 LLM 生成的 YAML 是否合法
"""

import yaml
import logging
from typing import List, Dict, Any
from pydantic import ValidationError

from ..core.checklist_model import Checklist
from ..core.checker_registry import get_initialized_registry

logger = logging.getLogger(__name__)


class ValidationResult:
    """验证结果"""
    
    def __init__(self):
        self.valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def add_error(self, msg: str):
        """添加错误"""
        self.valid = False
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        """添加警告"""
        self.warnings.append(msg)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


async def validate_checklist_yaml(yaml_content: str) -> ValidationResult:
    """
    验证清单 YAML 的合法性
    
    检查项：
    1. YAML 格式是否合法
    2. 必需字段是否完整
    3. 检查类型是否有效（或已标记为未实现）
    4. 引用是否一致
    
    Args:
        yaml_content: YAML 字符串
    
    Returns:
        ValidationResult
    """
    result = ValidationResult()
    registry = get_initialized_registry()
    
    # 1. 解析 YAML
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.add_error(f"YAML 格式错误: {e}")
        return result
    
    if not data or "checklist" not in data:
        result.add_error("缺少根节点 'checklist'")
        return result
    
    checklist_data = data["checklist"]
    
    # 2. 检查必需字段
    required_fields = ["id", "name"]
    for field in required_fields:
        if field not in checklist_data:
            result.add_error(f"缺少必需字段: checklist.{field}")
    
    if not result.valid:
        return result
    
    # 3. 检查文档配置
    docs = checklist_data.get("required_documents", [])
    if not docs:
        result.add_warning("没有配置必需文档")
    
    available_checkers = registry.list_available()
    all_checkers = registry.list_all()
    
    for i, doc in enumerate(docs):
        doc_name = doc.get("name", f"文档_{i}")
        
        if not doc.get("name"):
            result.add_error(f"文档 {i} 缺少 name 字段")
            continue
        
        # 检查 checks 配置
        checks = doc.get("checks", [])
        if not checks:
            result.add_warning(f"文档 '{doc_name}' 没有配置 checks，将使用默认")
            continue
        
        has_completeness = False
        for j, check in enumerate(checks):
            check_type = check.get("type")
            
            if not check_type:
                result.add_error(f"文档 '{doc_name}' 的检查 {j} 缺少 type")
                continue
            
            if check_type == "completeness":
                has_completeness = True
            
            # 检查类型是否有效
            if check_type not in all_checkers:
                result.add_warning(
                    f"检查类型 '{check_type}' 未注册，将被视为未实现功能"
                )
            elif check_type not in available_checkers:
                result.add_warning(
                    f"检查类型 '{check_type}' 已标记为未实现"
                )
        
        if not has_completeness:
            result.add_warning(f"文档 '{doc_name}' 建议添加 completeness 检查")
    
    # 4. 尝试用 Pydantic 验证完整结构
    try:
        Checklist.model_validate(checklist_data)
    except ValidationError as e:
        # 只报告关键错误，因为新版格式可能包含扩展字段
        for err in e.errors():
            if err.get("type") == "missing" or "loc" in err:
                result.add_error(f"Pydantic 验证失败: {err.get('msg', str(err))}")
    
    return result


def validate_checklist_dict(data: Dict[str, Any]) -> ValidationResult:
    """
    验证清单字典的合法性
    
    Args:
        data: 清单字典
    
    Returns:
        ValidationResult
    """
    result = ValidationResult()
    
    if not data or "checklist" not in data:
        result.add_error("缺少根节点 'checklist'")
        return result
    
    checklist_data = data["checklist"]
    
    # 检查必需字段
    required_fields = ["id", "name"]
    for field in required_fields:
        if field not in checklist_data:
            result.add_error(f"缺少必需字段: checklist.{field}")
    
    # 尝试用 Pydantic 验证
    try:
        Checklist.model_validate(checklist_data)
    except ValidationError as e:
        for err in e.errors():
            result.add_error(f"验证失败: {err['msg']}")
    
    return result
