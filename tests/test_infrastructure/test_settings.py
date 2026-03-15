"""
Settings 配置模块单元测试

测试目标：
    - 验证 CheckerConfig 数据类的创建和属性
    - 验证从环境变量加载配置的功能
    - 验证路径生成和文档扫描功能
    - 验证 OCR 配置功能
    - 所有异常类型和错误信息的校验
"""

import os
import pytest
from pathlib import Path
from dataclasses import fields

from src.infrastructure.config.settings import (
    CheckerConfig,
    DEFAULT_DOCUMENT_PATH,
    DEFAULT_OUTPUT_DIR,
    generate_output_path,
    scan_default_documents,
    get_ocr_backend,
    get_aliyun_ocr_credentials,
)
from src.infrastructure.llm.config import LLMConfig


# ============== CheckerConfig 数据类测试 ==============


class TestCheckerConfig:
    """CheckerConfig 数据类测试"""

    def test_default_values(self):
        """
        测试 CheckerConfig 默认值
        
        验证：
            - 所有字段都有正确的默认值
            - similarity_threshold 默认为 0.75
            - use_semantic 默认为 True
            - visual_enabled 默认为 True
            - visual_confidence_threshold 默认为 0.7
            - visual_default_check_type 默认为 "both"
            - embed_model 默认为 "text-embedding-v1"
            - embed_timeout 默认为 30.0
            - embed_max_retries 默认为 3
        """
        config = CheckerConfig()
        
        # 完整性检查器配置
        assert config.similarity_threshold == 0.75
        assert config.use_semantic is True
        
        # 时效性检查器配置
        assert config.project_period is None
        
        # 视觉检查器配置
        assert config.visual_enabled is True
        assert config.visual_confidence_threshold == 0.7
        assert config.visual_default_check_type == "both"
        
        # 嵌入模型配置
        assert config.embed_api_key is None
        assert config.embed_base_url is None
        assert config.embed_model == "text-embedding-v1"
        assert config.embed_timeout == 30.0
        assert config.embed_max_retries == 3

    def test_custom_values(self):
        """
        测试 CheckerConfig 自定义值
        
        验证：
            - 可以通过构造函数设置所有字段
        """
        llm_config = LLMConfig(api_key="test-key")
        
        config = CheckerConfig(
            similarity_threshold=0.85,
            use_semantic=False,
            project_period={"start": "2024-01-01", "end": "2024-12-31"},
            visual_enabled=False,
            visual_confidence_threshold=0.8,
            visual_default_check_type="seal",
            llm_config=llm_config,
            embed_api_key="embed-key",
            embed_base_url="https://embed.api.com",
            embed_model="text-embedding-v2",
            embed_timeout=60.0,
            embed_max_retries=5,
        )
        
        assert config.similarity_threshold == 0.85
        assert config.use_semantic is False
        assert config.project_period == {"start": "2024-01-01", "end": "2024-12-31"}
        assert config.visual_enabled is False
        assert config.visual_confidence_threshold == 0.8
        assert config.visual_default_check_type == "seal"
        assert config.llm_config is llm_config
        assert config.embed_api_key == "embed-key"
        assert config.embed_base_url == "https://embed.api.com"
        assert config.embed_model == "text-embedding-v2"
        assert config.embed_timeout == 60.0
        assert config.embed_max_retries == 5

    def test_llm_config_default_factory(self):
        """
        测试 llm_config 默认工厂
        
        验证：
            - 默认创建 LLMConfig 实例
            - api_key 默认为空字符串
        """
        config = CheckerConfig()
        
        assert isinstance(config.llm_config, LLMConfig)
        assert config.llm_config.api_key == ""

    def test_dataclass_fields(self):
        """
        测试 CheckerConfig 的数据类字段
        
        验证：
            - 所有预期字段都存在
        """
        field_names = {f.name for f in fields(CheckerConfig)}
        
        expected_fields = {
            "similarity_threshold",
            "use_semantic",
            "project_period",
            "visual_enabled",
            "visual_confidence_threshold",
            "visual_default_check_type",
            "llm_config",
            "embed_api_key",
            "embed_base_url",
            "embed_model",
            "embed_timeout",
            "embed_max_retries",
            "ocr_backend",
        }
        
        assert field_names == expected_fields


# ============== 环境变量加载测试 ==============


