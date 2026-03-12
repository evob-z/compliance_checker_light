"""
Compliance Checker MCP Server
项目手续合规审查助手 - MCP Server 入口
"""

# 加载环境变量（Cherry Studio 等外部启动时需要）
from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Any, Optional

from compliance_checker.tools.checklist import load_checklist
from compliance_checker.tools.parser import parse_documents
from compliance_checker.tools.completeness import check_completeness
from compliance_checker.tools.timeliness import check_timeliness
from compliance_checker.tools.compliance import check_compliance
from compliance_checker.tools.visual import visual_inspection
from compliance_checker.core.document import Document
from compliance_checker.core.checklist_model import Checklist
from .config.settings import (
    get_default_similarity_threshold,
    get_default_use_semantic,
    get_default_use_visual,
)

# 创建 FastMCP 实例
mcp = FastMCP("compliance-checker")

# ==================== V2 新接口 ====================

@mcp.tool()
async def run_compliance_check(
    project_id: str,
    checklist_id: Optional[str] = None,
    checklist_yaml: Optional[str] = None,
    document_paths: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    max_concurrent: Optional[int] = None,
    enable_throttling: Optional[bool] = None,
    timeout: Optional[int] = None
) -> dict:
    """
    【高级接口】智能合规审查 - 需要预定义检查清单

    ⚠️ 注意：这是高级接口，需要了解检查清单格式。普通用户请使用 check_with_description 接口。

    使用场景：
    - 需要精确控制检查流程和参数
    - 已有预定义的 checklist_id 或 checklist_yaml
    - 需要指定具体的文档路径列表

    如需简单用法，请使用：check_with_description(project_path, requirements)

    Args:
        project_id: 项目唯一标识
        checklist_id: 清单配置ID（从 config/checklists/ 加载）
        checklist_yaml: 直接传入清单 YAML（与 checklist_id 二选一）
        document_paths: 文档绝对路径列表，None 则扫描默认路径
        output_dir: 报告输出目录，None 使用默认配置
        max_concurrent: 最大并行检查数，覆盖配置文件
        enable_throttling: 是否启用限流，覆盖配置文件
        timeout: 单个检查超时时间（秒），覆盖配置文件

    Returns:
        {
            "success": true/false,
            "summary": {
                "total": 15,
                "passed": 12,
                "failed": 2,
                "unavailable": 1
            },
            "messages": ["以下功能暂不支持..."],
            "execution_time": 12.5
        }
    """
    import time
    import yaml
    from .engine.declarative_engine import DeclarativeCheckEngine
    from .core.checker_registry import get_initialized_registry
    from .core.document import Document
    from .core.checklist_model import Checklist
    from .tools.parser import parse_documents
    from .tools.report import generate_report
    from .config.settings import get_concurrency_config, generate_output_path
    
    start_time = time.time()
    
    # 1. 加载清单
    if checklist_yaml:
        checklist_data = yaml.safe_load(checklist_yaml)
        checklist = Checklist.model_validate(checklist_data["checklist"])
    elif checklist_id:
        checklist_result = await load_checklist(checklist_id=checklist_id)
        checklist = Checklist.model_validate(checklist_result)
    else:
        checklist_result = await load_checklist(checklist_id="default")
        checklist = Checklist.model_validate(checklist_result)
    
    # 2. 解析文档
    if not document_paths:
        from .config.settings import scan_default_documents
        document_paths = scan_default_documents()
    
    parse_result = await parse_documents(document_paths)
    documents = [Document.model_validate(d) for d in parse_result["documents"]]
    
    if not documents:
        return {"success": False, "error": "没有成功解析任何文档"}
    
    # 3. 获取并发配置（用户参数覆盖配置文件）
    concurrency_config = get_concurrency_config()
    if max_concurrent is not None:
        concurrency_config["max_concurrent_checks"] = max_concurrent
    if enable_throttling is not None:
        concurrency_config["enable_throttling"] = enable_throttling
    if timeout is not None:
        concurrency_config["check_timeout"] = timeout
    
    # 4. 创建声明式引擎并执行
    registry = get_initialized_registry()
    engine = DeclarativeCheckEngine(
        registry=registry,
        concurrency_config=concurrency_config
    )
    
    execution_result = await engine.execute(documents, checklist)
    
    # 5. 生成报告
    if output_dir is None:
        output_path = generate_output_path(project_id)
    else:
        from pathlib import Path
        output_path = Path(output_dir) / f"compliance_report_{project_id}.pdf"
    
    report_result = await generate_report(
        project_id=project_id,
        check_results=execution_result.to_dict(),
        output_path=str(output_path),
        documents=[{"name": d.name, "path": d.path} for d in documents],
        unavailable_notices=execution_result.messages
    )
    
    return {
        "success": execution_result.success,
        "report_path": report_result.get("report_path"),
        "summary": execution_result.summary,
        "notices": execution_result.messages,
        "execution_time": time.time() - start_time,
        "document_count": len(documents)
    }


