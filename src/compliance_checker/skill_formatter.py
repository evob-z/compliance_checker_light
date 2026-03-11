"""
Skill 结果格式化模块

将检查结果转换为自然语言描述
"""

from typing import List, Dict, Any
from datetime import datetime

from .core.checker_base import CheckResult
from .core.result_model import CheckStatus
from .engine.declarative_engine import ExecutionResult


def format_check_result(execution_result: ExecutionResult) -> str:
    """
    将执行结果格式化为可读文本
    
    Args:
        execution_result: 执行结果对象
    
    Returns:
        格式化的文本描述
    """
    lines = []
    
    # 总体摘要
    summary = execution_result.summary
    lines.append("=" * 50)
    lines.append("合规审查结果")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"检查总数: {summary.get('total', 0)}")
    lines.append(f"通过: {summary.get('passed', 0)} 项")
    lines.append(f"失败: {summary.get('failed', 0)} 项")
    lines.append(f"错误: {summary.get('errors', 0)} 项")
    
    if summary.get('unavailable', 0) > 0:
        lines.append(f"暂不可用: {summary.get('unavailable', 0)} 项")
    
    lines.append(f"执行时间: {execution_result.execution_time:.2f} 秒")
    lines.append("")
    
    # 如果有提示信息
    if execution_result.messages:
        lines.append("-" * 50)
        lines.append("提示信息")
        lines.append("-" * 50)
        for msg in execution_result.messages:
            lines.append(f"  • {msg}")
        lines.append("")
    
    # 按文档分组的问题
    doc_results = execution_result.document_results
    
    # 项目级别结果
    if "__PROJECT_LEVEL__" in doc_results:
        lines.append("-" * 50)
        lines.append("【项目级别检查】")
        lines.append("-" * 50)
        for result in doc_results["__PROJECT_LEVEL__"]:
            lines.extend(_format_single_result(result))
        lines.append("")
    
    # 文档级别结果
    for doc_name, results in doc_results.items():
        if doc_name == "__PROJECT_LEVEL__":
            continue
        
        # 显示所有非通过状态的检查结果（包括FAIL、ERROR、WARNING等）
        # VALID状态视为通过，不显示
        issues = [r for r in results if r.status not in (CheckStatus.PASS, CheckStatus.VALID)]
        if not issues:
            continue
        
        lines.append("-" * 50)
        lines.append(f"【文档: {doc_name}】")
        lines.append("-" * 50)
        
        for result in issues:
            lines.extend(_format_single_result(result))
        
        lines.append("")
    
    # 如果没有发现问题
    if summary.get('failed', 0) == 0 and summary.get('errors', 0) == 0:
        lines.append("✅ 所有检查通过，未发现问题")
    
    return "\n".join(lines)


