"""
Application 层 bootstrap 模块单元测试

测试范围：
- Container 依赖注入容器的初始化和属性访问
- create_container 工厂函数

测试策略：
- 使用 Mock 对象隔离 Infrastructure 层依赖
- 验证配置参数正确传递
- 验证异常处理和降级逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from src.compliance_checker.application.bootstrap import Container, create_container
from src.compliance_checker.infrastructure.config.settings import CheckerConfig


class MockLLMConfig:
    """Mock LLM 配置"""

    def __init__(self, api_key="test_key"):
        self.api_key = api_key
        self.base_url = "https://test.api.com"
        self.model = "test-model"


@pytest.fixture
def mock_checker_config():
    """创建测试用的 CheckerConfig"""
    config = CheckerConfig(
        similarity_threshold=0.8,
        use_semantic=True,
        visual_enabled=True,
        visual_confidence_threshold=0.75,
        visual_default_check_type="seal",
        llm_config=MockLLMConfig(api_key="test_api_key"),
        embed_api_key="test_embed_key",
        embed_base_url="https://embed.test.com",
        embed_model="test-embed-model",
        pdf_zoom_factor=2.0,
    )
    return config


@pytest.fixture
def mock_checker_config_no_api_key():
    """创建没有 API Key 的 CheckerConfig（用于测试降级逻辑）"""
    config = CheckerConfig(
        similarity_threshold=0.8,
        use_semantic=True,
        visual_enabled=False,  # 禁用视觉检查
        llm_config=MockLLMConfig(api_key=""),  # 空 API Key
    )
    return config


class TestContainer:
    """测试 Container 依赖注入容器"""

    def test_container_init(self, mock_checker_config):
        """测试 Container 初始化"""
        container = Container(mock_checker_config)

        assert container.config == mock_checker_config
        assert container._llm_client is None
        assert container._semantic_matcher is None
        assert container._visual_client is None
        assert container._ocr_engine is None
        assert container._pdf_converter is None

    def test_container_config_properties(self, mock_checker_config):
        """测试 Container 配置属性访问"""
        container = Container(mock_checker_config)

        # 验证配置对象正确存储
        assert container.config.similarity_threshold == 0.8
        assert container.config.use_semantic is True
        assert container.config.visual_enabled is True
        assert container.config.visual_confidence_threshold == 0.75
        assert container.config.visual_default_check_type == "seal"

    @patch("src.application.bootstrap.LLMClient")
    def test_llm_client_property_with_api_key(self, mock_llm_client_class, mock_checker_config):
        """测试 llm_client 属性 - 有 API Key 时正常初始化"""
        mock_instance = MagicMock()
        mock_llm_client_class.return_value = mock_instance

        container = Container(mock_checker_config)
        client = container.llm_client

        # 验证 LLMClient 被正确创建
        mock_llm_client_class.assert_called_once()
        call_kwargs = mock_llm_client_class.call_args[0][0]
        assert call_kwargs.api_key == "test_api_key"

        # 验证返回的是同一个实例（缓存）
        assert container.llm_client is client

    def test_llm_client_property_without_api_key(self, mock_checker_config_no_api_key):
        """测试 llm_client 属性 - 无 API Key 时返回 None"""
        container = Container(mock_checker_config_no_api_key)

        client = container.llm_client

        # 无 API Key 时应返回 None
        assert client is None

    @patch("src.application.bootstrap.LLMClient")
    def test_llm_client_property_exception_handling(
        self, mock_llm_client_class, mock_checker_config
    ):
        """测试 llm_client 属性 - 初始化异常处理"""
        mock_llm_client_class.side_effect = Exception("Connection failed")

        container = Container(mock_checker_config)
        client = container.llm_client

        # 异常时应返回 None
        assert client is None

    @patch("src.application.bootstrap.LLMClient")
    def test_llm_client_lazy_loading(self, mock_llm_client_class, mock_checker_config):
        """测试 llm_client 延迟加载"""
        container = Container(mock_checker_config)

        # 访问前未初始化
        assert container._llm_client is None

        # 第一次访问触发初始化
        client1 = container.llm_client
        assert mock_llm_client_class.called

        # 第二次访问使用缓存
        mock_llm_client_class.reset_mock()
        client2 = container.llm_client
        assert not mock_llm_client_class.called
        assert client1 is client2

    @patch("src.infrastructure.llm.semantic_matcher.LLMSemanticMatcher")
    def test_semantic_matcher_property_with_config(self, mock_matcher_class, mock_checker_config):
        """测试 semantic_matcher 属性 - 配置正常时初始化"""
        mock_instance = MagicMock()
        mock_matcher_class.return_value = mock_instance

        container = Container(mock_checker_config)
        matcher = container.semantic_matcher

        # 验证 LLMSemanticMatcher 被正确创建
        mock_matcher_class.assert_called_once()
        call_kwargs = mock_matcher_class.call_args.kwargs
        assert call_kwargs["api_key"] == "test_embed_key"
        assert call_kwargs["base_url"] == "https://embed.test.com"
        assert call_kwargs["model"] == "test-embed-model"
        assert call_kwargs["timeout"] == 30.0
        assert call_kwargs["max_retries"] == 3

    def test_semantic_matcher_property_disabled(self, mock_checker_config):
        """测试 semantic_matcher 属性 - 禁用时返回 None"""
        mock_checker_config.use_semantic = False
        container = Container(mock_checker_config)

        matcher = container.semantic_matcher
        assert matcher is None

    @patch("src.infrastructure.llm.semantic_matcher.LLMSemanticMatcher")
    def test_semantic_matcher_exception_handling(self, mock_matcher_class, mock_checker_config):
        """测试 semantic_matcher 属性 - 初始化异常处理"""
        mock_matcher_class.side_effect = Exception("Init failed")

        container = Container(mock_checker_config)
        matcher = container.semantic_matcher

        # 异常时应返回 None
        assert matcher is None

    @patch("src.application.bootstrap.QwenVLClient")
    def test_visual_client_property_available(self, mock_visual_class, mock_checker_config):
        """测试 visual_client 属性 - 可用时初始化"""
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_visual_class.return_value = mock_instance

        container = Container(mock_checker_config)
        client = container.visual_client

        # 验证 QwenVLClient 被创建
        mock_visual_class.assert_called_once()
        assert client is mock_instance

    @patch("src.application.bootstrap.QwenVLClient")
    def test_visual_client_property_not_available(self, mock_visual_class, mock_checker_config):
        """测试 visual_client 属性 - 不可用时仍返回实例"""
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = False
        mock_visual_class.return_value = mock_instance

        container = Container(mock_checker_config)
        client = container.visual_client

        # 即使不可用也返回实例
        assert client is mock_instance

    def test_visual_client_property_disabled(self, mock_checker_config):
        """测试 visual_client 属性 - 禁用时返回 None"""
        mock_checker_config.visual_enabled = False
        container = Container(mock_checker_config)

        client = container.visual_client
        assert client is None

    @patch("src.application.bootstrap.QwenVLClient")
    def test_visual_client_exception_handling(self, mock_visual_class, mock_checker_config):
        """测试 visual_client 属性 - 初始化异常处理"""
        mock_visual_class.side_effect = Exception("Visual init failed")

        container = Container(mock_checker_config)
        client = container.visual_client

        # 异常时应返回 None
        assert client is None

    @patch("src.application.bootstrap.PyMuPDFConverter")
    def test_pdf_converter_property_initialization(self, mock_converter_class, mock_checker_config):
        """测试 pdf_converter 属性 - 正常初始化"""
        mock_instance = MagicMock()
        mock_converter_class.return_value = mock_instance

        container = Container(mock_checker_config)
        converter = container.pdf_converter

        # 验证 PyMuPDFConverter 被正确创建
        mock_converter_class.assert_called_once()
        call_kwargs = mock_converter_class.call_args.kwargs
        assert call_kwargs["zoom_factor"] == 2.0

        # 验证返回的是同一个实例（缓存）
        assert container.pdf_converter is converter

    def test_pdf_converter_property_with_different_zoom(self, mock_checker_config):
        """测试 pdf_converter 属性 - 不同缩放因子配置"""
        mock_checker_config.pdf_zoom_factor = 3.5

        with patch("src.application.bootstrap.PyMuPDFConverter") as mock_converter:
            mock_instance = MagicMock()
            mock_converter.return_value = mock_instance

            container = Container(mock_checker_config)
            converter = container.pdf_converter

            # 验证使用配置的缩放因子
            call_kwargs = mock_converter.call_args.kwargs
            assert call_kwargs["zoom_factor"] == 3.5

    @patch("src.application.bootstrap.PyMuPDFConverter")
    def test_pdf_converter_exception_handling(self, mock_converter_class, mock_checker_config):
        """测试 pdf_converter 属性 - 初始化异常处理"""
        mock_converter_class.side_effect = Exception("Converter init failed")

        container = Container(mock_checker_config)
        converter = container.pdf_converter

        # 异常时应返回 None
        assert converter is None

    @patch("src.application.bootstrap.PyMuPDFConverter")
    def test_pdf_converter_lazy_loading(self, mock_converter_class, mock_checker_config):
        """测试 pdf_converter 延迟加载"""
        mock_instance = MagicMock()
        mock_converter_class.return_value = mock_instance

        container = Container(mock_checker_config)

        # 访问前未初始化
        assert container._pdf_converter is None

        # 第一次访问触发初始化
        converter1 = container.pdf_converter
        assert mock_converter_class.called

        # 第二次访问使用缓存
        mock_converter_class.reset_mock()
        converter2 = container.pdf_converter
        assert not mock_converter_class.called
        assert converter1 is converter2


class TestCreateContainer:
    """测试 create_container 工厂函数"""

    @patch("src.application.bootstrap.CheckerConfig.from_env")
    def test_create_container_default_config(self, mock_from_env):
        """测试使用默认配置创建容器"""
        mock_config = MagicMock()
        mock_from_env.return_value = mock_config

        container = create_container()

        mock_from_env.assert_called_once()
        assert container.config == mock_config

    def test_create_container_custom_config(self, mock_checker_config):
        """测试使用自定义配置创建容器"""
        container = create_container(config=mock_checker_config)

        assert isinstance(container, Container)
        assert container.config == mock_checker_config
        assert container.config.similarity_threshold == 0.8


class TestContainerEdgeCases:
    """测试 Container 边界情况"""

    def test_container_with_minimal_config(self):
        """测试最小配置"""
        config = CheckerConfig(
            similarity_threshold=0.5,
            use_semantic=False,
            visual_enabled=False,
        )

        container = Container(config)

        # 禁用的服务应返回 None
        assert container.semantic_matcher is None
        assert container.visual_client is None
        # LLM 无 API Key 也应返回 None
        assert container.llm_client is None

    def test_container_property_caching(self, mock_checker_config):
        """测试属性缓存行为"""
        with patch("src.application.bootstrap.LLMClient") as mock_llm:
            mock_llm.return_value = MagicMock()

            container = Container(mock_checker_config)

            # 多次访问应返回同一对象
            client1 = container.llm_client
            client2 = container.llm_client
            client3 = container.llm_client

            # 只初始化一次
            mock_llm.assert_called_once()
            assert client1 is client2 is client3
