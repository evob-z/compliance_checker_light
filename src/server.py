"""
Compliance Checker Server 入口点

此文件作为包的入口点，实际的 MCP Server 实现在 interface/mcp_server.py
"""

from interface.mcp_server import main

if __name__ == "__main__":
    main()