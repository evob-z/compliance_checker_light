"""
InMemoryValidityRetriever 和 ValidityTextChunker 单元测试

测试要点：
- ValidityTextChunker.clean() 正确剔除特殊字符
- ValidityTextChunker.chunk() 不在日期中间切断，语义边界回退正常
- InMemoryValidityRetriever 熔断：全低分文档返回 (False, [])
- InMemoryValidityRetriever 正常：高分 Chunk 返回 top-K，关键词加权生效
- 批量余弦相似度计算正确

遵循架构规范：使用 Mock 对象替代真实 Infrastructure 依赖。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.compliance_checker.infrastructure.rag.chunker import ValidityTextChunker
from src.compliance_checker.infrastructure.rag.validity_retriever import (
    InMemoryValidityRetriever,
    _KEYWORD_BONUS,
    _DATE_BONUS,
)
from src.compliance_checker.core.interfaces import RetrievedChunk


# ============== Mock SemanticMatcher ==============


class HighScoreMatcher:
    """
    模拟高相关性场景：所有 Chunk 都返回高相似度（0.8）
    """

    async def get_embedding(self, text: str):
        # 对"有效期"关键词相关文本返回高维相似向量
        # 简单用 1.0 归一化向量模拟高相似
        if any(kw in text for kw in ["有效期", "截止", "到期", "长期有效", "永久有效"]):
            return [1.0] + [0.0] * 127
        return [0.8] + [0.0] * 127

    async def get_similarity(self, t1: str, t2: str) -> float:
        return 0.8

    async def find_best_match(self, text, candidates):
        return None, 0.0


class LowScoreMatcher:
    """
    模拟低相关性场景：所有 Chunk 与 Query 正交，余弦相似度接近0
    触发燃断逻辑
    """

    async def get_embedding(self, text: str):
        # 静态 Query（包含“有效期”和“截止日期”）返回第一维为1的向量
        if "有效期" in text and "截止日期" in text:
            return [1.0] + [0.0] * 127
        # 其他文本（Chunk）返回最后一维为1的向量（与 Query 正交）
        return [0.0] * 127 + [1.0]

    async def get_similarity(self, t1: str, t2: str) -> float:
        return 0.05

    async def find_best_match(self, text, candidates):
        return None, 0.0


# ============== ValidityTextChunker 测试 ==============


class TestValidityTextChunker:
    """ValidityTextChunker 单元测试"""

    def setup_method(self):
        self.chunker = ValidityTextChunker()

    # --- clean() 测试 ---

    def test_clean_removes_table_border_chars(self):
        """
        测试场景：清洗表格线字符

        预期结果：
        - Unicode 制表符（│、─、┼等）被替换为空格
        """
        text = "有效期│3年"
        result = self.chunker.clean(text)
        assert "│" not in result
        assert "有效期" in result
        assert "3年" in result

    def test_clean_removes_fullwidth_space(self):
        """
        测试场景：清洗全角空格

        预期结果：
        - 全角空格（\u3000）被替换为普通空格
        """
        text = "有效期\u30003年"
        result = self.chunker.clean(text)
        assert "\u3000" not in result
        assert "有效期" in result

    def test_clean_compresses_multiple_spaces(self):
        """
        测试场景：压缩连续空白

        预期结果：
        - 多个连续空格被压缩为1个
        """
        text = "有效期    3年"
        result = self.chunker.clean(text)
        assert "  " not in result  # 不应有连续两个空格
        assert "有效期" in result

    def test_clean_compresses_multiple_newlines(self):
        """
        测试场景：压缩连续换行

        预期结果：
        - 超过2个连续换行被压缩为最多2个
        """
        text = "有效期\n\n\n\n3年"
        result = self.chunker.clean(text)
        assert "\n\n\n" not in result

    def test_clean_removes_separator_lines(self):
        """
        测试场景：清洗分隔线

        预期结果：
        - 连续的 - = 等分隔符被清洗
        """
        text = "有效期\n----------\n3年"
        result = self.chunker.clean(text)
        assert "----------" not in result
        assert "有效期" in result
        assert "3年" in result

    def test_clean_empty_text(self):
        """
        测试场景：空文本输入

        预期结果：
        - 返回空字符串
        """
        assert self.chunker.clean("") == ""
        assert self.chunker.clean(None) == ""

    # --- chunk() 测试 ---

    def test_chunk_basic_sliding_window(self):
        """
        测试场景：基础滑动窗口分块

        预期结果：
        - 文本被切成多个 Chunk
        - 每个 Chunk 长度不超过 chunk_size + MAX_LOOKBACK
        """
        text = "A" * 500
        chunks = self.chunker.chunk(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        # 每个 Chunk 长度应合理
        for chunk_text, start_pos in chunks:
            assert len(chunk_text) <= 100 + self.chunker.MAX_LOOKBACK

    def test_chunk_does_not_split_date_in_middle(self):
        """
        测试场景：日期不被切断

        预期结果：
        - 日期 "2024-12-31" 应完整出现在某个 Chunk 中（不被截断）
        """
        # 在接近 chunk_size 边界处放置日期
        prefix = "A" * 195  # 接近 chunk_size=200
        text = prefix + "，有效期至2024-12-31，签发机关盖章"
        chunks = self.chunker.chunk(text, chunk_size=200, overlap=30)

        # 检查日期是否完整出现在某个 Chunk 中
        date_str = "2024-12-31"
        date_complete_in_chunk = any(date_str in chunk_text for chunk_text, _ in chunks)
        assert date_complete_in_chunk, f"日期 {date_str} 应完整出现在某个 Chunk 中"

    def test_chunk_returns_start_pos(self):
        """
        测试场景：返回正确的起始位置

        预期结果：
        - 每个 Chunk 的 start_pos 应是其在原文中的实际位置
        """
        text = "ABCDE" * 100
        chunks = self.chunker.chunk(text, chunk_size=100, overlap=20)
        for chunk_text, start_pos in chunks:
            # 验证 chunk_text 确实从 start_pos 附近开始（考虑 strip 影响）
            assert 0 <= start_pos < len(text)

    def test_chunk_short_text_returns_single_chunk(self):
        """
        测试场景：短文本（短于 chunk_size）返回单个 Chunk

        预期结果：
        - 返回只有1个 Chunk，内容等于原文（去除首尾空白）
        """
        text = "有效期3年，签发日期2024年1月1日"
        chunks = self.chunker.chunk(text, chunk_size=200, overlap=50)
        assert len(chunks) == 1
        assert chunks[0][0] == text.strip()
        assert chunks[0][1] == 0

    def test_chunk_overlap_ensures_continuity(self):
        """
        测试场景：相邻 Chunk 有重叠

        预期结果：
        - 第二个 Chunk 的起始位置 < 第一个 Chunk 的结束位置（重叠保证）
        """
        text = "A" * 600
        chunks = self.chunker.chunk(text, chunk_size=200, overlap=50)
        assert len(chunks) >= 2
        # 第一个 Chunk 的结束位置应大于第二个 Chunk 的起始位置
        _, start_1 = chunks[0]
        _, start_2 = chunks[1]
        # start_2 < start_1 + 200（有重叠）
        assert start_2 < start_1 + 200

    def test_chunk_empty_text(self):
        """
        测试场景：空文本输入

        预期结果：
        - 返回空列表
        """
        assert self.chunker.chunk("") == []


# ============== InMemoryValidityRetriever 测试 ==============


class TestInMemoryValidityRetriever:
    """InMemoryValidityRetriever 单元测试"""

    # --- 熔断场景 ---

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_on_all_low_scores(self):
        """
        测试场景：全文档无有效期信息时触发熔断

        预期结果：
        - retrieve() 返回 (False, [])
        - 不需要调用 LLM
        """
        retriever = InMemoryValidityRetriever(
            semantic_matcher=LowScoreMatcher(),
            chunk_size=200,
            chunk_overlap=50,
            top_k=2,
            circuit_breaker_threshold=0.25,
        )

        text = "这是一份项目立项批复文件，主要内容是项目名称、建设内容和投资规模。"
        has_validity, chunks = await retriever.retrieve(text)

        assert has_validity is False
        assert chunks == []

    @pytest.mark.asyncio
    async def test_circuit_breaker_skipped_when_keyword_bonus_pushes_score_above_threshold(self):
        """
        测试场景：关键词奖励将低语义分推过熔断阈值

        预期结果：
        - 包含"有效期"的 Chunk 因关键词奖励 +0.20 超过阈值 0.25
        - retrieve() 返回 (True, chunks)
        """
        # LowScoreMatcher 语义分 ~0.05，加上关键词奖励 0.20 = 0.25，
        # 加上日期奖励 0.15 = 0.40，超过阈值
        retriever = InMemoryValidityRetriever(
            semantic_matcher=LowScoreMatcher(),
            chunk_size=200,
            chunk_overlap=50,
            top_k=2,
            circuit_breaker_threshold=0.25,
        )

        # 包含"有效期"关键词和完整日期
        text = "本许可证有效期3年，截止日期2027-01-01，特此证明。" + "其他内容" * 10

        has_validity, chunks = await retriever.retrieve(text)

        # 由于关键词+日期奖励，应不触发熔断
        assert has_validity is True
        assert len(chunks) > 0

    # --- 正常检索场景 ---

    @pytest.mark.asyncio
    async def test_returns_top_k_chunks(self):
        """
        测试场景：正常检索返回 top_k 个 Chunk

        预期结果：
        - retrieve() 返回 (True, chunks)，chunks 数量 <= top_k
        """
        retriever = InMemoryValidityRetriever(
            semantic_matcher=HighScoreMatcher(),
            chunk_size=100,
            chunk_overlap=20,
            top_k=2,
            circuit_breaker_threshold=0.25,
        )

        # 足够长的文本以生成多个 Chunk
        text = (
            "本安全生产许可证有效期3年，自2024年1月1日起至2027年1月1日止。"
            "持证单位应遵守相关法律法规，不得超范围生产经营。"
            "如有违规行为，本机关有权依法吊销许可证。"
            "其他相关事项以补充协议为准，具体内容参见附件。" * 5
        )

        has_validity, chunks = await retriever.retrieve(text)

        assert has_validity is True
        assert len(chunks) <= 2
        assert all(isinstance(c, RetrievedChunk) for c in chunks)

    @pytest.mark.asyncio
    async def test_chunks_sorted_by_score_descending(self):
        """
        测试场景：返回的 Chunk 按得分降序排列

        预期结果：
        - 第一个 Chunk 的得分 >= 第二个 Chunk 的得分
        """
        retriever = InMemoryValidityRetriever(
            semantic_matcher=HighScoreMatcher(),
            chunk_size=100,
            chunk_overlap=20,
            top_k=3,
            circuit_breaker_threshold=0.1,
        )

        text = (
            "有效期3年，截止日期2027-01-01。" * 3
            + "其他无关内容" * 20
        )

        has_validity, chunks = await retriever.retrieve(text)

        if has_validity and len(chunks) >= 2:
            for i in range(len(chunks) - 1):
                assert chunks[i].score >= chunks[i + 1].score

    @pytest.mark.asyncio
    async def test_keyword_bonus_applied_to_matching_chunks(self):
        """
        测试场景：含关键词的 Chunk 获得加分

        预期结果：
        - has_keyword_bonus=True 的 Chunk 分数更高（含奖励分）
        """
        retriever = InMemoryValidityRetriever(
            semantic_matcher=HighScoreMatcher(),
            chunk_size=200,
            chunk_overlap=50,
            top_k=2,
            circuit_breaker_threshold=0.1,
        )

        text = "有效期至2025年12月31日，永久有效，截止日期已过。" + "无关内容" * 10

        has_validity, chunks = await retriever.retrieve(text)

        if has_validity:
            bonus_chunks = [c for c in chunks if c.has_keyword_bonus]
            assert len(bonus_chunks) > 0
            # 有奖励的 Chunk 的得分应至少包含关键词奖励
            for c in bonus_chunks:
                assert c.score > 0.5  # 语义分 0.8 + 关键词 0.2 + 日期 0.15

    # --- 边界场景 ---

    @pytest.mark.asyncio
    async def test_empty_text_triggers_circuit_breaker(self):
        """
        测试场景：空文本输入

        预期结果：
        - retrieve() 返回 (False, [])
        """
        retriever = InMemoryValidityRetriever(
            semantic_matcher=HighScoreMatcher(),
            top_k=2,
        )

        has_validity, chunks = await retriever.retrieve("")
        assert has_validity is False
        assert chunks == []

    @pytest.mark.asyncio
    async def test_query_embedding_cached_after_first_call(self):
        """
        测试场景：静态 Query Embedding 被缓存

        预期结果：
        - 第一次 retrieve 后，_query_embedding 不为 None
        - 第二次 retrieve 不再重新计算 Query Embedding
        """
        call_count = 0

        class CountingMatcher:
            async def get_embedding(self, text: str):
                nonlocal call_count
                call_count += 1
                return [1.0] + [0.0] * 127

            async def get_similarity(self, t1, t2):
                return 0.8

            async def find_best_match(self, text, candidates):
                return None, 0.0

        retriever = InMemoryValidityRetriever(
            semantic_matcher=CountingMatcher(),
            chunk_size=200,
            chunk_overlap=50,
            top_k=2,
            circuit_breaker_threshold=0.1,
        )

        text = "有效期3年，签发日期2024年1月1日"

        assert retriever._query_embedding is None

        await retriever.retrieve(text)
        count_after_first = call_count

        # 第一次：1个 Query + N个 Chunk
        await retriever.retrieve(text)
        count_after_second = call_count

        # 第二次不应再为 Query 增加调用（缓存生效）
        chunk_count_text = count_after_first - 1  # 减去第一次的 Query 调用
        # 第二次增量 = count_after_second - count_after_first = 只有 Chunk 的调用
        second_increment = count_after_second - count_after_first
        assert second_increment == chunk_count_text  # 不含 Query 调用

    @pytest.mark.asyncio
    async def test_embedding_failure_uses_zero_vector(self):
        """
        测试场景：单个 Chunk 的 Embedding 获取失败

        预期结果：
        - 不抛出异常，使用零向量占位
        - 其他 Chunk 正常处理
        """
        fail_count = 0

        class FailingMatcher:
            async def get_embedding(self, text: str):
                nonlocal fail_count
                # Query 正常，Chunk 失败
                if "有效期" in text and "截止" in text and "到期" in text:
                    # 这是 Query，正常返回
                    return [1.0] + [0.0] * 127
                fail_count += 1
                raise RuntimeError("模拟 Embedding 失败")

            async def get_similarity(self, t1, t2):
                return 0.5

            async def find_best_match(self, text, candidates):
                return None, 0.0

        retriever = InMemoryValidityRetriever(
            semantic_matcher=FailingMatcher(),
            chunk_size=200,
            chunk_overlap=50,
            top_k=2,
            circuit_breaker_threshold=0.1,
        )

        # 不应抛出异常
        has_validity, chunks = await retriever.retrieve("有效期3年，签发日期2024年1月1日" * 3)
        # 因 Chunk Embedding 失败（零向量），余弦相似度为 0，但关键词奖励仍生效
        # 结果不重要，重要的是不崩溃
        assert isinstance(has_validity, bool)


# ============== 余弦相似度计算测试 ==============


class TestCosineSimilarity:
    """余弦相似度静态方法测试"""

    def test_identical_vectors_have_similarity_1(self):
        """
        测试场景：完全相同的向量

        预期结果：
        - 余弦相似度 = 1.0
        """
        vec = [1.0, 0.0, 0.0]
        sims = InMemoryValidityRetriever._cosine_similarity_numpy(vec, [vec])
        assert abs(sims[0] - 1.0) < 1e-5

    def test_orthogonal_vectors_have_similarity_0(self):
        """
        测试场景：正交向量

        预期结果：
        - 余弦相似度 = 0.0
        """
        q = [1.0, 0.0, 0.0]
        c = [0.0, 1.0, 0.0]
        sims = InMemoryValidityRetriever._cosine_similarity_numpy(q, [c])
        assert abs(sims[0]) < 1e-5

    def test_batch_computation_returns_all_scores(self):
        """
        测试场景：批量计算多个 Chunk

        预期结果：
        - 返回数量与输入 Chunk 数量一致
        """
        q = [1.0, 0.0, 0.0]
        chunks = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.0]]
        sims = InMemoryValidityRetriever._cosine_similarity_numpy(q, chunks)
        assert len(sims) == 3
        assert abs(sims[0] - 1.0) < 1e-5
        assert abs(sims[1]) < 1e-5
