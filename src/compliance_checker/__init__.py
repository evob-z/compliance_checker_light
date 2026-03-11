"""Compliance Checker - 项目手续合规审查助手

基于 MCP 协议的自动化文档审核工具，支持：
- 资料完整性核对
- 资料时效性核对
- 基础合规性核对
- 视觉检测（印章/签名）
- PDF 报告生成
"""

__version__ = "0.1.0"
__author__ = "evob + claw"

# 延迟导入 server，避免在导入 __init__ 时就加载 fastmcp
def get_mcp():
    from .server import mcp
    return mcp

__all__ = ["get_mcp"]
