"""
核心组件模块

包含数据模型、检查器基类和注册表
"""

from .document import Document, PageContent
from .checklist_model import (
    Checklist,
    RequiredDocument,
    CompliancePoint,
    ValidityRule,
    ProjectPeriod,
    CheckMethod,
    DocumentType,
    ChecklistSummary
)
from .result_model import (
    CheckResult as LegacyCheckResult,
    CheckStatus as LegacyCheckStatus,
    CheckSummary,
    IssueItem,
    CompletenessResult,
    TimelinessResult,
    TimelinessDetail,
    ComplianceResult,
    DocumentCompliance,
    ComplianceCheckItem,
    DocumentMatch,
    MatchType
)
from .checker_base import (
    CheckStatus,
    CheckResult,
    BaseChecker,
    UnavailableChecker
)
from .checker_registry import (
    CheckerRegistry,
    get_initialized_registry
)
from .exceptions import (
    ComplianceCheckerError,
    ChecklistError,
    DocumentParseError,
    CheckExecutionError
)

__all__ = [
    # 文档模型
    "Document",
    "PageContent",
    
    # 清单模型
    "Checklist",
    "RequiredDocument",
    "CompliancePoint",
    "ValidityRule",
    "ProjectPeriod",
    "CheckMethod",
    "DocumentType",
    "ChecklistSummary",
    
    # 检查结果模型 (新版)
    "CheckStatus",
    "CheckResult",
    
    # 检查结果模型 (旧版兼容)
    "LegacyCheckStatus",
    "LegacyCheckResult",
    "CheckSummary",
    "IssueItem",
    "CompletenessResult",
    "TimelinessResult",
    "TimelinessDetail",
    "ComplianceResult",
    "DocumentCompliance",
    "ComplianceCheckItem",
    "DocumentMatch",
    "MatchType",
    
    # 检查器基类
    "BaseChecker",
    "UnavailableChecker",
    
    # 注册表
    "CheckerRegistry",
    "get_initialized_registry",
    
    # 异常
    "ComplianceCheckerError",
    "ChecklistError",
    "DocumentParseError",
    "CheckExecutionError"
]
