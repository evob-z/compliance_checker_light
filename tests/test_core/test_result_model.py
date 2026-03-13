"""
检查结果数据模型测试

测试 CheckResult、CompletenessResult、DocumentMatch 等结果模型的功能
"""

import pytest
import json
from datetime import datetime

from compliance_checker.core.result_model import (
    CheckStatus,
    MatchType,
    DocumentMatch,
    CompletenessResult,
    TimelinessDetail,
    TimelinessResult,
    ComplianceCheckItem,
    DocumentCompliance,
    ComplianceResult,
    IssueItem,
    CheckSummary,
    CheckResult,
)


class TestCheckStatus:
    """测试检查状态枚举"""
    
    def test_status_values(self):
        """测试状态值定义"""
        assert CheckStatus.PASS == "PASS"
        assert CheckStatus.FAIL == "FAIL"
        assert CheckStatus.WARNING == "WARNING"
        assert CheckStatus.INCOMPLETE == "INCOMPLETE"
        assert CheckStatus.HAS_ISSUES == "HAS_ISSUES"
        assert CheckStatus.UNCLEAR == "UNCLEAR"
        assert CheckStatus.MISSING == "MISSING"
        assert CheckStatus.EXPIRED == "EXPIRED"
        assert CheckStatus.VALID == "VALID"
        assert CheckStatus.UNAVAILABLE == "UNAVAILABLE"
        assert CheckStatus.ERROR == "ERROR"


class TestMatchType:
    """测试匹配类型枚举"""
    
    def test_match_type_values(self):
        """测试匹配类型值"""
        assert MatchType.EXACT == "exact"
        assert MatchType.SEMANTIC == "semantic"
        assert MatchType.ALIAS == "alias"
        assert MatchType.NONE == "none"


class TestDocumentMatch:
    """测试文档匹配结果模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        match = DocumentMatch(
            document_name="立项批复",
            status=CheckStatus.VALID,
            matched_file="立项批复.pdf",
            match_type=MatchType.EXACT,
            similarity=1.0
        )
        
        assert match.document_name == "立项批复"
        assert match.status == CheckStatus.VALID
        assert match.similarity == 1.0
    
    def test_default_values(self):
        """测试默认值"""
        match = DocumentMatch(
            document_name="测试文档",
            status=CheckStatus.MISSING
        )
        
        assert match.matched_file is None
        assert match.match_type == MatchType.NONE
        assert match.similarity == 0.0
        assert match.requirement == "必须上传"


class TestCompletenessResult:
    """测试完整性检查结果模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        result = CompletenessResult(
            status=CheckStatus.PASS,
            total_required=5,
            uploaded=5,
            missing=0
        )
        
        assert result.status == CheckStatus.PASS
        assert result.total_required == 5
        assert result.uploaded == 5
        assert result.missing == 0
    
    def test_with_details(self):
        """测试带详情的创建"""
        result = CompletenessResult(
            status=CheckStatus.INCOMPLETE,
            total_required=3,
            uploaded=2,
            missing=1,
            details=[
                DocumentMatch(
                    document_name="文档1",
                    status=CheckStatus.VALID,
                    match_type=MatchType.EXACT
                ),
                DocumentMatch(
                    document_name="文档2",
                    status=CheckStatus.MISSING,
                    match_type=MatchType.NONE
                ),
            ]
        )
        
        assert len(result.details) == 2
        assert result.details[0].status == CheckStatus.VALID
        assert result.details[1].status == CheckStatus.MISSING
    
    def test_has_issues_true(self):
        """测试 has_issues 返回 True 的情况"""
        result = CompletenessResult(
            status=CheckStatus.INCOMPLETE,
            total_required=3,
            uploaded=2,
            missing=1
        )
        
        assert result.has_issues() is True
    
    def test_has_issues_by_status(self):
        """测试通过状态判断 has_issues"""
        result = CompletenessResult(
            status=CheckStatus.HAS_ISSUES,
            total_required=3,
            uploaded=3,
            missing=0
        )
        
        assert result.has_issues() is True
    
    def test_has_issues_false(self):
        """测试 has_issues 返回 False 的情况"""
        result = CompletenessResult(
            status=CheckStatus.PASS,
            total_required=3,
            uploaded=3,
            missing=0
        )
        
        assert result.has_issues() is False
    
    def test_has_issues_by_missing_count(self):
        """测试通过缺失数量判断 has_issues"""
        result = CompletenessResult(
            status=CheckStatus.PASS,  # 即使状态是 PASS
            total_required=3,
            uploaded=3,
            missing=1  # 但有缺失
        )
        
        assert result.has_issues() is True


