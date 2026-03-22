"""
TimelinessChecker（时效性检查器）单元测试 - 全新业务规则版本

测试全新的4步业务规则实现：
1. 提取有效期（Validity Period）
2. 提取落款日期（Sign Date）
3. 确定比对基准时间（Reference Time）
4. 核心判定矩阵（分支 A/B/C）

遵循 architecture.md 中『10.2 Domain 层测试示例』规范：
- 不引入真实 infrastructure
- 使用内存对象构造测试输入
- 至少包含 PASS 和 FAIL 两种核心场景用例
- 详尽的 assert 校验返回字段、异常类型和错误信息
"""

import pytest
from datetime import datetime, timedelta

from src.compliance_checker.core.checker_base import CheckStatus, CheckResult
from src.compliance_checker.core.document import Document, DocumentMetadata, PageContent
from src.compliance_checker.domain.checkers.timeliness import TimelinessChecker, ValidityPeriod, DateMatch

# ============== 辅助函数 ==============


def create_document_with_content(
    file_name: str,
    content: str,
) -> Document:
    """
    创建带有内容的 Document 对象

    Args:
        file_name: 文件名
        content: 文档内容

    Returns:
        Document 实例
    """
    return Document(
        path=f"/test/documents/{file_name}",
        name=file_name,
        pages_content=[
            PageContent(page_num=0, text=content),
        ],
        metadata=DocumentMetadata(),
    )


# ============== 测试 Fixtures ==============


@pytest.fixture
def checker():
    """创建时效性检查器实例"""
    return TimelinessChecker()


@pytest.fixture
def fixed_reference_time():
    """固定的基准时间用于测试"""
    return "2024-06-15"


# ============== 检查器基础属性测试 ==============


@pytest.mark.asyncio
async def test_checker_properties(checker):
    """
    测试场景：验证检查器的基本属性

    预期结果：
    - name 属性为 "timeliness"
    - description 属性存在且不为空
    - version 属性存在
    """
    assert checker.name == "timeliness", "检查器名称应为 'timeliness'"
    assert isinstance(checker.description, str), "description 应为字符串"
    assert len(checker.description) > 0, "description 不应为空"
    assert hasattr(checker, "version"), "应有 version 属性"
    assert checker.version == "3.0.0", "版本应为 3.0.0"


@pytest.mark.asyncio
async def test_checker_init_with_project_period():
    """
    测试场景：使用 project_period 初始化检查器

    预期结果：
    - project_period 被正确保存
    """
    period = {"start": "2024-01", "end": "2026-12"}
    checker = TimelinessChecker(project_period=period)
    assert checker.project_period == period


# ============== 步骤1：提取有效期测试 ==============


@pytest.mark.asyncio
async def test_extract_validity_period_numeric_years(checker):
    """
    测试场景：提取数字格式的有效期（年）

    预期结果：
    - 正确提取 "有效期1年"、"有效期 3 年" 等格式
    """
    # 测试 "有效期1年"
    text1 = "本证书有效期1年"
    result1 = checker._extract_validity_period(text1)
    assert result1 is not None
    assert result1.value == 1
    assert result1.unit == "years"
    assert result1.is_permanent is False

    # 测试 "有效期 3 年"
    text2 = "有效期 3 年"
    result2 = checker._extract_validity_period(text2)
    assert result2.value == 3
    assert result2.unit == "years"


@pytest.mark.asyncio
async def test_extract_validity_period_numeric_months(checker):
    """
    测试场景：提取数字格式的有效期（月）

    预期结果：
    - 正确提取 "有效期6个月"、"有效期 12 月" 等格式
    """
    # 测试 "有效期6个月"
    text1 = "有效期限: 6个月"
    result1 = checker._extract_validity_period(text1)
    assert result1 is not None
    assert result1.value == 6
    assert result1.unit == "months"

    # 测试 "有效期 12 月"
    text2 = "有效期 12 月"
    result2 = checker._extract_validity_period(text2)
    assert result2.value == 12
    assert result2.unit == "months"


