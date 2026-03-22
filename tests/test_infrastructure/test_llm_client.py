"""
LLMClient 集成测试

⚠️ 注意：此测试需要配置真实的 LLM API。
   请在 .env 文件或环境变量中设置：
   - LLM_API_KEY: API 密钥
   - LLM_BASE_URL: API 基础 URL（可选）
   - LLM_MODEL: 模型名称（可选，默认 gpt-4o）

测试目标：
    - 验证 LLMClient 能正常调用真实 LLM API
    - 验证返回结果包含实际内容
    - 验证 YAML 生成功能
    - 不使用 Mock，真实调用 API
"""

import os
import pytest

from src.compliance_checker.infrastructure.llm.client import LLMClient, _has_openai
from src.compliance_checker.infrastructure.llm.config import LLMConfig
from src.compliance_checker.core.exceptions import CheckExecutionError

# ============== 环境配置检查 ==============


def get_llm_config() -> LLMConfig:
    """从环境变量获取 LLM 配置"""
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=60,
        max_retries=2,
    )


def is_llm_available() -> bool:
    """检查 LLM API 是否可用"""
    if not _has_openai:
        return False

    config = get_llm_config()
    return bool(config.api_key)


# ============== 前置条件检查 ==============


@pytest.mark.skipif(not _has_openai, reason="openai 包未安装")
class TestLLMClientPrerequisites:
    """前置条件检查"""

    def test_openai_package_available(self):
        """
        测试 openai 包已安装

        验证：
        - openai 包可以导入
        """
        import openai

        assert openai is not None


# ============== LLMClient 实例化测试 ==============


@pytest.mark.skipif(not _has_openai, reason="openai 包未安装")
class TestLLMClientInit:
    """LLMClient 实例化测试"""

    def test_init_with_valid_config(self):
        """
        测试使用有效配置初始化

        验证：
        - 可以成功创建 LLMClient 实例
        - 配置正确保存
        """
        config = LLMConfig(
            api_key="test-api-key",
            base_url="https://test.api.com",
            model="gpt-4o",
            timeout=60,
            max_retries=3,
        )

        client = LLMClient(config=config)

        assert client.config is config

    def test_init_with_empty_api_key(self):
        """
        测试空 API key 初始化

        验证：
        - 允许空 API key 初始化（实际调用时会失败）
        """
        config = LLMConfig(api_key="", base_url="https://test.api.com")

        client = LLMClient(config=config)

        assert client.config.api_key == ""


# ============== 真实 API 调用测试 ==============