class TestTimelinessDetail:
    """测试时效性详情模型"""
    
    def test_creation(self):
        """测试创建"""
        detail = TimelinessDetail(
            document_name="安全生产许可证",
            file_path="/data/license.pdf",
            validity={"valid_from": "2024-01", "valid_to": "2027-12"},
            project_period={"start": "2024-01", "end": "2026-12"},
            status=CheckStatus.VALID,
            message="证件在有效期内"
        )
        
        assert detail.document_name == "安全生产许可证"
        assert detail.status == CheckStatus.VALID


class TestTimelinessResult:
    """测试时效性结果模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        result = TimelinessResult(
            status=CheckStatus.HAS_ISSUES,
            checked=5,
            valid=3,
            expired=1,
            unclear=1
        )
        
        assert result.checked == 5
        assert result.valid == 3
        assert result.expired == 1
        assert result.unclear == 1
    
    def test_with_details(self):
        """测试带详情的创建"""
        result = TimelinessResult(
            status=CheckStatus.HAS_ISSUES,
            checked=2,
            valid=1,
            expired=1,
            unclear=0,
            details=[
                TimelinessDetail(
                    document_name="证件1",
                    file_path="/data/1.pdf",
                    validity={},
                    project_period={},
                    status=CheckStatus.VALID,
                    message="有效"
                ),
            ]
        )
        
        assert len(result.details) == 1


class TestComplianceCheckItem:
    """测试单项合规检查结果"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        item = ComplianceCheckItem(
            point="公章",
            found=True,
            status=CheckStatus.PASS,
            value="公司公章"
        )
        
        assert item.point == "公章"
        assert item.found is True
        assert item.status == CheckStatus.PASS
    
    def test_default_status(self):
        """测试默认状态"""
        item = ComplianceCheckItem(
            point="签名",
            found=False
        )
        
        assert item.status == CheckStatus.UNCLEAR


class TestDocumentCompliance:
    """测试文档合规性结果"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        doc_compliance = DocumentCompliance(
            document_name="合同.pdf",
            file_path="/data/合同.pdf",
            checks=[
                ComplianceCheckItem(point="公章", found=True, status=CheckStatus.PASS),
                ComplianceCheckItem(point="签名", found=False, status=CheckStatus.FAIL),
            ]
        )
        
        assert doc_compliance.document_name == "合同.pdf"
        assert len(doc_compliance.checks) == 2
    
    def test_get_failed_checks(self):
        """测试获取失败的检查项"""
        doc_compliance = DocumentCompliance(
            document_name="合同.pdf",
            file_path="/data/合同.pdf",
            checks=[
                ComplianceCheckItem(point="公章", found=True, status=CheckStatus.PASS),
                ComplianceCheckItem(point="签名", found=False, status=CheckStatus.FAIL),
                ComplianceCheckItem(point="日期", found=False, status=CheckStatus.MISSING),
            ]
        )
        
        failed = doc_compliance.get_failed_checks()
        assert len(failed) == 2
        assert all(c.status in (CheckStatus.FAIL, CheckStatus.MISSING) for c in failed)
    
    def test_get_passed_checks(self):
        """测试获取通过的检查项"""
        doc_compliance = DocumentCompliance(
            document_name="合同.pdf",
            file_path="/data/合同.pdf",
            checks=[
                ComplianceCheckItem(point="公章", found=True, status=CheckStatus.PASS),
                ComplianceCheckItem(point="签名", found=False, status=CheckStatus.FAIL),
            ]
        )
        
        passed = doc_compliance.get_passed_checks()
        assert len(passed) == 1
        assert passed[0].point == "公章"


class TestComplianceResult:
    """测试合规性结果模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        result = ComplianceResult(
            status=CheckStatus.PASS,
            details=[]
        )
        
        assert result.status == CheckStatus.PASS
    
    def test_get_failed_documents(self):
        """测试获取有问题的文档"""
        result = ComplianceResult(
            status=CheckStatus.HAS_ISSUES,
            details=[
                DocumentCompliance(
                    document_name="合同1.pdf",
                    file_path="/data/合同1.pdf",
                    checks=[
                        ComplianceCheckItem(point="公章", found=True, status=CheckStatus.PASS),
                    ]
                ),
                DocumentCompliance(
                    document_name="合同2.pdf",
                    file_path="/data/合同2.pdf",
                    checks=[
                        ComplianceCheckItem(point="公章", found=False, status=CheckStatus.FAIL),
                    ]
                ),
            ]
        )
        
        failed = result.get_failed_documents()
        assert len(failed) == 1
        assert failed[0].document_name == "合同2.pdf"
    
    def test_get_failed_documents_empty(self):
        """测试无失败文档的情况"""
        result = ComplianceResult(
            status=CheckStatus.PASS,
            details=[
                DocumentCompliance(
                    document_name="合同.pdf",
                    file_path="/data/合同.pdf",
                    checks=[
                        ComplianceCheckItem(point="公章", found=True, status=CheckStatus.PASS),
                    ]
                ),
            ]
        )
        
        failed = result.get_failed_documents()
        assert len(failed) == 0