class TestCheckerConfigFromEnv:
    """CheckerConfig.from_env() 测试"""

    def test_from_env_default_values(self, monkeypatch):
        """
        测试从环境变量加载默认值
        
        验证：
            - 当环境变量未设置时使用默认值
        """
        # 清除相关环境变量
        env_vars = [
            "CC_SIMILARITY_THRESHOLD",
            "CC_USE_SEMANTIC",
            "CC_VISUAL_ENABLED",
            "CC_VISUAL_CONFIDENCE_THRESHOLD",
            "CC_VISUAL_CHECK_TYPE",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL",
            "LLM_TIMEOUT",
            "LLM_MAX_RETRIES",
            "EMBED_API_KEY",
            "EMBED_BASE_URL",
            "EMBED_MODEL",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)
        
        config = CheckerConfig.from_env()
        
        assert config.similarity_threshold == 0.75
        assert config.use_semantic is True
        assert config.visual_enabled is True
        assert config.visual_confidence_threshold == 0.7
        assert config.visual_default_check_type == "both"

    def test_from_env_custom_values(self, monkeypatch):
        """
        测试从环境变量加载自定义值
        
        验证：
            - 环境变量值正确覆盖默认值
        """
        monkeypatch.setenv("CC_SIMILARITY_THRESHOLD", "0.9")
        monkeypatch.setenv("CC_USE_SEMANTIC", "false")
        monkeypatch.setenv("CC_VISUAL_ENABLED", "false")
        monkeypatch.setenv("CC_VISUAL_CONFIDENCE_THRESHOLD", "0.85")
        monkeypatch.setenv("CC_VISUAL_CHECK_TYPE", "signature")
        monkeypatch.setenv("LLM_API_KEY", "test-api-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.api.com")
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        monkeypatch.setenv("LLM_TIMEOUT", "120")
        monkeypatch.setenv("LLM_MAX_RETRIES", "5")
        monkeypatch.setenv("EMBED_API_KEY", "embed-key")
        monkeypatch.setenv("EMBED_BASE_URL", "https://embed.api.com")
        monkeypatch.setenv("EMBED_MODEL", "text-embedding-v3")
        
        config = CheckerConfig.from_env()
        
        assert config.similarity_threshold == 0.9
        assert config.use_semantic is False
        assert config.visual_enabled is False
        assert config.visual_confidence_threshold == 0.85
        assert config.visual_default_check_type == "signature"
        assert config.llm_config.api_key == "test-api-key"
        assert config.llm_config.base_url == "https://custom.api.com"
        assert config.llm_config.model == "gpt-4"
        assert config.llm_config.timeout == 120
        assert config.llm_config.max_retries == 5
        assert config.embed_api_key == "embed-key"
        assert config.embed_base_url == "https://embed.api.com"
        assert config.embed_model == "text-embedding-v3"

    def test_from_env_embed_fallback_to_llm(self, monkeypatch):
        """
        测试嵌入模型配置回退到 LLM 配置
        
        验证：
            - 当 EMBED_API_KEY 未设置时，使用 LLM_API_KEY
            - 当 EMBED_BASE_URL 未设置时，使用 LLM_BASE_URL
        """
        monkeypatch.setenv("LLM_API_KEY", "shared-api-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://shared.api.com")
        monkeypatch.delenv("EMBED_API_KEY", raising=False)
        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        
        config = CheckerConfig.from_env()
        
        assert config.embed_api_key == "shared-api-key"
        assert config.embed_base_url == "https://shared.api.com"

    def test_from_env_boolean_parsing(self, monkeypatch):
        """
        测试布尔值环境变量解析
        
        验证：
            - "true" 解析为 True
            - "false" 解析为 False
            - "TRUE" 解析为 True
            - "FALSE" 解析为 False
        """
        # 测试 true 变体
        monkeypatch.setenv("CC_USE_SEMANTIC", "true")
        config = CheckerConfig.from_env()
        assert config.use_semantic is True
        
        monkeypatch.setenv("CC_USE_SEMANTIC", "TRUE")
        config = CheckerConfig.from_env()
        assert config.use_semantic is True
        
        monkeypatch.setenv("CC_USE_SEMANTIC", "True")
        config = CheckerConfig.from_env()
        assert config.use_semantic is True
        
        # 测试 false 变体
        monkeypatch.setenv("CC_USE_SEMANTIC", "false")
        config = CheckerConfig.from_env()
        assert config.use_semantic is False
        
        monkeypatch.setenv("CC_USE_SEMANTIC", "FALSE")
        config = CheckerConfig.from_env()
        assert config.use_semantic is False
        
        monkeypatch.setenv("CC_USE_SEMANTIC", "False")
        config = CheckerConfig.from_env()
        assert config.use_semantic is False


# ============== 路径生成测试 ==============


class TestGenerateOutputPath:
    """generate_output_path 函数测试"""

    def test_generate_output_path_default(self, tmp_path, monkeypatch):
        """
        测试默认输出路径生成
        
        验证：
            - 路径包含项目 ID
            - 使用默认输出目录
        """
        monkeypatch.setenv("CC_OUTPUT_DIR", str(tmp_path))
        
        output_path = generate_output_path("project123")
        
        assert isinstance(output_path, Path)
        assert output_path.name == "compliance_report_project123.pdf"
        assert output_path.parent == tmp_path

    def test_generate_output_path_creates_directory(self, tmp_path, monkeypatch):
        """
        测试输出目录自动创建
        
        验证：
            - 目录不存在时自动创建
        """
        new_dir = tmp_path / "new_output_dir"
        monkeypatch.setenv("CC_OUTPUT_DIR", str(new_dir))
        
        assert not new_dir.exists()
        
        output_path = generate_output_path("test")
        
        assert new_dir.exists()
        assert new_dir.is_dir()


# ============== 文档扫描测试 ==============


