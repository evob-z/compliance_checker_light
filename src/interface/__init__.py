"""
Interface Layer - 接口层

负责 MCP 协议适配，参数转换。
不包含业务逻辑，只调用 Application 层。
"""

from .mcp_server import mcp, main, run_compliance_check

__all__ = ["mcp", "main", "run_compliance_check"]
