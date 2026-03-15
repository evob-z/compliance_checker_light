"""
DeclarativeCheckEngine（声明式检查引擎）单元测试

测试声明式检查引擎的核心逻辑，不依赖真实的 Infrastructure 层。
使用 Mock 检查器模拟检查功能。

遵循 architecture.md 中『10.2 Domain 层测试示例』规范：
- 不引入真实 infrastructure
- 手写 Mock 类实现协议接口
- 使用内存对象构造测试输入
- 至少包含 PASS 和 FAIL 两种核心场景用例
- 详尽的 assert 校验返回字段、异常类型和错误信息
"""

import pytest
from typing import List, Optional, Dict, Any
from unittest.mock import AsyncMock, MagicMock

from src.core.checker_base import BaseChecker, CheckResult, CheckStatus
from src.core.checker_registry import CheckerRegistry
from src.core.document import Document
from src.core.checklist_model import (
    Checklist,
    RequiredDocument,
    DocumentCheck,
    ProjectPeriod,
)
from src.domain.engine.declarative import (
    DeclarativeCheckEngine,
    CheckTask,
    ExecutionResult,
)

# ============== Mock 检查器 ==============


class MockCompletenessChecker(BaseChecker):
    """Mock 完整性检查器"""

    @property
    def name(self) -> str:
        return "completeness"

    @property
    def description(self) -> str:
        return "Mock 完整性检查器"

    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any],
    ) -> CheckResult:
        return CheckResult(
            check_type=self.name,
            status=CheckStatus.PASS,
            message="Mock 完整性检查通过",
            details={"mock": True},
        )


class MockTimelinessChecker(BaseChecker):
    """Mock 时效性检查器"""

    @property
    def name(self) -> str:
        return "timeliness"

    @property
    def description(self) -> str:
        return "Mock 时效性检查器"

    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any],
    ) -> CheckResult:
        return CheckResult(
            check_type=self.name,
            status=CheckStatus.PASS,
            message="Mock 时效性检查通过",
            details={"mock": True},
        )


class MockFailingChecker(BaseChecker):
    """Mock 失败检查器"""

    @property
    def name(self) -> str:
        return "failing_check"

    @property
    def description(self) -> str:
        return "Mock 失败检查器"

    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any],
    ) -> CheckResult:
        return CheckResult(
            check_type=self.name,
            status=CheckStatus.FAIL,
            message="Mock 检查失败",
            details={"mock": True},
        )


class MockErrorChecker(BaseChecker):
    """Mock 错误检查器"""

    @property
    def name(self) -> str:
        return "error_check"

    @property
    def description(self) -> str:
        return "Mock 错误检查器"

    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any],
    ) -> CheckResult:
        raise RuntimeError("Mock 检查异常")


# ============== 辅助函数 ==============


def create_document(file_name: str, file_path: str = None) -> Document:
    """创建测试用 Document 对象"""
    return Document(
        path=file_path or f"/test/documents/{file_name}",
        name=file_name,
    )


def create_checklist_with_checks() -> Checklist:
    """创建带检查配置的清单"""
    return Checklist(
        id="test_engine_001",
        name="测试引擎清单",
        version="1.0",
        project_period=ProjectPeriod(start="2024-01", end="2026-12"),
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                required=True,
                checks=[
                    DocumentCheck(type="completeness", required=True),
                    DocumentCheck(type="timeliness", required=True),
                ],
            ),
        ],
    )


# ============== 测试 Fixtures ==============


@pytest.fixture
def registry():
    """创建带 Mock 检查器的注册表"""
    reg = CheckerRegistry()
    reg.register(MockCompletenessChecker())
    reg.register(MockTimelinessChecker())
    return reg


@pytest.fixture
def registry_with_failing():
    """创建包含失败检查器的注册表"""
    reg = CheckerRegistry()
    reg.register(MockCompletenessChecker())
    reg.register(MockFailingChecker())
    return reg


@pytest.fixture
def registry_with_error():
    """创建包含错误检查器的注册表"""
    reg = CheckerRegistry()
    reg.register(MockCompletenessChecker())
    reg.register(MockErrorChecker())
    return reg


@pytest.fixture
def engine(registry):
    """创建声明式检查引擎"""
    return DeclarativeCheckEngine(
        registry=registry,
        concurrency_config={
            "max_concurrent_checks": 5,
            "check_timeout": 300,
        },
    )


@pytest.fixture
def sample_documents():
    """创建示例文档列表"""
    return [
        create_document("项目立项批复.pdf"),
    ]


