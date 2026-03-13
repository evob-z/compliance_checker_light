"""
LLM 客户端模块

提供异步调用 LLM 的能力，支持将自然语言转换为 YAML 清单
"""

import asyncio
import logging
from typing import Optional

import yaml

try:
    import openai

    _has_openai = True
except ImportError:
    _has_openai = False
    logging.warning("openai 未安装，LLM 功能将不可用。请运行: pip install openai")

from .config import LLMConfig, get_llm_config
from ..prompts.checklist_generator import generate_checklist_prompt

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM 客户端

    封装 OpenAI 兼容 API 的调用，支持重试和错误处理
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        初始化 LLM 客户端

        Args:
            config: LLM 配置，为 None 则从环境变量读取
        """
        if not _has_openai:
            raise ImportError("使用 LLM 功能需要安装 openai: pip install openai")

        self.config = config or get_llm_config()
        self.client = openai.AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    async def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """
        调用 LLM 完成文本生成

        Args:
            prompt: 提示词
            temperature: 温度参数 (0-1，越低越确定)
            max_tokens: 最大生成 token 数

        Returns:
            生成的文本内容

        Raises:
            Exception: API 调用失败
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的合规审查清单生成助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content
            logger.info(f"LLM 调用成功，生成 {len(content)} 字符")
            return content

        except openai.APIError as e:
            logger.error(f"LLM API 错误: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

    async def generate_yaml(self, user_description: str, temperature: float = 0.3) -> dict:
        """
        将用户自然语言描述转换为 YAML 清单

        Args:
            user_description: 用户的自然语言描述
            temperature: 温度参数

        Returns:
            解析后的 YAML 字典

        Raises:
            ValueError: YAML 解析失败
            Exception: LLM 调用失败
        """
        prompt = generate_checklist_prompt(user_description)

        # 调用 LLM
        content = await self.complete(prompt, temperature=temperature)

        # 清理内容（去除可能的 markdown 代码块标记）
        content = self._clean_yaml_content(content)

        # 解析 YAML
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict) or "checklist" not in data:
                raise ValueError("生成的 YAML 缺少 'checklist' 根节点")
            return data
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析失败: {e}\n内容: {content[:500]}")
            raise ValueError(f"LLM 生成的内容不是有效的 YAML: {e}")

    def _clean_yaml_content(self, content: str) -> str:
        """
        清理 YAML 内容

        去除 markdown 代码块标记等
        """
        # 去除开头的 ```yaml 或 ```
        lines = content.strip().split("\n")

        # 找到第一个非空行
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip() and not line.strip().startswith("```"):
                start_idx = i
                break

        # 找到最后一个非 ``` 行
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].strip().startswith("```"):
                end_idx = i + 1
                break

        return "\n".join(lines[start_idx:end_idx])


# 全局客户端实例（延迟初始化）
_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """
    获取全局 LLM 客户端实例（单例模式）

    Returns:
        LLMClient: 客户端实例
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


async def generate_checklist_from_description(
    user_description: str, config: Optional[LLMConfig] = None
) -> dict:
    """
    便捷函数：将自然语言描述转换为清单

    Args:
        user_description: 用户描述
        config: 可选的配置

    Returns:
        清单字典
    """
    if config:
        client = LLMClient(config)
    else:
        client = get_llm_client()

    return await client.generate_yaml(user_description)