@mcp.tool()
async def list_available_checkers() -> dict:
    """
    列出所有可用和待开发的检查器
    
    Returns:
        {
            "available": ["completeness", "timeliness", ...],
            "all_status": {
                "completeness": "available",
                "authenticity": "not_implemented",
                ...
            }
        }
    """
    from .core.checker_registry import get_initialized_registry
    
    registry = get_initialized_registry()
    return {
        "available": registry.list_available(),
        "all_status": registry.list_all()
    }


@mcp.tool()
async def check_with_description(
    project_path: str,
    requirements: str,
    project_period: Optional[Dict[str, str]] = None
) -> dict:
    """
    自然语言合规审查（Skill 接口）
    
    通过自然语言描述检查要求，自动：
    1. 扫描文件夹中的文档
    2. 使用 LLM 生成检查清单
    3. 执行完整检查流程
    4. 返回文本格式的问题描述
    
    Args:
        project_path: 项目手续文件夹路径（绝对路径）
        requirements: 自然语言描述的检查要求
            例如："审查建设工程项目，需要立项批复、环评批复、施工许可证，检查公章和有效期"
        project_period: 可选的项目周期
            格式：{"start": "YYYY-MM", "end": "YYYY-MM"}
            例如：{"start": "2025-01", "end": "2027-12"}
    
    Returns:
        {
            "success": true/false,
            "summary": {
                "total_checks": 15,
                "passed": 12,
                "failed": 2,
                "errors": 0,
                "unavailable": 1
            },
            "issues_description": "文本格式的问题描述...",
            "issues_simple": [
                {"document": "立项批复", "check_type": "compliance", "message": "..."}
            ],
            "generated_checklist": {"checklist": {...}},  // 生成的清单
            "document_count": 5,
            "execution_time": 12.5,
            "project_id": "project_123"
        }
    
    Raises:
        通过返回值中的 success 和 error 字段返回错误信息
    """
    from .skill import ComplianceSkill
    
    try:
        skill = ComplianceSkill()
        result = await skill.check(
            project_path=project_path,
            requirements=requirements,
            project_period=project_period
        )
        return result
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"路径错误: {str(e)}",
            "error_type": "file_not_found"
        }
    except ValueError as e:
        return {
            "success": False,
            "error": f"输入错误: {str(e)}",
            "error_type": "value_error"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"执行错误: {str(e)}",
            "error_type": type(e).__name__
        }


async def validate_checklist(
    checklist_yaml: str
) -> dict:
    """
    验证清单 YAML 的合法性
    
    Args:
        checklist_yaml: 清单 YAML 字符串
    
    Returns:
        {
            "valid": true/false,
            "errors": ["错误1", ...],
            "warnings": ["警告1", ...]
        }
    """
    from .validators.checklist_validator import validate_checklist_yaml
    
    result = await validate_checklist_yaml(checklist_yaml)
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings
    }


async def get_checklist_generation_prompt(
    user_description: str,
    include_examples: bool = False
) -> dict:
    """
    获取清单生成 Prompt（用于外部 LLM）
    
    将用户的自然语言描述转换为 Prompt，供外部 LLM 生成清单 YAML。
    
    Args:
        user_description: 用户的自然语言描述，如"我要审查建设工程项目..."
        include_examples: 是否包含少样本示例
    
    Returns:
        {
            "prompt": "完整的 Prompt 字符串",
            "usage": "将此 prompt 发送给 LLM，获取 YAML 输出"
        }
    """
    if include_examples:
        from .prompts.checklist_generator import generate_checklist_prompt_with_examples
        prompt = generate_checklist_prompt_with_examples(user_description, num_examples=1)
    else:
        from .prompts.checklist_generator import generate_checklist_prompt
        prompt = generate_checklist_prompt(user_description)
    
    return {
        "prompt": prompt,
        "usage": "将此 prompt 发送给 LLM，获取 YAML 输出后可用 validate_checklist 验证"
    }


# ==================== V1 兼容接口 ====================


async def load_checklist_tool(
    checklist_id: Optional[str] = None,
    yaml_content: Optional[str] = None,
    yaml_file_path: Optional[str] = None,
    project_period: Optional[dict] = None
) -> dict:
    """
    加载审核清单配置。
    
    支持三种方式：
    1. 从配置文件加载：提供 checklist_id（如 "default" 会加载 default.yaml）
    2. 从 YAML 字符串加载：直接提供 yaml_content
    3. 从 YAML 文件路径加载：提供 yaml_file_path（绝对路径）
    
    优先级：yaml_file_path > yaml_content > checklist_id > 默认配置
    
    Args:
        checklist_id: 清单配置文件ID，从 config/checklists/ 目录加载
        yaml_content: 直接传入 YAML 内容字符串
        yaml_file_path: YAML 文件的绝对路径（优先级最高）
        project_period: 项目周期，格式 {"start": "2025-01", "end": "2027-12"}
    
    Returns:
        结构化清单对象，包含 checklist_id, project_period, required_documents 等
    """
    return await load_checklist(
        checklist_id=checklist_id,
        yaml_content=yaml_content,
        yaml_file_path=yaml_file_path,
        project_period=project_period
    )