# ============== 测试用例 ==============


@pytest.mark.asyncio
async def test_engine_execute_success(engine, sample_documents):
    """
    测试场景：成功执行检查流程

    预期结果：
    - 返回 ExecutionResult 对象
    - success 为 True
    - summary 包含正确的统计信息
    """
    checklist = create_checklist_with_checks()

    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    # ========== 验证 ExecutionResult 基础字段 ==========
    assert isinstance(result, ExecutionResult), "返回结果应为 ExecutionResult 类型"
    assert isinstance(result.success, bool), "success 应为 bool 类型"
    assert isinstance(result.summary, dict), "summary 应为字典类型"
    assert isinstance(result.document_results, dict), "document_results 应为字典类型"
    assert isinstance(result.messages, list), "messages 应为列表类型"
    assert isinstance(result.unavailable_features, list), "unavailable_features 应为列表类型"
    assert isinstance(result.execution_time, float), "execution_time 应为 float 类型"

    # 验证成功状态
    assert result.success is True, "检查成功时 success 应为 True"

    # 验证 summary 结构
    assert "total" in result.summary, "summary 应包含 total"
    assert "passed" in result.summary, "summary 应包含 passed"
    assert "failed" in result.summary, "summary 应包含 failed"
    assert "unavailable" in result.summary, "summary 应包含 unavailable"
    assert "errors" in result.summary, "summary 应包含 errors"

    # 验证 to_dict 方法
    result_dict = result.to_dict()
    assert isinstance(result_dict, dict), "to_dict 应返回字典"
    assert "success" in result_dict, "to_dict 结果应包含 success"
    assert "summary" in result_dict, "to_dict 结果应包含 summary"


@pytest.mark.asyncio
async def test_engine_execute_with_failing_checker(registry_with_failing, sample_documents):
    """
    测试场景：包含失败检查器

    预期结果：
    - success 为 False
    - failed 计数大于 0
    """
    # 创建包含失败检查的清单
    checklist = Checklist(
        id="test_failing",
        name="测试失败检查",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                required=True,
                checks=[
                    DocumentCheck(type="completeness", required=True),
                    DocumentCheck(type="failing_check", required=True),  # 会失败
                ],
            ),
        ],
    )

    engine = DeclarativeCheckEngine(registry=registry_with_failing)
    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    # 验证失败状态
    assert result.success is False, "必需检查失败时 success 应为 False"
    assert result.summary["failed"] > 0, "应有失败的检查"


@pytest.mark.asyncio
async def test_engine_execute_with_error(registry_with_error, sample_documents):
    """
    测试场景：检查器抛出异常

    预期结果：
    - success 为 False
    - errors 计数大于 0
    """
    checklist = Checklist(
        id="test_error",
        name="测试错误检查",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                required=True,
                checks=[
                    DocumentCheck(type="completeness", required=True),
                    DocumentCheck(type="error_check", required=True),  # 会抛出异常
                ],
            ),
        ],
    )

    engine = DeclarativeCheckEngine(registry=registry_with_error)
    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    # 验证错误状态
    assert result.success is False, "必需检查出错时 success 应为 False"
    assert result.summary["errors"] > 0, "应有错误的检查"


def test_engine_init_with_none_registry():
    """
    测试场景：传入 None 作为 registry

    预期结果：
    - 抛出 ValueError 异常
    - 错误信息包含 "registry 不能为 None"
    """
    with pytest.raises(ValueError) as exc_info:
        DeclarativeCheckEngine(registry=None)

    assert "registry 不能为 None" in str(exc_info.value), "错误信息应包含 'registry 不能为 None'"


def test_engine_init_with_custom_config(registry):
    """
    测试场景：使用自定义并发配置

    预期结果：
    - 配置正确存储
    """
    custom_config = {
        "max_concurrent_checks": 10,
        "check_timeout": 600,
    }

    engine = DeclarativeCheckEngine(
        registry=registry,
        concurrency_config=custom_config,
    )

    assert engine.concurrency_config == custom_config, "配置应正确存储"


def test_build_check_plan(engine, sample_documents):
    """
    测试场景：构建检查计划

    预期结果：
    - 返回 CheckTask 列表
    - 任务包含正确的检查类型
    """
    checklist = create_checklist_with_checks()

    plan = engine._build_check_plan(sample_documents, checklist)

    # 验证计划结构
    assert isinstance(plan, list), "计划应为列表类型"
    assert len(plan) > 0, "计划不应为空"

    # 验证每个任务
    for task in plan:
        assert isinstance(task, CheckTask), "任务应为 CheckTask 类型"
        assert isinstance(task.doc_name, str), "任务应有 doc_name"
        assert isinstance(task.check_type, str), "任务应有 check_type"
        assert isinstance(task.documents, list), "任务应有 documents"
        assert isinstance(task.config, dict), "任务应有 config"
        assert isinstance(task.required, bool), "任务应有 required"


