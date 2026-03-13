"""
完整性检查工具测试

测试 CompletenessChecker 和 LLMSemanticMatcher 的核心逻辑
使用 Mock 模拟外部依赖（LLM API）
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, Mock
import asyncio

from compliance_checker.tools.completeness import (
    CompletenessChecker,
    LLMSemanticMatcher,
    check_completeness
)
from compliance_checker.core.document import Document, DocumentType
from compliance_checker.core.checklist_model import Checklist, RequiredDocument
from compliance_checker.core.result_model import CheckStatus, MatchType


class TestLLMSemanticMatcher:
    """测试语义匹配器 - Mock LLM API"""
    
    @pytest.fixture
    def matcher(self):
        """创建匹配器实例"""
        return LLMSemanticMatcher()
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        matcher1 = LLMSemanticMatcher()
        matcher2 = LLMSemanticMatcher()
        assert matcher1 is matcher2
    
    def test_cosine_similarity_identical(self):
        """测试相同向量的余弦相似度为 1"""
        matcher = LLMSemanticMatcher()
        vec = [1.0, 2.0, 3.0]
        
        similarity = matcher._cosine_similarity(vec, vec)
        
        assert similarity == pytest.approx(1.0)
    
    def test_cosine_similarity_orthogonal(self):
        """测试正交向量的余弦相似度为 0"""
        matcher = LLMSemanticMatcher()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        
        similarity = matcher._cosine_similarity(vec1, vec2)
        
        assert similarity == pytest.approx(0.0)
    
    def test_cosine_similarity_opposite(self):
        """测试相反向量的余弦相似度为 -1"""
        matcher = LLMSemanticMatcher()
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        
        similarity = matcher._cosine_similarity(vec1, vec2)
        
        assert similarity == pytest.approx(-1.0)
    
    def test_cosine_similarity_zero_vector(self):
        """测试零向量的情况"""
        matcher = LLMSemanticMatcher()
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        
        similarity = matcher._cosine_similarity(vec1, vec2)
        
        assert similarity == 0.0
    
    def test_simple_embedding_length(self):
        """测试简单嵌入方法返回固定长度"""
        matcher = LLMSemanticMatcher()
        
        embedding = matcher._simple_embedding("测试文本")
        
        assert len(embedding) == 128
        assert all(isinstance(x, float) for x in embedding)
    
    def test_simple_embedding_consistency(self):
        """测试相同文本产生相同的嵌入"""
        matcher = LLMSemanticMatcher()
        
        embedding1 = matcher._simple_embedding("相同文本")
        embedding2 = matcher._simple_embedding("相同文本")
        
        assert embedding1 == embedding2
    
    def test_simple_embedding_different_texts(self):
        """测试不同文本产生不同的嵌入"""
        matcher = LLMSemanticMatcher()
        
        embedding1 = matcher._simple_embedding("文本一")
        embedding2 = matcher._simple_embedding("文本二")
        
        assert embedding1 != embedding2
    
    @pytest.mark.asyncio
    async def test_calculate_similarity_with_mock(self, matcher):
        """测试相似度计算 - Mock API"""
        with patch.object(matcher, "_get_embedding") as mock_embed:
            # 模拟返回相似向量
            mock_embed.side_effect = [
                [0.1, 0.2, 0.3],
                [0.11, 0.21, 0.31],  # 相似的向量
            ]
            
            similarity = await matcher.calculate_similarity(
                "文件名.pdf",
                ["目标名称"]
            )
            
            assert 0 <= similarity <= 1
            assert similarity > 0.9  # 相似的向量应该有高相似度
            assert mock_embed.call_count == 2
    
    @pytest.mark.asyncio
    async def test_calculate_similarity_empty_targets(self, matcher):
        """测试空目标列表返回 0"""
        similarity = await matcher.calculate_similarity("文件名.pdf", [])
        
        assert similarity == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_similarity_with_fallback(self, matcher):
        """测试 API 失败时使用备用方法"""
        with patch.object(matcher, "_get_embedding") as mock_embed:
            # 第一次调用失败，第二次成功
            mock_embed.side_effect = [
                Exception("API Error"),
                [0.1, 0.2, 0.3],
                [0.15, 0.25, 0.35],
            ]
            
            similarity = await matcher.calculate_similarity(
                "文件名.pdf",
                ["目标"]
            )
            
            # 应该使用备用方法继续计算
            assert 0 <= similarity <= 1
    
    @pytest.mark.asyncio
    async def test_find_best_match_with_mock(self, matcher):
        """测试查找最佳匹配"""
        with patch.object(matcher, "_get_embedding") as mock_embed:
            # 模拟返回不同相似度的向量
            mock_embed.side_effect = [
                [0.1, 0.2, 0.3],  # file_name
                [0.8, 0.9, 1.0],  # 不相似的目标
                [0.11, 0.21, 0.31],  # 相似的目标
            ]
            
            best_match, similarity = await matcher.find_best_match(
                "文件名.pdf",
                ["不相关", "相关文件"]
            )
            
            assert best_match == "相关文件"
            assert similarity > 0.9
    
    @pytest.mark.asyncio
    async def test_embedding_cache(self, matcher):
        """测试嵌入缓存功能"""
        # 先清空缓存
        matcher._cache.clear()
        
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            # 重置客户端以使用 mock
            matcher._client = None
            
            # 第一次调用 - 应该调用 API
            result1 = await matcher._get_embedding("测试文本")
            # 第二次调用 - 应该使用缓存
            result2 = await matcher._get_embedding("测试文本")
            
            # 验证缓存生效（结果相同）
            assert result1 == result2
            # 验证缓存中有数据
            assert "测试文本" in matcher._cache
            assert matcher._cache["测试文本"] == [0.1, 0.2, 0.3]


class TestCompletenessChecker:
    """测试完整性检查器"""
    
    @pytest.fixture
    def checker(self):
        """创建检查器实例（不使用语义匹配）"""
        return CompletenessChecker(use_semantic=False)
    
    @pytest.fixture
    def sample_checklist(self):
        """测试清单"""
        return Checklist(
            id="test",
            name="测试清单",
            required_documents=[
                RequiredDocument(
                    name="项目立项批复文件",
                    aliases=["立项批复", "项目批复"],
                    required=True
                ),
                RequiredDocument(
                    name="施工许可证",
                    aliases=["施工许可"],
                    required=True
                ),
            ]
        )
    
    def test_exact_match_direct_contain(self):
        """测试直接包含匹配"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(
            name="立项批复",
            aliases=["项目批复"]
        )
        
        match = checker._exact_match("立项批复.pdf", req_doc)
        
        assert match is not None
        assert match.match_type == MatchType.EXACT
        assert match.similarity == 1.0
    
    def test_exact_match_alias(self):
        """测试别名匹配 - 别名在文件名中"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(
            name="项目立项批复文件",
            aliases=["立项批复", "项目批复"]
        )
        
        # 别名"立项批复"在文件名中 - 应该匹配
        match = checker._exact_match("立项批复.pdf", req_doc)
        
        assert match is not None
        # 注意：由于别名"立项批复"在文件名中，会触发直接包含匹配，返回 EXACT
        assert match.match_type in [MatchType.EXACT, MatchType.ALIAS]
    
    def test_exact_match_clean_name(self):
        """测试清理扩展名后的匹配"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(
            name="立项批复",
            aliases=[]
        )
        
        # "立项批复"在"立项批复文件.pdf"中 - 应该直接匹配
        match = checker._exact_match("立项批复文件.pdf", req_doc)
        
        assert match is not None
        # 直接包含匹配返回 EXACT
        assert match.match_type == MatchType.EXACT
    
    def test_exact_match_no_match(self):
        """测试不匹配的情况"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(
            name="立项批复",
            aliases=[]
        )
        
        match = checker._exact_match("完全不相关.pdf", req_doc)
        
        assert match is None
    
    def test_exact_match_various_extensions(self):
        """测试各种扩展名的处理"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(name="文档")
        
        extensions = [".pdf", ".docx", ".doc", ".jpg", ".png"]
        for ext in extensions:
            match = checker._exact_match(f"文档{ext}", req_doc)
            assert match is not None, f"应该支持 {ext} 扩展名"
    
    @pytest.mark.asyncio
    async def test_match_document_exact(self):
        """测试文档匹配 - 精确匹配"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(name="立项批复")
        
        match = await checker.match_document("立项批复.pdf", req_doc)
        
        assert match.status == CheckStatus.VALID
        assert match.match_type == MatchType.EXACT
    
    @pytest.mark.asyncio
    async def test_match_document_no_match(self):
        """测试文档匹配 - 无匹配"""
        checker = CompletenessChecker(use_semantic=False)
        req_doc = RequiredDocument(name="立项批复")
        
        match = await checker.match_document("不相关.pdf", req_doc)
        
        assert match.status == CheckStatus.MISSING
        assert match.match_type == MatchType.NONE
    
    @pytest.mark.asyncio
    async def test_match_document_semantic_with_mock(self):
        """测试语义匹配 - Mock"""
        checker = CompletenessChecker(use_semantic=True)
        
        with patch.object(
            checker._semantic_matcher,
            "find_best_match",
            new_callable=AsyncMock
        ) as mock_match:
            mock_match.return_value = ("立项批复", 0.85)
            
            req_doc = RequiredDocument(name="立项批复")
            match = await checker.match_document("项目批准文件.pdf", req_doc)
            
            assert match.status == CheckStatus.VALID
            assert match.match_type == MatchType.SEMANTIC
            assert match.similarity == 0.85
    
    @pytest.mark.asyncio
    async def test_check_all_matched(self, checker, sample_checklist):
        """测试全部匹配的情况"""
        documents = [
            Document(file_path="/data/立项批复.pdf", file_name="立项批复.pdf"),
            Document(file_path="/data/施工许可.pdf", file_name="施工许可.pdf"),
        ]
        
        result = await checker.check(documents, sample_checklist)
        
        assert result.status == CheckStatus.PASS
        assert result.total_required == 2
        assert result.uploaded == 2
        assert result.missing == 0
    
    @pytest.mark.asyncio
    async def test_check_partial_matched(self, checker, sample_checklist):
        """测试部分匹配的情况"""
        documents = [
            Document(file_path="/data/立项批复.pdf", file_name="立项批复.pdf"),
            # 缺少施工许可证
        ]
        
        result = await checker.check(documents, sample_checklist)
        
        assert result.status == CheckStatus.INCOMPLETE
        assert result.total_required == 2
        assert result.uploaded == 1
        assert result.missing == 1
    
    @pytest.mark.asyncio
    async def test_check_none_matched(self, checker, sample_checklist):
        """测试全部未匹配的情况"""
        documents = [
            Document(file_path="/data/无关文件.pdf", file_name="无关文件.pdf"),
        ]
        
        result = await checker.check(documents, sample_checklist)
        
        assert result.status == CheckStatus.INCOMPLETE
        assert result.uploaded == 0
        assert result.missing == 2
    
    @pytest.mark.asyncio
    async def test_check_empty_documents(self, checker, sample_checklist):
        """测试空文档列表"""
        result = await checker.check([], sample_checklist)
        
        assert result.status == CheckStatus.INCOMPLETE
        assert result.uploaded == 0
        assert result.missing == 2
    
    @pytest.mark.asyncio
    async def test_check_optional_documents(self):
        """测试可选文档的处理"""
        checklist = Checklist(
            id="test",
            name="测试清单",
            required_documents=[
                RequiredDocument(name="必需文档", required=True),
                RequiredDocument(name="可选文档", required=False),
            ]
        )
        
        checker = CompletenessChecker(use_semantic=False)
        documents = [Document(file_path="/data/必需.pdf", file_name="必需文档.pdf")]
        
        result = await checker.check(documents, checklist)
        
        # 只检查必需文档
        assert result.total_required == 1
        assert result.uploaded == 1
        assert result.status == CheckStatus.PASS
    
    @pytest.mark.asyncio
    async def test_check_best_match_selection(self, checker):
        """测试选择最佳匹配"""
        checklist = Checklist(
            id="test",
            name="测试清单",
            required_documents=[
                RequiredDocument(name="立项批复", aliases=["项目批复"]),
            ]
        )
        
        # 多个文件都可能匹配，选择最佳的一个
        documents = [
            Document(file_path="/data/项目批复.pdf", file_name="项目批复.pdf"),
            Document(file_path="/data/其他.pdf", file_name="其他.pdf"),
        ]
        
        result = await checker.check(documents, checklist)
        
        assert result.uploaded == 1
        assert result.details[0].matched_file == "项目批复.pdf"
    
    @pytest.mark.asyncio
    async def test_check_completeness_function(self, sample_checklist):
        """测试 check_completeness 函数入口"""
        documents = [
            Document(file_path="/data/立项批复.pdf", file_name="立项批复.pdf"),
            Document(file_path="/data/施工许可.pdf", file_name="施工许可.pdf"),
        ]
        
        result = await check_completeness(
            documents,
            sample_checklist,
            similarity_threshold=0.75,
            use_semantic=False
        )
        
        assert result.status == CheckStatus.PASS
        assert result.total_required == 2
    
    def test_similarity_threshold_configuration(self):
        """测试相似度阈值配置"""
        checker = CompletenessChecker(similarity_threshold=0.8)
        
        assert checker.similarity_threshold == 0.8
    
    def test_semantic_disabled(self):
        """测试禁用语义匹配"""
        checker = CompletenessChecker(use_semantic=False)
        
        assert checker.use_semantic is False
        assert checker._semantic_matcher is None


class TestCompletenessResultDetails:
    """测试完整性结果的详细信息"""
    
    @pytest.mark.asyncio
    async def test_match_details_structure(self):
        """测试匹配详情结构"""
        checker = CompletenessChecker(use_semantic=False)
        checklist = Checklist(
            id="test",
            name="测试清单",
            required_documents=[
                RequiredDocument(name="文档1"),
            ]
        )
        documents = [Document(file_path="/data/文档1.pdf", file_name="文档1.pdf")]
        
        result = await checker.check(documents, checklist)
        
        assert len(result.details) == 1
        detail = result.details[0]
        assert detail.document_name == "文档1"
        assert detail.matched_file == "文档1.pdf"
        assert detail.match_type == MatchType.EXACT
        assert detail.requirement == "必须上传"
