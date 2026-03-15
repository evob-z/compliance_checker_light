"""
LLMSemanticMatcher 集成测试

⚠️ 注意：此测试需要配置真实的嵌入模型 API。
   请在 .env 文件或环境变量中设置：
   - EMBED_API_KEY 或 LLM_API_KEY: API 密钥
   - EMBED_BASE_URL 或 LLM_BASE_URL: API 基础 URL（可选）

测试目标：
    - 验证 LLMSemanticMatcher 能正常调用真实嵌入 API
    - 验证返回的嵌入向量包含实际数据
    - 验证相似度计算功能
    - 不使用 Mock，真实调用 API
"""

import os
import pytest

from src.infrastructure.llm.semantic_matcher import LLMSemanticMatcher

# ============== 环境配置检查 ==============


def get_embed_config():
    """从环境变量获取嵌入模型配置"""
    api_key = os.getenv("EMBED_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("EMBED_BASE_URL") or os.getenv("LLM_BASE_URL")
    model = os.getenv("EMBED_MODEL", "text-embedding-v3")

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def is_embed_available() -> bool:
    """检查嵌入 API 是否可用"""
    config = get_embed_config()
    return bool(config["api_key"])


# ============== 实例化测试 ==============


class TestLLMSemanticMatcherInit:
    """LLMSemanticMatcher 实例化测试"""

    def test_init_with_all_params(self):
        """
        测试使用所有参数初始化

        验证：
        - 所有参数正确保存
        - 缓存初始化为空字典
        """
        matcher = LLMSemanticMatcher(
            api_key="test-key",
            base_url="https://api.test.com",
            model="custom-model",
            timeout=60.0,
            max_retries=5,
        )

        assert matcher._api_key == "test-key"
        assert matcher._base_url == "https://api.test.com"
        assert matcher._model == "custom-model"
        assert matcher._timeout == 60.0
        assert matcher._max_retries == 5
        assert matcher._cache == {}
        assert matcher._client is None

    def test_init_with_defaults(self):
        """
        测试使用默认值初始化

        验证：
        - 可选参数使用默认值
        - model 默认为 "text-embedding-v3"
        """
        matcher = LLMSemanticMatcher()

        assert matcher._api_key is None
        assert matcher._base_url is None
        assert matcher._model == "text-embedding-v3"
        assert matcher._timeout == 30.0
        assert matcher._max_retries == 3


# ============== 真实 API 调用测试 ==============


@pytest.mark.skipif(
    not is_embed_available(),
    reason="嵌入 API 未配置（需要设置 EMBED_API_KEY 或 LLM_API_KEY 环境变量）",
)
@pytest.mark.asyncio
class TestLLMSemanticMatcherRealAPI:
    """LLMSemanticMatcher 真实 API 调用测试"""

    async def test_get_embedding_returns_vector(self):
        """
        测试 get_embedding 返回向量

        验证：
        - 返回类型是列表
        - 列表元素是浮点数
        - 向量长度大于 0
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.get_embedding("测试文本")

        assert isinstance(result, list), "返回结果应该是列表"
        assert len(result) > 0, "向量长度应该大于 0"
        assert all(isinstance(x, float) for x in result), "向量元素应该是浮点数"

    async def test_get_embedding_vector_dimension(self):
        """
        测试嵌入向量维度

        验证：
        - 向量维度合理（通常 1024 或 1536）
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.get_embedding("测试文本")

        # 常见嵌入模型维度：1024, 1280, 1536
        assert len(result) >= 512, f"向量维度 {len(result)} 过小"
        assert len(result) <= 4096, f"向量维度 {len(result)} 过大"

    async def test_get_embedding_caching(self):
        """
        测试嵌入缓存

        验证：
        - 相同文本返回相同向量（缓存命中）
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        text = "缓存测试文本"
        result1 = await matcher.get_embedding(text)
        result2 = await matcher.get_embedding(text)

        # 应该返回完全相同的向量（缓存）
        assert result1 == result2, "相同文本应该返回相同向量（缓存）"

    async def test_get_similarity_returns_float(self):
        """
        测试 get_similarity 返回浮点数

        验证：
        - 返回类型是浮点数
        - 值在 0-1 范围内
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.get_similarity("文本1", "文本2")

        assert isinstance(result, float), "返回结果应该是浮点数"
        assert 0 <= result <= 1, f"相似度 {result} 应该在 0-1 范围内"

    async def test_get_similarity_identical_texts(self):
        """
        测试相同文本的相似度

        验证：
        - 相同文本相似度接近 1.0
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.get_similarity("相同的文本", "相同的文本")

        assert result > 0.99, f"相同文本相似度 {result} 应该接近 1.0"

    async def test_get_similarity_similar_texts(self):
        """
        测试相似文本的相似度

        验证：
        - 相似文本相似度较高
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        # 语义相似的文本
        result = await matcher.get_similarity("项目立项批复文件", "立项批复")

        # 相似度应该较高
        assert result > 0.5, f"相似文本相似度 {result} 应该较高"

    async def test_get_similarity_different_texts(self):
        """
        测试不同文本的相似度

        验证：
        - 完全不同文本相似度较低
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        # 语义完全不同的文本
        result = await matcher.get_similarity("项目立项批复文件", "天气预报今天下雨")

        # 相似度应该较低
        assert result < 0.7, f"不同文本相似度 {result} 应该较低"

    async def test_find_best_match_returns_result(self):
        """
        测试 find_best_match 返回结果

        验证：
        - 能找到最佳匹配
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        candidates = ["立项批复", "环评报告", "施工许可证"]
        best_match, similarity = await matcher.find_best_match("项目立项文件", candidates)

        assert best_match is not None, "应该找到最佳匹配"
        assert best_match in candidates, "最佳匹配应该在候选列表中"
        assert isinstance(similarity, float), "相似度应该是浮点数"
        assert 0 <= similarity <= 1, "相似度应该在 0-1 范围内"

    async def test_find_best_match_correctness(self):
        """
        测试 find_best_match 正确性

        验证：
        - 能正确识别最相似的候选
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        candidates = ["环境评估报告", "环境影响评价", "施工图纸"]
        best_match, _ = await matcher.find_best_match("环评报告", candidates)

        # 应该匹配到语义最接近的
        assert best_match in [
            "环境评估报告",
            "环境影响评价",
        ], f"最佳匹配 '{best_match}' 应该是环境相关的文档"

    async def test_find_best_match_empty_candidates(self):
        """
        测试空候选列表

        验证：
        - 返回 (None, 0.0)
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        best_match, similarity = await matcher.find_best_match("测试文本", [])

        assert best_match is None
        assert similarity == 0.0

    async def test_calculate_similarity_returns_max(self):
        """
        测试 calculate_similarity 返回最高相似度

        验证：
        - 返回多个目标中的最高相似度
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.calculate_similarity(
            "立项批复", ["项目立项批准文件", "环评报告", "施工许可"]
        )

        # 应该返回最高相似度
        assert isinstance(result, float)
        assert 0 <= result <= 1
        # "项目立项批准文件" 应该最相似
        assert result > 0.5

    async def test_calculate_similarity_empty_targets(self):
        """
        测试空目标列表

        验证：
        - 返回 0.0
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.calculate_similarity("测试文件", [])

        assert result == 0.0

    async def test_chinese_text_embedding(self):
        """
        测试中文文本嵌入

        验证：
        - 能正确处理中文文本
        """
        config = get_embed_config()
        matcher = LLMSemanticMatcher(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        result = await matcher.get_embedding("这是一个中文测试文本")

        assert isinstance(result, list)
        assert len(result) > 0


# ============== 备用方法测试 ==============


class TestLLMSemanticMatcherFallback:
    """LLMSemanticMatcher 备用方法测试"""

    def test_simple_embedding_returns_vector(self):
        """
        测试简单嵌入返回向量

        验证：
        - 返回固定长度（128）的向量
        - 向量已归一化
        """
        matcher = LLMSemanticMatcher()

        result = matcher._simple_embedding("test text")

        assert isinstance(result, list)
        assert len(result) == 128
        assert all(isinstance(x, float) for x in result)

    def test_simple_embedding_normalization(self):
        """
        测试向量归一化

        验证：
        - 向量 L2 范数为 1（或接近 1）
        """
        matcher = LLMSemanticMatcher()

        result = matcher._simple_embedding("test text")

        # 计算 L2 范数
        norm = sum(x**2 for x in result) ** 0.5

        # 如果向量非零，应该已归一化
        if any(x != 0 for x in result):
            assert abs(norm - 1.0) < 0.01  # 允许小误差

    def test_simple_embedding_consistency(self):
        """
        测试嵌入一致性

        验证：
        - 相同输入产生相同输出
        """
        matcher = LLMSemanticMatcher()

        result1 = matcher._simple_embedding("same text")
        result2 = matcher._simple_embedding("same text")

        assert result1 == result2

    def test_simple_embedding_different_inputs(self):
        """
        测试不同输入产生不同输出

        验证：
        - 不同输入产生不同的嵌入
        """
        matcher = LLMSemanticMatcher()

        result1 = matcher._simple_embedding("text one")
        result2 = matcher._simple_embedding("text two")

        assert result1 != result2


# ============== 余弦相似度测试 ==============


class TestLLMSemanticMatcherCosineSimilarity:
    """LLMSemanticMatcher 余弦相似度测试"""

    def test_identical_vectors(self):
        """
        测试相同向量的相似度

        验证：
        - 相同向量的相似度为 1.0
        """
        matcher = LLMSemanticMatcher()
        vec = [0.5, 0.5, 0.5, 0.5]
        result = matcher._cosine_similarity(vec, vec)

        assert result == 1.0

    def test_orthogonal_vectors(self):
        """
        测试正交向量的相似度

        验证：
        - 正交向量的相似度为 0.0
        """
        matcher = LLMSemanticMatcher()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        result = matcher._cosine_similarity(vec1, vec2)

        assert result == 0.0

    def test_opposite_vectors(self):
        """
        测试相反向量的相似度

        验证：
        - 相反向量的相似度为 -1.0
        """
        matcher = LLMSemanticMatcher()
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        result = matcher._cosine_similarity(vec1, vec2)

        assert result == -1.0

    def test_zero_vector(self):
        """
        测试零向量

        验证：
        - 零向量的相似度为 0.0
        """
        matcher = LLMSemanticMatcher()
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        result = matcher._cosine_similarity(vec1, vec2)

        assert result == 0.0