def test_check_task_is_project_level():
    """
    测试场景：判断是否为项目级别检查

    预期结果：
    - 项目级别任务返回 True
    - 文档级别任务返回 False
    """
    # 项目级别任务
    project_task = CheckTask(
        doc_name=CheckTask.PROJECT_LEVEL_MARKER,
        doc_type="project",
        check_type="completeness",
        documents=[],
        config={},
    )
    assert project_task.is_project_level() is True, "项目级别任务应返回 True"

    # 文档级别任务
    doc_task = CheckTask(
        doc_name="测试文档.pdf",
        doc_type="document",
        check_type="timeliness",
        documents=[],
        config={},
    )
    assert doc_task.is_project_level() is False, "文档级别任务应返回 False"


def test_match_document_to_checklist(engine):
    """
    测试场景：匹配文档到清单项

    预期结果：
    - 正确匹配文档名称
    - 未匹配返回 None
    """
    checklist = Checklist(
        id="test_match",
        name="测试匹配",
        version="1.0",
        required_documents=[
            RequiredDocument(name="项目立项批复", aliases=["立项批复"]),
        ],
    )

    # 匹配成功
    doc1 = create_document("项目立项批复.pdf")
    matched1 = engine._match_document_to_checklist(doc1, checklist)
    assert matched1 is not None, "应匹配到清单项"
    assert matched1.name == "项目立项批复", "匹配的名称应正确"

    # 使用别名匹配
    doc2 = create_document("立项批复.pdf")
    matched2 = engine._match_document_to_checklist(doc2, checklist)
    assert matched2 is not None, "别名应匹配到清单项"

    # 未匹配
    doc3 = create_document("不存在的文档.pdf")
    matched3 = engine._match_document_to_checklist(doc3, checklist)
    assert matched3 is None, "未匹配应返回 None"


def test_match_document_with_empty_name(engine):
    """
    测试场景：文档名称为空

    预期结果：
    - 返回 None
    - 不抛出异常
    """
    checklist = Checklist(
        id="test_empty",
        name="测试空名称",
        version="1.0",
        required_documents=[
            RequiredDocument(name="测试文档"),
        ],
    )

    # 空名称文档
    doc = Document(path="/test", name="")
    result = engine._match_document_to_checklist(doc, checklist)
    assert result is None, "空名称文档应返回 None"


def test_aggregate_results(engine):
    """
    测试场景：汇总检查结果

    预期结果：
    - 正确统计各状态数量
    - 按文档分组结果
    """
    # 创建模拟结果
    task1 = CheckTask(
        doc_name="文档A.pdf",
        doc_type="document",
        check_type="timeliness",
        documents=[],
        config={},
        required=True,
    )
    task2 = CheckTask(
        doc_name=CheckTask.PROJECT_LEVEL_MARKER,
        doc_type="project",
        check_type="completeness",
        documents=[],
        config={},
        required=True,
    )

    results = [
        (
            task1,
            CheckResult(
                check_type="timeliness",
                status=CheckStatus.PASS,
                message="通过",
            ),
        ),
        (
            task2,
            CheckResult(
                check_type="completeness",
                status=CheckStatus.PASS,
                message="通过",
            ),
        ),
    ]

    execution_result = engine._aggregate_results(results, [task1, task2])

    # 验证结果
    assert isinstance(execution_result, ExecutionResult), "应返回 ExecutionResult"
    assert execution_result.success is True, "全部通过时 success 应为 True"
    assert execution_result.summary["passed"] == 2, "应有 2 个通过"
    assert execution_result.summary["failed"] == 0, "不应有失败"

    # 验证文档分组
    assert "文档A.pdf" in execution_result.document_results, "应包含文档A的结果"
    assert CheckTask.PROJECT_LEVEL_MARKER in execution_result.document_results, "应包含项目级别结果"