@pytest.mark.asyncio
async def test_extract_validity_period_numeric_days(checker):
    """
    测试场景：提取数字格式的有效期（天）

    预期结果：
    - 正确提取 "有效期30天"、"有效期 90 日" 等格式
    """
    # 测试 "有效期30天"
    text1 = "有效期30天"
    result1 = checker._extract_validity_period(text1)
    assert result1 is not None
    assert result1.value == 30
    assert result1.unit == "days"

    # 测试 "有效期 90 日"
    text2 = "有效期 90 日"
    result2 = checker._extract_validity_period(text2)
    assert result2.value == 90
    assert result2.unit == "days"


@pytest.mark.asyncio
async def test_extract_validity_period_chinese(checker):
    """
    测试场景：提取中文数字格式的有效期

    预期结果：
    - 正确提取 "有效期一年"、"有效期三十天" 等格式
    """
    # 测试 "有效期一年"
    text1 = "本证书有效期一年"
    result1 = checker._extract_validity_period(text1)
    assert result1 is not None
    assert result1.value == 1
    assert result1.unit == "years"

    # 测试 "有效期三十天"
    text2 = "有效期三十天"
    result2 = checker._extract_validity_period(text2)
    assert result2.value == 30
    assert result2.unit == "days"

    # 测试 "有效期六个月"
    text3 = "有效期六个月"
    result3 = checker._extract_validity_period(text3)
    assert result3.value == 6
    assert result3.unit == "months"


@pytest.mark.asyncio
async def test_extract_validity_period_permanent(checker):
    """
    测试场景：提取长期/永久有效

    预期结果：
    - 正确识别 "长期有效"、"永久有效"、"长期"、"永久"
    - is_permanent 标记为 True
    """
    # 测试 "长期有效"
    text1 = "本证书长期有效"
    result1 = checker._extract_validity_period(text1)
    assert result1 is not None
    assert result1.is_permanent is True
    assert result1.unit == "permanent"

    # 测试 "永久有效"
    text2 = "永久有效"
    result2 = checker._extract_validity_period(text2)
    assert result2.is_permanent is True

    # 测试 "长期"
    text3 = "本文件长期"
    result3 = checker._extract_validity_period(text3)
    assert result3.is_permanent is True


@pytest.mark.asyncio
async def test_extract_validity_period_not_found(checker):
    """
    测试场景：文本中没有有效期声明

    预期结果：
    - 返回 None（调用方应视为长期有效）
    """
    text = "这是一份没有任何有效期声明的文档"
    result = checker._extract_validity_period(text)
    assert result is None


# ============== 步骤2：提取落款日期测试 ==============


@pytest.mark.asyncio
async def test_extract_all_dates(checker):
    """
    测试场景：提取文本中所有日期

    预期结果：
    - 正确提取各种标准日期格式
    """
    # 测试中文日期格式
    text1 = "签发日期：2024年3月15日"
    dates1 = checker._extract_all_dates(text1)
    assert len(dates1) == 1
    assert dates1[0].date.year == 2024
    assert dates1[0].date.month == 3
    assert dates1[0].date.day == 15

    # 测试 ISO 日期格式
    text2 = "日期：2024-03-15"
    dates2 = checker._extract_all_dates(text2)
    assert len(dates2) == 1
    assert dates2[0].date.year == 2024

    # 测试斜杠日期格式
    text3 = "日期：2024/06/30"
    dates3 = checker._extract_all_dates(text3)
    assert len(dates3) == 1

    # 测试点分隔日期格式
    text4 = "日期：2024.12.31"
    dates4 = checker._extract_all_dates(text4)
    assert len(dates4) == 1


@pytest.mark.asyncio
async def test_extract_all_dates_multiple(checker):
    """
    测试场景：提取文本中多个日期

    预期结果：
    - 正确提取所有日期并记录位置
    """
    text = "签发日期：2024年3月15日，有效期至2025年3月15日"
    dates = checker._extract_all_dates(text)
    assert len(dates) == 2


@pytest.mark.asyncio
async def test_find_nearest_keyword_distance(checker):
    """
    测试场景：计算日期到最近关键词的距离

    预期结果：
    - 正确计算距离
    """
    text = "签发日期：2024年3月15日，盖章确认"
    # "2024年3月15日" 距离 "签发" 关键词很近
    distance = checker._find_nearest_keyword_distance(text, text.find("2024"))
    assert distance < 100  # 应该很近