def _format_single_result(result: CheckResult) -> List[str]:
    """格式化单个检查结果"""
    lines = []
    
    check_type_display = {
        "completeness": "完整性",
        "timeliness": "时效性",
        "compliance": "合规性",
        "visual": "视觉检查",
        "authenticity": "真实性",
        "cross_reference": "交叉核对"
    }
    
    type_name = check_type_display.get(result.check_type, result.check_type)
    
    # 状态图标
    if result.status == CheckStatus.PASS:
        icon = "✅"
    elif result.status == CheckStatus.FAIL:
        icon = "❌"
    elif result.status == CheckStatus.UNAVAILABLE:
        icon = "⚠️"
    else:
        icon = "💥"
    
    lines.append(f"  {icon} [{type_name}] {result.message}")
    
    # 详细信息
    if result.details:
        for key, value in result.details.items():
            if key == "document":
                continue  # 已在标题中显示
            if isinstance(value, list):
                lines.append(f"     - {key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"     - {key}: {value}")
    
    # 问题列表
    if result.issues:
        for issue in result.issues:
            if isinstance(issue, dict):
                issue_desc = issue.get("description", str(issue))
            else:
                issue_desc = str(issue)
            lines.append(f"     ⚡ {issue_desc}")
    
    return lines


def format_completeness_issues(results: List[CheckResult]) -> str:
    """
    格式化完整性问题
    
    Args:
        results: 完整性检查结果列表
    
    Returns:
        格式化的文本
    """
    lines = []
    lines.append("【完整性检查】")
    
    for result in results:
        if result.status == CheckStatus.PASS:
            continue
        
        details = result.details
        if "missing_documents" in details:
            lines.append("缺失文档:")
            for doc in details["missing_documents"]:
                lines.append(f"  - {doc}")
        
        if "matched_documents" in details:
            lines.append("已匹配文档:")
            for doc in details["matched_documents"]:
                lines.append(f"  ✓ {doc}")
    
    return "\n".join(lines) if len(lines) > 1 else ""


def format_timeliness_issues(results: List[CheckResult]) -> str:
    """
    格式化时效性问题
    
    Args:
        results: 时效性检查结果列表
    
    Returns:
        格式化的文本
    """
    lines = []
    lines.append("【时效性检查】")
    
    expired_docs = []
    unclear_docs = []
    
    for result in results:
        if result.status == CheckStatus.PASS:
            continue
        
        doc_name = result.details.get("document", "未知文档")
        
        if "expired" in result.message.lower() or result.status == CheckStatus.FAIL:
            expired_docs.append({
                "name": doc_name,
                "valid_to": result.details.get("valid_to", "未知"),
                "message": result.message
            })
        elif "unclear" in result.message.lower():
            unclear_docs.append({
                "name": doc_name,
                "message": result.message
            })
    
    if expired_docs:
        lines.append("已过期或即将过期:")
        for doc in expired_docs:
            lines.append(f"  ⚠️  {doc['name']}")
            lines.append(f"      有效期至: {doc['valid_to']}")
    
    if unclear_docs:
        lines.append("日期不明确:")
        for doc in unclear_docs:
            lines.append(f"  ❓ {doc['name']}: {doc['message']}")
    
    return "\n".join(lines) if len(lines) > 1 else ""


def format_compliance_issues(results: List[CheckResult]) -> str:
    """
    格式化合规性问题
    
    Args:
        results: 合规性检查结果列表
    
    Returns:
        格式化的文本
    """
    lines = []
    lines.append("【合规性检查】")
    
    for result in results:
        if result.status == CheckStatus.PASS:
            continue
        
        doc_name = result.details.get("document", "未知文档")
        lines.append(f"文档: {doc_name}")
        
        # 检查要点缺失
        if "missing_points" in result.details:
            lines.append("  缺失要素:")
            for point in result.details["missing_points"]:
                lines.append(f"    - {point}")
        
        # 检查结果详情
        if "checks" in result.details:
            for check in result.details["checks"]:
                point = check.get("point", "")
                found = check.get("found", False)
                status_icon = "✓" if found else "✗"
                lines.append(f"  {status_icon} {point}")
    
    return "\n".join(lines) if len(lines) > 1 else ""


def format_simple_result(execution_result: ExecutionResult) -> Dict[str, Any]:
    """
    格式化为简化的结果字典
    
    适用于返回给 AI 助手的结构化数据
    
    Args:
        execution_result: 执行结果
    
    Returns:
        简化的字典格式
    """
    summary = execution_result.summary
    
    # 收集所有问题
    all_issues = []
    for doc_name, results in execution_result.document_results.items():
        for result in results:
            if result.status != CheckStatus.PASS:
                all_issues.append({
                    "document": doc_name if doc_name != "__PROJECT_LEVEL__" else "项目级别",
                    "check_type": result.check_type,
                    "status": result.status.value,
                    "message": result.message,
                    "details": result.details
                })
    
    return {
        "success": execution_result.success,
        "summary": {
            "total_checks": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "errors": summary.get("errors", 0),
            "unavailable": summary.get("unavailable", 0)
        },
        "issues_count": len(all_issues),
        "issues": all_issues,
        "messages": execution_result.messages,
        "execution_time": execution_result.execution_time
    }