async def parse_documents_tool(
    file_paths: Optional[List[str]] = None,
    extract_options: Optional[Dict[str, Any]] = None
) -> dict:
    """
    解析项目文档，提取文字和元数据。
    
    如果 file_paths 为空或未提供，将自动扫描默认文档路径
    （由配置 defaults.yaml 中的 default_document_path 指定）
    
    Args:
        file_paths: 文件绝对路径列表。如果为空，扫描默认路径
        extract_options: 提取选项
            - ocr: bool, 是否对扫描件使用OCR，默认True
            - metadata: bool, 是否提取元数据，默认True
    
    Returns:
        {
            "documents": [...],
            "errors": [...]
        }
    """
    # 如果 file_paths 为 None，使用空列表（会触发默认路径扫描）
    if file_paths is None:
        file_paths = []
    
    return await parse_documents(file_paths=file_paths, extract_options=extract_options)


async def check_completeness_tool(
    documents: List[Dict[str, Any]],
    checklist: Dict[str, Any],
    similarity_threshold: Optional[float] = None,
    use_semantic: Optional[bool] = None
) -> dict:
    """
    核对资料完整性。
    
    支持文件名语义匹配，使用 sentence-transformers 计算相似度。
    匹配逻辑：
    1. 优先按"文件名称"精准匹配（文件名包含清单名称或别名）
    2. 名称不匹配时，使用语义相似度计算
    3. 相似度 >= threshold 时，判定为匹配
    
    Args:
        documents: 已上传的文档列表，每个文档包含 name, path, content 等字段
        checklist: 审核清单，包含 required_documents 等字段
        similarity_threshold: 语义匹配阈值（默认从配置读取，一般为0.75）
        use_semantic: 是否使用语义匹配（默认从配置读取）
    
    Returns:
        {
            "status": "INCOMPLETE",
            "total_required": 10,
            "uploaded": 8,
            "missing": 2,
            "details": [...]
        }
    """
    # 使用配置默认值
    if similarity_threshold is None:
        similarity_threshold = get_default_similarity_threshold()
    if use_semantic is None:
        use_semantic = get_default_use_semantic()
    
    # 将字典转换为 Document 对象列表
    doc_objects = []
    for doc_data in documents:
        doc = Document(
            path=doc_data.get("path", doc_data.get("file_path", "")),
            name=doc_data.get("name", doc_data.get("file_name", "")),
            type=doc_data.get("type", "unknown"),
            pages=doc_data.get("pages", 1),
            pages_content=doc_data.get("pages_content", []),
            metadata=doc_data.get("metadata", {})
        )
        doc_objects.append(doc)
    
    # 将字典转换为 Checklist 对象
    checklist_obj = Checklist.model_validate(checklist)
    
    result = await check_completeness(
        documents=doc_objects,
        checklist=checklist_obj,
        similarity_threshold=similarity_threshold,
        use_semantic=use_semantic
    )
    
    return result.model_dump()


async def check_timeliness_tool(
    documents: List[Dict[str, Any]],
    project_period: Optional[Dict[str, str]] = None,
    checklist: Optional[Dict[str, Any]] = None,
    date_rules: Optional[List[Dict[str, Any]]] = None
) -> dict:
    """
    核对资料时效性。
    
    验证文件有效期是否覆盖项目周期，支持多种日期格式提取：
    - 2024年3月15日
    - 2024-03-15
    - 有效期至2026年5月
    - 签发日期：2024-01-15
    
    Args:
        documents: 文档列表，每个文档包含 name, path, content 等字段
        project_period: 项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}
        checklist: 审核清单（可选，用于获取有效期规则）
        date_rules: 自定义日期规则列表（可选）
    
    Returns:
        {
            "status": "HAS_ISSUES",
            "checked": 8,
            "valid": 6,
            "expired": 1,
            "unclear": 1,
            "details": [...]
        }
    """
    # 将字典转换为 Document 对象列表
    doc_objects = []
    for doc_data in documents:
        doc = Document(
            path=doc_data.get("path", doc_data.get("file_path", "")),
            name=doc_data.get("name", doc_data.get("file_name", "")),
            type=doc_data.get("type", "unknown"),
            pages=doc_data.get("pages", 1),
            pages_content=doc_data.get("pages_content", []),
            metadata=doc_data.get("metadata", {})
        )
        doc_objects.append(doc)
    
    # 转换 checklist
    checklist_obj = None
    if checklist:
        checklist_obj = Checklist.model_validate(checklist)
    
    result = await check_timeliness(
        documents=doc_objects,
        project_period=project_period,
        checklist=checklist_obj,
        date_rules=date_rules
    )
    
    return result.model_dump()


