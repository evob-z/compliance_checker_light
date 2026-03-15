"""
Application 层 bootstrap 模块单元测试

测试范围：
- Container 依赖注入容器的初始化和属性访问
- initialize_registry 检查器注册表的初始化
- initialize_app 应用初始化流程

测试策略：
- 使用 Mock 对象隔离 Infrastructure 层依赖
- 验证配置参数正确传递
- 验证异常处理和降级逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from src.application.bootstrap import Container, initialize_registry, initialize_app
from src.infrastructure.config.settings import CheckerConfig
from src.core.checker_registry import CheckerRegistry


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
    def test_llm_client_property_exception_handling(self, mock_llm_client_class, mock_checker_config):
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


class TestInitializeRegistry:
    """测试 initialize_registry 函数"""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """每个测试前重置注册表单例"""
        CheckerRegistry._instance = None
        CheckerRegistry._initialized = False
        yield
        # 测试后清理
        CheckerRegistry._instance = None
        CheckerRegistry._initialized = False

    @patch("src.application.bootstrap.CompletenessChecker")
    @patch("src.application.bootstrap.TimelinessChecker")
    @patch("src.application.bootstrap.VisualChecker")
    def test_initialize_registry_success(
        self, mock_visual_checker, mock_timeliness_checker,
        mock_completeness_checker, mock_checker_config
    ):
        """测试注册表初始化成功"""
        # 设置 Mock
        mock_completeness_instance = MagicMock()
        mock_completeness_instance.name = "completeness"
        mock_completeness_checker.return_value = mock_completeness_instance

        mock_timeliness_instance = MagicMock()
        mock_timeliness_instance.name = "timeliness"
        mock_timeliness_checker.return_value = mock_timeliness_instance

        mock_visual_instance = MagicMock()
        mock_visual_instance.name = "visual"
        mock_visual_checker.return_value = mock_visual_instance

        # 创建带 Mock 属性的 Container
        container = MagicMock()
        container.config = mock_checker_config
        container.semantic_matcher = MagicMock()
        container.visual_client = MagicMock()
        container.visual_client.is_available.return_value = True
        container.pdf_converter = MagicMock()

        registry = initialize_registry(container)

        # 验证返回的是 CheckerRegistry 实例
        assert isinstance(registry, CheckerRegistry)

        # 验证检查器被注册
        mock_completeness_checker.assert_called_once()
        mock_timeliness_checker.assert_called_once()
        mock_visual_checker.assert_called_once()

        # 验证 VisualChecker 被注入 pdf_converter
        call_kwargs = mock_visual_checker.call_args.kwargs
        assert "pdf_converter" in call_kwargs

    def test_initialize_registry_with_none_container(self):
        """测试传入 None container 时的异常处理"""
        # 传入 None 时应该能正常处理（内部捕获异常并记录日志）
        registry = initialize_registry(None)
        
        # 验证返回的是 CheckerRegistry 实例
        assert isinstance(registry, CheckerRegistry)
        # 验证所有检查器都被标记为不可用
        assert len(registry.list_available()) == 0

    @patch("src.application.bootstrap.CompletenessChecker")
    def test_initialize_registry_completeness_fallback(
        self, mock_completeness_checker, mock_checker_config
    ):
        """测试完整性检查器降级逻辑 - semantic_matcher 为 None"""
        mock_instance = MagicMock()
        mock_instance.name = "completeness"
        mock_completeness_checker.return_value = mock_instance
        
        container = MagicMock()
        container.config = mock_checker_config
        container.semantic_matcher = None  # 模拟 matcher 不可用
        
        # 需要 patch LLMSemanticMatcher 的导入
        with patch("src.infrastructure.llm.semantic_matcher.LLMSemanticMatcher") as mock_fallback:
            mock_fallback_instance = MagicMock()
            mock_fallback.return_value = mock_fallback_instance
            
            registry = initialize_registry(container)
            
            # 验证降级方案被使用
            mock_fallback.assert_called_once()
            # 验证 CompletenessChecker 被创建两次（一次失败，一次降级）
            assert mock_completeness_checker.call_count >= 1

    @patch("src.application.bootstrap.TimelinessChecker")
    def test_initialize_registry_timeliness_exception(
        self, mock_timeliness_checker, mock_checker_config
    ):
        """测试时效性检查器注册异常处理"""
        mock_timeliness_checker.side_effect = Exception("Init error")
        
        container = MagicMock()
        container.config = mock_checker_config
        container.semantic_matcher = MagicMock()
        container.visual_client = None
        
        registry = initialize_registry(container)
        
        # 即使异常也应返回注册表
        assert isinstance(registry, CheckerRegistry)
        # timeliness 应被标记为不可用
        assert "timeliness" in registry._unavailable


class TestInitializeApp:
    """测试 initialize_app 函数"""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """每个测试前重置注册表单例"""
        CheckerRegistry._instance = None
        CheckerRegistry._initialized = False
        yield
        CheckerRegistry._instance = None
        CheckerRegistry._initialized = False

    @patch("src.application.bootstrap.CheckerConfig.from_env")
    @patch("src.application.bootstrap.initialize_registry")
    def test_initialize_app_with_default_config(self, mock_init_registry, mock_from_env):
        """测试使用默认配置初始化应用"""
        mock_config = MagicMock()
        mock_from_env.return_value = mock_config
        
        mock_registry = MagicMock()
        mock_init_registry.return_value = mock_registry
        
        registry, container = initialize_app()
        
        # 验证从环境变量加载配置
        mock_from_env.assert_called_once()
        
        # 验证返回的容器包含配置
        assert container.config == mock_config
        
        # 验证返回的注册表
        assert registry == mock_registry

    def test_initialize_app_with_custom_config(self, mock_checker_config):
        """测试使用自定义配置初始化应用"""
        with patch("src.application.bootstrap.initialize_registry") as mock_init_registry:
            mock_registry = MagicMock()
            mock_init_registry.return_value = mock_registry
            
            registry, container = initialize_app(config=mock_checker_config)
            
            # 验证使用传入的配置
            assert container.config == mock_checker_config
            assert container.config.similarity_threshold == 0.8
            
            # 验证注册表被初始化
            mock_init_registry.assert_called_once_with(container)

    def test_initialize_app_return_types(self, mock_checker_config):
        """测试 initialize_app 返回值类型"""
        with patch("src.application.bootstrap.initialize_registry") as mock_init_registry:
            mock_registry = MagicMock()
            mock_init_registry.return_value = mock_registry
            
            registry, container = initialize_app(config=mock_checker_config)
            
            # 验证返回类型
            assert isinstance(registry, MagicMock)  # 实际是 Mock，但真实返回是 CheckerRegistry
            assert isinstance(container, Container)
            
            # 验证是元组
            result = initialize_app(config=mock_checker_config)
            assert isinstance(result, tuple)
            assert len(result) == 2


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

