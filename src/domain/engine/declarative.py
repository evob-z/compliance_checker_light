"""
声明式检查引擎

根据清单声明自动执行检查，支持并行执行和优雅降级。

架构说明：
- 此引擎属于 Domain 层，只依赖 Core 层的类型
- 通过构造函数注入 CheckerRegistry，实现依赖倒置
- 严禁引入 Infrastructure 层
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from ...core.checker_base import BaseChecker, CheckResult, CheckStatus, UnavailableChecker
from ...core.checker_registry import CheckerRegistry
from ...core.document import Document
from ...core.checklist_model import Checklist, RequiredDocument

logger = logging.getLogger(__name__)


@dataclass
class CheckTask:
    """
    单个检查任务

    封装一次检查执行所需的全部信息。

    Attributes:
        doc_name: 文档名称（项目级别检查使用特殊标记）
        doc_type: 文档类型（对应清单中的 name）
        check_type: 检查类型（completeness/timeliness/compliance/visual）
        documents: 涉及的文档列表（某些检查需要多文档）
        config: 检查配置（来自清单的 checks 配置）
        required: 是否必需（非必需检查失败不阻断流程）
    """

    doc_name: str
    doc_type: str
    check_type: str
    documents: List[Document]
    config: Dict[str, Any]
    required: bool = True

    # 项目级别检查的特殊标记
    PROJECT_LEVEL_MARKER = "__PROJECT_LEVEL__"

    def is_project_level(self) -> bool:
        """判断是否为项目级别检查"""
        return self.doc_name == self.PROJECT_LEVEL_MARKER


@dataclass
class ExecutionResult:
    """
    执行结果汇总

    聚合所有检查任务的结果，提供统一的输出格式。

    Attributes:
        success: 整体是否成功（必需检查全部通过）
        summary: 各状态统计
        document_results: 按文档分组的检查结果
        messages: 提示信息列表
        unavailable_features: 不可用功能列表
        execution_time: 执行耗时（秒）
    """

    success: bool
    summary: Dict[str, int]
    document_results: Dict[str, List[CheckResult]]
    messages: List[str]
    unavailable_features: List[str]
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于报告生成"""
        return {
            "success": self.success,
            "summary": self.summary,
            "document_results": {
                k: [r.to_dict() for r in v] for k, v in self.document_results.items()
            },
            "messages": self.messages,
            "unavailable_features": self.unavailable_features,
            "execution_time": self.execution_time,
        }


