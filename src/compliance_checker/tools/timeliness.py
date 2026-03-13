"""
timeliness.py - 时效性检查工具
实现 check_timeliness MCP 工具
用于检查文档日期（签发日期、有效期）是否与项目周期匹配
"""

import re
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from ..core.document import Document
from ..core.checklist_model import Checklist, ValidityRule
from ..core.result_model import TimelinessResult, TimelinessDetail, CheckStatus

logger = logging.getLogger(__name__)


# 日期提取正则表达式模式
DATE_PATTERNS = [
    # 标准日期格式
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "ymd"),  # 2024年3月15日
    (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),  # 2024-03-15
    (r"(\d{4})/(\d{2})/(\d{2})", "ymd"),  # 2024/03/15
    (r"(\d{4})\.(\d{2})\.(\d{2})", "ymd"),  # 2024.03.15
    # 年月格式
    (r"(\d{4})年(\d{1,2})月", "ym"),  # 2024年3月
    (r"(\d{4})-(\d{2})", "ym"),  # 2024-03
    (r"(\d{4})/(\d{2})", "ym"),  # 2024/03
    # 中文日期描述
    (r"有效期[至到](\d{4})年(\d{1,2})月(\d{1,2})日", "valid_to_ymd"),  # 有效期至2024年3月15日
    (r"有效期[至到](\d{4})-(\d{2})-(\d{2})", "valid_to_ymd"),  # 有效期至2024-03-15
    (r"有效期[至到](\d{4})年(\d{1,2})月", "valid_to_ym"),  # 有效期至2024年3月
    (r"有效期[至到](\d{4})-(\d{2})", "valid_to_ym"),  # 有效期至2024-03
    (r"有效期[至到](\d{4})年", "valid_to_y"),  # 有效期至2024年
    (r"有效期[至到](\d{4})", "valid_to_y"),  # 有效期至2024
    # 签发日期
    (r"签发日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    (r"签发日期[：:]\s*(\d{4})-(\d{2})-(\d{2})", "issue_ymd"),
    (r"签发[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    # 发布/印发日期
    (r"发布日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    (r"印发日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    # 开票日期 - 支持多种格式，包括换行后的日期
    (r"开票日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    (r"开票日期[：:]\s*(\d{4})-(\d{2})-(\d{2})", "issue_ymd"),
    (r"开票日期.*?(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    (r"日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    # 发票专用 - 直接匹配日期格式（在发票上下文中）
    (r"发票.*?(\d{4})年(\d{1,2})月(\d{1,2})日", "issue_ymd"),
    # 起始日期
    (r"起始日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "valid_from_ymd"),
    (r"开始日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "valid_from_ymd"),
    (r"自(\d{4})年(\d{1,2})月(\d{1,2})日起", "valid_from_ymd"),
    # 截止日期
    (r"截止日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "valid_to_ymd"),
    (r"结束日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", "valid_to_ymd"),
    (r"至(\d{4})年(\d{1,2})月(\d{1,2})日止", "valid_to_ymd"),
]

# 有效期描述模式 - 用于提取有效期说明文字
VALIDITY_DESCRIPTION_PATTERNS = [
    # 有效期N年/月/日
    (r"有效期\s*(\d+)\s*年", "years"),
    (r"有效期\s*(\d+)\s*个月", "months"),
    (r"有效期\s*(\d+)\s*月", "months"),
    (r"有效期\s*(\d+)\s*天", "days"),
    (r"有效期\s*(\d+)\s*日", "days"),
    # 长期/永久有效
    (r"(长期有效|永久有效|长期|永久)", "permanent"),
    # 本文件/证书/批文有效期
    (r"本(文件|证书|批文|证明|发票).*?有效期", "has_validity"),
]


class DateExtractor:
    """日期提取器"""

    def __init__(self):
        self.patterns = DATE_PATTERNS
        self.validity_patterns = VALIDITY_DESCRIPTION_PATTERNS

    def extract_validity_description(self, text: str) -> Dict[str, Any]:
        """
        提取有效期描述信息

        Returns:
            {
                "has_explicit_validity": bool,  # 是否有明确的有效期描述
                "validity_type": str,           # "years", "months", "days", "permanent", "has_validity"
                "validity_value": int or None,  # 有效期数值（年/月/日）
                "description": str,             # 原始描述文字
                "is_permanent": bool            # 是否长期/永久有效
            }
        """
        result = {
            "has_explicit_validity": False,
            "validity_type": None,
            "validity_value": None,
            "description": None,
            "is_permanent": False,
        }

        for pattern, validity_type in self.validity_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                result["has_explicit_validity"] = True
                result["validity_type"] = validity_type
                result["description"] = match.group(0)

                if validity_type == "permanent":
                    result["is_permanent"] = True
                elif validity_type in ("years", "months", "days"):
                    # 提取数值
                    if match.groups():
                        try:
                            result["validity_value"] = int(match.group(1))
                        except (ValueError, IndexError):
                            pass

                return result  # 返回第一个匹配

        return result

    def calculate_validity_from_description(
        self, validity_desc: Dict[str, Any], issue_date: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        根据有效期描述计算有效期结束日期

        Args:
            validity_desc: 有效期描述
            issue_date: 签发日期

        Returns:
            有效期结束日期或 None
        """
        if validity_desc.get("is_permanent"):
            return None  # 长期有效，无结束日期

        if not issue_date:
            return None

        validity_type = validity_desc.get("validity_type")
        validity_value = validity_desc.get("validity_value")

        if not validity_type or not validity_value:
            return None

        try:
            if validity_type == "years":
                return issue_date + relativedelta(years=validity_value)
            elif validity_type == "months":
                return issue_date + relativedelta(months=validity_value)
            elif validity_type == "days":
                return issue_date + relativedelta(days=validity_value)
        except Exception as e:
            logger.warning(f"计算有效期失败: {e}")

        return None

    def extract_dates(self, text: str) -> Dict[str, List[datetime]]:
        """
        从文本中提取各种日期

        Returns:
            {
                "issue_dates": [datetime],      # 签发日期
                "valid_from_dates": [datetime], # 有效期开始
                "valid_to_dates": [datetime],   # 有效期结束
                "all_dates": [datetime]         # 所有日期
            }
        """
        result = {"issue_dates": [], "valid_from_dates": [], "valid_to_dates": [], "all_dates": []}

        for pattern, date_type in self.patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    groups = match.groups()
                    if len(groups) >= 1:
                        year = int(groups[0])
                        month = int(groups[1]) if len(groups) >= 2 else 12  # 默认12月
                        day = int(groups[2]) if len(groups) >= 3 else 31  # 默认31日

                        # 验证日期有效性
                        if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                            dt = datetime(year, month, day)

                            if date_type in ("issue_ymd", "issue_ym", "issue_y"):
                                result["issue_dates"].append(dt)
                            elif date_type in ("valid_from_ymd", "valid_from_ym", "valid_from_y"):
                                result["valid_from_dates"].append(dt)
                            elif date_type in ("valid_to_ymd", "valid_to_ym", "valid_to_y"):
                                result["valid_to_dates"].append(dt)

                            result["all_dates"].append(dt)

                except (ValueError, IndexError) as e:
                    logger.debug(f"日期解析失败: {match.group()}, 错误: {e}")
                    continue

        return result

    def _extract_invoice_date(self, text: str) -> Optional[str]:
        """
        专门提取发票开票日期
        处理开票日期和日期值之间有换行的情况
        """
        # 模式1: 开票日期后紧跟日期（在同一行或换行后）
        patterns = [
            # 开票日期: 2026年01月19日（支持换行）
            r"开票日期[：:]\s*\n?\s*(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"开票日期[：:]\s*\n?\s*(\d{4})-(\d{2})-(\d{2})",
            # 在"开票日期"标签附近查找日期（前后100字符）
            r"开票日期.{0,100}?(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"开票日期.{0,100}?(\d{4})-(\d{2})-(\d{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        return f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    continue

        # 模式2: 如果没有找到明确的开票日期标签，但文档是发票类型
        # 查找所有日期，选择最可能是开票日期的那个
        if "发票" in text:
            all_dates = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
            if all_dates:
                # 选择第一个找到的日期作为开票日期
                year, month, day = all_dates[0]
                try:
                    y, m, d = int(year), int(month), int(day)
                    if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                        return f"{y:04d}-{m:02d}-{d:02d}"
                except ValueError:
                    pass

        return None

    def extract_document_dates(self, document: Document) -> Dict[str, Optional[str]]:
        """
        提取文档的关键日期

        Returns:
            {
                "issue_date": "YYYY-MM-DD" or None,
                "valid_from": "YYYY-MM-DD" or None,
                "valid_to": "YYYY-MM-DD" or None
            }
        """
        text = document.content
        extracted = self.extract_dates(text)

        # 尝试专门提取发票日期
        invoice_date = self._extract_invoice_date(text)

        result = {"issue_date": None, "valid_from": None, "valid_to": None}

        # 优先使用专门提取的发票日期
        if invoice_date:
            result["issue_date"] = invoice_date
        # 然后使用通用日期提取
        elif extracted["issue_dates"]:
            # 优先选择最精确的日期
            valid_dates = [
                d
                for d in extracted["issue_dates"]
                if not (d.month == 12 and d.day == 31) and d.day != 31
            ]
            if valid_dates:
                result["issue_date"] = min(valid_dates).strftime("%Y-%m-%d")
            else:
                result["issue_date"] = min(extracted["issue_dates"]).strftime("%Y-%m-%d")

        if extracted["valid_from_dates"]:
            # 优先选择最精确的日期
            valid_dates = [
                d
                for d in extracted["valid_from_dates"]
                if not (d.month == 12 and d.day == 31) and d.day != 31
            ]
            if valid_dates:
                result["valid_from"] = min(valid_dates).strftime("%Y-%m-%d")
            else:
                result["valid_from"] = min(extracted["valid_from_dates"]).strftime("%Y-%m-%d")

        if extracted["valid_to_dates"]:
            # 优先选择最精确的日期（不是默认的12月31日或31日）
            # 按日期分组，选择有具体日期的
            valid_dates = [
                d
                for d in extracted["valid_to_dates"]
                if not (d.month == 12 and d.day == 31) and d.day != 31
            ]
            if valid_dates:
                result["valid_to"] = max(valid_dates).strftime("%Y-%m-%d")
            else:
                result["valid_to"] = max(extracted["valid_to_dates"]).strftime("%Y-%m-%d")

        # 如果没有明确的有效期结束日期，尝试从有效期描述计算
        if not result["valid_to"]:
            validity_desc = self.extract_validity_description(text)

            if validity_desc.get("has_explicit_validity"):
                if validity_desc.get("is_permanent"):
                    # 长期/永久有效 - 不设置valid_to表示永久有效
                    result["valid_to"] = None
                    result["validity_description"] = validity_desc
                else:
                    # 根据有效期描述计算结束日期
                    issue_date = None
                    if result["issue_date"]:
                        issue_date = datetime.strptime(result["issue_date"], "%Y-%m-%d")
                    elif result["valid_from"]:
                        issue_date = datetime.strptime(result["valid_from"], "%Y-%m-%d")

                    if issue_date:
                        calculated_valid_to = self.calculate_validity_from_description(
                            validity_desc, issue_date
                        )
                        if calculated_valid_to:
                            result["valid_to"] = calculated_valid_to.strftime("%Y-%m-%d")
                            result["validity_description"] = validity_desc
                            result["validity_calculated"] = True

        # 如果没有找到任何有效期信息，视为长期有效
        if not result["valid_to"] and not result.get("validity_description"):
            result["validity_description"] = {
                "has_explicit_validity": False,
                "is_permanent": True,
                "note": "未找到有效期描述，视为长期有效",
            }

        return result


class TimelinessChecker:
    """时效性检查器"""

    def __init__(self, project_period: Optional[Dict[str, str]] = None):
        """
        初始化检查器

        Args:
            project_period: 项目周期 {"start": "2025-01", "end": "2027-12"}
        """
        self.project_period = project_period
        self.date_extractor = DateExtractor()

    def _parse_period(self, period_str: str) -> datetime:
        """解析周期字符串为日期"""
        try:
            # 支持 "2025-01" 或 "2025-01-01" 格式
            if len(period_str) == 7:  # YYYY-MM
                return datetime.strptime(period_str + "-01", "%Y-%m-%d")
            else:
                return datetime.strptime(period_str, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"无法解析日期: {period_str}")
            return datetime.now()

    def _check_date_coverage(
        self,
        valid_from: Optional[str],
        valid_to: Optional[str],
        project_start: datetime,
        project_end: datetime,
        validity_description: Optional[Dict] = None,
    ) -> Tuple[CheckStatus, str]:
        """
        检查日期是否覆盖项目周期

        Args:
            valid_from: 有效期开始日期
            valid_to: 有效期结束日期
            project_start: 项目开始日期
            project_end: 项目结束日期
            validity_description: 有效期描述信息

        Returns:
            (状态, 说明信息)
        """
        # 检查是否有明确的有效期描述
        if validity_description:
            if validity_description.get("is_permanent"):
                # 长期/永久有效
                if valid_from:
                    try:
                        doc_valid_from = datetime.strptime(valid_from, "%Y-%m-%d")
                        if doc_valid_from <= project_end:
                            return CheckStatus.VALID, "文档长期有效，签发日期在项目周期内"
                    except ValueError:
                        pass
                return CheckStatus.VALID, "文档长期/永久有效"

            if validity_description.get("validity_calculated"):
                # 根据描述计算的有效期
                desc = validity_description.get("description", "")
                return CheckStatus.VALID, f"根据有效期描述'{desc}'计算，有效期至 {valid_to}"

        if not valid_to and not valid_from:
            return CheckStatus.UNCLEAR, "无法提取有效期信息"

        try:
            doc_valid_from = datetime.strptime(valid_from, "%Y-%m-%d") if valid_from else None
            doc_valid_to = datetime.strptime(valid_to, "%Y-%m-%d") if valid_to else None
        except ValueError:
            return CheckStatus.UNCLEAR, f"日期格式无效: from={valid_from}, to={valid_to}"

        # 如果没有有效期结束，假设长期有效
        if not doc_valid_to:
            # 检查签发日期是否早于项目结束
            if doc_valid_from and doc_valid_from <= project_end:
                return CheckStatus.VALID, "签发日期在项目周期内，无明确有效期结束（视为长期有效）"
            return CheckStatus.UNCLEAR, "无法确定有效期结束时间"

        # 检查是否覆盖项目周期
        # 文档有效期结束 >= 项目结束 且 文档有效期开始 <= 项目开始
        covers_end = doc_valid_to >= project_end
        covers_start = (doc_valid_from is None) or (doc_valid_from <= project_start)

        if covers_end and covers_start:
            return CheckStatus.VALID, f"有效期 {valid_from} 至 {valid_to} 覆盖项目周期"
        elif not covers_end:
            return (
                CheckStatus.EXPIRED,
                f"有效期至 {valid_to}，未覆盖项目结束时间 {project_end.strftime('%Y-%m-%d')}",
            )
        elif not covers_start:
            return CheckStatus.WARNING, f"有效期开始 {valid_from} 晚于项目开始时间"

        return CheckStatus.UNCLEAR, "覆盖情况不明确"

    def _check_issue_date(
        self, issue_date: Optional[str], rule: ValidityRule
    ) -> Tuple[CheckStatus, str]:
        """检查签发日期是否符合规则"""
        if not issue_date:
            return CheckStatus.UNCLEAR, "无法提取签发日期"

        try:
            issue_dt = datetime.strptime(issue_date, "%Y-%m-%d")
        except ValueError:
            return CheckStatus.UNCLEAR, f"签发日期格式无效: {issue_date}"

        messages = []
        status = CheckStatus.VALID

        # 检查 issue_after
        if rule.issue_after:
            try:
                after_dt = self._parse_period(rule.issue_after)
                if issue_dt < after_dt:
                    status = CheckStatus.FAIL
                    messages.append(f"签发日期 {issue_date} 早于要求时间 {rule.issue_after}")
            except Exception as e:
                logger.warning(f"解析 issue_after 失败: {e}")

        # 检查 issue_before
        if rule.issue_before:
            try:
                before_dt = self._parse_period(rule.issue_before)
                if issue_dt > before_dt:
                    status = CheckStatus.FAIL
                    messages.append(f"签发日期 {issue_date} 晚于要求时间 {rule.issue_before}")
            except Exception as e:
                logger.warning(f"解析 issue_before 失败: {e}")

        if not messages:
            messages.append(f"签发日期 {issue_date} 符合要求")

        return status, "; ".join(messages)

    def check_document(
        self, document: Document, validity_rule: Optional[ValidityRule] = None
    ) -> TimelinessDetail:
        """
        检查单个文档的时效性

        Args:
            document: 文档对象
            validity_rule: 有效期规则（可选）

        Returns:
            时效性检查详情
        """
        # 提取文档日期
        dates = self.date_extractor.extract_document_dates(document)

        # 如果没有项目周期且没有有效期规则，返回不明确
        if not self.project_period and not validity_rule:
            return TimelinessDetail(
                document_name=document.name,
                file_path=document.path,
                validity=dates,
                project_period={},
                status=CheckStatus.UNCLEAR,
                message="未提供项目周期或有效期规则",
            )

        project_period_dict = self.project_period or {}

        # 如果有有效期规则
        if validity_rule:
            # 检查签发日期
            if validity_rule.issue_after or validity_rule.issue_before:
                issue_status, issue_message = self._check_issue_date(
                    dates.get("issue_date"), validity_rule
                )
                if issue_status != CheckStatus.VALID:
                    return TimelinessDetail(
                        document_name=document.name,
                        file_path=document.path,
                        validity=dates,
                        project_period=project_period_dict,
                        status=issue_status,
                        message=issue_message,
                    )
                # 如果签发日期检查通过且不需要检查项目周期覆盖，直接返回
                elif not validity_rule.cover_project:
                    return TimelinessDetail(
                        document_name=document.name,
                        file_path=document.path,
                        validity=dates,
                        project_period=project_period_dict,
                        status=CheckStatus.VALID,
                        message=issue_message,
                    )

            # 检查是否需覆盖项目周期
            if validity_rule.cover_project and self.project_period:
                project_start = self._parse_period(self.project_period.get("start", "1900-01"))
                project_end = self._parse_period(self.project_period.get("end", "2100-12"))

                status, message = self._check_date_coverage(
                    dates.get("valid_from"),
                    dates.get("valid_to"),
                    project_start,
                    project_end,
                    dates.get("validity_description"),
                )

                return TimelinessDetail(
                    document_name=document.name,
                    file_path=document.path,
                    validity=dates,
                    project_period=project_period_dict,
                    status=status,
                    message=message,
                )

        # 仅检查项目周期覆盖
        if self.project_period:
            project_start = self._parse_period(self.project_period.get("start", "1900-01"))
            project_end = self._parse_period(self.project_period.get("end", "2100-12"))

            status, message = self._check_date_coverage(
                dates.get("valid_from"),
                dates.get("valid_to"),
                project_start,
                project_end,
                dates.get("validity_description"),
            )

            return TimelinessDetail(
                document_name=document.name,
                file_path=document.path,
                validity=dates,
                project_period=project_period_dict,
                status=status,
                message=message,
            )

        # 默认返回有效
        return TimelinessDetail(
            document_name=document.name,
            file_path=document.path,
            validity=dates,
            project_period=project_period_dict,
            status=CheckStatus.VALID,
            message="未设置检查规则，默认通过",
        )

    def check(
        self, documents: List[Document], checklist: Optional[Checklist] = None
    ) -> TimelinessResult:
        """
        执行时效性检查

        Args:
            documents: 文档列表
            checklist: 审核清单（可选，用于获取有效期规则）

        Returns:
            时效性检查结果
        """
        details: List[TimelinessDetail] = []
        valid_count = 0
        expired_count = 0
        unclear_count = 0

        for doc in documents:
            # 获取文档对应的有效期规则
            validity_rule = None
            if checklist:
                for req_doc in checklist.required_documents:
                    if req_doc.name in doc.name or doc.name in req_doc.aliases:
                        validity_rule = req_doc.validity
                        break

            detail = self.check_document(doc, validity_rule)
            details.append(detail)

            if detail.status == CheckStatus.VALID:
                valid_count += 1
            elif detail.status == CheckStatus.EXPIRED or detail.status == CheckStatus.FAIL:
                expired_count += 1
            else:
                unclear_count += 1

        # 确定整体状态
        if expired_count > 0:
            status = CheckStatus.HAS_ISSUES
        elif unclear_count > 0:
            status = CheckStatus.HAS_ISSUES
        else:
            status = CheckStatus.PASS

        return TimelinessResult(
            status=status,
            checked=len(documents),
            valid=valid_count,
            expired=expired_count,
            unclear=unclear_count,
            details=details,
        )


async def check_timeliness(
    documents: List[Document],
    project_period: Optional[Dict[str, str]] = None,
    checklist: Optional[Checklist] = None,
    date_rules: Optional[List[Dict[str, Any]]] = None,
) -> TimelinessResult:
    """
    核对资料时效性（MCP工具入口）

    功能：
    - 提取文档日期（签发日期、有效期）
    - 支持多种日期格式（2024年3月15日、2024-03-15、有效期至2026年5月等）
    - 与项目周期比对，判断是否覆盖

    Args:
        documents: 文档列表
        project_period: 项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}
        checklist: 审核清单（用于获取有效期规则）
        date_rules: 自定义日期规则列表（可选）

    Returns:
        时效性检查结果
    """
    # 优先使用清单中的项目周期
    effective_period = project_period
    if checklist and checklist.project_period:
        effective_period = {
            "start": checklist.project_period.start,
            "end": checklist.project_period.end,
        }

    checker = TimelinessChecker(project_period=effective_period)
    return checker.check(documents, checklist)