@pytest.mark.asyncio
async def test_extract_sign_date_with_keyword(checker):
    """
    测试场景：有关键词时提取落款日期

    预期结果：
    - 优先选取距离关键词最近的日期
    """
    # 关键词 "签发" 附近的日期应该被选中
    text = "文件编号：2023-01-01，签发日期：2024年6月15日，存档日期：2025-01-01"
    sign_date = checker._extract_sign_date(text)
    assert sign_date is not None
    assert sign_date.year == 2024
    assert sign_date.month == 6
    assert sign_date.day == 15


@pytest.mark.asyncio
async def test_extract_sign_date_without_keyword(checker):
    """
    测试场景：无关键词时提取落款日期

    预期结果：
    - 默认取文档末尾的最后一个日期
    """
    # 使用没有关键词的纯日期文本
    text = "文档记录：2023年01月01日，2024年06月15日，2025年12月31日"
    sign_date = checker._extract_sign_date(text)
    assert sign_date is not None
    # 应该取最后一个日期（按位置排序）
    assert sign_date.year == 2025
    assert sign_date.month == 12
    assert sign_date.day == 31


@pytest.mark.asyncio
async def test_extract_sign_date_no_date(checker):
    """
    测试场景：文本中没有日期

    预期结果：
    - 返回 None
    """
    text = "这是一份没有任何日期的文档"
    sign_date = checker._extract_sign_date(text)
    assert sign_date is None


# ============== 步骤3：基准时间测试 ==============


@pytest.mark.asyncio
async def test_get_reference_time_from_config(checker):
    """
    测试场景：从配置中获取基准时间

    预期结果：
    - 正确解析传入的时间字符串
    """
    # 测试 YYYY-MM-DD 格式
    config1 = {"reference_time": "2024-06-15"}
    ref1 = checker._get_reference_time(config1)
    assert ref1.year == 2024
    assert ref1.month == 6
    assert ref1.day == 15

    # 测试 YYYY-MM-DD HH:MM:SS 格式
    config2 = {"reference_time": "2024-06-15 10:30:00"}
    ref2 = checker._get_reference_time(config2)
    assert ref2.year == 2024
    assert ref2.hour == 10
    assert ref2.minute == 30


@pytest.mark.asyncio
async def test_get_reference_time_default(checker):
    """
    测试场景：未传入基准时间时使用当前时间

    预期结果：
    - 返回当前服务器时间
    """
    config = {}
    before = datetime.now()
    ref = checker._get_reference_time(config)
    after = datetime.now()

    # 验证时间在合理范围内
    assert before <= ref <= after


@pytest.mark.asyncio
async def test_get_reference_time_invalid_format(checker):
    """
    测试场景：传入无效的时间格式

    预期结果：
    - 回退到使用当前时间
    """
    config = {"reference_time": "invalid-date-format"}
    ref = checker._get_reference_time(config)
    # 应该返回当前时间
    assert isinstance(ref, datetime)


# ============== 步骤4：核心判定矩阵测试 ==============


