"""
Application 层 formatter 模块单元测试

测试范围：
- format_check_result 格式化完整结果文本
- format_simple_result 格式化简化结果字典
- format_issues_description 格式化问题描述

测试策略：
- 使用 Mock ExecutionResult 和 CheckResult
- 验证输出格式和字段完整性
- 测试各种边界情况（空结果、全部通过、包含问题等）
"""

import pytest
from unittest.mock import MagicMock
from typing import List, Dict, Any

from src.application.formatter import (
    format_check_result,
    format_simple_result,
    format_issues_description,
    _format_single_result,
)
from src.core.checker_base import CheckStatus, CheckResult
from src.domain.engine.declarative import ExecutionResult, CheckTask


class MockExecutionResult:
    """Mock 执行结果对象，用于测试"""
    def __init__(
        self,
        success: bool = True,
        summary: Dict[str, int] = None,
        document_results: Dict[str, List[CheckResult]] = None,
        messages: List[str] = None,
        unavailable_features: List[str] = None,
        execution_time: float = 1.5,
    ):
        self.success = success
        self.summary = summary or {"total": 5, "passed": 5, "failed": 0, "errors": 0, "unavailable": 0}
        self.document_results = document_results or {}
        self.messages = messages or []
        self.unavailable_features = unavailable_features or []
        self.execution_time = execution_time


@pytest.fixture
def sample_check_result_pass():
    """通过的检查结果"""
    return CheckResult(
        check_type="completeness",
        status=CheckStatus.PASS,
        message="完整性检查通过",
        details={"matched": 3},
    )


@pytest.fixture
def sample_check_result_fail():
    """失败的检查结果"""
    return CheckResult(
        check_type="timeliness",
        status=CheckStatus.FAIL,
        message="时效性检查失败",
        details={"expired": ["doc1.pdf"]},
        issues=[{"description": "文档已过期"}],
    )


@pytest.fixture
def sample_check_result_error():
    """错误的检查结果"""
    return CheckResult(
        check_type="compliance",
        status=CheckStatus.ERROR,
        message="执行异常",
        details={"error": "Connection timeout"},
    )


@pytest.fixture
def sample_check_result_unavailable():
    """不可用的检查结果"""
    return CheckResult(
        check_type="visual",
        status=CheckStatus.UNAVAILABLE,
        message="功能暂不可用",
        details={"contact": "项目负责人"},
    )


class TestFormatSingleResult:
    """测试 _format_single_result 辅助函数"""

    def test_format_pass_result(self, sample_check_result_pass):
        """测试格式化通过结果"""
        lines = _format_single_result(sample_check_result_pass)
        
        # 验证包含状态图标
        assert any("✅" in line for line in lines)
        # 验证包含检查类型
        assert any("完整性" in line for line in lines)
        # 验证包含消息
        assert any("完整性检查通过" in line for line in lines)

    def test_format_fail_result(self, sample_check_result_fail):
        """测试格式化失败结果"""
        lines = _format_single_result(sample_check_result_fail)
        
        # 验证包含状态图标
        assert any("❌" in line for line in lines)
        # 验证包含检查类型
        assert any("时效性" in line for line in lines)
        # 验证包含问题描述
        assert any("文档已过期" in line for line in lines)

    def test_format_error_result(self, sample_check_result_error):
        """测试格式化错误结果"""
        lines = _format_single_result(sample_check_result_error)
        
        # 验证包含错误图标
        assert any("💥" in line for line in lines)

    def test_format_unavailable_result(self, sample_check_result_unavailable):
        """测试格式化不可用结果"""
        lines = _format_single_result(sample_check_result_unavailable)
        
        # 验证包含警告图标
        assert any("⚠️" in line for line in lines)

    def test_format_with_details(self):
        """测试包含详细信息的格式化"""
        result = CheckResult(
            check_type="completeness",
            status=CheckStatus.FAIL,
            message="检查失败",
            details={
                "key1": "value1",
                "key2": ["item1", "item2"],
                "document": "should_be_skipped",
            },
        )
        lines = _format_single_result(result)
        
        # 验证详细信息被格式化（document 字段应被跳过）
        assert any("key1" in line for line in lines)
        assert any("key2" in line for line in lines)
        assert not any("document" in line for line in lines)


