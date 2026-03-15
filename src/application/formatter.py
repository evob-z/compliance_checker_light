"""
结果格式化模块

将检查结果转换为自然语言描述和可序列化的字典格式。
"""

from typing import List, Dict, Any

from ..core.checker_base import CheckStatus, CheckResult
from ..domain.engine.declarative import ExecutionResult


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

    if summary.get("unavailable", 0) > 0:
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
    if summary.get("failed", 0) == 0 and summary.get("errors", 0) == 0:
        lines.append("✅ 所有检查通过，未发现问题")

    return "\n".join(lines)


def _format_single_result(result: CheckResult) -> List[str]:
    """格式化单个检查结果"""
    lines = []

    check_type_display = {
        "completeness": "完整性",
        "timeliness": "时效性",
        "compliance": "合规性/视觉检查",
        "authenticity": "真实性",
        "cross_reference": "交叉核对",
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

    # 收集所有问题（PASS 和 VALID 状态视为通过，不视为问题）
    all_issues = []
    for doc_name, results in execution_result.document_results.items():
        for result in results:
            if result.status not in (CheckStatus.PASS, CheckStatus.VALID):
                all_issues.append(
                    {
                        "document": doc_name if doc_name != "__PROJECT_LEVEL__" else "项目级别",
                        "check_type": result.check_type,
                        "status": result.status.value,
                        "message": result.message,
                        "details": result.details,
                    }
                )

    return {
        "success": execution_result.success,
        "summary": {
            "total_checks": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "errors": summary.get("errors", 0),
            "unavailable": summary.get("unavailable", 0),
        },
        "issues_count": len(all_issues),
        "issues": all_issues,
        "messages": execution_result.messages,
        "execution_time": execution_result.execution_time,
    }


def format_issues_description(execution_result: ExecutionResult) -> str:
    """
    格式化为问题描述字符串

    生成大段的中文描述，适合直接展示给用户。

    Args:
        execution_result: 执行结果

    Returns:
        中文问题描述字符串
    """
    if execution_result.success:
        return "✅ 合规检查通过，所有必需文档齐全且符合要求。"

    lines = []

    # 添加摘要
    summary = execution_result.summary
    if summary.get("failed", 0) > 0:
        lines.append(f"发现 {summary.get('failed', 0)} 项问题需要处理：")
        lines.append("")

    # 按文档组织问题
    for doc_name, results in execution_result.document_results.items():
        issues = [r for r in results if r.status == CheckStatus.FAIL]

        if not issues:
            continue

        display_name = "项目整体" if doc_name == "__PROJECT_LEVEL__" else doc_name
        lines.append(f"【{display_name}】")

        for result in issues:
            check_type_map = {
                "completeness": "完整性检查",
                "timeliness": "时效性检查",
                "compliance": "合规性/视觉检查",
            }
            type_name = check_type_map.get(result.check_type, result.check_type)
            lines.append(f"  - {type_name}: {result.message}")

            if result.issues:
                for issue in result.issues:
                    if isinstance(issue, dict):
                        lines.append(f"    • {issue.get('description', str(issue))}")
                    else:
                        lines.append(f"    • {issue}")

        lines.append("")

    # 添加不可用功能提示
    if execution_result.unavailable_features:
        lines.append("⚠️ 以下功能暂不可用：")
        for feature in execution_result.unavailable_features:
            lines.append(f"  - {feature}")
        lines.append("")

    return "\n".join(lines)
