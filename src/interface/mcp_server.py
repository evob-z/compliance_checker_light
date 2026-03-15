"""
Compliance Checker MCP Server
项目手续合规审查助手 - MCP Server 入口

遵循架构设计原则：
- 只依赖 Application 层的 ComplianceSkill
- 不直接引入 Domain 或 Infrastructure 层
- 职责：MCP 协议适配、参数转换、异常处理
"""

# 加载环境变量（外部启动时需要）
from dotenv import load_dotenv

load_dotenv()

import logging
from typing import Optional, Dict

from mcp.server.fastmcp import FastMCP

from ..application.skill import ComplianceSkill

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastMCP 实例
mcp = FastMCP("compliance-checker")

# 全局实例化 ComplianceSkill（Facade 模式）
skill = ComplianceSkill()


@mcp.tool(
    description="""项目手续合规审查工具 - 自动检查项目文档的完整性、时效性和合规性

【使用场景】
当用户需要审查项目手续文档是否齐全、有效、合规时调用此工具。典型场景包括：
- 建设工程项目开工前手续审查
- 环评项目文档完整性检查
- 施工许可证及相关文件审核
- 项目竣工验收文档检查
- 各类行政审批材料合规性审查

【工作流程】
1. 扫描指定文件夹中的所有支持文档（PDF、Word、图片）
2. 根据 requirements 自动生成检查清单
3. 执行多维度检查：
   - 完整性检查：必需文档是否齐全
   - 时效性检查：文件是否在有效期内
   - 合规性检查：内容是否符合规范
   - 视觉检查：公章、签字是否齐全
4. 返回详细的中文检查报告

【支持的文档格式】
- PDF 文件（.pdf）
- Word 文档（.docx, .doc）
- 图片文件（.png, .jpg, .jpeg）- 用于检查公章、签字

【requirements 编写指南】
requirements 是自然语言描述的检查要求，应包含以下要素：

1. 项目类型（必须）
   说明是什么类型的项目，例如："建设工程项目"、"环评项目"

2. 必需文档列表（必须）
   列出需要检查的所有文档名称，使用标准行政术语：
   - 立项批复（不是"立项文件"）
   - 环评批复
   - 施工许可证
   - 规划许可证
   - 竣工验收报告

3. 检查维度（可选但推荐）
   明确要检查哪些方面：
   - 公章：检查是否有单位公章
   - 有效期：检查文件是否在有效期内
   - 签字：检查签字是否齐全
   - 完整性：检查文档内容是否完整

【示例】

示例1 - 基础用法：
    project_path: "D:\\\\projects\\\\construction_2024"
    requirements: "审查建设工程项目，需要立项批复、环评批复、施工许可证"

示例2 - 完整用法（推荐）：
    project_path: "D:\\\\projects\\\\building_project"
    requirements: "审查建筑工程施工项目，需要立项批复、环评批复、施工许可证、规划许可证，检查公章和有效期"
    project_period: {"start": "2024-01", "end": "2026-12"}

示例3 - 详细描述：
    project_path: "/path/to/project"
    requirements: "审查一个工业园区建设项目，需要以下手续文件：1.项目立项批复 2.环境影响评价批复 3.建设用地规划许可证 4.建设工程规划许可证 5.建筑工程施工许可证 6.竣工验收备案表。检查所有文件是否有公章、是否在有效期内、签字是否齐全"

【参数说明】
    project_path: 项目手续文件夹的绝对路径，文件夹中应包含需要检查的文档
    requirements: 自然语言描述的检查要求（详见上述编写指南）
    project_period: 可选的项目周期，用于时效性检查。格式：{"start": "YYYY-MM", "end": "YYYY-MM"}

【返回结果】
返回中文格式的检查报告，包含：
- 检查统计（通过/失败/错误数量）
- 问题详情列表
- 执行耗时
"""
)
async def run_compliance_check(
    project_path: str,
    requirements: str,
    project_period: Optional[Dict[str, str]] = None,
) -> str:
    """
    执行项目合规检查

    通过自然语言描述检查要求，自动：
    1. 扫描项目文件夹中的文档
    2. 使用 LLM 生成检查清单
    3. 执行完整检查流程（完整性、时效性、合规性）
    4. 返回中文格式的检查结果

    Args:
        project_path: 项目手续文件夹路径（绝对路径）
            例如：D:\\projects\\construction_project
        requirements: 自然语言描述的检查要求
            例如："审查建设工程项目，需要立项批复、环评批复、施工许可证，检查公章和有效期"
            详细编写指南请参考工具 description
        project_period: 可选的项目周期
            格式：{"start": "YYYY-MM", "end": "YYYY-MM"}
            例如：{"start": "2025-01", "end": "2027-12"}
            用于检查文件是否在项目周期内有效

    Returns:
        中文格式的检查结果字符串，包含：
        - 检查统计（通过/失败/错误数量）
        - 问题详情列表
        - 执行耗时
        如发生错误，返回错误提示信息
    """
    try:
        # 调用 Application 层的 Facade 接口
        result = await skill.check(
            project_path=project_path,
            requirements=requirements,
            project_period=project_period,
        )

        # 格式化返回结果为友好的中文描述
        return _format_result(result)

    except FileNotFoundError as e:
        error_msg = f"❌ 路径错误：找不到指定的项目文件夹\n详细信息：{str(e)}"
        logger.error(error_msg)
        return error_msg

    except ValueError as e:
        error_msg = f"❌ 参数错误：输入参数不合法\n详细信息：{str(e)}"
        logger.error(error_msg)
        return error_msg

    except PermissionError as e:
        error_msg = f"❌ 权限错误：无法访问指定路径\n详细信息：{str(e)}"
        logger.error(error_msg)
        return error_msg

    except Exception as e:
        error_msg = f"❌ 执行错误：检查过程中发生异常\n异常类型：{type(e).__name__}\n详细信息：{str(e)}"
        logger.exception("合规检查执行失败")
        return error_msg


