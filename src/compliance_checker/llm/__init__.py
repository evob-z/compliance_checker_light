"""
LLM 模块

提供大语言模型调用能力，用于将自然语言转换为 YAML 清单
"""

from .client import LLMClient, generate_checklist_from_description
from .config import LLMConfig, get_llm_config

__all__ = [
    "LLMClient",
    "generate_checklist_from_description",
    "LLMConfig",
    "get_llm_config",
]
