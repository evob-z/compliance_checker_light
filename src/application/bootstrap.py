"""
Application 层启动器模块

负责依赖注入和检查器注册，避免 Core 层与 Domain 层之间的循环依赖。
遵循 architecture.md 的『第 6 节 避免循环依赖』和『第 7 节 配置注入策略』。

架构原则：
- 环境变量读取（os.getenv）属于 I/O 操作，归属于 Infrastructure 层
- Application 层从 Infrastructure 层导入配置，注入到 Domain 层
"""

import logging
from typing import Optional

from ..core.checker_registry import CheckerRegistry
from ..infrastructure.llm.client import LLMClient
from ..infrastructure.llm.ocr_engine import create_ocr_engine, OCREngineProtocol
from ..infrastructure.config.settings import CheckerConfig

# Domain 层检查器
from ..domain.checkers.completeness import CompletenessChecker
from ..domain.checkers.timeliness import TimelinessChecker
from ..domain.checkers.compliance import VisualChecker

# Infrastructure 层客户端
from ..infrastructure.visual.qwen_client import QwenVLClient
from ..infrastructure.converter.pdf_converter import PyMuPDFConverter

logger = logging.getLogger(__name__)


class Container:
    """
    依赖注入容器

    管理所有 Infrastructure 层客户端实例的生命周期，
    并在 Application 层组装依赖关系。
    """

    def __init__(self, config: CheckerConfig):
        """
        初始化容器

        Args:
            config: 检查器配置
        """
        self.config = config
        self._llm_client: Optional[LLMClient] = None
        self._semantic_matcher: Optional["LLMSemanticMatcher"] = None
        self._visual_client: Optional[QwenVLClient] = None
        self._ocr_engine: Optional[OCREngineProtocol] = None
        self._pdf_converter: Optional[PyMuPDFConverter] = None

    @property
    def llm_client(self) -> Optional[LLMClient]:
        """获取 LLM 客户端实例（延迟加载）"""
        if self._llm_client is None:
            if self.config.llm_config.api_key:
                try:
                    self._llm_client = LLMClient(self.config.llm_config)
                    logger.info(f"LLM 客户端初始化成功: {self.config.llm_config.model}")
                except Exception as e:
                    logger.warning(f"LLM 客户端初始化失败: {e}")
            else:
                logger.warning("未配置 LLM_API_KEY，LLM 功能将不可用")
        return self._llm_client

    @property
    def semantic_matcher(self) -> Optional["LLMSemanticMatcher"]:
        """获取语义匹配器实例（延迟加载）"""
        if self._semantic_matcher is None and self.config.use_semantic:
            try:
                # 延迟导入，避免循环依赖
                from ..infrastructure.llm.semantic_matcher import LLMSemanticMatcher

                self._semantic_matcher = LLMSemanticMatcher(
                    api_key=self.config.embed_api_key,
                    base_url=self.config.embed_base_url,
                    model=self.config.embed_model,
                    timeout=self.config.embed_timeout,
                    max_retries=self.config.embed_max_retries,
                )
                logger.info(f"语义匹配器初始化成功: {self.config.embed_model}")
            except Exception as e:
                logger.warning(f"语义匹配器初始化失败: {e}")
        return self._semantic_matcher

    @property
    def visual_client(self) -> Optional[QwenVLClient]:
        """获取视觉客户端实例（延迟加载）"""
        if self._visual_client is None and self.config.visual_enabled:
            try:
                self._visual_client = QwenVLClient()
                if self._visual_client.is_available():
                    logger.info(f"视觉客户端初始化成功: {self._visual_client.model}")
                else:
                    logger.warning("视觉客户端初始化完成，但 API 未配置")
            except Exception as e:
                logger.warning(f"视觉客户端初始化失败: {e}")
        return self._visual_client

    @property
    def ocr_engine(self) -> Optional[OCREngineProtocol]:
        """获取 OCR 引擎实例（延迟加载）"""
        if self._ocr_engine is None:
            try:
                self._ocr_engine = create_ocr_engine(self.config.ocr_backend)
                logger.info(f"OCR 引擎初始化成功: {self.config.ocr_backend}")
            except Exception as e:
                logger.warning(f"OCR 引擎初始化失败: {e}，将使用无 OCR 模式")
                from ..infrastructure.llm.ocr_engine import NoOCREngine

                self._ocr_engine = NoOCREngine()
        return self._ocr_engine

    @property
    def pdf_converter(self) -> Optional[PyMuPDFConverter]:
        """获取 PDF 转换器实例（延迟加载）"""
        if self._pdf_converter is None:
            try:
                self._pdf_converter = PyMuPDFConverter(
                    zoom_factor=self.config.pdf_zoom_factor,
                )
                logger.info("PDF 转换器初始化成功 (PyMuPDF)")
            except Exception as e:
                logger.warning(f"PDF 转换器初始化失败: {e}")
        return self._pdf_converter


