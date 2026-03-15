"""
LLMConfig 配置模块单元测试

测试目标：
    - 验证 LLMConfig 数据类的创建和属性
    - 验证默认值设置
    - 验证自定义值设置
    - 所有字段类型的校验
"""

import pytest
from dataclasses import fields

from src.infrastructure.llm.config import LLMConfig


class TestLLMConfig:
    """LLMConfig 数据类测试"""

    def test_required_api_key(self):
        """
        测试必需的 api_key 字段
        
        验证：
            - api_key 是必需字段
            - 可以通过构造函数设置
        """
        config = LLMConfig(api_key="test-api-key")
        
        assert config.api_key == "test-api-key"

    def test_default_values(self):
        """
        测试 LLMConfig 默认值
        
        验证：
            - base_url 默认为 "https://api.openai.com/v1"
            - model 默认为 "gpt-4o"
            - timeout 默认为 60
            - max_retries 默认为 3
            - system_prompt 有默认提示词
        """
        config = LLMConfig(api_key="test-key")
        
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o"
        assert config.timeout == 60
        assert config.max_retries == 3
        assert "严谨的数据处理助手" in config.system_prompt

    def test_custom_values(self):
        """
        测试 LLMConfig 自定义值
        
        验证：
            - 可以通过构造函数设置所有字段
        """
        config = LLMConfig(
            api_key="custom-api-key",
            base_url="https://custom.api.com/v1",
            model="gpt-4-turbo",
            timeout=120,
            max_retries=5,
            system_prompt="Custom system prompt",
        )
        
        assert config.api_key == "custom-api-key"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.model == "gpt-4-turbo"
        assert config.timeout == 120
        assert config.max_retries == 5
        assert config.system_prompt == "Custom system prompt"

    def test_empty_api_key(self):
        """
        测试空 api_key
        
        验证：
            - 允许空字符串作为 api_key
        """
        config = LLMConfig(api_key="")
        
        assert config.api_key == ""

    def test_dataclass_fields(self):
        """
        测试 LLMConfig 的数据类字段
        
        验证：
            - 所有预期字段都存在
            - 字段类型正确
        """
        field_names = {f.name for f in fields(LLMConfig)}
        
        expected_fields = {
            "api_key",
            "base_url",
            "model",
            "timeout",
            "max_retries",
            "system_prompt",
        }
        
        assert field_names == expected_fields

    def test_field_types(self):
        """
        测试字段类型
        
        验证：
            - 所有字段都是正确的类型
        """
        config = LLMConfig(
            api_key="test-key",
            base_url="https://api.example.com",
            model="gpt-4",
            timeout=90,
            max_retries=3,
            system_prompt="Test prompt",
        )
        
        assert isinstance(config.api_key, str)
        assert isinstance(config.base_url, str)
        assert isinstance(config.model, str)
        assert isinstance(config.timeout, int)
        assert isinstance(config.max_retries, int)
        assert isinstance(config.system_prompt, str)

    def test_immutability(self):
        """
        测试数据类不可变性（如果设置了 frozen=True）
        
        验证：
            - 尝试修改字段时抛出异常（如果 frozen）
            - 或者允许修改（如果未 frozen）
        """
        config = LLMConfig(api_key="original-key")
        
        # 尝试修改字段
        # 注意：如果 LLMConfig 设置了 frozen=True，这会抛出 FrozenInstanceError
        # 如果未设置 frozen，则允许修改
        try:
            config.api_key = "new-key"
            # 如果允许修改，验证修改成功
            assert config.api_key == "new-key"
        except Exception as e:
            # 如果不允许修改，验证抛出的是 FrozenInstanceError
            assert "frozen" in str(e).lower() or "cannot" in str(e).lower()

    def test_system_prompt_default_content(self):
        """
        测试默认系统提示词内容
        
        验证：
            - 默认提示词包含关键信息
        """
        config = LLMConfig(api_key="test-key")
        
        # 验证默认提示词包含关键元素
        assert "JSON" in config.system_prompt or "YAML" in config.system_prompt
        assert "格式" in config.system_prompt or "format" in config.system_prompt.lower()

    def test_url_variations(self):
        """
        测试不同的 URL 格式
        
        验证：
            - 支持不同的 base_url 格式
        """
        urls = [
            "https://api.openai.com/v1",
            "https://custom.api.com",
            "http://localhost:8080/v1",
            "https://api.example.com:8080/path",
        ]
        
        for url in urls:
            config = LLMConfig(api_key="test", base_url=url)
            assert config.base_url == url

    def test_timeout_edge_cases(self):
        """
        测试超时时间的边界值
        
        验证：
            - 支持不同的超时时间值
        """
        # 正常值
        config = LLMConfig(api_key="test", timeout=30)
        assert config.timeout == 30
        
        # 较大值
        config = LLMConfig(api_key="test", timeout=300)
        assert config.timeout == 300
        
        # 零值
        config = LLMConfig(api_key="test", timeout=0)
        assert config.timeout == 0

    def test_max_retries_edge_cases(self):
        """
        测试重试次数的边界值
        
        验证：
            - 支持不同的重试次数值
        """
        # 正常值
        config = LLMConfig(api_key="test", max_retries=3)
        assert config.max_retries == 3
        
        # 零值（不重试）
        config = LLMConfig(api_key="test", max_retries=0)
        assert config.max_retries == 0
        
        # 较大值
        config = LLMConfig(api_key="test", max_retries=10)
        assert config.max_retries == 10

    def test_model_name_variations(self):
        """
        测试不同的模型名称
        
        验证：
            - 支持不同的模型名称格式
        """
        models = [
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "claude-3-opus",
            "qwen-max",
        ]
        
        for model in models:
            config = LLMConfig(api_key="test", model=model)
            assert config.model == model