async def check_compliance_tool(
    documents: List[Dict[str, Any]],
    checklist: Optional[Dict[str, Any]] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
    use_visual: Optional[bool] = None
) -> dict:
    """
    基础合规性核对。
    
    识别公章、签字、文件编号等要素（文字层面检查）。
    检查项包括：
    - 公章：通过关键词检测
    - 签字：通过关键词检测
    - 文件编号：正则匹配验证
    - 日期：检查是否存在
    
    Args:
        documents: 文档列表，每个文档包含 name, path, content 等字段
        checklist: 审核清单（可选，用于获取合规要点）
        rules: 自定义合规规则列表（可选）
        use_visual: 是否启用视觉检查辅助（默认从配置读取）
    
    Returns:
        {
            "status": "HAS_ISSUES",
            "details": [
                {
                    "document_name": "立项批复",
                    "file_path": "/data/立项批复.pdf",
                    "checks": [
                        {"point": "公章", "found": true, "evidence": "..."},
                        {"point": "签字", "found": false, "status": "MISSING"}
                    ]
                }
            ]
        }
    """
    # 使用配置默认值
    if use_visual is None:
        use_visual = get_default_use_visual()
    
    # 将字典转换为 Document 对象列表
    doc_objects = []
    for doc_data in documents:
        doc = Document(
            path=doc_data.get("path", doc_data.get("file_path", "")),
            name=doc_data.get("name", doc_data.get("file_name", "")),
            type=doc_data.get("type", "unknown"),
            pages=doc_data.get("pages", 1),
            pages_content=doc_data.get("pages_content", []),
            metadata=doc_data.get("metadata", {})
        )
        doc_objects.append(doc)
    
    # 转换 checklist
    checklist_obj = None
    if checklist:
        checklist_obj = Checklist.model_validate(checklist)
    
    result = await check_compliance(
        documents=doc_objects,
        checklist=checklist_obj,
        rules=rules,
        use_visual=use_visual
    )
    
    return result.model_dump()


async def visual_inspection_tool(
    document_path: str,
    check_type: str = "both",
    search_context: Optional[str] = None,
    page_hint: Optional[int] = None
) -> dict:
    """
    视觉检查工具 - 检测文档中的印章/签名。
    
    使用 Qwen-VL 视觉模型进行两阶段检测：
    1. 如提供 search_context，先用 OCR 定位大概区域
    2. 截取相关区域图片，调用 Qwen-VL 判断印章/签名是否存在
    
    Args:
        document_path: 文档路径（PDF 文件）
        check_type: 检查类型 ("seal" | "signature" | "both")
            - seal: 仅检查公章
            - signature: 仅检查签名
            - both: 同时检查公章和签名（默认）
        search_context: OCR 定位的上下文文字（如"公章"、"法定代表人"）
            提供此参数可提高检测精度和速度
        page_hint: 建议查找的页码（从0开始），默认从第0页开始搜索
    
    Returns:
        {
            "document_path": "/data/立项批复.pdf",
            "check_type": "seal",
            "found": true,
            "confidence": 0.95,
            "location": {
                "page": 3,
                "bbox": [100, 200, 300, 400],
                "description": "右下角"
            },
            "screenshot_path": "/tmp/seal_123.png",
            "reasoning": "在页面右下角发现红色圆形印章，文字清晰可辨"
        }
    """
    result = await visual_inspection(
        document_path=document_path,
        check_type=check_type,
        search_context=search_context,
        page_hint=page_hint
    )
    return result


async def generate_report_tool(
    project_id: str,
    check_results: Dict[str, Any],
    output_path: Optional[str] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
    template: str = "default",
    include_screenshots: Optional[bool] = None
) -> dict:
    """
    生成合规审查报告（已废弃）。
    
    PDF 生成功能已移除，此工具保留用于兼容性。
    请使用 check_with_description 工具获取文本格式的检查结果。
    
    Args:
        project_id: 项目ID
        check_results: 所有检查结果汇总
        output_path: 已废弃
        documents: 已废弃
        template: 已废弃
        include_screenshots: 已废弃
    
    Returns:
        {
            "status": "error",
            "error": "PDF 生成功能已移除"
        }
    """
    return {
        "status": "error",
        "error": "PDF 生成功能已移除，请使用 check_with_description 工具获取文本格式的检查结果"
    }



# 启动入口
def main():
    """MCP Server entry point"""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