@pytest.mark.asyncio
async def test_evaluate_document_branch_a_validity_no_sign_date(checker):
    """
    测试场景：分支 A - 有有效期但无落款日期

    预期结果：
    - passed 为 False
    - branch 为 "A"
    - reason 包含 "印章时间未提取到" 和 "有效期审查未通过"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="本证书有效期1年",  # 只有有效期，没有日期
    )

    reference_time = datetime(2024, 6, 15)
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "A"
    assert result["passed"] is False
    assert result["has_validity"] is True
    assert result["has_sign_date"] is False
    assert "印章时间未提取到" in result["reason"]
    assert "有效期1年" in result["reason"]
    assert "有效期审查未通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_b_sign_date_no_validity_passed(checker):
    """
    测试场景：分支 B - 有落款日期但无有效期，且已生效

    预期结果：
    - passed 为 True（视为长期有效）
    - branch 为 "B"
    - validity.is_permanent 为 True
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2024年3月15日",  # 只有落款日期，没有有效期
    )

    reference_time = datetime(2024, 6, 15)  # 落款日期已生效
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "B"
    assert result["passed"] is True
    assert result["has_validity"] is False
    assert result["has_sign_date"] is True
    assert result["sign_date"] == "2024-03-15"
    assert result["validity"]["is_permanent"] is True
    assert "印章时间2024-03-15" in result["reason"]
    assert "长期有效" in result["reason"]
    assert "早于当前时间2024-06-15" in result["reason"]
    assert "有效期审查通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_b_sign_date_no_validity_not_yet(checker):
    """
    测试场景：分支 B - 有落款日期但无有效期，且尚未生效

    预期结果：
    - passed 为 False
    - branch 为 "B"
    - reason 包含 "晚于当前时间" 和 "有效期审查未通过"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2025年3月15日",  # 落款日期在未来
    )

    reference_time = datetime(2024, 6, 15)  # 基准时间在落款日期之前
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "B"
    assert result["passed"] is False
    assert "印章时间2025-03-15" in result["reason"]
    assert "长期有效" in result["reason"]
    assert "晚于当前时间2024-06-15" in result["reason"]
    assert "有效期审查未通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_c_both_valid_passed(checker):
    """
    测试场景：分支 C - 两者都有，且在有效期内

    预期结果：
    - passed 为 True
    - branch 为 "C"
    - 正确计算截止日期
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2024年3月15日，有效期1年",
    )

    reference_time = datetime(2024, 6, 15)  # 在有效期内
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "C"
    assert result["passed"] is True
    assert result["has_validity"] is True
    assert result["has_sign_date"] is True
    assert result["sign_date"] == "2024-03-15"
    assert result["expiry_date"] == "2025-03-15"  # 1年后
    assert "印章时间2024-03-15" in result["reason"]
    assert "有效期1年" in result["reason"]
    assert "早于当前时间2024-06-15" in result["reason"]
    assert "在有效期内（至2025-03-15）" in result["reason"]
    assert "有效期审查通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_c_not_yet_effective(checker):
    """
    测试场景：分支 C - 两者都有，但尚未生效

    预期结果：
    - passed 为 False
    - reason 包含 "晚于当前时间" 和 "有效期审查未通过"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2025年3月15日，有效期1年",
    )

    reference_time = datetime(2024, 6, 15)  # 在落款日期之前
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "C"
    assert result["passed"] is False
    assert "印章时间2025-03-15" in result["reason"]
    assert "有效期1年" in result["reason"]
    assert "晚于当前时间2024-06-15" in result["reason"]
    assert "有效期审查未通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_c_expired(checker):
    """
    测试场景：分支 C - 两者都有，但已过期

    预期结果：
    - passed 为 False
    - reason 包含 "已过期" 和 "有效期审查未通过"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2023年1月15日，有效期1年",  # 2024-01-15 过期
    )

    reference_time = datetime(2024, 6, 15)  # 已过期
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "C"
    assert result["passed"] is False
    assert result["expiry_date"] == "2024-01-15"
    assert "印章时间2023-01-15" in result["reason"]
    assert "有效期1年" in result["reason"]
    assert "早于当前时间2024-06-15但已过期（有效期至2024-01-15）" in result["reason"]
    assert "有效期审查未通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_c_permanent_valid(checker):
    """
    测试场景：分支 C - 两者都有，长期有效

    预期结果：
    - passed 为 True
    - reason 包含 "长期有效" 和 "有效期审查通过"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="签发日期：2024年3月15日，长期有效",
    )

    reference_time = datetime(2024, 6, 15)
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "C"
    assert result["passed"] is True
    assert result["validity"]["is_permanent"] is True
    assert "印章时间2024-03-15" in result["reason"]
    assert "长期有效" in result["reason"]
    assert "早于当前时间2024-06-15" in result["reason"]
    assert "有效期审查通过" in result["reason"]


@pytest.mark.asyncio
async def test_evaluate_document_branch_none_no_info(checker):
    """
    测试场景：两者都没有

    预期结果：
    - branch 为 "NONE"
    - passed 为 False
    - reason 包含 "印章时间未提取到" 和 "无法完成时效性审查"
    """
    doc = create_document_with_content(
        "测试文档.pdf",
        content="这是一份没有任何日期和有效期信息的文档",
    )

    reference_time = datetime(2024, 6, 15)
    result = checker.evaluate_document(doc, reference_time)

    assert result["branch"] == "NONE"
    assert result["passed"] is False
    assert result["has_validity"] is False
    assert result["has_sign_date"] is False
    assert "印章时间未提取到" in result["reason"]
    assert "有效期信息缺失" in result["reason"]
    assert "无法完成时效性审查" in result["reason"]


# ============== 日期计算测试 ==============


@pytest.mark.asyncio
async def test_calculate_expiry_date_years(checker):
    """
    测试场景：按年计算截止日期

    预期结果：
    - 正确计算 N 年后的日期
    """
    sign_date = datetime(2024, 3, 15)
    validity = ValidityPeriod(value=2, unit="years", is_permanent=False)

    expiry = checker._calculate_expiry_date(sign_date, validity)
    assert expiry.year == 2026
    assert expiry.month == 3
    assert expiry.day == 15


@pytest.mark.asyncio
async def test_calculate_expiry_date_months(checker):
    """
    测试场景：按月计算截止日期

    预期结果：
    - 正确计算 N 个月后的日期
    """
    sign_date = datetime(2024, 3, 15)
    validity = ValidityPeriod(value=6, unit="months", is_permanent=False)

    expiry = checker._calculate_expiry_date(sign_date, validity)
    assert expiry.year == 2024
    assert expiry.month == 9
    assert expiry.day == 15


@pytest.mark.asyncio
async def test_calculate_expiry_date_days(checker):
    """
    测试场景：按天计算截止日期

    预期结果：
    - 正确计算 N 天后的日期
    """
    sign_date = datetime(2024, 3, 15)
    validity = ValidityPeriod(value=30, unit="days", is_permanent=False)

    expiry = checker._calculate_expiry_date(sign_date, validity)
    assert expiry.year == 2024
    assert expiry.month == 4
    assert expiry.day == 14  # 3月15日 + 30天 = 4月14日


@pytest.mark.asyncio
async def test_calculate_expiry_date_permanent(checker):
    """
    测试场景：长期有效的截止日期

    预期结果：
    - 返回一个极远的日期（2099-12-31）
    """
    sign_date = datetime(2024, 3, 15)
    validity = ValidityPeriod(value=0, unit="permanent", is_permanent=True)

    expiry = checker._calculate_expiry_date(sign_date, validity)
    assert expiry.year == 2099
    assert expiry.month == 12
    assert expiry.day == 31


# ============== 中文数字转换测试 ==============


@pytest.mark.asyncio
async def test_chinese_to_number_simple(checker):
    """
    测试场景：简单中文数字转换

    预期结果：
    - 正确转换 "一"、"二"、"三" 等
    """
    assert checker._chinese_to_number("一") == 1
    assert checker._chinese_to_number("三") == 3
    assert checker._chinese_to_number("十") == 10


@pytest.mark.asyncio
async def test_chinese_to_number_complex(checker):
    """
    测试场景：复杂中文数字转换

    预期结果：
    - 正确转换 "三十"、"一百" 等
    """
    assert checker._chinese_to_number("三十") == 30
    assert checker._chinese_to_number("一百") == 100


# ============== 主 check 方法测试 ==============


@pytest.mark.asyncio
async def test_check_empty_documents(checker):
    """
    测试场景：空文档列表

    预期结果：
    - status 为 PASS
    - message 提示没有文档需要检查
    """
    result = await checker.check(
        documents=[],
        checklist=None,
        config={},
    )

    assert isinstance(result, CheckResult)
    assert result.check_type == "timeliness"
    assert result.status == CheckStatus.PASS
    assert "没有文档" in result.message
    assert result.details == {}


@pytest.mark.asyncio
async def test_check_single_document_passed(checker):
    """
    测试场景：单个文档检查通过

    预期结果：
    - status 为 PASS
    - passed 计数为 1
    """
    documents = [
        create_document_with_content(
            "测试文档.pdf",
            content="签发日期：2024年3月15日，有效期1年",
        ),
    ]

    result = await checker.check(
        documents=documents,
        checklist=None,
        config={"reference_time": "2024-06-15"},  # 在有效期内
    )

    assert result.status == CheckStatus.PASS
    assert result.details["checked"] == 1
    assert result.details["passed"] == 1
    assert result.details["failed"] == 0
    assert result.details["unclear"] == 0


@pytest.mark.asyncio
async def test_check_single_document_failed(checker):
    """
    测试场景：单个文档检查未通过

    预期结果：
    - status 为 FAIL
    - failed 计数为 1
    - issues 列表包含失败信息
    """
    documents = [
        create_document_with_content(
            "测试文档.pdf",
            content="有效期1年",  # 只有有效期，没有落款日期（分支A）
        ),
    ]

    result = await checker.check(
        documents=documents,
        checklist=None,
        config={"reference_time": "2024-06-15"},
    )

    assert result.status == CheckStatus.FAIL
    assert result.details["checked"] == 1
    assert result.details["passed"] == 0
    assert result.details["failed"] == 1
    assert len(result.issues) == 1
    assert result.issues[0]["type"] == "timeliness_failed"
    assert result.issues[0]["branch"] == "A"


@pytest.mark.asyncio
async def test_check_single_document_unclear(checker):
    """
    测试场景：单个文档信息不明确

    预期结果：
    - status 为 UNAVAILABLE
    - unclear 计数为 1
    """
    documents = [
        create_document_with_content(
            "测试文档.pdf",
            content="这是一份没有任何日期和有效期信息的文档",
        ),
    ]

    result = await checker.check(
        documents=documents,
        checklist=None,
        config={"reference_time": "2024-06-15"},
    )

    assert result.status == CheckStatus.UNAVAILABLE
    assert result.details["checked"] == 1
    assert result.details["unclear"] == 1


@pytest.mark.asyncio
async def test_check_multiple_documents_mixed(checker):
    """
    测试场景：多个文档混合情况

    预期结果：
    - 正确统计 passed、failed、unclear 数量
    """
    documents = [
        # 通过：在有效期内
        create_document_with_content(
            "文档A.pdf",
            content="签发日期：2024年3月15日，有效期1年",
        ),
        # 失败：有有效期无落款日期
        create_document_with_content(
            "文档B.pdf",
            content="有效期1年",
        ),
        # 不明确：无日期信息
        create_document_with_content(
            "文档C.pdf",
            content="无日期信息",
        ),
    ]

    result = await checker.check(
        documents=documents,
        checklist=None,
        config={"reference_time": "2024-06-15"},
    )

    assert result.status == CheckStatus.FAIL  # 有失败的文档
    assert result.details["checked"] == 3
    assert result.details["passed"] == 1
    assert result.details["failed"] == 1
    assert result.details["unclear"] == 1
    assert len(result.issues) == 1  # 只有失败的文档会生成 issue


@pytest.mark.asyncio
async def test_check_with_reference_time_in_config(checker):
    """
    测试场景：通过配置传入基准时间

    预期结果：
    - 使用传入的基准时间进行判定
    """
    documents = [
        create_document_with_content(
            "测试文档.pdf",
            content="签发日期：2024年3月15日，有效期1年",
        ),
    ]

    # 使用 2024-06-15 作为基准时间（在有效期内）
    result = await checker.check(
        documents=documents,
        checklist=None,
        config={"reference_time": "2024-06-15"},
    )

    assert result.status == CheckStatus.PASS
    assert result.details["passed"] == 1


# ============== 配置验证测试 ==============


@pytest.mark.asyncio
async def test_validate_config_valid(checker):
    """
    测试场景：验证有效配置

    预期结果：
    - 返回 (True, "")
    """
    valid, msg = checker.validate_config({"reference_time": "2024-06-15"})
    assert valid is True
    assert msg == ""


@pytest.mark.asyncio
async def test_validate_config_invalid_type(checker):
    """
    测试场景：验证无效配置（reference_time 类型错误）

    预期结果：
    - 返回 (False, 错误信息)
    """
    valid, msg = checker.validate_config({"reference_time": 12345})  # 不是字符串
    assert valid is False
    assert "字符串" in msg


@pytest.mark.asyncio
async def test_validate_config_empty(checker):
    """
    测试场景：验证空配置

    预期结果：
    - 返回 (True, "")
    """
    valid, msg = checker.validate_config({})
    assert valid is True
    assert msg == ""
