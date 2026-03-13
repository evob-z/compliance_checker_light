"""
LLM 配置模块

从环境变量读取 LLM 配置
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    """LLM 配置数据类"""

    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    timeout: int = 60
    max_retries: int = 3


def get_llm_config() -> LLMConfig:
    """
    从环境变量获取 LLM 配置

    必需环境变量:
        LLM_API_KEY: API 密钥

    可选环境变量:
        LLM_BASE_URL: API 端点 (默认: https://api.openai.com/v1)
        LLM_MODEL: 模型名称 (默认: gpt-4o)
        LLM_TIMEOUT: 超时时间秒数 (默认: 60)
        LLM_MAX_RETRIES: 最大重试次数 (默认: 3)

    Returns:
        LLMConfig: 配置对象

    Raises:
        ValueError: 缺少必需的 LLM_API_KEY
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("缺少 LLM_API_KEY 环境变量。" "请在 .env 文件中设置或使用 export LLM_API_KEY=your-key")

    return LLMConfig(
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        timeout=int(os.getenv("LLM_TIMEOUT", "60")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
    )
