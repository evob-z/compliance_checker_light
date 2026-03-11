"""
执行引擎模块

声明式检查引擎 - 根据清单配置自动执行检查
"""

from .declarative_engine import (
    DeclarativeCheckEngine,
    CheckTask,
    ExecutionResult
)

__all__ = [
    "DeclarativeCheckEngine",
    "CheckTask",
    "ExecutionResult"
]