def _format_result(result: Dict) -> str:
    """
    将检查结果格式化为友好的中文描述

    Args:
        result: skill.check() 返回的结果字典

    Returns:
        格式化的中文结果字符串
    """
    lines = []

    # 检查是否成功
    success = result.get("success", False)

    if success:
        lines.append("✅ 合规检查完成")
    else:
        lines.append("⚠️ 合规检查完成（存在问题）")

    # 添加核心审查结论（分项结论）
    itemized_conclusions = result.get("itemized_conclusions", [])
    if itemized_conclusions:
        lines.append("")
        lines.append("✅ 核心审查结论：")
        for conclusion in itemized_conclusions:
            lines.append(f"- {conclusion}")

    # 添加统计摘要
    summary = result.get("summary", {})
    if summary:
        total = summary.get("total_checks", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        errors = summary.get("errors", 0)
        unavailable = summary.get("unavailable", 0)

        lines.append("")
        lines.append("📊 检查统计：")
        lines.append(f"  - 总检查项：{total}")
        lines.append(f"  - ✅ 通过：{passed}")
        lines.append(f"  - ❌ 失败：{failed}")
        lines.append(f"  - ⚠️ 错误：{errors}")
        lines.append(f"  - ⏸️ 不可用：{unavailable}")

    # 添加问题描述
    issues_description = result.get("issues_description", "")
    if issues_description:
        lines.append("")
        lines.append("📝 问题详情：")
        lines.append(issues_description)

    # 添加问题列表（简化版）
    issues = result.get("issues", [])
    if issues:
        lines.append("")
        lines.append("📋 问题列表：")
        for i, issue in enumerate(issues, 1):
            doc_name = issue.get("document", "未知文档")
            check_type = issue.get("check_type", "未知类型")
            message = issue.get("message", "")
            lines.append(f"  {i}. [{check_type}] {doc_name}：{message}")

    # 添加执行信息
    execution_time = result.get("execution_time")
    if execution_time is not None:
        lines.append("")
        lines.append(f"⏱️ 执行耗时：{execution_time:.2f} 秒")

    project_id = result.get("project_id")
    if project_id:
        lines.append(f"📌 项目标识：{project_id}")

    return "\n".join(lines)


# 启动入口
def main():
    """MCP Server 入口点"""
    logger.info("启动 Compliance Checker MCP Server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