class TestIssueItem:
    """测试问题项模型"""
    
    def test_creation(self):
        """测试创建"""
        issue = IssueItem(
            index=1,
            issue_type="完整性",
            document_name="立项批复",
            description="缺少该文件",
            page_num=None,
            screenshot_path=None
        )
        
        assert issue.index == 1
        assert issue.issue_type == "完整性"


class TestCheckResult:
    """测试完整检查结果模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        result = CheckResult(
            status=CheckStatus.HAS_ISSUES,
            summary=CheckSummary(
                project_id="proj_123",
                checklist_id="list_a",
                total_documents=8,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.HAS_ISSUES,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.HAS_ISSUES
            ),
            completeness=CompletenessResult(
                status=CheckStatus.PASS,
                total_required=5,
                uploaded=5,
                missing=0
            ),
            timeliness=TimelinessResult(
                status=CheckStatus.HAS_ISSUES,
                checked=3,
                valid=2,
                expired=1,
                unclear=0
            ),
            compliance=ComplianceResult(
                status=CheckStatus.PASS,
                details=[]
            )
        )
        
        assert result.status == CheckStatus.HAS_ISSUES
        assert result.summary.total_documents == 8
        assert result.completeness.status == CheckStatus.PASS
    
    def test_add_issue(self):
        """测试添加问题"""
        result = CheckResult(
            status=CheckStatus.PASS,
            summary=CheckSummary(
                total_documents=1,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.PASS,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.PASS
            )
        )
        
        result.add_issue(
            issue_type="完整性",
            document_name="合同",
            description="缺少签名页",
            page_num=5
        )
        
        assert len(result.issues) == 1
        assert result.issues[0].index == 1
        assert result.issues[0].issue_type == "完整性"
        assert result.issues[0].page_num == 5
    
    def test_add_issue_auto_index(self):
        """测试自动递增序号"""
        result = CheckResult(
            status=CheckStatus.PASS,
            summary=CheckSummary(
                total_documents=1,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.PASS,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.PASS
            )
        )
        
        result.add_issue("类型1", "文档1", "描述1")
        result.add_issue("类型2", "文档2", "描述2")
        result.add_issue("类型3", "文档3", "描述3")
        
        assert result.issues[0].index == 1
        assert result.issues[1].index == 2
        assert result.issues[2].index == 3
    
    def test_has_issues_true(self):
        """测试存在问题时 has_issues 返回 True"""
        result = CheckResult(
            status=CheckStatus.PASS,
            summary=CheckSummary(
                total_documents=1,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.PASS,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.PASS
            )
        )
        result.add_issue("类型", "文档", "描述")
        
        assert result.has_issues() is True
    
    def test_has_issues_false(self):
        """测试无问题时 has_issues 返回 False"""
        result = CheckResult(
            status=CheckStatus.PASS,
            summary=CheckSummary(
                total_documents=1,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.PASS,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.PASS
            )
        )
        
        assert result.has_issues() is False
    
    def test_get_issues_by_type(self):
        """测试按类型获取问题"""
        result = CheckResult(
            status=CheckStatus.PASS,
            summary=CheckSummary(
                total_documents=1,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.PASS,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.PASS
            )
        )
        
        result.add_issue("完整性", "文档1", "描述1")
        result.add_issue("时效性", "文档2", "描述2")
        result.add_issue("完整性", "文档3", "描述3")
        
        completeness_issues = result.get_issues_by_type("完整性")
        assert len(completeness_issues) == 2
        
        timeliness_issues = result.get_issues_by_type("时效性")
        assert len(timeliness_issues) == 1


class TestResultSerialization:
    """测试结果模型序列化"""
    
    def test_completeness_to_json(self):
        """测试完整性结果转 JSON"""
        result = CompletenessResult(
            status=CheckStatus.PASS,
            total_required=3,
            uploaded=3,
            missing=0,
            details=[
                DocumentMatch(
                    document_name="文档1",
                    status=CheckStatus.VALID,
                    match_type=MatchType.EXACT,
                    similarity=1.0
                )
            ]
        )
        
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        
        assert data["status"] == "PASS"
        assert data["total_required"] == 3
        assert data["details"][0]["match_type"] == "exact"
    
    def test_check_result_to_dict(self):
        """测试完整检查结果转字典"""
        result = CheckResult(
            status=CheckStatus.HAS_ISSUES,
            summary=CheckSummary(
                project_id="proj_123",
                total_documents=5,
                completeness_status=CheckStatus.PASS,
                timeliness_status=CheckStatus.HAS_ISSUES,
                compliance_status=CheckStatus.PASS,
                overall_status=CheckStatus.HAS_ISSUES
            ),
            issues=[
                IssueItem(
                    index=1,
                    issue_type="测试",
                    document_name="测试文档",
                    description="测试问题"
                )
            ]
        )
        
        data = result.model_dump()
        
        assert data["status"] == "HAS_ISSUES"
        assert data["summary"]["total_documents"] == 5
        assert len(data["issues"]) == 1
    
    def test_enum_serialization(self):
        """测试枚举值序列化为字符串"""
        match = DocumentMatch(
            document_name="测试",
            status=CheckStatus.VALID,
            match_type=MatchType.SEMANTIC,
            similarity=0.85
        )
        
        data = match.model_dump()
        
        # 枚举应该序列化为字符串值
        assert data["status"] == "VALID"
        assert isinstance(data["status"], str)
        assert data["match_type"] == "semantic"
        assert isinstance(data["match_type"], str)
    
    def test_deserialization(self):
        """测试从字典反序列化"""
        data = {
            "status": "PASS",
            "total_required": 3,
            "uploaded": 3,
            "missing": 0,
            "details": []
        }
        
        result = CompletenessResult.model_validate(data)
        
        assert result.status == CheckStatus.PASS
        assert result.total_required == 3
    
    def test_datetime_serialization(self):
        """测试日期时间序列化"""
        check_time = datetime(2024, 1, 15, 10, 30, 0)
        
        summary = CheckSummary(
            check_time=check_time,
            total_documents=1,
            completeness_status=CheckStatus.PASS,
            timeliness_status=CheckStatus.PASS,
            compliance_status=CheckStatus.PASS,
            overall_status=CheckStatus.PASS
        )
        
        # 使用 mode='json' 来序列化 datetime
        from pydantic import ConfigDict
        data = summary.model_dump(mode='json')
        
        # datetime 应该被序列化为 ISO 格式字符串
        assert isinstance(data["check_time"], str)
        assert "2024-01-15" in data["check_time"]
