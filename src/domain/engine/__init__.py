"""
声明式检查引擎模块

根据清单声明自动执行检查，支持并行执行和优雅降级。
"""

from .declarative import DeclarativeCheckEngine, CheckTask, ExecutionResult

__all__ = ["DeclarativeCheckEngine", "CheckTask", "ExecutionResult"]
