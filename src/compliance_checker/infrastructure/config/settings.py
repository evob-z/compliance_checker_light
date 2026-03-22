"""
配置设置模块

Infrastructure 层的配置加载功能。
负责所有 os.getenv 读取和默认值设置，属于 I/O 操作层。

架构原则：
- 环境变量读取（os.getenv）属于 I/O 操作，归属于 Infrastructure 层
- Domain 层不直接导入 settings，配置通过 Application 层注入
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from ..llm.config import LLMConfig

# ==================== 路径默认值 ====================
DEFAULT_DOCUMENT_PATH = Path("./documents")
DEFAULT_OUTPUT_DIR = Path("./output")


# ==================== OCR 默认值 ====================
DEFAULT_OCR_BACKEND = "none"


@dataclass
class CheckerConfig:
    """
    检查器配置数据类

    从环境变量加载配置，传递给 Domain 层检查器。
    遵循『Domain 层不能直接 import settings』的架构原则。

    Attributes:
        similarity_threshold: 语义匹配相似度阈值
        use_semantic: 是否启用语义匹配
        project_period: 项目周期（用于时效性检查）
        visual_enabled: 是否启用视觉检查
        visual_confidence_threshold: 视觉检测置信度阈值
        visual_default_check_type: 默认视觉检查类型
        llm_config: LLM 配置
        embed_api_key: 嵌入模型 API 密钥
        embed_base_url: 嵌入模型 API 端点
        embed_model: 嵌入模型名称
        embed_timeout: 嵌入模型请求超时
        embed_max_retries: 嵌入模型最大重试次数
    """

    # 完整性检查器配置
    similarity_threshold: float = 0.75
    use_semantic: bool = True

    # 时效性检查器配置
    project_period: Optional[Dict[str, str]] = None

    # 视觉检查器配置
    visual_enabled: bool = True
    visual_confidence_threshold: float = 0.7
    visual_default_check_type: str = "both"

    # LLM 配置
    llm_config: LLMConfig = field(default_factory=lambda: LLMConfig(api_key=""))

    # 嵌入模型配置（用于语义匹配）
    embed_api_key: Optional[str] = None
    embed_base_url: Optional[str] = None
    embed_model: str = "text-embedding-v1"
    embed_timeout: float = 30.0
    embed_max_retries: int = 3

    # OCR 配置
    ocr_backend: str = "none"

    # PDF 转换器配置
    pdf_zoom_factor: float = 2.0  # PDF 渲染缩放因子，影响印章清晰度

    @classmethod
    def from_env(cls) -> "CheckerConfig":
        """
        从环境变量创建配置

        Returns:
            CheckerConfig 实例
        """
        # LLM 配置
        llm_config = LLMConfig(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("LLM_MODEL", "gpt-4o"),
            timeout=int(os.getenv("LLM_TIMEOUT", "60")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            system_prompt="你是一个专业的合规审查清单生成助手。",
        )

        # 嵌入模型配置（优先使用专用配置，否则使用 LLM 配置）
        embed_api_key = os.getenv("EMBED_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        embed_base_url = os.getenv("EMBED_BASE_URL", "") or os.getenv("LLM_BASE_URL", "")
        embed_model = os.getenv("EMBED_MODEL", "text-embedding-v1")

        return cls(
            similarity_threshold=float(os.getenv("CC_SIMILARITY_THRESHOLD", "0.75")),
            use_semantic=os.getenv("CC_USE_SEMANTIC", "true").lower() == "true",
            visual_enabled=os.getenv("CC_VISUAL_ENABLED", "true").lower() == "true",
            visual_confidence_threshold=float(os.getenv("CC_VISUAL_CONFIDENCE_THRESHOLD", "0.7")),
            visual_default_check_type=os.getenv("CC_VISUAL_CHECK_TYPE", "both"),
            llm_config=llm_config,
            embed_api_key=embed_api_key if embed_api_key else None,
            embed_base_url=embed_base_url if embed_base_url else None,
            embed_model=embed_model,
            ocr_backend=os.getenv("OCR_BACKEND", "none"),
            pdf_zoom_factor=float(os.getenv("CC_PDF_ZOOM_FACTOR", "2.0")),
        )


def generate_output_path(project_id: str) -> Path:
    """
    生成报告输出路径

    Args:
        project_id: 项目标识符

    Returns:
        输出文件的 Path 对象
    """
    output_dir = Path(os.getenv("CC_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"compliance_report_{project_id}.pdf"


def scan_default_documents() -> List[str]:
    """
    扫描默认文档目录

    Returns:
        文档文件路径列表
    """
    doc_path = Path(os.getenv("CC_DOCUMENT_PATH", DEFAULT_DOCUMENT_PATH))

    if not doc_path.exists():
        return []

    supported_extensions = {".pdf", ".docx", ".doc"}
    document_paths = []

    for ext in supported_extensions:
        for file_path in doc_path.glob(f"*{ext}"):
            if file_path.is_file():
                document_paths.append(str(file_path))

    return sorted(document_paths)


def get_ocr_backend() -> str:
    """
    获取 OCR 后端类型

    Returns:
        OCR 后端类型: "none", "paddle", "aliyun"
    """
    return os.getenv("OCR_BACKEND", DEFAULT_OCR_BACKEND)


def get_aliyun_ocr_credentials() -> Optional[Tuple[str, str]]:
    """
    获取阿里云 OCR 凭证

    Returns:
        (access_key_id, access_key_secret) 元组，未配置则返回 None
    """
    access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    if access_key_id and access_key_secret:
        return (access_key_id, access_key_secret)
    return None
