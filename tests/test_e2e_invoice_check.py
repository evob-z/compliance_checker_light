"""
端到端测试 - 发票合规检查场景

测试场景：
用户输入："文件夹路径："D:\\AI_model\\MCP_server\\项目手续测试"，
         检查是否有发票文件，验证签发日期是否在2026/3/12之前，
         检查是否有印章"

此测试验证完整的合规检查流程，包括：
1. 文档扫描和解析（PDF/DOCX/图片）
2. LLM 生成检查清单
3. 完整性检查（发票文件是否存在）
4. 时效性检查（签发日期与有效期判定 - 4步业务规则）
5. 视觉检查（印章检测）
6. 结果格式化和返回

测试策略：
- 使用 Mock 替代真实的 LLM 和视觉 API 调用
- 使用临时文件系统创建测试文档
- 验证完整的调用链和数据流

时效性检查更新说明：
- 新规则使用4步判定：提取有效期 -> 提取落款日期 -> 确定基准时间 -> 核心判定矩阵
- 支持 reference_time 参数指定校验时间
- 判定分支：
  - 分支A：有有效期但无落款日期 → 不通过
  - 分支B：有落款日期但无有效期（长期有效）→ 落款日期 ≤ 基准时间则通过
  - 分支C：两者都有 → 落款日期 ≤ 基准时间 ≤ 截止日期则通过

视觉检查更新说明：
- 检查器名称是 "compliance"，但支持 "visual" 别名
- 状态包括：VALID, MISSING, UNCLEAR, ERROR, UNAVAILABLE
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from src.application.skill import ComplianceSkill
from src.application.use_cases.project_check import ProjectCheckUseCase
from src.application.bootstrap import Container, CheckerConfig
from src.domain.engine.declarative import DeclarativeCheckEngine, ExecutionResult
from src.core.checker_base import CheckStatus, CheckResult
from src.core.checker_registry import CheckerRegistry


class MockExecutionResult:
    """Mock 执行结果 - 模拟发票检查场景（适配新版时效性和视觉检查规则）"""

    def __init__(self, success=True, has_invoice=True, date_valid=True, has_seal=True):
        self.success = success
        self.execution_time = 1.5
        self.messages = []
        self.unavailable_features = []

        # 构建检查结果
        self.document_results = {}
        self.summary = {"total": 3, "passed": 0, "failed": 0, "errors": 0, "unavailable": 0}

        # 项目级别检查（完整性）
        project_results = []

        # 1. 完整性检查 - 发票文件是否存在
        if has_invoice:
            project_results.append(
                CheckResult(
                    check_type="completeness",
                    status=CheckStatus.PASS,
                    message="找到发票文件",
                    details={"found_documents": ["发票.pdf"], "required_count": 1},
                )
            )
            self.summary["passed"] += 1
        else:
            project_results.append(
                CheckResult(
                    check_type="completeness",
                    status=CheckStatus.FAIL,
                    message="未找到发票文件",
                    details={"missing": ["发票"], "found": []},
                    issues=[{"description": "缺少必需的发票文件"}],
                )
            )
            self.summary["failed"] += 1

        self.document_results["__PROJECT_LEVEL__"] = project_results

        # 文档级别检查
        if has_invoice:
            doc_results = []

            # 2. 时效性检查 - 新版4步判定规则
            # 分支C判定：两者都有 → 落款日期 ≤ 基准时间 ≤ 截止日期则通过
            if date_valid:
                doc_results.append(
                    CheckResult(
                        check_type="timeliness",
                        status=CheckStatus.PASS,
                        message="时效性检查完成: 1/1 文档通过",
                        details={
                            "checked": 1,
                            "passed": 1,
                            "failed": 0,
                            "unclear": 0,
                            "reference_time": "2026-03-15 10:00:00",
                            "documents": [
                                {
                                    "document_name": "发票.pdf",
                                    "has_validity": True,
                                    "has_sign_date": True,
                                    "validity": {
                                        "value": 1,
                                        "unit": "years",
                                        "is_permanent": False,
                                    },
                                    "sign_date": "2026-03-10",
                                    "expiry_date": "2027-03-10",
                                    "reference_time": "2026-03-15 10:00:00",
                                    "passed": True,
                                    "reason": "落款日期 2026-03-10 已生效，有效期至 2027-03-10",
                                    "branch": "C",
                                }
                            ],
                        },
                    )
                )
                self.summary["passed"] += 1
            else:
                # 日期逾期场景 - 分支C判定失败
                doc_results.append(
                    CheckResult(
                        check_type="timeliness",
                        status=CheckStatus.FAIL,
                        message="时效性检查完成: 0/1 文档通过, 1 个文档未通过",
                        details={
                            "checked": 1,
                            "passed": 0,
                            "failed": 1,
                            "unclear": 0,
                            "reference_time": "2026-03-15 10:00:00",
                            "documents": [
                                {
                                    "document_name": "发票.pdf",
                                    "has_validity": True,
                                    "has_sign_date": True,
                                    "validity": {
                                        "value": 1,
                                        "unit": "months",
                                        "is_permanent": False,
                                    },
                                    "sign_date": "2026-03-10",
                                    "expiry_date": "2026-04-10",
                                    "reference_time": "2026-03-15 10:00:00",
                                    "passed": False,
                                    "reason": "文档已过期，有效期至 2026-04-10",
                                    "branch": "C",
                                }
                            ],
                        },
                        issues=[
                            {
                                "type": "timeliness_failed",
                                "document": "发票.pdf",
                                "branch": "C",
                                "reason": "文档已过期，有效期至 2026-04-10",
                                "sign_date": "2026-03-10",
                                "expiry_date": "2026-04-10",
                            }
                        ],
                    )
                )
                self.summary["failed"] += 1

            # 3. 视觉检查 - 印章（适配新版 compliance 检查器状态）
            # 新版使用 VALID 状态表示通过，MISSING 表示未检测到
            if has_seal:
                doc_results.append(
                    CheckResult(
                        check_type="compliance",  # 检查器名称是 compliance
                        status=CheckStatus.VALID,  # 新版使用 VALID 而非 PASS
                        message="所有 1 个文档视觉检查通过",
                        details={
                            "check_type": "both",
                            "total_documents": 1,
                            "valid_count": 1,
                            "missing_count": 0,
                            "error_count": 0,
                            "unclear_count": 0,
                            "confidence_threshold": 0.7,
                            "document_results": [
                                {
                                    "document_name": "发票.pdf",
                                    "document_path": "/tmp/发票.pdf",
                                    "check_type": "both",
                                    "seal_result": {"found": True, "confidence": 0.95},
                                    "signature_result": {"found": False, "confidence": 0.0},
                                    "status": CheckStatus.VALID.value,
                                    "message": "印章: 已发现 (置信度: 0.95)",
                                }
                            ],
                        },
                    )
                )
                self.summary["passed"] += 1
            else:
                doc_results.append(
                    CheckResult(
                        check_type="compliance",
                        status=CheckStatus.FAIL,  # 当所有文档都 MISSING 时返回 FAIL
                        message="所有 1 个文档均未检测到目标视觉元素",
                        details={
                            "check_type": "both",
                            "total_documents": 1,
                            "valid_count": 0,
                            "missing_count": 1,
                            "error_count": 0,
                            "unclear_count": 0,
                            "document_results": [
                                {
                                    "document_name": "发票.pdf",
                                    "document_path": "/tmp/发票.pdf",
                                    "check_type": "both",
                                    "seal_result": {"found": False, "confidence": 0.0},
                                    "status": CheckStatus.MISSING.value,
                                    "message": "印章: 未发现 (置信度: 0.00)",
                                }
                            ],
                        },
                        issues=[
                            {
                                "document": "发票.pdf",
                                "status": CheckStatus.MISSING.value,
                                "message": "印章: 未发现 (置信度: 0.00)",
                            }
                        ],
                    )
                )
                self.summary["failed"] += 1

            self.document_results["发票.pdf"] = doc_results

        self.summary["total"] = self.summary["passed"] + self.summary["failed"]


@pytest.fixture
def mock_container():
    """创建 Mock 依赖注入容器"""
    config = CheckerConfig(
        similarity_threshold=0.75,
        use_semantic=True,
        visual_enabled=True,
    )
    container = MagicMock(spec=Container)
    container.config = config
    container.llm_client = AsyncMock()
    container.semantic_matcher = AsyncMock()
    container.visual_client = MagicMock()
    container.visual_client.is_available.return_value = True
    return container


@pytest.fixture
def mock_engine():
    """创建 Mock 检查引擎"""
    engine = MagicMock(spec=DeclarativeCheckEngine)
    return engine


@pytest.fixture
def mock_registry():
    """创建 Mock 检查器注册表"""
    registry = MagicMock(spec=CheckerRegistry)
    registry.list_available.return_value = ["completeness", "timeliness", "visual"]
    return registry


class TestInvoiceCheckEndToEnd:
    """发票检查端到端测试"""

    @pytest.mark.asyncio
    async def test_invoice_check_all_pass(self, tmp_path):
        """
        测试场景：所有检查通过（新版检查规则）

        用户要求：
        - 检查是否有发票文件 ✓
        - 验证签发日期是否在2026/3/12之前 ✓
        - 检查是否有印章 ✓

        新版检查规则说明：
        - 时效性：分支C判定通过（落款日期 ≤ 基准时间 ≤ 截止日期）
        - 视觉检查：compliance 检查器返回 VALID 状态
        """
        # 创建测试发票文件
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        # Mock 执行结果 - 全部通过（新版4步判定规则）
        mock_result = MockExecutionResult(
            success=True,
            has_invoice=True,
            date_valid=True,  # 分支C判定通过
            has_seal=True,  # 状态 VALID
        )

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_001",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [
                            {
                                "name": "发票",
                                "aliases": ["发票", "增值税发票", "普通发票"],
                                "required": True,
                            }
                        ],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True, "reference_time": "2026-03-15"},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                    )

        # 验证结果结构
        assert isinstance(result, dict)
        assert "success" in result
        assert "summary" in result
        assert "issues_count" in result
        assert "issues" in result
        assert "issues_description" in result

        # 验证检查通过
        assert result["success"] is True
        assert result["summary"]["passed"] == 3
        assert result["summary"]["failed"] == 0
        assert result["issues_count"] == 0

        # 验证问题描述
        assert "通过" in result["issues_description"]

    @pytest.mark.asyncio
    async def test_invoice_check_missing_invoice(self, tmp_path):
        """
        测试场景：缺少发票文件（完整性检查失败）

        用户要求：
        - 检查是否有发票文件 ✗（未找到）
        - 验证签发日期是否在2026/3/12之前（跳过）
        - 检查是否有印章（跳过）
        """
        # 创建其他文件，但不创建发票
        other_file = tmp_path / "合同.pdf"
        other_file.write_text("模拟合同内容")

        # Mock 执行结果 - 缺少发票
        mock_result = MockExecutionResult(
            success=False, has_invoice=False, date_valid=True, has_seal=True
        )

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(other_file),
            name="合同.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="合同内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_002",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [
                            {
                                "name": "发票",
                                "aliases": ["发票", "增值税发票"],
                                "required": True,
                            }
                        ],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                    )

        # 验证检查失败
        assert result["success"] is False
        assert result["summary"]["failed"] >= 1
        assert result["issues_count"] >= 1

        # 验证问题描述包含完整性检查
        assert "发票" in result["issues_description"] or "完整性" in result["issues_description"]

    @pytest.mark.asyncio
    async def test_invoice_check_date_overdue(self, tmp_path):
        """
        测试场景：签发日期超过期限（新版时效性检查 - 分支C判定失败）

        用户要求：
        - 检查是否有发票文件 ✓
        - 验证签发日期是否在2026/3/12之前 ✗（逾期 - 文档已过期）
        - 检查是否有印章 ✓

        新版时效性检查逻辑：
        - 分支C：两者都有 → 落款日期 ≤ 基准时间 ≤ 截止日期则通过
        - 此场景：基准时间(2026-03-15) > 截止日期(2026-04-10) → 判定失败
        """
        # 创建测试发票文件
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        # Mock 执行结果 - 日期逾期（新版4步判定规则）
        mock_result = MockExecutionResult(
            success=False,
            has_invoice=True,
            date_valid=False,  # 日期逾期 - 分支C判定失败
            has_seal=True,
        )

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_003",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True, "reference_time": "2026-03-15"},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                    )

        # 验证检查失败
        assert result["success"] is False
        assert result["summary"]["failed"] >= 1

        # 验证问题描述包含时效性检查（新版使用"过期"而非"逾期"）
        issues_desc = result["issues_description"]
        assert (
            "日期" in issues_desc
            or "时效" in issues_desc
            or "过期" in issues_desc
            or "有效期" in issues_desc
        )

    @pytest.mark.asyncio
    async def test_invoice_check_missing_seal(self, tmp_path):
        """
        测试场景：缺少印章（新版视觉检查 - compliance 检查器）

        用户要求：
        - 检查是否有发票文件 ✓
        - 验证签发日期是否在2026/3/12之前 ✓
        - 检查是否有印章 ✗（未找到）

        新版视觉检查说明：
        - 检查器名称是 "compliance"，支持 "visual" 别名
        - 状态使用 MISSING 表示未检测到，整体返回 FAIL
        """
        # 创建测试发票文件
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        # Mock 执行结果 - 缺少印章（新版 compliance 检查器）
        mock_result = MockExecutionResult(
            success=False,
            has_invoice=True,
            date_valid=True,
            has_seal=False,  # 缺少印章 - 状态为 MISSING
        )

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_004",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                    )

        # 验证检查失败
        assert result["success"] is False

        # 验证问题描述包含视觉检查/印章（新版使用 "未检测" 或 "未发现"）
        issues_desc = result["issues_description"]
        assert (
            "印章" in issues_desc
            or "公章" in issues_desc
            or "视觉" in issues_desc
            or "未检测" in issues_desc
            or "未发现" in issues_desc
        )

    @pytest.mark.asyncio
    async def test_invoice_check_multiple_issues(self, tmp_path):
        """
        测试场景：多个问题同时存在（时效性 + 视觉检查）

        用户要求：
        - 检查是否有发票文件 ✓
        - 验证签发日期是否在2026/3/12之前 ✗（文档已过期）
        - 检查是否有印章 ✗（未检测到）

        新版检查规则：
        - 时效性：分支C判定失败（基准时间 > 截止日期）
        - 视觉检查：状态 MISSING，整体返回 FAIL
        """
        # 创建测试发票文件
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        # Mock 执行结果 - 多个问题（新版检查规则）
        mock_result = MockExecutionResult(
            success=False,
            has_invoice=True,
            date_valid=False,  # 日期逾期 - 分支C判定失败
            has_seal=False,  # 缺少印章 - 状态 MISSING
        )

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_005",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True, "reference_time": "2026-03-15"},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                    )

        # 验证多个问题
        assert result["success"] is False
        assert result["summary"]["failed"] >= 2
        assert result["issues_count"] >= 2


class TestInvoiceCheckWithProjectPeriod:
    """带项目周期的发票检查测试（适配新版时效性检查）"""

    @pytest.mark.asyncio
    async def test_invoice_check_with_explicit_period(self, tmp_path):
        """
        测试场景：使用显式项目周期参数

        用户可以通过 project_period 参数指定检查的时间范围，
        新版时效性检查支持 reference_time 参数进行精确时间校验。
        """
        # 创建测试发票文件
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        mock_result = MockExecutionResult(success=True)

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_006",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True, "reference_time": "2026-06-15"},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()

                    # 使用 project_period 参数（新版也支持 reference_time 进行精确校验）
                    result = await skill.check(
                        project_path=str(tmp_path),
                        requirements="检查是否有发票文件，验证签发日期是否在2026/3/12之前，检查是否有印章",
                        project_period={"start": "2026-01", "end": "2026-12"},
                    )

        # 验证结果
        assert isinstance(result, dict)
        assert "success" in result
        assert "project_id" in result
        assert result["project_id"] == tmp_path.name


class TestInvoiceCheckErrorHandling:
    """发票检查错误处理测试"""

    @pytest.mark.asyncio
    async def test_invoice_check_path_not_found(self):
        """测试路径不存在的情况 - 验证 use_case 抛出 FileNotFoundError"""
        from src.application.use_cases.project_check import ProjectCheckUseCase

        mock_engine = MagicMock()
        mock_parsers = {".pdf": MagicMock()}
        mock_llm_client = MagicMock()

        use_case = ProjectCheckUseCase(
            engine=mock_engine,
            parsers=mock_parsers,
            llm_client=mock_llm_client,
        )

        # 验证抛出 FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            await use_case.execute(
                project_path="/nonexistent/path/to/invoice", requirements="检查是否有发票文件"
            )

        assert "路径不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invoice_check_empty_directory(self, tmp_path):
        """测试空目录的情况 - 验证 use_case 抛出 ValueError"""
        from src.application.use_cases.project_check import ProjectCheckUseCase

        mock_engine = MagicMock()
        mock_parsers = {".pdf": MagicMock()}
        mock_llm_client = MagicMock()

        use_case = ProjectCheckUseCase(
            engine=mock_engine,
            parsers=mock_parsers,
            llm_client=mock_llm_client,
        )

        # 验证抛出 ValueError
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute(project_path=str(tmp_path), requirements="检查是否有发票文件")

        assert "未找到可解析的文档" in str(exc_info.value)


class TestInvoiceCheckResultFormat:
    """发票检查结果格式验证（适配新版检查器返回格式）"""

    @pytest.mark.asyncio
    async def test_result_structure(self, tmp_path):
        """验证返回结果的数据结构（适配新版时效性和视觉检查）"""
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        mock_result = MockExecutionResult(success=True)

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_007",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True, "reference_time": "2026-03-15"},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()
                    result = await skill.check(project_path=str(tmp_path), requirements="检查发票")

        # 验证必需字段
        required_fields = [
            "success",
            "summary",
            "issues_count",
            "issues",
            "issues_description",
            "messages",
            "execution_time",
        ]
        for field in required_fields:
            assert field in result, f"缺少必需字段: {field}"

        # 验证 summary 结构
        summary = result["summary"]
        assert "total_checks" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "errors" in summary

        # 验证 issues 是列表
        assert isinstance(result["issues"], list)

        # 验证 issues_description 是字符串
        assert isinstance(result["issues_description"], str)

    @pytest.mark.asyncio
    async def test_execution_time_present(self, tmp_path):
        """验证执行时间字段"""
        invoice_file = tmp_path / "发票.pdf"
        invoice_file.write_text("模拟发票内容")

        mock_result = MockExecutionResult(success=True)

        # Mock Document 对象
        from src.core.document import Document, DocumentType, PageContent, DocumentMetadata

        mock_document = Document(
            path=str(invoice_file),
            name="发票.pdf",
            type=DocumentType.PDF,
            pages=1,
            pages_content=[PageContent(page_num=0, text="发票内容")],
            metadata=DocumentMetadata(),
        )

        with patch("src.application.skill.initialize_app") as mock_init:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client.generate_yaml = AsyncMock(
                return_value={
                    "checklist": {
                        "id": "invoice_check_008",
                        "name": "发票合规检查清单",
                        "version": "1.0",
                        "required_documents": [{"name": "发票", "required": True}],
                        "checks": [
                            {"type": "completeness", "enabled": True},
                            {"type": "timeliness", "enabled": True},
                            {"type": "compliance", "enabled": True, "visual_type": "seal"},
                        ],
                    }
                }
            )
            mock_init.return_value = (mock_registry, mock_container)

            with patch.object(DeclarativeCheckEngine, "execute", return_value=mock_result):
                with patch("src.application.skill.PDFParser") as mock_pdf_parser:
                    mock_parser_instance = MagicMock()
                    mock_parser_instance.parse.return_value = mock_document
                    mock_pdf_parser.return_value = mock_parser_instance

                    skill = ComplianceSkill()
                    result = await skill.check(project_path=str(tmp_path), requirements="检查发票")

        # 验证执行时间
        assert "execution_time" in result
        assert isinstance(result["execution_time"], float)
        assert result["execution_time"] > 0
