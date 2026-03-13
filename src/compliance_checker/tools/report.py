"""
report.py - 报告生成工具（已废弃）

PDF 生成功能已彻底移除，仅保留占位符模块。
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)
logger.debug("report.py 模块已废弃，PDF 生成功能已移除")


async def generate_report(*args, **kwargs) -> Dict[str, Any]:
    """
    已废弃：PDF 生成功能已移除

    此函数保留用于兼容性，但始终返回错误。
    """
    logger.error("PDF 生成功能已移除")
    return {"status": "error", "error": "PDF 生成功能已移除", "report_path": None, "pages": 0}


async def generate_html_report(*args, **kwargs) -> Dict[str, Any]:
    """
    已废弃：HTML 报告生成功能已移除

    此函数保留用于兼容性，但始终返回错误。
    """
    logger.error("HTML 报告生成功能已移除")
    return {"status": "error", "error": "HTML 报告生成功能已移除", "html": None}