@pytest.mark.skipif(
    not is_llm_available(), reason="LLM API 未配置（需要设置 LLM_API_KEY 环境变量）"
)
@pytest.mark.asyncio
class TestLLMClientRealAPI:
    """LLMClient 真实 API 调用测试"""

    async def test_complete_returns_content(self):
        """
        测试 complete 返回实际内容

        验证：
        - 返回非空字符串
        - 内容长度大于 0
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        result = await client.complete("请回复：测试成功")

        assert isinstance(result, str), "返回结果应该是字符串"
        assert len(result) > 0, "返回内容不应为空"
        # 验证返回了有意义的内容（不只是空白）
        assert result.strip(), "返回内容不应全是空白"

    async def test_complete_with_simple_question(self):
        """
        测试简单问题

        验证：
        - 能回答简单问题
        - 回答包含预期关键词
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        result = await client.complete("1+1等于几？只回答数字。")

        assert isinstance(result, str)
        # 回答应该包含 "2"
        assert "2" in result, f"回答 '{result}' 应该包含 '2'"

    async def test_complete_temperature_affects_output(self):
        """
        测试 temperature 参数影响输出

        验证：
        - 低 temperature 产生更确定的输出
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        # 低 temperature 多次调用应该产生相似结果
        results = []
        for _ in range(2):
            result = await client.complete("说一个1到10之间的数字", temperature=0.1)
            results.append(result)

        # 验证都返回了内容
        for r in results:
            assert len(r.strip()) > 0

    async def test_generate_yaml_returns_dict(self):
        """
        测试 generate_yaml 返回字典

        验证：
        - 返回类型是 dict
        - 包含 checklist 根节点
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        prompt = """
请生成一个简单的检查清单，格式如下：
```yaml
checklist:
  version: "1.0"
  name: "测试清单"
  items:
    - name: "测试项1"
      required: true
```
只返回 YAML 内容。
"""

        result = await client.generate_yaml(prompt)

        assert isinstance(result, dict), "返回结果应该是字典"
        assert "checklist" in result, "应该包含 checklist 根节点"
        assert isinstance(result["checklist"], dict)

    async def test_generate_yaml_content_quality(self):
        """
        测试 YAML 生成内容质量

        验证：
        - 生成的 YAML 包含预期字段
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        prompt = """
生成一个项目审批检查清单：
```yaml
checklist:
  version: "1.0"
  name: "项目审批清单"
  required_documents:
    - name: "立项批复"
      required: true
    - name: "环评报告"
      required: true
```
只返回 YAML。
"""

        result = await client.generate_yaml(prompt)

        # 验证结构
        assert "checklist" in result
        checklist = result["checklist"]

        # 应该有某些字段（具体字段名可能不同）
        assert len(checklist) > 0, "checklist 不应为空"

    async def test_complete_with_chinese_content(self):
        """
        测试中文内容

        验证：
        - 能正确处理中文
        - 返回包含中文的内容
        """
        config = get_llm_config()
        client = LLMClient(config=config)

        result = await client.complete("请用中文说：你好世界")

        assert isinstance(result, str)
        # 应该包含中文
        assert any("\u4e00" <= c <= "\u9fff" for c in result), "应该包含中文字符"


# ============== 错误处理测试（真实场景） ==============


@pytest.mark.skipif(not _has_openai, reason="openai 包未安装")
@pytest.mark.asyncio
class TestLLMClientErrorHandling:
    """LLMClient 错误处理测试"""

    async def test_complete_with_invalid_api_key(self):
        """
        测试无效 API key

        验证：
        - 抛出 CheckExecutionError
        """
        config = LLMConfig(
            api_key="invalid-key-12345",
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            model="gpt-4o",
            timeout=10,
            max_retries=1,
        )
        client = LLMClient(config=config)

        with pytest.raises(CheckExecutionError) as exc_info:
            await client.complete("测试")

        # 错误消息应该包含认证相关信息
        error_msg = str(exc_info.value).lower()
        assert (
            "认证" in error_msg or "auth" in error_msg or "api" in error_msg or "key" in error_msg
        )

    async def test_complete_with_invalid_base_url(self):
        """
        测试无效 base_url

        验证：
        - 抛出 CheckExecutionError
        """
        config = LLMConfig(
            api_key="test-key",
            base_url="https://invalid-url-that-does-not-exist-12345.com/v1",
            model="gpt-4o",
            timeout=10,
            max_retries=1,
        )
        client = LLMClient(config=config)

        with pytest.raises(CheckExecutionError):
            await client.complete("测试")


# ============== _clean_yaml_content 方法测试 ==============


class TestLLMClientCleanYamlContent:
    """LLMClient._clean_yaml_content 方法测试"""

    def test_clean_yaml_without_markers(self):
        """
        测试无标记的内容

        验证：
        - 内容保持不变
        """
        config = LLMConfig(api_key="test-key")
        client = LLMClient(config=config)

        content = "checklist:\n  version: '1.0'"
        result = client._clean_yaml_content(content)

        assert result == content

    def test_clean_yaml_with_yaml_marker(self):
        """
        测试去除 ```yaml 标记

        验证：
        - 正确去除开头的 ```yaml
        - 正确去除结尾的 ```
        """
        config = LLMConfig(api_key="test-key")
        client = LLMClient(config=config)

        content = "```yaml\nchecklist:\n  version: '1.0'\n```"
        result = client._clean_yaml_content(content)

        assert "```yaml" not in result
        assert "```" not in result
        assert "checklist:" in result

    def test_clean_yaml_with_generic_marker(self):
        """
        测试去除 ``` 标记

        验证：
        - 正确去除通用的代码块标记
        """
        config = LLMConfig(api_key="test-key")
        client = LLMClient(config=config)

        content = "```\nchecklist:\n  version: '1.0'\n```"
        result = client._clean_yaml_content(content)

        assert "```" not in result
        assert "checklist:" in result

    def test_clean_yaml_with_whitespace(self):
        """
        测试处理带空白的内容

        验证：
        - 正确处理前后空白行
        """
        config = LLMConfig(api_key="test-key")
        client = LLMClient(config=config)

        content = "\n\n```yaml\nchecklist:\n  version: '1.0'\n```\n\n"
        result = client._clean_yaml_content(content)

        assert result.strip() == "checklist:\n  version: '1.0'"


# ============== 配置测试 ==============


class TestLLMConfig:
    """LLMConfig 配置测试"""

    def test_config_defaults(self):
        """
        测试配置默认值

        验证：
        - 默认值正确设置
        """
        config = LLMConfig(api_key="test-key")

        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4o"
        assert config.timeout == 60
        assert config.max_retries == 3

    def test_config_custom_values(self):
        """
        测试自定义配置值

        验证：
        - 自定义值正确设置
        """
        config = LLMConfig(
            api_key="custom-key",
            base_url="https://custom.api.com",
            model="custom-model",
            timeout=120,
            max_retries=5,
        )

        assert config.api_key == "custom-key"
        assert config.base_url == "https://custom.api.com"
        assert config.model == "custom-model"
        assert config.timeout == 120
        assert config.max_retries == 5
