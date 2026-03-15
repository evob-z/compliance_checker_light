"""
QwenVLClient 集成测试

⚠️ 注意：此测试需要配置真实的视觉模型 API。
   请在 .env 文件或环境变量中设置：
   - VISION_API_KEY 或 LLM_API_KEY: API 密钥
   - VISION_BASE_URL 或 LLM_BASE_URL: API 基础 URL（可选）
   - VISION_MODEL: 模型名称（可选，默认 qwen3-vl-flash）

测试目标：
    - 验证 QwenVLClient 能正常调用真实视觉 API
    - 验证能检测真实图片中的内容
    - 验证返回结果包含实际检测信息
    - 不使用 Mock，真实调用 API 和读取图片
"""

import os
import pytest
from pathlib import Path

from src.infrastructure.visual.qwen_client import (
    QwenVLClient,
    VisualAPIError,
    ImageReadError,
)

# ============== 环境配置检查 ==============


def get_vision_config():
    """从环境变量获取视觉模型配置"""
    api_key = os.getenv("VISION_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("VISION_BASE_URL") or os.getenv("LLM_BASE_URL")
    model = os.getenv("VISION_MODEL", "qwen3-vl-flash")

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def is_vision_available() -> bool:
    """检查视觉 API 是否可用"""
    config = get_vision_config()
    return bool(config["api_key"])


# ============== 测试 Fixtures ==============


@pytest.fixture
def fixtures_dir() -> Path:
    """获取 fixtures 目录路径"""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_image_path(fixtures_dir: Path) -> Path:
    """获取测试用图片文件路径"""
    return fixtures_dir / "dummy_seal.jpg"


# ============== 实例化测试 ==============


class TestQwenVLClientInit:
    """QwenVLClient 实例化测试"""

    def test_init_with_all_params(self):
        """
        测试使用所有参数初始化

        验证：
        - 所有参数正确保存
        - 正确识别 OpenAI 兼容模式
        """
        client = QwenVLClient(
            api_key="test-key",
            base_url="https://test.api.com/v1",
            model="custom-model",
        )

        assert client.api_key == "test-key"
        assert client.base_url == "https://test.api.com/v1"
        assert client.model == "custom-model"
        assert client.use_openai_format is True  # /v1 结尾

    def test_init_default_values(self):
        """
        测试使用默认值初始化

        验证：
        - model 默认为 "qwen3-vl-flash"
        - base_url 默认为 OpenAI 兼容模式
        """
        client = QwenVLClient(api_key="test-key")

        assert client.api_key == "test-key"
        assert client.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert client.model == "qwen3-vl-flash"
        assert client.use_openai_format is True

    def test_init_openai_format_detection_compatible_mode(self):
        """
        测试 OpenAI 兼容模式检测（compatible-mode）

        验证：
        - 包含 "compatible-mode" 的 URL 识别为 OpenAI 格式
        """
        client = QwenVLClient(
            api_key="test-key",
            base_url="https://custom.com/compatible-mode/v1",
        )

        assert client.use_openai_format is True

    def test_init_openai_format_detection_v1_endpoint(self):
        """
        测试 OpenAI 兼容模式检测（/v1 结尾）

        验证：
        - 以 /v1 结尾的 URL 识别为 OpenAI 格式
        """
        client = QwenVLClient(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )

        assert client.use_openai_format is True

    def test_init_aliyun_native_format(self):
        """
        测试阿里云原生格式检测

        验证：
        - 非 OpenAI 格式的 URL 使用阿里云原生格式
        """
        client = QwenVLClient(
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/api",
        )

        assert client.use_openai_format is False

    def test_init_no_api_key(self, monkeypatch):
        """
        测试无 API key 初始化

        验证：
        - 允许无 API key 初始化
        - is_available() 返回 False
        """
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        client = QwenVLClient()

        assert client.api_key is None
        assert client.is_available() is False


# ============== is_available 测试 ==============


class TestQwenVLClientIsAvailable:
    """QwenVLClient.is_available 方法测试"""

    def test_is_available_with_key(self):
        """
        测试有 API key 时的可用性

        验证：
        - 返回 True
        """
        client = QwenVLClient(api_key="test-key")

        assert client.is_available() is True

    def test_is_available_without_key(self, monkeypatch):
        """
        测试无 API key 时的可用性

        验证：
        - 返回 False
        """
        # 清除环境变量，确保测试不受 .env 影响
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        client = QwenVLClient(api_key=None)

        assert client.is_available() is False

    def test_is_available_with_empty_key(self, monkeypatch):
        """
        测试空 API key 时的可用性

        验证：
        - 返回 False
        """
        # 清除环境变量，确保测试不受 .env 影响
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        client = QwenVLClient(api_key="")

        assert client.is_available() is False


# ============== 真实 API 调用测试 ==============


@pytest.mark.skipif(
    not is_vision_available(),
    reason="视觉 API 未配置（需要设置 VISION_API_KEY 或 LLM_API_KEY 环境变量）",
)
@pytest.mark.asyncio
class TestQwenVLClientRealAPI:
    """QwenVLClient 真实 API 调用测试"""

    async def test_detect_seal_returns_result(self, sample_image_path: Path):
        """
        测试 detect_seal 返回结果

        验证：
        - 返回类型是字典
        - 包含必要字段
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        config = get_vision_config()
        client = QwenVLClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        context = "检测图片中是否存在公章。请回答：是否存在公章、置信度（高/中/低）、位置。"
        result = await client.detect_seal(str(sample_image_path), context=context)

        assert isinstance(result, dict), "返回结果应该是字典"
        assert "success" in result, "应该包含 success 字段"
        assert "found" in result, "应该包含 found 字段"
        assert "confidence" in result, "应该包含 confidence 字段"
        assert "reasoning" in result, "应该包含 reasoning 字段"
        assert "location" in result, "应该包含 location 字段"

    async def test_detect_seal_detects_content(self, sample_image_path: Path):
        """
        测试 detect_seal 能检测到内容

        验证：
        - API 调用成功
        - reasoning 包含实际内容
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        config = get_vision_config()
        client = QwenVLClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        context = "检测图片中是否存在公章。请回答：是否存在公章、置信度、位置。"
        result = await client.detect_seal(str(sample_image_path), context=context)

        # 验证 API 调用成功
        assert result["success"] is True, f"API 调用应该成功: {result.get('reasoning', '')}"

        # 验证 reasoning 包含实际内容（不只是空字符串）
        assert len(result["reasoning"].strip()) > 0, "reasoning 应该包含实际内容"

    async def test_detect_signature_returns_result(self, sample_image_path: Path):
        """
        测试 detect_signature 返回结果

        验证：
        - 返回类型是字典
        - 包含必要字段
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        config = get_vision_config()
        client = QwenVLClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        context = "检测图片中是否存在签名。请回答：是否存在签名、置信度、位置。"
        result = await client.detect_signature(str(sample_image_path), context=context)

        assert isinstance(result, dict)
        assert "success" in result
        assert "found" in result
        assert "confidence" in result

    async def test_detect_signature_detects_content(self, sample_image_path: Path):
        """
        测试 detect_signature 能检测到内容

        验证：
        - API 调用成功
        - reasoning 包含实际内容
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        config = get_vision_config()
        client = QwenVLClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        context = "检测图片中是否存在签名。请回答：是否存在签名、置信度、位置。"
        result = await client.detect_signature(str(sample_image_path), context=context)

        # 验证 API 调用成功
        assert result["success"] is True, f"API 调用应该成功: {result.get('reasoning', '')}"

        # 验证 reasoning 包含实际内容
        assert len(result["reasoning"].strip()) > 0, "reasoning 应该包含实际内容"

    async def test_detect_with_chinese_context(self, sample_image_path: Path):
        """
        测试中文提示词

        验证：
        - 能正确处理中文提示词
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        config = get_vision_config()
        client = QwenVLClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
        )

        context = "请描述这张图片的内容。图片中有什么？"
        result = await client.detect_seal(str(sample_image_path), context=context)

        assert result["success"] is True
        # 应该返回一些描述内容
        assert len(result["reasoning"]) > 0


# ============== 错误处理测试 ==============


class TestQwenVLClientErrorHandling:
    """QwenVLClient 错误处理测试"""

    def test_detect_seal_without_context_raises_error(self):
        """
        测试缺少 context 参数

        验证：
        - 抛出 ValueError
        """
        client = QwenVLClient(api_key="test-key")

        import asyncio

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(client.detect_seal("/path/to/image.jpg"))

        assert "context" in str(exc_info.value).lower()

    def test_detect_signature_without_context_raises_error(self):
        """
        测试缺少 context 参数

        验证：
        - 抛出 ValueError
        """
        client = QwenVLClient(api_key="test-key")

        import asyncio

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(client.detect_signature("/path/to/image.jpg"))

        assert "context" in str(exc_info.value).lower()

    def test_detect_seal_from_bytes_without_context_raises_error(self):
        """
        测试 detect_seal_from_bytes 缺少 context 参数

        验证：
        - 抛出 ValueError
        """
        client = QwenVLClient(api_key="test-key")

        import asyncio

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(client.detect_seal_from_bytes(b"fake_image_bytes"))

        assert "context" in str(exc_info.value).lower()

    def test_detect_signature_from_bytes_without_context_raises_error(self):
        """
        测试 detect_signature_from_bytes 缺少 context 参数

        验证：
        - 抛出 ValueError
        """
        client = QwenVLClient(api_key="test-key")

        import asyncio

        with pytest.raises(ValueError) as exc_info:
            asyncio.run(client.detect_signature_from_bytes(b"fake_image_bytes"))

        assert "context" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_detect_seal_not_available(self, monkeypatch, sample_image_path: Path):
        """
        测试 API 不可用时

        验证：
        - 返回不可用标记的结果
        """
        # 清除环境变量，确保 API 不可用
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        client = QwenVLClient(api_key=None)

        # 使用真实存在的图片
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        result = await client.detect_seal(str(sample_image_path), context="测试")

        assert result["success"] is False
        assert result["found"] is False
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_detect_signature_not_available(self, monkeypatch, sample_image_path: Path):
        """
        测试 API 不可用时

        验证：
        - 返回不可用标记的结果
        """
        # 清除环境变量，确保 API 不可用
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        client = QwenVLClient(api_key=None)

        # 使用真实存在的图片
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        result = await client.detect_signature(str(sample_image_path), context="测试")

        assert result["success"] is False
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_detect_nonexistent_image(self):
        """
        测试不存在的图片

        验证：
        - 抛出 ImageReadError
        """
        client = QwenVLClient(api_key="test-key")

        with pytest.raises(ImageReadError):
            await client.detect_seal("/nonexistent/path/image.jpg", context="测试")


# ============== 响应解析测试 ==============


class TestQwenVLClientParseContent:
    """QwenVLClient 响应解析测试"""

    def test_parse_with_existence_marker_yes(self):
        """
        测试解析"是"标记

        验证：
        - found 为 True
        """
        client = QwenVLClient(api_key="test-key")
        content = "是否存在公章：是\n置信度：高\n位置：右下角"

        result = client._parse_detection_content(content)

        assert result["found"] is True
        assert result["confidence"] > 0.5

    def test_parse_with_existence_marker_no(self):
        """
        测试解析"否"标记

        验证：
        - found 为 False
        """
        client = QwenVLClient(api_key="test-key")
        content = "是否存在公章：否\n置信度：高"

        result = client._parse_detection_content(content)

        assert result["found"] is False

    def test_parse_confidence_high(self):
        """
        测试高置信度解析

        验证：
        - 包含"高"时 confidence 为 0.9
        """
        client = QwenVLClient(api_key="test-key")
        content = "置信度：高"

        result = client._parse_detection_content(content)

        assert result["confidence"] == 0.9

    def test_parse_confidence_medium(self):
        """
        测试中置信度解析

        验证：
        - 包含"中"时 confidence 为 0.6
        """
        client = QwenVLClient(api_key="test-key")
        content = "置信度：中"

        result = client._parse_detection_content(content)

        assert result["confidence"] == 0.6

    def test_parse_confidence_low(self):
        """
        测试低置信度解析

        验证：
        - 包含"低"时 confidence 为 0.3
        """
        client = QwenVLClient(api_key="test-key")
        content = "置信度：低"

        result = client._parse_detection_content(content)

        assert result["confidence"] == 0.3

    def test_parse_numeric_confidence(self):
        """
        测试数字置信度解析

        验证：
        - 正确解析 [0.95] 格式的置信度
        """
        client = QwenVLClient(api_key="test-key")
        content = "置信度：[0.85]"

        result = client._parse_detection_content(content)

        assert result["confidence"] == 0.85

    def test_parse_location(self):
        """
        测试位置信息解析

        验证：
        - 正确提取位置关键词
        """
        client = QwenVLClient(api_key="test-key")
        locations = ["右下角", "左下角", "右上角", "左上角", "中央"]

        for loc in locations:
            content = f"位置：{loc}"
            result = client._parse_detection_content(content)
            assert result["location"] == loc

    def test_parse_empty_content(self):
        """
        测试空内容处理

        验证：
        - 返回默认值
        """
        client = QwenVLClient(api_key="test-key")
        result = client._parse_detection_content("")

        assert result["found"] is False
        assert result["confidence"] == 0.0
        assert result["location"] == ""


# ============== 异常类测试 ==============


class TestQwenVLClientExceptions:
    """QwenVLClient 异常类测试"""

    def test_visual_api_error_inheritance(self):
        """
        测试 VisualAPIError 继承关系

        验证：
        - VisualAPIError 继承自 ComplianceCheckerError
        """
        from src.core.exceptions import ComplianceCheckerError

        assert issubclass(VisualAPIError, ComplianceCheckerError)

    def test_image_read_error_inheritance(self):
        """
        测试 ImageReadError 继承关系

        验证：
        - ImageReadError 继承自 ComplianceCheckerError
        """
        from src.core.exceptions import ComplianceCheckerError

        assert issubclass(ImageReadError, ComplianceCheckerError)

    def test_visual_api_error_message(self):
        """
        测试 VisualAPIError 消息

        验证：
        - 可以正确设置错误消息
        """
        error = VisualAPIError("Test error message")

        assert str(error) == "Test error message"

    def test_image_read_error_message(self):
        """
        测试 ImageReadError 消息

        验证：
        - 可以正确设置错误消息
        """
        error = ImageReadError("Failed to read image")

        assert str(error) == "Failed to read image"
