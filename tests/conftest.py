"""
Pytest 配置和共享 Fixtures

提供测试用的模拟数据和通用配置
"""

import pytest
from unittest.mock import Mock
from typing import List

from compliance_checker.core.document import Document, DocumentType, PageContent, DocumentMetadata
from compliance_checker.core.checklist_model import (
    Checklist, 
    RequiredDocument, 
    ProjectPeriod,
    ValidityRule
)
from compliance_checker.core.result_model import (
    CheckStatus,
    MatchType,
    DocumentMatch,
    CompletenessResult
)


# =============================================================================
# 文档 Fixtures
# =============================================================================

@pytest.fixture
def sample_page_content() -> PageContent:
    """单页内容样本"""
    return PageContent(
        page_num=0,
        text="这是一页测试内容",
        ocr_text=None,
        has_text_layer=True
    )


@pytest.fixture
def sample_page_with_ocr() -> PageContent:
    """带 OCR 的单页内容"""
    return PageContent(
        page_num=0,
        text="",
        ocr_text="OCR识别的文本内容",
        has_text_layer=False
    )


@pytest.fixture
def sample_document() -> Document:
    """标准文档样本"""
    return Document(
        file_path="/data/立项批复.pdf",
        file_name="立项批复.pdf",
        file_type=DocumentType.PDF,
        pages=5,
        pages_content=[
            PageContent(page_num=0, text="第一页内容"),
            PageContent(page_num=1, text="第二页内容"),
        ],
        metadata=DocumentMetadata(
            title="项目立项批复",
            issue_date="2024-03-15"
        )
    )


@pytest.fixture
def sample_documents() -> List[Document]:
    """多个文档样本"""
    return [
        Document(
            file_path="/data/立项批复.pdf",
            file_name="立项批复.pdf",
            file_type=DocumentType.PDF
        ),
        Document(
            file_path="/data/施工许可.pdf",
            file_name="施工许可.pdf",
            file_type=DocumentType.PDF
        ),
        Document(
            file_path="/data/合同.pdf",
            file_name="建设工程合同.pdf",
            file_type=DocumentType.PDF
        ),
    ]


# =============================================================================
# 清单 Fixtures
# =============================================================================

@pytest.fixture
def sample_required_doc() -> RequiredDocument:
    """单个必需文档定义"""
    return RequiredDocument(
        name="项目立项批复文件",
        aliases=["立项批复", "项目批复", "立项批准"],
        type=[DocumentType.PDF, DocumentType.DOCX],
        required=True
    )


@pytest.fixture
def sample_checklist() -> Checklist:
    """标准审核清单"""
    return Checklist(
        id="test_checklist",
        name="测试清单",
        version="1.0",
        project_period=ProjectPeriod(
            start="2024-01",
            end="2026-12"
        ),
        required_documents=[
            RequiredDocument(
                name="项目立项批复文件",
                aliases=["立项批复", "项目批复"],
                required=True
            ),
            RequiredDocument(
                name="施工许可证",
                aliases=["施工许可"],
                required=True
            ),
            RequiredDocument(
                name="建设工程合同",
                aliases=["施工合同", "工程合同"],
                required=True
            ),
            RequiredDocument(
                name="竣工验收报告",
                aliases=["验收报告"],
                required=False  # 可选文档
            ),
        ]
    )


@pytest.fixture
def sample_checklist_with_validity() -> Checklist:
    """带有效期规则的清单"""
    return Checklist(
        id="validity_test",
        name="有效期测试清单",
        required_documents=[
            RequiredDocument(
                name="安全生产许可证",
                required=True,
                validity=ValidityRule(
                    cover_project=True
                )
            ),
            RequiredDocument(
                name="资质证书",
                required=True,
                validity=ValidityRule(
                    valid_from="2024-01",
                    valid_to="2027-12"
                )
            ),
        ]
    )


# =============================================================================
# 结果 Fixtures
# =============================================================================

@pytest.fixture
def sample_document_match() -> DocumentMatch:
    """文档匹配结果样本"""
    return DocumentMatch(
        document_name="立项批复",
        status=CheckStatus.VALID,
        matched_file="立项批复.pdf",
        match_type=MatchType.EXACT,
        similarity=1.0,
        requirement="必须上传"
    )


@pytest.fixture
def sample_completeness_result() -> CompletenessResult:
    """完整性检查结果样本"""
    return CompletenessResult(
        status=CheckStatus.PASS,
        total_required=3,
        uploaded=3,
        missing=0,
        details=[
            DocumentMatch(
                document_name="立项批复",
                status=CheckStatus.VALID,
                matched_file="立项批复.pdf",
                match_type=MatchType.EXACT,
                similarity=1.0
            ),
            DocumentMatch(
                document_name="施工许可",
                status=CheckStatus.VALID,
                matched_file="施工许可.pdf",
                match_type=MatchType.EXACT,
                similarity=1.0
            ),
        ]
    )


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_response():
    """模拟 LLM API 响应"""
    return {
        "choices": [
            {
                "message": {
                    "content": "测试响应内容"
                }
            }
        ]
    }


@pytest.fixture
def mock_embedding_response():
    """模拟嵌入 API 响应"""
    return Mock(
        data=[
            Mock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5])
        ]
    )


@pytest.fixture
def mock_ocr_result():
    """模拟 OCR 识别结果"""
    return "OCR识别的文本内容"


# =============================================================================
# Pytest 配置
# =============================================================================

def pytest_configure(config):
    """配置 pytest"""
    # 注册自定义标记
    config.addinivalue_line(
        "markers", "async_test: 标记异步测试"
    )
    config.addinivalue_line(
        "markers", "mock_test: 标记使用 Mock 的测试"
    )


# 测试环境变量
import os
os.environ.setdefault("LLM_API_KEY", "test-api-key")
os.environ.setdefault("EMBED_API_KEY", "test-embed-key")
os.environ.setdefault("LLM_BASE_URL", "https://test.api.com/v1")