class TestScanDefaultDocuments:
    """scan_default_documents 函数测试"""

    def test_scan_empty_directory(self, tmp_path, monkeypatch):
        """
        测试空目录扫描
        
        验证：
            - 空目录返回空列表
        """
        monkeypatch.setenv("CC_DOCUMENT_PATH", str(tmp_path))
        
        result = scan_default_documents()
        
        assert isinstance(result, list)
        assert result == []

    def test_scan_with_documents(self, tmp_path, monkeypatch):
        """
        测试扫描包含文档的目录
        
        验证：
            - 返回所有支持的文档格式
            - 路径是字符串类型
            - 结果按字母排序
        """
        monkeypatch.setenv("CC_DOCUMENT_PATH", str(tmp_path))
        
        # 创建测试文件
        (tmp_path / "doc1.pdf").write_text("PDF content")
        (tmp_path / "doc2.docx").write_text("DOCX content")
        (tmp_path / "doc3.doc").write_text("DOC content")
        (tmp_path / "readme.txt").write_text("Not a document")
        
        result = scan_default_documents()
        
        assert len(result) == 3
        assert all(isinstance(path, str) for path in result)
        # 验证排序
        assert result == sorted(result)
        # 验证包含所有支持的格式
        assert any(".pdf" in path for path in result)
        assert any(".docx" in path for path in result)
        assert any(".doc" in path for path in result)

    def test_scan_nonexistent_directory(self, monkeypatch):
        """
        测试扫描不存在的目录
        
        验证：
            - 返回空列表
            - 不抛出异常
        """
        monkeypatch.setenv("CC_DOCUMENT_PATH", "/nonexistent/path/12345")
        
        result = scan_default_documents()
        
        assert isinstance(result, list)
        assert result == []

    def test_scan_default_path(self, monkeypatch):
        """
        测试默认文档路径
        
        验证：
            - 当 CC_DOCUMENT_PATH 未设置时使用默认值
        """
        monkeypatch.delenv("CC_DOCUMENT_PATH", raising=False)
        
        result = scan_default_documents()
        
        assert isinstance(result, list)
        # 默认路径可能不存在，结果应为空列表


# ============== OCR 配置测试 ==============


class TestGetOcrBackend:
    """get_ocr_backend 函数测试"""

    def test_default_ocr_backend(self, monkeypatch):
        """
        测试默认 OCR 后端
        
        验证：
            - 默认返回 "none"
        """
        monkeypatch.delenv("OCR_BACKEND", raising=False)
        
        result = get_ocr_backend()
        
        assert result == "none"

    def test_custom_ocr_backend(self, monkeypatch):
        """
        测试自定义 OCR 后端
        
        验证：
            - 环境变量值正确返回
        """
        monkeypatch.setenv("OCR_BACKEND", "paddle")
        
        result = get_ocr_backend()
        
        assert result == "paddle"

    def test_aliyun_ocr_backend(self, monkeypatch):
        """
        测试阿里云 OCR 后端
        
        验证：
            - 支持 aliyun 后端
        """
        monkeypatch.setenv("OCR_BACKEND", "aliyun")
        
        result = get_ocr_backend()
        
        assert result == "aliyun"


class TestGetAliyunOcrCredentials:
    """get_aliyun_ocr_credentials 函数测试"""

    def test_no_credentials(self, monkeypatch):
        """
        测试无凭证情况
        
        验证：
            - 当环境变量未设置时返回 None
        """
        monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", raising=False)
        
        result = get_aliyun_ocr_credentials()
        
        assert result is None

    def test_partial_credentials(self, monkeypatch):
        """
        测试部分凭证情况
        
        验证：
            - 只有 access_key_id 时返回 None
            - 只有 access_key_secret 时返回 None
        """
        # 只有 access_key_id
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "key-id")
        monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", raising=False)
        
        result = get_aliyun_ocr_credentials()
        assert result is None
        
        # 只有 access_key_secret
        monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_ID", raising=False)
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "key-secret")
        
        result = get_aliyun_ocr_credentials()
        assert result is None

    def test_full_credentials(self, monkeypatch):
        """
        测试完整凭证
        
        验证：
            - 返回 (access_key_id, access_key_secret) 元组
        """
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "test-access-key-id")
        monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "test-access-key-secret")
        
        result = get_aliyun_ocr_credentials()
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "test-access-key-id"
        assert result[1] == "test-access-key-secret"


# ============== 常量测试 ==============


class TestConstants:
    """模块常量测试"""

    def test_default_document_path(self):
        """
        测试默认文档路径常量
        
        验证：
            - DEFAULT_DOCUMENT_PATH 是 Path 对象
            - 路径值为 "./documents"
        """
        assert isinstance(DEFAULT_DOCUMENT_PATH, Path)
        assert str(DEFAULT_DOCUMENT_PATH) == "documents"

    def test_default_output_dir(self):
        """
        测试默认输出目录常量
        
        验证：
            - DEFAULT_OUTPUT_DIR 是 Path 对象
            - 路径值为 "./output"
        """
        assert isinstance(DEFAULT_OUTPUT_DIR, Path)
        assert str(DEFAULT_OUTPUT_DIR) == "output"
