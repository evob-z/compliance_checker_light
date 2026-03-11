"""
自定义异常类
"""


class ComplianceCheckerError(Exception):
    """合规检查器基础异常"""
    pass


class ChecklistError(ComplianceCheckerError):
    """清单相关错误"""
    pass


class DocumentParseError(ComplianceCheckerError):
    """文档解析错误"""
    pass


class CheckExecutionError(ComplianceCheckerError):
    """检查执行错误"""
    pass
