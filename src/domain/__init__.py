"""
Domain 层（领域层）

包含业务逻辑实现，只依赖 Core 层的模型和 Protocol 接口。
"""

from .engine import DeclarativeCheckEngine, CheckTask, ExecutionResult

__all__ = ["DeclarativeCheckEngine", "CheckTask", "ExecutionResult"]
