"""
Application 层

负责用例编排和依赖注入组装，统筹整个合规检查流程。
"""

from .bootstrap import (
    CheckerConfig,
    Container,
    initialize_app,
    initialize_registry,
)
from .formatter import (
    format_check_result,
    format_simple_result,
    format_issues_description,
)
from .skill import ComplianceSkill
from .use_cases import ProjectCheckUseCase

__all__ = [
    # Facade
    "ComplianceSkill",
    # Bootstrap
    "CheckerConfig",
    "Container",
    "initialize_app",
    "initialize_registry",
    # Formatter
    "format_check_result",
    "format_simple_result",
    "format_issues_description",
    # Use Cases
    "ProjectCheckUseCase",
]
