"""
时效性检查器 - 适配新架构

包装原有的 check_timeliness 功能为检查器类
"""

import logging
from typing import Any, Dict, List, Optional

from ..core.checker_base import BaseChecker, CheckResult, CheckStatus
from ..core.document import Document
from ..core.checklist_model import Checklist
from ..tools.timeliness import TimelinessChecker as LegacyChecker

logger = logging.getLogger(__name__)


class TimelinessChecker(BaseChecker):
    """
    时效性检查器

    检查文档日期（签发日期、有效期）是否与项目周期匹配。
    """

    @property
    def name(self) -> str:
        return "timeliness"

    @property
    def description(self) -> str:
        return "检查文档日期有效性，与项目周期比对"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def check(
        self, documents: List[Document], checklist: Optional[Checklist], doc_checks: Dict[str, Any]
    ) -> CheckResult:
        """
        执行时效性检查

        Args:
            documents: 文档列表
            checklist: 审核清单（用于获取项目周期和有效期规则）
            doc_checks: 检查配置
                - date_rules: 自定义日期规则列表（可选）

        Returns:
            CheckResult: 检查结果
        """
        if not documents:
            return CheckResult(
                check_type=self.name, status=CheckStatus.PASS, message="没有文档需要检查时效性", details={}
            )

        # 获取项目周期
        project_period = None
        if checklist and checklist.project_period:
            project_period = {
                "start": checklist.project_period.start,
                "end": checklist.project_period.end,
            }

        # 获取日期规则（从doc_checks或checklist）
        date_rules = doc_checks.get("date_rules", [])

        # 从date_rules构建validity_rule
        validity_rule = None
        if date_rules and isinstance(date_rules, list):
            from ..core.checklist_model import ValidityRule

            validity_rule = ValidityRule()
            for rule in date_rules:
                rule_type = rule.get("type")
                if rule_type == "issue_date":
                    expected_date = rule.get("expected_date")
                    expected_before = rule.get("expected_before")
                    expected_after = rule.get("expected_after")
                    if expected_date:
                        # 精确匹配某一天
                        validity_rule.issue_after = expected_date
                        validity_rule.issue_before = expected_date
                    if expected_before:
                        # 不晚于某天
                        validity_rule.issue_before = expected_before
                    if expected_after:
                        # 不早于某天
                        validity_rule.issue_after = expected_after
                elif rule_type == "before_date":
                    # 签发日期不晚于指定日期
                    validity_rule.issue_before = rule.get("value")
                elif rule_type == "after_date":
                    # 签发日期不早于指定日期
                    validity_rule.issue_after = rule.get("value")
                elif rule_type == "valid_period":
                    validity_rule.cover_project = True

        try:
            # 使用原有的检查逻辑
            legacy_checker = LegacyChecker(project_period=project_period)

            # 如果构建的validity_rule不为空，使用它
            if validity_rule and (
                validity_rule.issue_after
                or validity_rule.issue_before
                or validity_rule.cover_project
            ):
                # 逐个文档检查，传入validity_rule
                from ..tools.timeliness import TimelinessDetail, TimelinessResult
                from ..core.result_model import CheckStatus as ResultCheckStatus

                details = []
                valid_count = 0
                expired_count = 0
                unclear_count = 0

                for doc in documents:
                    detail = legacy_checker.check_document(doc, validity_rule)
                    details.append(detail)

                    if detail.status == ResultCheckStatus.VALID:
                        valid_count += 1
                    elif detail.status in (ResultCheckStatus.EXPIRED, ResultCheckStatus.FAIL):
                        expired_count += 1
                    else:
                        unclear_count += 1

                # 确定整体状态
                if expired_count > 0:
                    status = ResultCheckStatus.HAS_ISSUES
                elif unclear_count > 0:
                    status = ResultCheckStatus.HAS_ISSUES
                else:
                    status = ResultCheckStatus.PASS

                result = TimelinessResult(
                    status=status,
                    checked=len(documents),
                    valid=valid_count,
                    expired=expired_count,
                    unclear=unclear_count,
                    details=details,
                )
            else:
                # 使用原来的方式检查
                result = legacy_checker.check(documents, checklist)

            # 转换结果为新的格式
            if result.status.value in ("PASS", "VALID"):
                status = CheckStatus.PASS
            elif result.status.value == "EXPIRED":
                status = CheckStatus.FAIL
            else:
                status = CheckStatus.FAIL

            # 构建详细信息
            details = {
                "checked": result.checked,
                "valid": result.valid,
                "expired": result.expired,
                "unclear": result.unclear,
                "documents": [
                    {
                        "document_name": d.document_name,
                        "status": d.status.value,
                        "validity": d.validity,
                        "message": d.message,
                    }
                    for d in result.details
                ],
            }

            # 构建问题列表
            issues = []
            for detail in result.details:
                if detail.status.value in ("EXPIRED", "FAIL"):
                    issues.append(
                        {
                            "type": "expired_document",
                            "document": detail.document_name,
                            "message": detail.message,
                            "validity": detail.validity,
                        }
                    )
                elif detail.status.value == "UNCLEAR":
                    issues.append(
                        {
                            "type": "unclear_date",
                            "document": detail.document_name,
                            "message": detail.message,
                            "severity": "warning",
                        }
                    )

            message = f"时效性检查完成: {result.valid}/{result.checked} 文档有效"
            if result.expired > 0:
                message += f", {result.expired} 个文档已过期"
            if result.unclear > 0:
                message += f", {result.unclear} 个文档日期不明确"

            return CheckResult(
                check_type=self.name, status=status, message=message, details=details, issues=issues
            )

        except Exception as e:
            logger.exception(f"时效性检查失败: {e}")
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {str(e)}",
                details={"error": str(e)},
            )

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证配置"""
        date_rules = config.get("date_rules", [])
        if date_rules and not isinstance(date_rules, list):
            return False, "date_rules 必须是列表"
        return True, ""