def initialize_registry(container: Container) -> CheckerRegistry:
    """
    初始化检查器注册表

    在 Application 层完成检查器的实例化和注册，避免 Core 层依赖 Domain 层。
    遵循 Bootstrap 模式解决循环依赖问题。

    Args:
        container: 依赖注入容器

    Returns:
        配置好的 CheckerRegistry 实例
    """
    registry = CheckerRegistry()

    # ==================== 1. 注册完整性检查器 ====================
    try:
        semantic_matcher = container.semantic_matcher
        if semantic_matcher:
            completeness_checker = CompletenessChecker(
                matcher=semantic_matcher,
                similarity_threshold=container.config.similarity_threshold,
                use_semantic=container.config.use_semantic,
            )
            registry.register(completeness_checker)
            logger.info("完整性检查器注册成功（带语义匹配）")
        else:
            # [架构警告] 采用局部导入以避免 Core 与 Infrastructure 之间的提前加载和潜在循环依赖。
            # 此处 LLMSemanticMatcher 作为降级方案，仅在语义匹配器不可用时使用。
            # 切勿将此 import 移至文件顶部，否则会破坏分层架构的依赖规则。
            from ..infrastructure.llm.semantic_matcher import LLMSemanticMatcher

            fallback_matcher = LLMSemanticMatcher(
                api_key=None,  # 使用备用方法
                base_url=None,
                model=None,
            )
            completeness_checker = CompletenessChecker(
                matcher=fallback_matcher,
                similarity_threshold=container.config.similarity_threshold,
                use_semantic=False,  # 禁用语义匹配
            )
            registry.register(completeness_checker)
            logger.info("完整性检查器注册成功（降级模式：无语义匹配）")
    except Exception as e:
        logger.error(f"完整性检查器注册失败: {e}")
        registry.register_unavailable("completeness")

    # ==================== 2. 注册时效性检查器 ====================
    try:
        timeliness_checker = TimelinessChecker(
            project_period=container.config.project_period,
        )
        registry.register(timeliness_checker)
        logger.info("时效性检查器注册成功")
    except Exception as e:
        logger.error(f"时效性检查器注册失败: {e}")
        registry.register_unavailable("timeliness")

    # ==================== 3. 注册视觉检查器 ====================
    # 注意：VisualChecker 的 name 属性返回 "compliance"，但检查类型可能是 "visual" 或 "compliance"
    # 为了兼容性，我们同时注册两个名称指向同一个检查器实例
    try:
        visual_client = container.visual_client
        pdf_converter = container.pdf_converter
        if visual_client and visual_client.is_available():
            visual_checker = VisualChecker(
                visual_client=visual_client,
                pdf_converter=pdf_converter,  # 注入 PDF 转换器
                default_check_type=container.config.visual_default_check_type,
                confidence_threshold=container.config.visual_confidence_threshold,
                enabled=container.config.visual_enabled,
            )
            registry.register(visual_checker)
            # 同时注册 "visual" 别名，确保清单中的 "visual" 检查类型能找到检查器
            from ..core.checker_base import AliasCheckerWrapper

            registry.register(AliasCheckerWrapper(visual_checker, "visual"))
            logger.info("视觉检查器注册成功 (compliance + visual)")
        else:
            logger.warning("视觉客户端不可用，视觉检查器将返回不可用状态")
            # 仍然注册，但会在检查时返回 unavailable 状态
            from ..infrastructure.visual.qwen_client import QwenVLClient

            dummy_client = QwenVLClient(api_key="")
            visual_checker = VisualChecker(
                visual_client=dummy_client,
                pdf_converter=pdf_converter,  # 注入 PDF 转换器（即使禁用）
                default_check_type=container.config.visual_default_check_type,
                confidence_threshold=container.config.visual_confidence_threshold,
                enabled=False,  # 禁用
            )
            registry.register(visual_checker)
            # 同时注册 "visual" 别名
            from ..core.checker_base import AliasCheckerWrapper

            registry.register(AliasCheckerWrapper(visual_checker, "visual"))
    except Exception as e:
        logger.error(f"视觉检查器注册失败: {e}")
        registry.register_unavailable("compliance")
        registry.register_unavailable("visual")

    # ==================== 4. 标记未实现的检查器 ====================
    # 注意：compliance 检查器已在上面注册为 VisualChecker，不需要标记为不可用
    logger.debug("检查器注册完成")

    logger.info(f"检查器注册完成，可用检查器: {registry.list_available()}")
    return registry


def initialize_app(config: Optional[CheckerConfig] = None) -> tuple[CheckerRegistry, Container]:
    """
    初始化应用

    完整的应用初始化流程，从配置加载到检查器注册。

    Args:
        config: 可选的配置对象，默认从环境变量加载

    Returns:
        (CheckerRegistry, Container) 元组
    """
    if config is None:
        config = CheckerConfig.from_env()

    container = Container(config)
    registry = initialize_registry(container)

    return registry, container