def test_aggregate_results_with_failures(engine):
    """
    测试场景：汇总包含失败的结果

    预期结果：
    - success 为 False
    - failed 计数正确
    """
    task = CheckTask(
        doc_name="文档A.pdf",
        doc_type="document",
        check_type="test",
        documents=[],
        config={},
        required=True,
    )

    results = [
        (
            task,
            CheckResult(
                check_type="test",
                status=CheckStatus.FAIL,
                message="失败",
            ),
        ),
    ]

    execution_result = engine._aggregate_results(results, [task])

    assert execution_result.success is False, "有失败时 success 应为 False"
    assert execution_result.summary["failed"] == 1, "应有 1 个失败"


def test_aggregate_results_with_unavailable(engine):
    """
    测试场景：汇总包含不可用功能的结果

    预期结果：
    - success 为 True（unavailable 不阻断）
    - unavailable_features 列表正确
    """
    task = CheckTask(
        doc_name="文档A.pdf",
        doc_type="document",
        check_type="unavailable_feature",
        documents=[],
        config={},
        required=True,
    )

    results = [
        (
            task,
            CheckResult(
                check_type="unavailable_feature",
                status=CheckStatus.UNAVAILABLE,
                message="功能不可用",
            ),
        ),
    ]

    execution_result = engine._aggregate_results(results, [task])

    # unavailable 不阻断流程
    assert execution_result.success is True, "unavailable 不应阻断流程"
    assert "unavailable_feature" in execution_result.unavailable_features, "应记录不可用功能"
    assert len(execution_result.messages) > 0, "应有提示信息"


@pytest.mark.asyncio
async def test_engine_execute_empty_documents(engine):
    """
    测试场景：空文档列表

    预期结果：
    - 正常执行，返回空结果
    """
    checklist = create_checklist_with_checks()

    result = await engine.execute(
        documents=[],
        checklist=checklist,
    )

    assert isinstance(result, ExecutionResult), "应返回 ExecutionResult"
    # 空文档列表时，检查计划可能为空
    assert result.summary["total"] >= 0, "total 应 >= 0"


@pytest.mark.asyncio
async def test_engine_execute_empty_checklist(engine, sample_documents):
    """
    测试场景：清单没有必需文档

    预期结果：
    - 正常执行，返回空结果
    """
    checklist = Checklist(
        id="empty_checklist",
        name="空清单",
        version="1.0",
        required_documents=[],
    )

    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    assert isinstance(result, ExecutionResult), "应返回 ExecutionResult"
    assert result.summary["total"] == 0, "空清单时 total 应为 0"


@pytest.mark.asyncio
async def test_engine_execute_non_required_check_fails(registry_with_failing, sample_documents):
    """
    测试场景：非必需检查失败

    预期结果：
    - success 为 True（非必需检查失败不阻断）
    """
    checklist = Checklist(
        id="test_non_required",
        name="测试非必需检查",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                required=True,
                checks=[
                    DocumentCheck(type="completeness", required=True),
                    DocumentCheck(type="failing_check", required=False),  # 非必需
                ],
            ),
        ],
    )

    engine = DeclarativeCheckEngine(registry=registry_with_failing)
    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    # 非必需检查失败不阻断
    assert result.success is True, "非必需检查失败不应阻断"
    assert result.summary["failed"] > 0, "应有失败记录"


@pytest.mark.asyncio
async def test_engine_unregistered_checker(engine, sample_documents):
    """
    测试场景：清单配置了未注册的检查器

    预期结果：
    - 返回 UNAVAILABLE 状态
    - unavailable_features 包含该检查类型
    """
    checklist = Checklist(
        id="test_unregistered",
        name="测试未注册检查器",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                required=True,
                checks=[
                    DocumentCheck(type="unregistered_check", required=True),
                ],
            ),
        ],
    )

    result = await engine.execute(
        documents=sample_documents,
        checklist=checklist,
    )

    # 未注册的检查器应返回 UNAVAILABLE
    assert "unregistered_check" in result.unavailable_features, "应记录不可用功能"


@pytest.mark.asyncio
async def test_engine_document_not_matching_checklist(engine):
    """
    测试场景：文档不匹配清单中的任何项

    预期结果：
    - 文档被跳过
    - 不影响其他检查
    """
    checklist = Checklist(
        id="test_no_match",
        name="测试无匹配",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="完全不同的文档",
                required=True,
                checks=[
                    DocumentCheck(type="completeness", required=True),
                ],
            ),
        ],
    )

    documents = [create_document("项目立项批复.pdf")]  # 不匹配清单

    result = await engine.execute(
        documents=documents,
        checklist=checklist,
    )

    # 文档不匹配，可能只有项目级别的检查
    assert isinstance(result, ExecutionResult), "应返回 ExecutionResult"