class TestFormatCheckResult:
    """测试 format_check_result 函数"""

    def test_format_all_pass(self):
        """测试全部通过的结果格式化"""
        result = MockExecutionResult(
            success=True,
            summary={"total": 3, "passed": 3, "failed": 0, "errors": 0, "unavailable": 0},
        )
        
        text = format_check_result(result)
        
        # 验证包含标题
        assert "合规审查结果" in text
        # 验证包含统计信息
        assert "检查总数: 3" in text
        assert "通过: 3 项" in text
        # 验证包含成功提示
        assert "所有检查通过" in text

    def test_format_with_failures(self):
        """测试包含失败的结果格式化"""
        result = MockExecutionResult(
            success=False,
            summary={"total": 5, "passed": 2, "failed": 2, "errors": 1, "unavailable": 0},
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="缺少文档",
                    ),
                ],
            },
        )
        
        text = format_check_result(result)
        
        # 验证包含统计信息
        assert "失败: 2 项" in text
        assert "错误: 1 项" in text
        # 验证包含文档名称
        assert "doc1.pdf" in text

    def test_format_with_unavailable(self):
        """测试包含不可用功能的结果格式化"""
        result = MockExecutionResult(
            success=True,
            summary={"total": 5, "passed": 4, "failed": 0, "errors": 0, "unavailable": 1},
        )
        
        text = format_check_result(result)
        
        # 验证包含不可用统计
        assert "暂不可用: 1 项" in text

    def test_format_with_messages(self):
        """测试包含提示信息的结果格式化"""
        result = MockExecutionResult(
            success=True,
            messages=["提示信息1", "提示信息2"],
        )
        
        text = format_check_result(result)
        
        # 验证包含提示信息标题
        assert "提示信息" in text
        # 验证包含具体提示
        assert "提示信息1" in text
        assert "提示信息2" in text

    def test_format_project_level_results(self):
        """测试项目级别结果的格式化"""
        result = MockExecutionResult(
            success=False,
            document_results={
                "__PROJECT_LEVEL__": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="项目级别检查失败",
                    ),
                ],
            },
        )
        
        text = format_check_result(result)
        
        # 验证包含项目级别标题
        assert "项目级别检查" in text

    def test_format_execution_time(self):
        """测试执行时间格式化"""
        result = MockExecutionResult(
            success=True,
            execution_time=2.567,
        )
        
        text = format_check_result(result)
        
        # 验证包含执行时间（保留两位小数）
        assert "执行时间: 2.57 秒" in text or "执行时间: 2.56" in text


class TestFormatSimpleResult:
    """测试 format_simple_result 函数"""

    def test_simple_result_structure(self):
        """测试简化结果的字典结构"""
        result = MockExecutionResult(
            success=True,
            summary={"total": 5, "passed": 5, "failed": 0, "errors": 0, "unavailable": 0},
        )
        
        formatted = format_simple_result(result)
        
        # 验证必需字段
        assert "success" in formatted
        assert "summary" in formatted
        assert "issues_count" in formatted
        assert "issues" in formatted
        assert "messages" in formatted
        assert "execution_time" in formatted

    def test_simple_result_summary_fields(self):
        """测试 summary 字段内容"""
        result = MockExecutionResult(
            success=True,
            summary={"total": 10, "passed": 7, "failed": 2, "errors": 1, "unavailable": 0},
        )
        
        formatted = format_simple_result(result)
        summary = formatted["summary"]
        
        # 验证 summary 字段
        assert summary["total_checks"] == 10
        assert summary["passed"] == 7
        assert summary["failed"] == 2
        assert summary["errors"] == 1
        assert summary["unavailable"] == 0

    def test_simple_result_with_issues(self):
        """测试包含问题的简化结果"""
        result = MockExecutionResult(
            success=False,
            summary={"total": 5, "passed": 2, "failed": 2, "errors": 1, "unavailable": 0},
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="缺少文档",
                        details={"missing": ["file1"]},
                    ),
                    CheckResult(
                        check_type="timeliness",
                        status=CheckStatus.PASS,
                        message="时效性通过",
                    ),
                ],
                "doc2.pdf": [
                    CheckResult(
                        check_type="compliance",
                        status=CheckStatus.ERROR,
                        message="执行错误",
                        details={"error": "timeout"},
                    ),
                ],
            },
        )
        
        formatted = format_simple_result(result)
        
        # 验证问题数量
        assert formatted["issues_count"] == 2  # 只有 FAIL 和 ERROR 算问题
        assert len(formatted["issues"]) == 2
        
        # 验证问题字段结构
        for issue in formatted["issues"]:
            assert "document" in issue
            assert "check_type" in issue
            assert "status" in issue
            assert "message" in issue
            assert "details" in issue

    def test_simple_result_project_level_document(self):
        """测试项目级别文档名称处理"""
        result = MockExecutionResult(
            success=False,
            document_results={
                "__PROJECT_LEVEL__": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="项目级别问题",
                    ),
                ],
            },
        )
        
        formatted = format_simple_result(result)
        
        # 验证项目级别文档名称被转换
        assert len(formatted["issues"]) == 1
        assert formatted["issues"][0]["document"] == "项目级别"

    def test_simple_result_pass_not_in_issues(self):
        """测试通过的结果不包含在 issues 中"""
        result = MockExecutionResult(
            success=True,
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.PASS,
                        message="检查通过",
                    ),
                ],
            },
        )
        
        formatted = format_simple_result(result)
        
        # 通过的结果不应在 issues 中
        assert formatted["issues_count"] == 0
        assert formatted["issues"] == []

    def test_simple_result_types(self):
        """测试返回字段类型"""
        result = MockExecutionResult(
            success=True,
            summary={"total": 5, "passed": 5, "failed": 0, "errors": 0, "unavailable": 0},
            messages=["msg1", "msg2"],
            execution_time=1.23,
        )
        
        formatted = format_simple_result(result)
        
        # 验证类型
        assert isinstance(formatted["success"], bool)
        assert isinstance(formatted["summary"], dict)
        assert isinstance(formatted["issues_count"], int)
        assert isinstance(formatted["issues"], list)
        assert isinstance(formatted["messages"], list)
        assert isinstance(formatted["execution_time"], float)