class DeclarativeCheckEngine:
    """
    声明式检查引擎

    核心职责：
    1. 解析清单，提取每个文档需要执行的检查
    2. 从 CheckerRegistry 获取对应的检查器
    3. 并行执行所有检查任务
    4. 汇总结果（含未实现功能提示）

    架构约束：
    - 只依赖 Core 层的类型
    - 通过构造函数注入 CheckerRegistry
    - 严禁引入 Infrastructure 层
    """

    def __init__(
        self,
        registry: CheckerRegistry,
        concurrency_config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化引擎

        Args:
            registry: Core 层的 CheckerRegistry 实例（必需，依赖注入）
            concurrency_config: 并发配置，包含：
                - max_concurrent_checks: 最大并发数，默认 5
                - check_timeout: 单个检查超时时间（秒），默认 300
        """
        if registry is None:
            raise ValueError("registry 不能为 None，必须传入 CheckerRegistry 实例")

        self.registry = registry
        self.concurrency_config = concurrency_config or {
            "max_concurrent_checks": 5,
            "check_timeout": 300,
        }

    async def execute(
        self,
        documents: List[Document],
        checklist: Checklist,
    ) -> ExecutionResult:
        """
        执行声明式检查流程

        Args:
            documents: 已解析的文档列表
            checklist: 审核清单

        Returns:
            ExecutionResult: 执行结果汇总
        """
        start_time = asyncio.get_event_loop().time()

        # 步骤1：构建检查计划
        logger.info("步骤1: 构建检查计划...")
        check_plan = self._build_check_plan(documents, checklist)
        logger.info(f"计划执行 {len(check_plan)} 个检查任务")

        # 步骤2：并行执行所有检查
        logger.info("步骤2: 并行执行检查...")
        results = await self._execute_parallel(check_plan, checklist)

        # 步骤3：汇总结果
        logger.info("步骤3: 汇总结果...")
        execution_result = self._aggregate_results(results, check_plan)
        execution_result.execution_time = asyncio.get_event_loop().time() - start_time

        return execution_result

    def _build_check_plan(
        self,
        documents: List[Document],
        checklist: Checklist,
    ) -> List[CheckTask]:
        """
        根据清单构建检查计划

        解析清单中每个文档的 checks 配置，生成任务列表。

        检查类型分类：
        - 项目级别（completeness）：只创建一次任务，传入所有文档
        - 文档级别（timeliness/compliance/visual）：为每个文档创建任务

        Args:
            documents: 文档列表
            checklist: 审核清单

        Returns:
            检查任务列表
        """
        tasks: List[CheckTask] = []

        # 收集所有需要的检查类型和文档-检查映射
        all_check_types: set = set()
        doc_checks_map: Dict[str, Dict[str, Any]] = {}

        for doc in documents:
            # 匹配文档对应的清单项
            matched_item = self._match_document_to_checklist(doc, checklist)
            if not matched_item:
                logger.warning(f"文档 '{doc.name}' 未匹配到清单项")
                continue

            # 解析该文档需要执行的检查
            checks_config = matched_item.checks

            # 如果没有显式配置 checks，使用默认检查
            if not checks_config:
                checks_config = self._get_default_checks()

            doc_checks_map[doc.name] = {
                "doc": doc,
                "doc_type": matched_item.name,
                "checks": checks_config,
            }

            for check_config in checks_config:
                all_check_types.add(check_config.type)

        # 处理项目级别的检查（completeness）
        if "completeness" in all_check_types:
            completeness_task = self._create_project_level_task(
                doc_checks_map, checklist
            )
            if completeness_task:
                tasks.append(completeness_task)

        # 处理文档级别的检查（timeliness, compliance, visual 等）
        for doc_name, info in doc_checks_map.items():
            doc = info["doc"]
            doc_type = info["doc_type"]

            for check_config in info["checks"]:
                check_type = check_config.type

                # 跳过项目级别的检查
                if check_type == "completeness":
                    continue

                tasks.append(
                    CheckTask(
                        doc_name=doc.name,
                        doc_type=doc_type,
                        check_type=check_type,
                        documents=[doc],  # 文档级别检查只传一个文档
                        config=check_config.model_dump(),
                        required=check_config.required,
                    )
                )

        return tasks

    def _get_default_checks(self) -> List[Any]:
        """获取默认检查配置（当清单未显式配置时使用）"""
        from ...core.checklist_model import DocumentCheck

        return [
            DocumentCheck(type="completeness", required=True),
            DocumentCheck(type="timeliness", required=True),
            DocumentCheck(type="compliance", required=True),
        ]

    def _create_project_level_task(
        self,
        doc_checks_map: Dict[str, Dict[str, Any]],
        checklist: Checklist,
    ) -> Optional[CheckTask]:
        """
        创建项目级别检查任务

        项目级别检查（如 completeness）需要传入所有文档。

        Args:
            doc_checks_map: 文档-检查映射
            checklist: 审核清单

        Returns:
            项目级别检查任务，或 None（如果无需执行）
        """
        # 找到 completeness 的配置
        comp_config = None
        required = True

        for doc_name, info in doc_checks_map.items():
            for check in info["checks"]:
                if check.type == "completeness":
                    comp_config = check
                    required = check.required
                    break
            if comp_config:
                break

        if not comp_config:
            return None

        # 项目级别检查：传入所有文档
        all_docs = [info["doc"] for info in doc_checks_map.values()]

        return CheckTask(
            doc_name=CheckTask.PROJECT_LEVEL_MARKER,
            doc_type="project",
            check_type="completeness",
            documents=all_docs,
            config=comp_config.model_dump(),
            required=required,
        )

    def _match_document_to_checklist(
        self,
        doc: Document,
        checklist: Checklist,
    ) -> Optional[RequiredDocument]:
        """
        匹配文档到清单项

        匹配规则：
        1. 文件名包含文档标准名称
        2. 文件名包含任何别名

        Args:
            doc: 文档对象
            checklist: 审核清单

        Returns:
            匹配的必需文档定义，或 None（未匹配）
        """
        # 边界情况处理：检查文档名称是否有效
        if not doc or not doc.name:
            logger.warning("文档名称为空，无法匹配")
            return None

        doc_name_lower = doc.name.lower()

        for req_doc in checklist.required_documents:
            # 边界情况：检查必需文档定义是否有效
            if not req_doc or not req_doc.name:
                logger.warning("清单中存在无效的文档定义（名称为空）")
                continue

            # 检查标准名称
            if req_doc.name.lower() in doc_name_lower:
                return req_doc

            # 检查别名
            if req_doc.aliases:
                for alias in req_doc.aliases:
                    if alias and alias.lower() in doc_name_lower:
                        return req_doc

        return None

    async def _execute_parallel(
        self,
        check_plan: List[CheckTask],
        checklist: Checklist,
    ) -> List[Tuple[CheckTask, CheckResult]]:
        """
        并行执行所有检查任务

        使用信号量控制并发数，支持超时和异常处理。

        Args:
            check_plan: 检查任务列表
            checklist: 审核清单

        Returns:
            任务-结果元组列表
        """
        # 获取并发配置
        max_concurrent = self.concurrency_config.get("max_concurrent_checks", 5)
        timeout = self.concurrency_config.get("check_timeout", 300)

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_single(task: CheckTask) -> Tuple[CheckTask, CheckResult]:
            """执行单个任务"""
            # 获取检查器（可能是真实检查器，也可能是 UnavailableChecker）
            checker = self.registry.get(task.check_type)

            # 如果是 UnavailableChecker，直接执行
            if isinstance(checker, UnavailableChecker):
                try:
                    result = await checker.check(task.documents, checklist, task.config)
                except Exception as e:
                    logger.exception(f"UnavailableChecker 执行异常: {task.check_type}")
                    result = CheckResult(
                        check_type=task.check_type,
                        status=CheckStatus.UNAVAILABLE,
                        message=f"功能 '{task.check_type}' 暂不可用: {str(e)}",
                        details={
                            "document": task.doc_name,
                            "contact": "项目负责人",
                            "status": "开发中",
                        },
                    )
                return task, result

            try:
                # 验证配置
                valid, error_msg = checker.validate_config(task.config)
                if not valid:
                    result = CheckResult(
                        check_type=task.check_type,
                        status=CheckStatus.ERROR,
                        message=f"配置错误: {error_msg}",
                        details={"document": task.doc_name},
                    )
                else:
                    # 执行检查
                    result = await checker.check(task.documents, checklist, task.config)
            except Exception as e:
                logger.exception(f"检查执行异常: {task.check_type} on {task.doc_name}")
                result = CheckResult(
                    check_type=task.check_type,
                    status=CheckStatus.ERROR,
                    message=f"执行异常: {str(e)}",
                    details={"document": task.doc_name},
                )

            return task, result

        async def run_with_limit(task: CheckTask) -> Tuple[CheckTask, CheckResult]:
            """在信号量控制下执行"""
            async with semaphore:
                try:
                    return await asyncio.wait_for(run_single(task), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.error(f"检查超时: {task.check_type} on {task.doc_name}")
                    return task, CheckResult(
                        check_type=task.check_type,
                        status=CheckStatus.ERROR,
                        message=f"检查超时（超过{timeout}秒）",
                        details={"timeout": timeout, "document": task.doc_name},
                    )
                except Exception as e:
                    # 捕获所有其他异常，确保信号量正确释放
                    logger.exception(f"检查执行失败: {task.check_type} on {task.doc_name}: {e}")
                    return task, CheckResult(
                        check_type=task.check_type,
                        status=CheckStatus.ERROR,
                        message=f"检查执行失败: {str(e)}",
                        details={
                            "document": task.doc_name,
                            "error_type": type(e).__name__,
                        },
                    )

        # 并行执行所有任务
        tasks = [run_with_limit(plan) for plan in check_plan]
        return await asyncio.gather(*tasks)

    def _aggregate_results(
        self,
        results: List[Tuple[CheckTask, CheckResult]],
        plan: List[CheckTask],
    ) -> ExecutionResult:
        """
        汇总所有检查结果

        统计各状态数量，按文档分组结果，生成提示信息。

        Args:
            results: 任务-结果元组列表
            plan: 原始检查计划

        Returns:
            汇总后的执行结果
        """
        summary = {
            "total": len(results),
            "passed": 0,
            "failed": 0,
            "unavailable": 0,
            "errors": 0,
        }

        grouped_by_doc: Dict[str, List[CheckResult]] = {}
        project_level_results: List[CheckResult] = []
        unavailable_features: set = set()
        messages: List[str] = []
        has_blocking_error = False

        for task, result in results:
            # 统计各状态
            if result.status == CheckStatus.PASS:
                summary["passed"] += 1
            elif result.status == CheckStatus.FAIL:
                summary["failed"] += 1
                if task.required:
                    has_blocking_error = True
            elif result.status == CheckStatus.UNAVAILABLE:
                summary["unavailable"] += 1
                unavailable_features.add(task.check_type)
            else:
                summary["errors"] += 1
                if task.required:
                    has_blocking_error = True

            # 区分项目级别和文档级别结果
            if task.is_project_level():
                project_level_results.append(result)
            else:
                # 按文档分组
                key = task.doc_name
                if key not in grouped_by_doc:
                    grouped_by_doc[key] = []
                grouped_by_doc[key].append(result)

        # 将项目级别结果也加入分组（使用特殊键）
        if project_level_results:
            grouped_by_doc[CheckTask.PROJECT_LEVEL_MARKER] = project_level_results

        # 生成提示信息
        if unavailable_features:
            feature_list = ", ".join(sorted(unavailable_features))
            messages.append(f"以下功能暂不支持，请联系项目负责人：{feature_list}")

        # 判断总体是否成功
        # 注意：unavailable 不阻断流程，只有 required 检查失败才阻断
        success = not has_blocking_error

        return ExecutionResult(
            success=success,
            summary=summary,
            document_results=grouped_by_doc,
            messages=messages,
            unavailable_features=list(unavailable_features),
            execution_time=0.0,  # 由调用方填充
        )
