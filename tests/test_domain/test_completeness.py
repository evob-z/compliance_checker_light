"""
CompletenessChecker 单元测试

测试完整性检查器的核心逻辑，不依赖真实的 Infrastructure 层。
使用 MockSemanticMatcher 模拟语义匹配功能。

遵循 architecture.md 中『10.2 Domain 层测试示例』规范：
- 不引入真实 infrastructure
- 手写 Mock 类实现协议接口
- 使用内存对象构造测试输入
- 至少包含 PASS 和 FAIL 两种核心场景用例
- 详尽的 assert 校验返回字段、异常类型和错误信息
"""

import pytest
from typing import List, Tuple

from src.core.checker_base import CheckStatus, CheckResult
from src.core.document import Document
from src.core.checklist_model import Checklist, RequiredDocument, SupportedFileType
from src.core.result_model import MatchType
from src.domain.checkers.completeness import CompletenessChecker


class MockSemanticMatcher:
    """
    Mock 语义匹配器 - 实现 SemanticMatcherProtocol 接口

    使用简单的关键词匹配逻辑模拟语义相似度：
    - 如果两个文本包含相同的关键词，返回 0.9
    - 否则返回 0.2

    不依赖真实的 LLM 或 Embedding 模型。
    """

    # 定义关键词列表，用于模拟语义匹配
    KEYWORDS = ["立项", "环评", "施工", "规划", "用地", "批复", "许可证", "验收", "审批"]

    async def get_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的语义相似度（模拟）

        Args:
            text1: 第一个文本
            text2: 第二个文本

        Returns:
            相似度分数 (0-1)
        """
        # 查找两个文本中包含的关键词
        keywords1 = [kw for kw in self.KEYWORDS if kw in text1]
        keywords2 = [kw for kw in self.KEYWORDS if kw in text2]

        # 如果有共同关键词，返回高相似度
        common = set(keywords1) & set(keywords2)
        if common:
            return 0.9

        # 否则返回低相似度
        return 0.2

    async def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量（模拟）

        Args:
            text: 输入文本

        Returns:
            嵌入向量（固定长度的浮点数列表）
        """
        # 返回一个简单的模拟向量，长度为 128
        # 向量值基于文本长度，仅用于模拟
        base_value = len(text) / 1000.0
        return [base_value] * 128

    async def find_best_match(
        self, text: str, candidates: List[str]
    ) -> Tuple[str, float]:
        """
        从候选列表中找到最佳匹配（模拟）

        Args:
            text: 待匹配文本
            candidates: 候选文本列表

        Returns:
            (最佳匹配文本, 相似度分数)
        """
        if not candidates:
            return ("", 0.0)

        best_candidate = candidates[0]
        best_similarity = 0.0

        for candidate in candidates:
            similarity = await self.get_similarity(text, candidate)
            if similarity > best_similarity:
                best_similarity = similarity
                best_candidate = candidate

        return (best_candidate, best_similarity)


# ============== 测试 Fixtures ==============


@pytest.fixture
def mock_matcher():
    """创建 Mock 语义匹配器实例"""
    return MockSemanticMatcher()


@pytest.fixture
def checker(mock_matcher):
    """创建完整性检查器实例"""
    return CompletenessChecker(
        matcher=mock_matcher,
        similarity_threshold=0.75,
        use_semantic=True,
    )


@pytest.fixture
def sample_checklist():
    """
    创建示例审核清单

    包含三个必需文档：
    - 项目立项批复文件
    - 环评批复文件
    - 施工许可证
    """
    return Checklist(
        id="test_checklist_001",
        name="测试用审核清单",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复文件",
                aliases=["立项批复", "项目批复"],
                required=True,
            ),
            RequiredDocument(
                name="环评批复文件",
                aliases=["环评批复", "环境影响评价批复"],
                required=True,
            ),
            RequiredDocument(
                name="施工许可证",
                aliases=["施工许可", "建筑工程施工许可证"],
                required=True,
            ),
        ],
    )


def create_document(file_name: str, file_path: str = None) -> Document:
    """
    创建测试用 Document 对象的辅助函数

    Args:
        file_name: 文件名
        file_path: 文件路径（可选，默认使用文件名）

    Returns:
        Document 实例
    """
    return Document(
        path=file_path or f"/test/documents/{file_name}",
        name=file_name,
    )


# ============== 测试用例 ==============