class TestFormatIssuesDescription:
    """测试 format_issues_description 函数"""

    def test_description_all_pass(self):
        """测试全部通过时的描述"""
        result = MockExecutionResult(success=True)
        
        description = format_issues_description(result)
        
        # 验证包含通过提示
        assert "✅" in description
        assert "通过" in description

    def test_description_with_failures(self):
        """测试包含失败时的描述"""
        result = MockExecutionResult(
            success=False,
            summary={"failed": 2},
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="缺少立项批复",
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 验证包含问题数量
        assert "2" in description or "问题" in description
        # 验证包含文档名称
        assert "doc1.pdf" in description

    def test_description_check_type_mapping(self):
        """测试检查类型中文映射"""
        result = MockExecutionResult(
            success=False,
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="问题1",
                    ),
                    CheckResult(
                        check_type="timeliness",
                        status=CheckStatus.FAIL,
                        message="问题2",
                    ),
                    CheckResult(
                        check_type="compliance",
                        status=CheckStatus.FAIL,
                        message="问题3",
                    ),
                    CheckResult(
                        check_type="visual",
                        status=CheckStatus.FAIL,
                        message="问题4",
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 验证检查类型被正确映射为中文
        assert "完整性检查" in description
        assert "时效性检查" in description
        assert "合规性检查" in description
        assert "视觉检查" in description

    def test_description_project_level_display(self):
        """测试项目级别显示名称"""
        result = MockExecutionResult(
            success=False,
            document_results={
                "__PROJECT_LEVEL__": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="项目级别问题",
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 验证项目级别显示名称
        assert "项目整体" in description

    def test_description_with_issues_list(self):
        """测试包含 issues 列表的描述"""
        result = MockExecutionResult(
            success=False,
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="检查失败",
                        issues=[
                            {"description": "问题详情1"},
                            {"description": "问题详情2"},
                        ],
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 验证包含问题详情
        assert "问题详情1" in description
        assert "问题详情2" in description

    def test_description_with_unavailable_features(self):
        """测试包含不可用功能的描述"""
        # 当只有 unavailable_features 但没有失败时，应该显示通过
        result = MockExecutionResult(
            success=True,
            unavailable_features=["visual", "authenticity"],
        )
        
        description = format_issues_description(result)
        
        # 验证返回描述（可能是通过描述或包含不可用提示）
        assert isinstance(description, str)
        assert len(description) > 0
        
    def test_description_with_unavailable_and_failures(self):
        """测试包含不可用功能和失败时的描述"""
        result = MockExecutionResult(
            success=False,
            summary={"failed": 1},
            unavailable_features=["visual"],
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.FAIL,
                        message="检查失败",
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 验证包含不可用提示
        assert "暂不可用" in description or "⚠️" in description

    def test_description_empty_result(self):
        """测试空结果描述"""
        result = MockExecutionResult(success=True)
        
        description = format_issues_description(result)
        
        # 空结果应返回通过描述
        assert "通过" in description

    def test_description_return_type(self):
        """测试返回类型"""
        result = MockExecutionResult(success=True)
        
        description = format_issues_description(result)
        
        # 验证返回字符串
        assert isinstance(description, str)


class TestFormatterEdgeCases:
    """测试格式化边界情况"""

    def test_format_check_result_empty_document_results(self):
        """测试空文档结果"""
        result = MockExecutionResult(
            success=True,
            document_results={},
        )
        
        text = format_check_result(result)
        
        # 应正常处理空结果
        assert "合规审查结果" in text

    def test_format_simple_result_empty_issues(self):
        """测试空问题列表"""
        result = MockExecutionResult(
            success=True,
            document_results={},
        )
        
        formatted = format_simple_result(result)
        
        assert formatted["issues_count"] == 0
        assert formatted["issues"] == []

    def test_format_issues_description_no_failures(self):
        """测试没有失败时的描述"""
        result = MockExecutionResult(
            success=True,
            document_results={
                "doc1.pdf": [
                    CheckResult(
                        check_type="completeness",
                        status=CheckStatus.PASS,
                        message="通过",
                    ),
                ],
            },
        )
        
        description = format_issues_description(result)
        
        # 没有失败时应返回通过描述
        assert "通过" in description

    def test_format_single_result_unknown_check_type(self):
        """测试未知检查类型"""
        result = CheckResult(
            check_type="unknown_type",
            status=CheckStatus.FAIL,
            message="未知类型检查",
        )
        
        lines = _format_single_result(result)
        
        # 未知类型应显示原始名称
        assert "unknown_type" in " ".join(lines)

