"""
Application 层 ComplianceSkill Facade 单元测试

测试范围：
- ComplianceSkill 初始化和依赖组装
- check 方法执行流程
- 结果格式化和字段校验

测试策略：
- Mock 所有外部依赖（registry, container, engine, use_case）
- 验证 Facade 模式正确委托给底层组件
- 验证返回结果包含所有必需字段
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from src.application.skill import ComplianceSkill
from src.core.checker_base import CheckStatus, CheckResult
from src.domain.engine.declarative import ExecutionResult


class MockExecutionResult:
    """Mock 执行结果对象"""

    def __init__(self, success=True, failed=0, errors=0, unavailable=0):
        self.success = success
        self.summary = {
            "total": 5,
            "passed": 5 - failed - errors - unavailable,
            "failed": failed,
            "errors": errors,
            "unavailable": unavailable,
        }
        self.document_results = {}
        self.messages = []
        self.unavailable_features = []
        self.execution_time = 1.23


@pytest.fixture
def mock_execution_result_all_pass():
    """所有检查通过的 Mock 结果"""
    return MockExecutionResult(success=True, failed=0, errors=0)


@pytest.fixture
def mock_execution_result_with_issues():
    """包含问题的 Mock 结果"""
    result = MockExecutionResult(success=False, failed=2, errors=1, unavailable=1)
    result.document_results = {
        "test_doc.pdf": [
            CheckResult(
                check_type="completeness",
                status=CheckStatus.FAIL,
                message="缺少必需文档",
                details={"missing": ["立项批复"]},
            ),
            CheckResult(
                check_type="timeliness",
                status=CheckStatus.PASS,
                message="时效性检查通过",
            ),
        ],
        "__PROJECT_LEVEL__": [
            CheckResult(
                check_type="completeness",
                status=CheckStatus.FAIL,
                message="项目级别完整性检查失败",
            ),
        ],
    }
    result.messages = ["发现 2 个问题"]
    result.unavailable_features = ["visual"]
    return result


class TestComplianceSkillInit:
    """测试 ComplianceSkill 初始化"""

    @patch("src.application.skill.initialize_app")
    @patch("src.application.skill.DeclarativeCheckEngine")
    @patch("src.application.skill.ProjectCheckUseCase")
    @patch("src.application.skill.PDFParser")
    @patch("src.application.skill.DocxParser")
    @patch("src.application.skill.ImageParser")
    def test_init_with_default_config(
        self,
        mock_image_parser,
        mock_docx_parser,
        mock_pdf_parser,
        mock_use_case,
        mock_engine,
        mock_init_app,
    ):
        """测试使用默认配置初始化"""
        # 设置 Mock
        mock_registry = MagicMock()
        mock_container = MagicMock()
        mock_container.llm_client = MagicMock()
        mock_init_app.return_value = (mock_registry, mock_container)

        mock_engine_instance = MagicMock()
        mock_engine.return_value = mock_engine_instance

        mock_use_case_instance = MagicMock()
        mock_use_case.return_value = mock_use_case_instance

        # 执行初始化
        skill = ComplianceSkill()

        # 验证 initialize_app 被调用
        mock_init_app.assert_called_once_with(None)

        # 验证属性设置
        assert skill.registry == mock_registry
        assert skill.container == mock_container
        assert skill.engine == mock_engine_instance
        assert skill.use_case == mock_use_case_instance

        # 验证解析器字典
        assert ".pdf" in skill.parsers
        assert ".docx" in skill.parsers
        assert ".doc" in skill.parsers
        assert ".png" in skill.parsers
        assert ".jpg" in skill.parsers
        assert ".jpeg" in skill.parsers

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        mock_config = MagicMock()

        with patch("src.application.skill.initialize_app") as mock_init_app:
            mock_registry = MagicMock()
            mock_container = MagicMock()
            mock_container.llm_client = MagicMock()
            mock_init_app.return_value = (mock_registry, mock_container)

            with patch("src.application.skill.DeclarativeCheckEngine"):
                with patch("src.application.skill.ProjectCheckUseCase"):
                    skill = ComplianceSkill(config=mock_config)

                    # 验证传入的配置被使用
                    mock_init_app.assert_called_once_with(mock_config)

    @patch("src.application.skill.initialize_app")
    @patch("src.application.skill.DeclarativeCheckEngine")
    @patch("src.application.skill.ProjectCheckUseCase")
    @patch("src.application.skill.PDFParser")
    def test_init_engine_config(self, mock_pdf_parser, mock_use_case, mock_engine, mock_init_app):
        """测试引擎并发配置"""
        mock_registry = MagicMock()
        mock_container = MagicMock()
        mock_container.llm_client = MagicMock()
        mock_init_app.return_value = (mock_registry, mock_container)

        ComplianceSkill()

        # 验证引擎被传入并发配置
        mock_engine.assert_called_once()
        call_kwargs = mock_engine.call_args.kwargs
        assert call_kwargs["registry"] == mock_registry
        assert call_kwargs["concurrency_config"]["max_concurrent_checks"] == 5
        assert call_kwargs["concurrency_config"]["check_timeout"] == 300


class TestComplianceSkillCheck:
    """测试 ComplianceSkill.check 方法"""

    @pytest.fixture(autouse=True)
    def setup_skill(self):
        """设置测试用的 Skill 实例"""
        with patch("src.application.skill.initialize_app") as mock_init_app:
            self.mock_registry = MagicMock()
            self.mock_container = MagicMock()
            self.mock_container.llm_client = MagicMock()
            mock_init_app.return_value = (self.mock_registry, self.mock_container)

            with patch("src.application.skill.DeclarativeCheckEngine") as mock_engine:
                self.mock_engine = MagicMock()
                mock_engine.return_value = self.mock_engine

                with patch("src.application.skill.ProjectCheckUseCase") as mock_use_case:
                    self.mock_use_case = MagicMock()
                    mock_use_case.return_value = self.mock_use_case

                    with patch("src.application.skill.PDFParser"):
                        with patch("src.application.skill.DocxParser"):
                            with patch("src.application.skill.ImageParser"):
                                self.skill = ComplianceSkill()
                                yield

    @pytest.mark.asyncio
    async def test_check_success_all_pass(self, mock_execution_result_all_pass):
        """测试检查成功 - 所有检查通过"""
        # 设置 use_case 返回 Mock 结果
        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_execution_result_all_pass,
                "project_id": "test_project",
                "checklist": {"name": "测试清单"},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        # 验证 use_case.execute 被调用
        self.mock_use_case.execute.assert_called_once_with("/test/path", "检查立项批复", None)

        # 验证返回结果结构
        assert isinstance(result, dict)
        assert "success" in result
        assert "summary" in result
        assert "issues_count" in result
        assert "issues" in result
        assert "messages" in result
        assert "execution_time" in result
        assert "issues_description" in result
        assert "project_id" in result
        assert "checklist" in result

        # 验证字段值
        assert result["success"] is True
        assert result["summary"]["passed"] == 5
        assert result["summary"]["failed"] == 0
        assert result["issues_count"] == 0
        assert result["issues"] == []
        assert result["project_id"] == "test_project"

    @pytest.mark.asyncio
    async def test_check_with_project_period(self, mock_execution_result_all_pass):
        """测试传入项目周期参数"""
        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_execution_result_all_pass,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        project_period = {"start": "2024-01", "end": "2024-12"}

        await self.skill.check(
            project_path="/test/path", requirements="检查立项批复", project_period=project_period
        )

        # 验证 project_period 被传递
        self.mock_use_case.execute.assert_called_once_with(
            "/test/path", "检查立项批复", project_period
        )

    @pytest.mark.asyncio
    async def test_check_with_issues(self, mock_execution_result_with_issues):
        """测试检查结果包含问题"""
        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": False,
                "execution_result": mock_execution_result_with_issues,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        # 验证失败状态
        assert result["success"] is False
        assert result["summary"]["failed"] == 2
        assert result["summary"]["errors"] == 1
        assert result["summary"]["unavailable"] == 1

        # 验证问题列表
        assert result["issues_count"] > 0
        assert len(result["issues"]) > 0

        # 验证问题字段结构
        first_issue = result["issues"][0]
        assert "document" in first_issue
        assert "check_type" in first_issue
        assert "status" in first_issue
        assert "message" in first_issue
        assert "details" in first_issue

        # 验证 issues_description 不为空
        assert result["issues_description"] != ""
        assert isinstance(result["issues_description"], str)

    @pytest.mark.asyncio
    async def test_check_issues_description_format(self, mock_execution_result_with_issues):
        """测试 issues_description 格式"""
        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": False,
                "execution_result": mock_execution_result_with_issues,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        description = result["issues_description"]

        # 验证描述包含问题数量
        assert "2" in description or "问题" in description

        # 验证是字符串类型
        assert isinstance(description, str)
        assert len(description) > 0

    @pytest.mark.asyncio
    async def test_check_all_pass_description(self, mock_execution_result_all_pass):
        """测试全部通过时的描述"""
        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_execution_result_all_pass,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        # 全部通过时应有正面描述
        description = result["issues_description"]
        assert isinstance(description, str)
        assert len(description) > 0


class TestComplianceSkillEdgeCases:
    """测试 ComplianceSkill 边界情况"""

    @pytest.fixture(autouse=True)
    def setup_skill(self):
        """设置测试用的 Skill 实例"""
        with patch("src.application.skill.initialize_app") as mock_init_app:
            self.mock_registry = MagicMock()
            self.mock_container = MagicMock()
            self.mock_container.llm_client = MagicMock()
            mock_init_app.return_value = (self.mock_registry, self.mock_container)

            with patch("src.application.skill.DeclarativeCheckEngine") as mock_engine:
                self.mock_engine = MagicMock()
                mock_engine.return_value = self.mock_engine

                with patch("src.application.skill.ProjectCheckUseCase") as mock_use_case:
                    self.mock_use_case = MagicMock()
                    mock_use_case.return_value = self.mock_use_case

                    with patch("src.application.skill.PDFParser"):
                        with patch("src.application.skill.DocxParser"):
                            with patch("src.application.skill.ImageParser"):
                                self.skill = ComplianceSkill()
                                yield

    @pytest.mark.asyncio
    async def test_check_empty_issues(self):
        """测试空问题列表"""
        mock_result = MockExecutionResult(success=True, failed=0)
        mock_result.document_results = {}

        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_result,
                "project_id": "empty_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        assert result["issues_count"] == 0
        assert result["issues"] == []

    @pytest.mark.asyncio
    async def test_check_execution_time_type(self):
        """测试 execution_time 字段类型"""
        mock_result = MockExecutionResult(success=True)

        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_result,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        # execution_time 应为数字类型
        assert isinstance(result["execution_time"], (int, float))
        assert result["execution_time"] >= 0

    @pytest.mark.asyncio
    async def test_check_messages_field(self):
        """测试 messages 字段"""
        mock_result = MockExecutionResult(success=True)
        mock_result.messages = ["提示1", "提示2"]

        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": True,
                "execution_result": mock_result,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        # messages 应为列表
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_check_summary_structure(self):
        """测试 summary 字段结构"""
        mock_result = MockExecutionResult(success=True, failed=1, errors=0, unavailable=1)

        self.mock_use_case.execute = AsyncMock(
            return_value={
                "success": False,
                "execution_result": mock_result,
                "project_id": "test_project",
                "checklist": {},
            }
        )

        result = await self.skill.check(project_path="/test/path", requirements="检查立项批复")

        summary = result["summary"]

        # 验证 summary 包含所有必需字段
        assert "total_checks" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "errors" in summary
        assert "unavailable" in summary

        # 验证字段类型
        assert isinstance(summary["total_checks"], int)
        assert isinstance(summary["passed"], int)
        assert isinstance(summary["failed"], int)
        assert isinstance(summary["errors"], int)
        assert isinstance(summary["unavailable"], int)


class TestComplianceSkillParsers:
    """测试 ComplianceSkill 解析器配置"""

    @patch("src.application.skill.initialize_app")
    @patch("src.application.skill.DeclarativeCheckEngine")
    @patch("src.application.skill.ProjectCheckUseCase")
    def test_parser_extensions(self, mock_use_case, mock_engine, mock_init_app):
        """测试支持的文件扩展名"""
        mock_registry = MagicMock()
        mock_container = MagicMock()
        mock_container.llm_client = MagicMock()
        mock_init_app.return_value = (mock_registry, mock_container)

        with patch("src.application.skill.PDFParser") as mock_pdf:
            with patch("src.application.skill.DocxParser") as mock_docx:
                with patch("src.application.skill.ImageParser") as mock_img:
                    mock_pdf.return_value = MagicMock()
                    mock_docx.return_value = MagicMock()
                    mock_img.return_value = MagicMock()

                    skill = ComplianceSkill()

                    # 验证所有支持的扩展名
                    expected_extensions = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}
                    assert set(skill.parsers.keys()) == expected_extensions

                    # 验证 .doc 使用 DocxParser
                    assert skill.parsers[".doc"] == skill.parsers[".docx"]