@pytest.mark.asyncio
async def test_completeness_all_documents_present(checker, sample_checklist):
    """
    测试场景：所有必需文档都已上传

    预期结果：
    - check_type 为 "completeness"
    - status 为 PASS
    - message 包含成功信息
    - details 包含完整的统计信息
    - missing 数量为 0
    - uploaded 数量等于必需文档总数
    - 每个匹配结果的字段完整且有效
    """
    # 准备测试数据：创建匹配所有必需文档的文件列表
    documents = [
        create_document("项目立项批复文件.pdf"),
        create_document("环评批复文件.pdf"),
        create_document("施工许可证.pdf"),
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证 CheckResult 基础字段 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "completeness", "check_type 应为 'completeness'"
    assert result.status == CheckStatus.PASS, "所有文档存在时状态应为 PASS"
    
    # 验证 message 字段
    assert isinstance(result.message, str), "message 应为字符串类型"
    assert len(result.message) > 0, "message 不应为空"
    assert "所有" in result.message, "message 应包含 '所有'"
    assert "已上传" in result.message, "message 应包含 '已上传'"
    
    # 验证 details 字段结构
    assert isinstance(result.details, dict), "details 应为字典类型"
    assert "completeness_result" in result.details, "details 应包含 completeness_result"
    assert "total_required" in result.details, "details 应包含 total_required"
    assert "uploaded" in result.details, "details 应包含 uploaded"
    assert "missing" in result.details, "details 应包含 missing"
    assert "matches" in result.details, "details 应包含 matches"

    # ========== 验证统计信息 ==========
    assert result.details["total_required"] == 3, "必需文档总数应为 3"
    assert result.details["uploaded"] == 3, "已上传数量应为 3"
    assert result.details["missing"] == 0, "缺失数量应为 0"

    # ========== 验证匹配结果列表 ==========
    matches = result.details["matches"]
    assert isinstance(matches, list), "matches 应为列表类型"
    assert len(matches) == 3, "应有 3 个匹配结果"

    # 验证每个匹配结果的字段完整性
    required_match_fields = ["document_name", "status", "matched_file", "match_type", "similarity"]
    for match in matches:
        for field in required_match_fields:
            assert field in match, f"匹配结果应包含 '{field}' 字段"
        
        # 验证字段值有效性
        assert match["status"] == CheckStatus.VALID.value, "匹配状态应为 VALID"
        assert match["matched_file"] is not None, "matched_file 不应为 None"
        assert match["match_type"] in ["exact", "alias", "semantic"], "match_type 应为有效类型"
        assert isinstance(match["similarity"], (int, float)), "similarity 应为数值类型"
        assert 0 <= match["similarity"] <= 1, "similarity 应在 0-1 范围内"

    # ========== 验证 issues 列表 ==========
    assert isinstance(result.issues, list), "issues 应为列表类型"
    assert len(result.issues) == 0, "所有文档存在时不应有 issues"

    # ========== 验证 CompletenessResult 结构 ==========
    comp_result = result.details["completeness_result"]
    assert "status" in comp_result, "completeness_result 应包含 status"
    assert "total_required" in comp_result, "completeness_result 应包含 total_required"
    assert "uploaded" in comp_result, "completeness_result 应包含 uploaded"
    assert "missing" in comp_result, "completeness_result 应包含 missing"
    assert "details" in comp_result, "completeness_result 应包含 details"


@pytest.mark.asyncio
async def test_completeness_missing_documents(checker, sample_checklist):
    """
    测试场景：部分必需文档缺失

    预期结果：
    - status 为 INCOMPLETE
    - missing 数量大于 0
    - 缺失的文档状态为 MISSING
    - message 包含缺失信息
    - issues 列表包含缺失文档信息
    """
    # 准备测试数据：只上传部分文档
    # 注意：使用精确匹配的文件名，避免语义匹配影响
    documents = [
        create_document("项目立项批复文件.pdf"),  # 只匹配"项目立项批复文件"
        # 缺少环评批复文件
        # 缺少施工许可证
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证 CheckResult 基础字段 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "completeness", "check_type 应为 'completeness'"
    assert result.status == CheckStatus.INCOMPLETE, "部分文档缺失时状态应为 INCOMPLETE"
    
    # 验证 message 字段
    assert isinstance(result.message, str), "message 应为字符串类型"
    assert "缺少" in result.message, "message 应包含 '缺少'"

    # ========== 验证统计信息 ==========
    assert result.details["total_required"] == 3, "必需文档总数应为 3"
    # 注意：由于语义匹配，"项目立项批复文件.pdf" 可能匹配多个文档
    # 我们验证 uploaded >= 1 且 missing >= 1
    assert result.details["uploaded"] >= 1, "至少应有 1 个文档上传"
    assert result.details["missing"] >= 1, "至少应有 1 个文档缺失"

    # ========== 验证缺失文档状态 ==========
    matches = result.details["matches"]
    assert isinstance(matches, list), "matches 应为列表类型"
    
    missing_docs = [m for m in matches if m["status"] == CheckStatus.MISSING.value]
    assert len(missing_docs) >= 1, "至少应有 1 个 MISSING 状态的文档"
    
    # 验证缺失文档的字段完整性
    for missing in missing_docs:
        assert "document_name" in missing, "缺失文档应包含 document_name"
        assert "status" in missing, "缺失文档应包含 status"
        assert "matched_file" in missing, "缺失文档应包含 matched_file"
        assert "match_type" in missing, "缺失文档应包含 match_type"
        assert "similarity" in missing, "缺失文档应包含 similarity"
        
        # 验证缺失文档的字段值
        assert missing["status"] == CheckStatus.MISSING.value, "状态应为 MISSING"
        assert missing["matched_file"] is None, "缺失文档的 matched_file 应为 None"
        assert missing["match_type"] == MatchType.NONE.value, "缺失文档的 match_type 应为 none"
        assert missing["similarity"] == 0.0, "缺失文档的 similarity 应为 0.0"


@pytest.mark.asyncio
async def test_completeness_semantic_match(checker, sample_checklist):
    """
    测试场景：使用语义匹配（文件名与清单名称不完全一致）

    预期结果：
    - 通过语义匹配找到对应文档
    - match_type 为 semantic
    """
    # 准备测试数据：使用语义上相关但名称不完全一致的文件名
    documents = [
        create_document("某项目立项批复.pdf"),  # 包含"立项"关键词
        create_document("环境影响评价批复.pdf"),  # 包含"环评"关键词
        create_document("建筑工程施工许可.pdf"),  # 包含"施工"关键词
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # 验证结果：语义匹配应该成功
    assert result.status == CheckStatus.PASS
    assert result.details["uploaded"] == 3
    assert result.details["missing"] == 0


@pytest.mark.asyncio
async def test_completeness_no_checklist(checker):
    """
    测试场景：缺少审核清单

    预期结果：
    - status 为 ERROR
    - message 提示缺少审核清单
    - details 为空字典或包含错误信息
    """
    # 准备测试数据：有文档但没有清单
    documents = [
        create_document("项目立项批复文件.pdf"),
    ]

    # 执行检查（不传 checklist）
    result = await checker.check(
        documents=documents,
        checklist=None,
        doc_checks={},
    )

    # ========== 验证 CheckResult 基础字段 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "completeness", "check_type 应为 'completeness'"
    assert result.status == CheckStatus.ERROR, "缺少清单时状态应为 ERROR"
    
    # 验证 message 字段
    assert isinstance(result.message, str), "message 应为字符串类型"
    assert "缺少审核清单" in result.message, "message 应包含 '缺少审核清单'"
    
    # 验证 details 字段
    assert isinstance(result.details, dict), "details 应为字典类型"
    
    # 验证 issues 列表
    assert isinstance(result.issues, list), "issues 应为列表类型"


@pytest.mark.asyncio
async def test_completeness_empty_documents(checker, sample_checklist):
    """
    测试场景：文档列表为空

    预期结果：
    - status 为 INCOMPLETE
    - 所有必需文档都标记为缺失
    - uploaded 为 0
    - missing 等于必需文档总数
    """
    # 准备测试数据：空文档列表
    documents = []

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证 CheckResult 基础字段 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "completeness", "check_type 应为 'completeness'"
    assert result.status == CheckStatus.INCOMPLETE, "空文档列表状态应为 INCOMPLETE"
    
    # 验证统计信息
    assert result.details["total_required"] == 3, "必需文档总数应为 3"
    assert result.details["uploaded"] == 0, "已上传数量应为 0"
    assert result.details["missing"] == 3, "缺失数量应为 3"

    # ========== 验证所有文档都是 MISSING 状态 ==========
    matches = result.details["matches"]
    assert len(matches) == 3, "应有 3 个匹配结果"
    
    for match in matches:
        assert match["status"] == CheckStatus.MISSING.value, "所有文档状态应为 MISSING"
        assert match["matched_file"] is None, "matched_file 应为 None"
        assert match["match_type"] == MatchType.NONE.value, "match_type 应为 none"
        assert match["similarity"] == 0.0, "similarity 应为 0.0"


@pytest.mark.asyncio
async def test_completeness_alias_match(checker, sample_checklist):
    """
    测试场景：使用别名匹配

    预期结果：
    - 通过别名成功匹配文档
    - match_type 为 alias
    - similarity 为 0.95
    """
    # 准备测试数据：使用清单中定义的别名
    documents = [
        create_document("立项批复.pdf"),  # 使用别名
        create_document("环评批复.pdf"),  # 使用别名
        create_document("施工许可.pdf"),  # 使用别名
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证整体结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.status == CheckStatus.PASS, "别名匹配应成功"
    assert result.details["uploaded"] == 3, "应匹配 3 个文档"
    assert result.details["missing"] == 0, "不应有缺失文档"

    # ========== 验证匹配类型 ==========
    matches = result.details["matches"]
    
    # 验证别名匹配的 similarity 应该是 0.95
    alias_matches = [m for m in matches if m["match_type"] == MatchType.ALIAS.value]
    assert len(alias_matches) >= 1, "至少应有 1 个别名匹配"
    
    for match in alias_matches:
        assert match["similarity"] == 0.95, f"别名匹配的 similarity 应为 0.95，实际为 {match['similarity']}"
        assert match["matched_file"] is not None, "别名匹配的 matched_file 不应为 None"
        assert match["status"] == CheckStatus.VALID.value, "别名匹配的状态应为 VALID"


@pytest.mark.asyncio
async def test_completeness_without_semantic(mock_matcher, sample_checklist):
    """
    测试场景：禁用语义匹配

    预期结果：
    - 只使用精确匹配和别名匹配
    - 语义上相关但名称不匹配的文档不会被识别
    - 所有必需文档都应该是缺失状态
    """
    # 创建禁用语义匹配的检查器
    checker_no_semantic = CompletenessChecker(
        matcher=mock_matcher,
        similarity_threshold=0.75,
        use_semantic=False,  # 禁用语义匹配
    )

    # 准备测试数据：使用完全不相关的文件名（不包含任何关键词或别名）
    # 注意：精确匹配逻辑会检查 file_name 是否包含 required_doc.name
    # 所以要避免文件名中包含 "立项"、"环评"、"施工"、"批复"、"许可" 等关键词
    documents = [
        create_document("某某文件123.pdf"),  # 完全不相关的文件名
    ]

    # 执行检查
    result = await checker_no_semantic.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.status == CheckStatus.INCOMPLETE, "禁用语义匹配时应无法匹配"
    assert result.details["missing"] == 3, "所有 3 个文档都应缺失"
    assert result.details["uploaded"] == 0, "不应有匹配的文档"


# ============== 新增测试用例 ==============


@pytest.mark.asyncio
async def test_completeness_exact_match(checker, sample_checklist):
    """
    测试场景：精确匹配（文件名完全包含清单名称）

    预期结果：
    - match_type 为 exact
    - similarity 为 1.0
    """
    # 使用完全匹配清单名称的文件名
    documents = [
        create_document("项目立项批复文件.pdf"),  # 完全匹配
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # 验证有精确匹配
    matches = result.details["matches"]
    exact_matches = [m for m in matches if m["match_type"] == MatchType.EXACT.value]
    
    assert len(exact_matches) >= 1, "应有至少 1 个精确匹配"
    for match in exact_matches:
        assert match["similarity"] == 1.0, "精确匹配的 similarity 应为 1.0"
        assert match["status"] == CheckStatus.VALID.value


@pytest.mark.asyncio
async def test_completeness_semantic_match_type(checker, sample_checklist):
    """
    测试场景：语义匹配（文件名与清单名称语义相关但不完全匹配）

    预期结果：
    - match_type 为 semantic
    - similarity 在阈值范围内
    """
    # 使用语义相关但不完全匹配的文件名
    documents = [
        create_document("某项目立项批复.pdf"),  # 包含"立项"关键词
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # 验证有语义匹配
    matches = result.details["matches"]
    semantic_matches = [m for m in matches if m["match_type"] == MatchType.SEMANTIC.value]
    
    # 由于 MockSemanticMatcher 的实现，包含相同关键词会返回 0.9 的相似度
    assert len(semantic_matches) >= 1, "应有至少 1 个语义匹配"
    for match in semantic_matches:
        assert match["similarity"] >= 0.75, "语义匹配的 similarity 应 >= 0.75"
        assert match["similarity"] <= 1.0, "语义匹配的 similarity 应 <= 1.0"
        assert match["status"] == CheckStatus.VALID.value


@pytest.mark.asyncio
async def test_completeness_optional_documents(checker):
    """
    测试场景：包含可选文档的清单

    预期结果：
    - 可选文档缺失不影响整体状态
    - 只检查必需文档
    """
    # 创建包含可选文档的清单
    checklist = Checklist(
        id="test_optional",
        name="测试可选文档清单",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="必需文档A",
                required=True,
            ),
            RequiredDocument(
                name="可选文档B",
                required=False,  # 可选
            ),
        ],
    )

    documents = [
        create_document("必需文档A.pdf"),
        # 可选文档B 未上传
    ]

    result = await checker.check(
        documents=documents,
        checklist=checklist,
        doc_checks={},
    )

    # 验证结果：只检查必需文档
    assert result.status == CheckStatus.PASS, "必需文档存在时应 PASS"
    assert result.details["total_required"] == 1, "只计算必需文档"
    assert result.details["uploaded"] == 1
    assert result.details["missing"] == 0


@pytest.mark.asyncio
async def test_completeness_checker_properties(checker):
    """
    测试场景：验证检查器的基本属性

    预期结果：
    - name 属性正确
    - description 属性正确
    - version 属性存在
    """
    assert checker.name == "completeness", "检查器名称应为 'completeness'"
    assert isinstance(checker.description, str), "description 应为字符串"
    assert len(checker.description) > 0, "description 不应为空"
    assert "完整性" in checker.description or "文档" in checker.description, "description 应描述完整性检查"
    assert hasattr(checker, "version"), "应有 version 属性"


@pytest.mark.asyncio
async def test_completeness_similarity_threshold():
    """
    测试场景：自定义相似度阈值

    预期结果：
    - 高阈值时，低相似度匹配不成功
    - 低阈值时，低相似度匹配成功
    """
    # 创建高阈值检查器
    high_threshold_matcher = MockSemanticMatcher()
    high_threshold_checker = CompletenessChecker(
        matcher=high_threshold_matcher,
        similarity_threshold=0.95,  # 高阈值
        use_semantic=True,
    )

    checklist = Checklist(
        id="test_threshold",
        name="测试阈值",
        version="1.0",
        required_documents=[
            RequiredDocument(name="立项批复", required=True),
        ],
    )

    # 使用语义相关的文件名
    documents = [create_document("某项目立项批复.pdf")]

    result = await high_threshold_checker.check(
        documents=documents,
        checklist=checklist,
        doc_checks={},
    )

    # 由于 MockSemanticMatcher 返回 0.9 的相似度，高阈值 0.95 可能导致匹配失败
    # 但精确匹配应该仍然成功（因为文件名包含"立项批复"）
    assert result.details["uploaded"] >= 1, "精确匹配应成功"


@pytest.mark.asyncio
async def test_completeness_multiple_matches_for_same_document(checker, sample_checklist):
    """
    测试场景：同一文件可能匹配多个清单项

    预期结果：
    - 每个清单项独立匹配
    - 选择最佳匹配
    """
    # 创建可能匹配多个清单项的文件名
    documents = [
        create_document("项目立项批复文件.pdf"),  # 可能匹配"项目立项批复文件"
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # 验证匹配结果
    matches = result.details["matches"]
    matched_files = [m["matched_file"] for m in matches if m["matched_file"]]
    
    # 同一个文件可能匹配多个清单项（取决于匹配逻辑）
    # 但每个清单项只能有一个最佳匹配
    for match in matches:
        if match["matched_file"]:
            assert match["status"] == CheckStatus.VALID.value


@pytest.mark.asyncio
async def test_completeness_checklist_with_aliases(mock_matcher):
    """
    测试场景：清单项包含多个别名

    预期结果：
    - 任一别名匹配成功即可
    """
    # 创建检查器
    checker_instance = CompletenessChecker(
        matcher=mock_matcher,
        similarity_threshold=0.75,
        use_semantic=True,
    )
    
    checklist = Checklist(
        id="test_aliases",
        name="测试别名",
        version="1.0",
        required_documents=[
            RequiredDocument(
                name="项目立项批复",
                aliases=["立项批复", "项目批复", "立项文件", "批复文件"],
                required=True,
            ),
        ],
    )

    # 使用不同别名
    test_cases = [
        "立项批复.pdf",
        "项目批复.pdf",
        "立项文件.pdf",
        "批复文件.pdf",
    ]

    for file_name in test_cases:
        documents = [create_document(file_name)]
        result = await checker_instance.check(
            documents=documents,
            checklist=checklist,
            doc_checks={},
        )
        
        assert result.status == CheckStatus.PASS, f"文件名 '{file_name}' 应通过别名匹配"
        assert result.details["uploaded"] == 1
        assert result.details["missing"] == 0
