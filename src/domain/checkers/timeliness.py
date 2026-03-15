"""
时效性检查器 - Domain 层实现（全新业务规则版本）

检查文档日期（签发日期、有效期）是否符合实际审批业务场景。
遵循架构红线：
- 继承 Core 层的 BaseChecker
- 输入使用 Core 层的 Document 和配置
- 输出使用 Core 层的 CheckResult
- 不包含文件读取、LLM 调用逻辑
- 不导入任何 infrastructure 或旧的 tools 模块

全新业务规则（4步判定）：
1. 提取有效期（Validity Period）
2. 提取落款日期（Sign Date）
3. 确定比对基准时间（Reference Time）
4. 核心判定矩阵
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, NamedTuple
from dateutil.relativedelta import relativedelta

from ...core.checker_base import BaseChecker, CheckResult, CheckStatus
from ...core.checklist_model import Checklist
from ...core.document import Document

logger = logging.getLogger(__name__)


class ValidityPeriod(NamedTuple):
    """有效期数据结构"""
    value: int  # 数值
    unit: str   # 单位: years, months, days
    is_permanent: bool = False  # 是否长期有效


class DateMatch(NamedTuple):
    """日期匹配结果"""
    date: datetime
    position: int  # 在文本中的位置
    distance_to_keyword: int  # 距离最近关键词的字符数


class TimelinessChecker(BaseChecker):
    """
    时效性检查器 - 全新业务规则实现

    核心判定逻辑：
    - 分支 A：有有效期但无落款日期 → 不通过
    - 分支 B：有落款日期但无有效期（长期有效）→ 落款日期 ≤ 基准时间则通过
    - 分支 C：两者都有 → 落款日期 ≤ 基准时间 ≤ 截止日期则通过
    """

    # 有效期提取正则模式
    VALIDITY_PATTERNS = [
        # 数字 + 单位格式
        (r"有效期[限\s]*[:：]?\s*(\d+)\s*年", "years"),
        (r"有效期[限\s]*[:：]?\s*(\d+)\s*个月", "months"),
        (r"有效期[限\s]*[:：]?\s*(\d+)\s*月", "months"),
        (r"有效期[限\s]*[:：]?\s*(\d+)\s*天", "days"),
        (r"有效期[限\s]*[:：]?\s*(\d+)\s*日", "days"),
        # 中文数字格式
        (r"有效期[限\s]*[:：]?\s*([一二三四五六七八九十百千万]+)\s*年", "years_chinese"),
        (r"有效期[限\s]*[:：]?\s*([一二三四五六七八九十百千万]+)\s*个月", "months_chinese"),
        (r"有效期[限\s]*[:：]?\s*([一二三四五六七八九十百千万]+)\s*月", "months_chinese"),
        (r"有效期[限\s]*[:：]?\s*([一二三四五六七八九十百千万]+)\s*天", "days_chinese"),
        (r"有效期[限\s]*[:：]?\s*([一二三四五六七八九十百千万]+)\s*日", "days_chinese"),
        # 长期/永久有效
        (r"(长期有效|永久有效|长期|永久)", "permanent"),
    ]

    # 日期提取正则模式
    DATE_PATTERNS = [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "ymd"),      # 2024年3月15日
        (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),              # 2024-03-15
        (r"(\d{4})/(\d{2})/(\d{2})", "ymd"),              # 2024/03/15
        (r"(\d{4})\.(\d{2})\.(\d{2})", "ymd"),            # 2024.03.15
    ]

    # 关键词列表（用于启发式定位落款日期）
    SIGN_KEYWORDS = [
        "签发", "日期", "盖章", "签字", "签署", "签章",
        "批准", "审批", "核准", "审核", "审定",
        "印发", "发布", "发文", "出具", "开具",
        "年月日", "签名", "盖章处"
    ]

    # 中文数字映射
    CHINESE_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100, '千': 1000, '万': 10000
    }

    def __init__(self, project_period: Optional[Dict[str, str]] = None):
        """
        初始化检查器

        Args:
            project_period: 可选的项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}
        """
        self.project_period = project_period

    @property
    def name(self) -> str:
        return "timeliness"

    @property
    def description(self) -> str:
        return "检查文档时效性：验证有效期与落款日期的合规性"

    @property
    def version(self) -> str:
        return "3.0.0"

    def _chinese_to_number(self, chinese: str) -> int:
        """将中文数字转换为阿拉伯数字"""
        if not chinese:
            return 0

        # 简单处理，支持 "三十天"、"一年" 等
        result = 0
        temp = 0
        for char in chinese:
            if char in self.CHINESE_NUMBERS:
                num = self.CHINESE_NUMBERS[char]
                if num >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * num
                    temp = 0
                else:
                    temp = temp * 10 + num if temp > 0 else num
        result += temp
        return result if result > 0 else 1

    def _extract_validity_period(self, text: str) -> Optional[ValidityPeriod]:
        """
        步骤 1: 提取有效期（Validity Period）

        从文档内容中提取有效期，支持多种格式：
        - "有效期一年"、"有效期限: 6个月"、"有效期三十天"
        - 未提取到则默认返回长期有效（is_permanent=True）

        Args:
            text: 文档文本内容

        Returns:
            ValidityPeriod 对象，未找到则返回 None（调用方应视为长期有效）
        """
        for pattern, unit in self.VALIDITY_PATTERNS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                match = matches[0]  # 取第一个匹配
                if unit == "permanent":
                    return ValidityPeriod(value=0, unit="permanent", is_permanent=True)

                try:
                    value_str = match.group(1)
                    if "chinese" in unit:
                        value = self._chinese_to_number(value_str)
                        unit = unit.replace("_chinese", "")
                    else:
                        value = int(value_str)

                    return ValidityPeriod(value=value, unit=unit, is_permanent=False)
                except (ValueError, IndexError):
                    continue

        # 未提取到有效期声明，返回 None（调用方应视为长期有效）
        return None

    def _extract_all_dates(self, text: str) -> List[DateMatch]:
        """
        提取文本中所有日期

        Args:
            text: 文档文本

        Returns:
            DateMatch 列表
        """
        dates = []
        for pattern, fmt in self.DATE_PATTERNS:
            for match in re.finditer(pattern, text):
                try:
                    groups = match.groups()
                    year = int(groups[0])
                    month = int(groups[1])
                    day = int(groups[2])

                    # 验证日期有效性
                    if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        dt = datetime(year, month, day)
                        dates.append(DateMatch(
                            date=dt,
                            position=match.start(),
                            distance_to_keyword=float('inf')
                        ))
                except (ValueError, IndexError):
                    continue
        return dates

    def _find_nearest_keyword_distance(self, text: str, position: int) -> int:
        """
        计算指定位置到最近关键词的字符距离

        Args:
            text: 文档文本
            position: 日期位置

        Returns:
            到最近关键词的字符距离（如果没有匹配到任何关键词，返回一个足够大的值）
        """
        min_distance = float('inf')

        for keyword in self.SIGN_KEYWORDS:
            for match in re.finditer(keyword, text):
                keyword_pos = match.start()
                distance = abs(position - keyword_pos)
                min_distance = min(min_distance, distance)

        # 如果没有匹配到任何关键词，返回一个足够大的值（大于阈值）
        # 确保调用方能够正确识别"无关键词"的情况
        KEYWORD_PROXIMITY_THRESHOLD = 500
        if min_distance == float('inf'):
            return KEYWORD_PROXIMITY_THRESHOLD + 1

        return int(min_distance)

    def _extract_sign_date(self, text: str) -> Optional[datetime]:
        """
        步骤 2: 提取落款日期（Sign Date）

        启发式规则：
        1. 优先选取距离"签发"、"日期"、"盖章"、"签字"等关键词最近的日期
        2. 如果无明显关键词，默认取文档末尾（倒序查找）的最后一个日期

        Args:
            text: 文档文本内容

        Returns:
            datetime 对象，未找到则返回 None
        """
        # 提取所有日期
        dates = self._extract_all_dates(text)

        if not dates:
            return None

        # 计算每个日期到最近关键词的距离
        dated_with_distance = []
        for dm in dates:
            distance = self._find_nearest_keyword_distance(text, dm.position)
            dated_with_distance.append(DateMatch(
                date=dm.date,
                position=dm.position,
                distance_to_keyword=distance
            ))

        # 检查是否有日期靠近关键词（距离小于阈值，比如500字符）
        KEYWORD_PROXIMITY_THRESHOLD = 500
        near_keyword_dates = [
            dm for dm in dated_with_distance
            if dm.distance_to_keyword < KEYWORD_PROXIMITY_THRESHOLD
        ]

        if near_keyword_dates:
            # 优先选择距离关键词最近的日期
            nearest = min(near_keyword_dates, key=lambda x: x.distance_to_keyword)
            return nearest.date
        else:
            # 无明显关键词，取文档末尾的最后一个日期（按位置排序，取最后一个）
            latest_position_date = max(dates, key=lambda x: x.position)
            return latest_position_date.date

    def _get_reference_time(self, config: Dict[str, Any]) -> datetime:
        """
        步骤 3: 确定比对基准时间（Reference Time）

        如果调用方传入了校验时间参数，则使用传入时间；
        如果未传入，则直接获取服务器当前真实时间（datetime.now()）作为基准时间。

        Args:
            config: 检查配置，可能包含 reference_time

        Returns:
            基准时间 datetime 对象
        """
        # 检查配置中是否有传入的校验时间
        reference_time_str = config.get("reference_time")

        if reference_time_str:
            try:
                # 尝试解析传入的时间字符串
                # 支持格式: YYYY-MM-DD, YYYY-MM-DD HH:MM:SS, ISO格式
                for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        return datetime.strptime(reference_time_str, fmt)
                    except ValueError:
                        continue
                # 尝试 ISO 格式
                from datetime import timezone
                return datetime.fromisoformat(reference_time_str.replace('Z', '+00:00'))
            except Exception:
                logger.warning(f"无法解析传入的校验时间: {reference_time_str}，使用当前时间")

        # 使用当前服务器时间
        return datetime.now()

    def _calculate_expiry_date(self, sign_date: datetime, validity: ValidityPeriod) -> datetime:
        """
        根据落款日期和有效期计算截止日期

        Args:
            sign_date: 落款日期
            validity: 有效期

        Returns:
            截止日期
        """
        if validity.is_permanent:
            # 长期有效，返回一个极远的日期
            return datetime(2099, 12, 31)

        if validity.unit == "years":
            return sign_date + relativedelta(years=validity.value)
        elif validity.unit == "months":
            return sign_date + relativedelta(months=validity.value)
        elif validity.unit == "days":
            return sign_date + timedelta(days=validity.value)
        else:
            return sign_date + relativedelta(years=1)  # 默认一年

    def _evaluate_document(
        self,
        document: Document,
        reference_time: datetime
    ) -> Dict[str, Any]:
        """
        步骤 4: 核心判定矩阵

        判定分支：
        - 分支 A：有有效期但无落款日期 → 不通过
        - 分支 B：有落款日期但无有效期（长期有效）→ 落款日期 ≤ 基准时间则通过
        - 分支 C：两者都有 → 落款日期 ≤ 基准时间 ≤ 截止日期则通过

        Args:
            document: 文档对象
            reference_time: 基准时间

        Returns:
            判定结果字典
        """
        text = document.content or ""

        # 提取有效期和落款日期
        validity = self._extract_validity_period(text)
        sign_date = self._extract_sign_date(text)

        has_validity = validity is not None
        has_sign_date = sign_date is not None

        result = {
            "document_name": document.name,
            "has_validity": has_validity,
            "has_sign_date": has_sign_date,
            "validity": None,
            "sign_date": sign_date.strftime("%Y-%m-%d") if sign_date else None,
            "expiry_date": None,
            "reference_time": reference_time.strftime("%Y-%m-%d %H:%M:%S"),
            "passed": False,
            "reason": "",
            "branch": None
        }

        if validity:
            result["validity"] = {
                "value": validity.value,
                "unit": validity.unit,
                "is_permanent": validity.is_permanent
            }

        # 格式化日期显示
        sign_date_str = result["sign_date"] if result["sign_date"] else "未提取到"
        ref_time_str = reference_time.strftime("%Y-%m-%d")

        # 构建有效期说明
        if validity:
            if validity.is_permanent:
                validity_desc = "长期有效"
            elif validity.unit == "years":
                validity_desc = f"有效期{validity.value}年"
            elif validity.unit == "months":
                validity_desc = f"有效期{validity.value}个月"
            elif validity.unit == "days":
                validity_desc = f"有效期{validity.value}天"
            else:
                validity_desc = f"有效期{validity.value}{validity.unit}"
        else:
            validity_desc = "长期有效（未声明有效期）"

        # 分支 A：有有效期但无落款日期
        if has_validity and not has_sign_date:
            result["branch"] = "A"
            result["passed"] = False
            result["reason"] = f"印章时间未提取到，{validity_desc}，晚于当前时间{ref_time_str}，有效期审查未通过。"
            return result

        # 分支 B：有落款日期但无有效期（视为长期有效）
        if has_sign_date and not has_validity:
            result["branch"] = "B"
            # 长期有效
            result["validity"] = {"is_permanent": True}

            if sign_date <= reference_time:
                result["passed"] = True
                result["reason"] = f"印章时间{sign_date_str}，长期有效，早于当前时间{ref_time_str}，有效期审查通过。"
            else:
                result["passed"] = False
                result["reason"] = f"印章时间{sign_date_str}，长期有效，晚于当前时间{ref_time_str}，有效期审查未通过。"
            return result

        # 分支 C：两者都有
        if has_sign_date and has_validity:
            result["branch"] = "C"
            expiry_date = self._calculate_expiry_date(sign_date, validity)
            result["expiry_date"] = expiry_date.strftime("%Y-%m-%d")
            expiry_date_str = result["expiry_date"]

            # 判定条件：落款日期 ≤ 基准时间 ≤ 截止日期
            if sign_date > reference_time:
                result["passed"] = False
                result["reason"] = f"印章时间{sign_date_str}，{validity_desc}，晚于当前时间{ref_time_str}，有效期审查未通过。"
            elif reference_time > expiry_date:
                result["passed"] = False
                result["reason"] = f"印章时间{sign_date_str}，{validity_desc}，早于当前时间{ref_time_str}但已过期（有效期至{expiry_date_str}），有效期审查未通过。"
            else:
                result["passed"] = True
                if validity.is_permanent:
                    result["reason"] = f"印章时间{sign_date_str}，{validity_desc}，早于当前时间{ref_time_str}，有效期审查通过。"
                else:
                    result["reason"] = f"印章时间{sign_date_str}，{validity_desc}，早于当前时间{ref_time_str}且在有效期内（至{expiry_date_str}），有效期审查通过。"
            return result

        # 特殊情况：两者都没有
        result["branch"] = "NONE"
        result["passed"] = False
        result["reason"] = f"印章时间未提取到，有效期信息缺失，无法完成时效性审查。"
        return result

    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        config: Dict[str, Any]
    ) -> CheckResult:
        """
        执行时效性检查

        Args:
            documents: 文档列表
            checklist: 审核清单（可选）
            config: 检查配置
                - reference_time: 自定义校验时间（可选）

        Returns:
            CheckResult: 检查结果
        """
        if not documents:
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.PASS,
                message="没有文档需要检查时效性",
                details={}
            )

        # 步骤 3: 确定基准时间
        reference_time = self._get_reference_time(config)

        try:
            document_results = []
            passed_count = 0
            failed_count = 0
            unclear_count = 0
            issues = []

            for doc in documents:
                # 步骤 4: 对每个文档执行核心判定
                eval_result = self._evaluate_document(doc, reference_time)
                document_results.append(eval_result)

                if eval_result["passed"]:
                    passed_count += 1
                elif eval_result["branch"] == "NONE":
                    unclear_count += 1
                else:
                    failed_count += 1
                    issues.append({
                        "type": "timeliness_failed",
                        "document": doc.name,
                        "branch": eval_result["branch"],
                        "reason": eval_result["reason"],
                        "sign_date": eval_result["sign_date"],
                        "expiry_date": eval_result["expiry_date"]
                    })

            # 确定整体状态
            if failed_count > 0:
                status = CheckStatus.FAIL
            elif unclear_count > 0:
                status = CheckStatus.UNAVAILABLE
            else:
                status = CheckStatus.PASS

            # 构建详细信息
            details = {
                "checked": len(documents),
                "passed": passed_count,
                "failed": failed_count,
                "unclear": unclear_count,
                "reference_time": reference_time.strftime("%Y-%m-%d %H:%M:%S"),
                "documents": document_results
            }

            # 构建消息
            message = f"时效性检查完成: {passed_count}/{len(documents)} 文档通过"
            if failed_count > 0:
                message += f", {failed_count} 个文档未通过"
            if unclear_count > 0:
                message += f", {unclear_count} 个文档信息不明确"

            return CheckResult(
                check_type=self.name,
                status=status,
                message=message,
                details=details,
                issues=issues
            )

        except Exception as e:
            logger.exception(f"时效性检查失败: {e}")
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {str(e)}",
                details={"error": str(e)}
            )

    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """验证配置"""
        reference_time = config.get("reference_time")
        if reference_time and not isinstance(reference_time, str):
            return False, "reference_time 必须是字符串格式"
        return True, ""
