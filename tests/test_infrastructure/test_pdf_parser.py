"""
PDFParser 集成测试

⚠️ 注意：需要在 tests/fixtures/ 目录下准备一个 dummy.pdf 文件用于测试。
   项目已提供 tests/fixtures/dummy_approval.pdf，可直接使用。
   如需生成新的测试文件，请运行：python tests/fixtures/generate_test_files.py

测试目标：
    - 验证 PDFParser 能否正常读取物理 PDF 文件
    - 验证返回结果必须是 Core 层定义的 Document 模型
    - 不使用 Mock，实例化真实的 PDFParser
"""

import pytest
from pathlib import Path

from src.compliance_checker.infrastructure.parsers.pdf_parser import PDFParser, parse_pdf
from src.compliance_checker.core.document import Document, DocumentType, PageContent, DocumentMetadata
from src.compliance_checker.core.exceptions import DocumentParseError

# ============== 测试 Fixtures ==============


@pytest.fixture
def fixtures_dir() -> Path:
    """获取 fixtures 目录路径"""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """获取测试用 PDF 文件路径"""
    return fixtures_dir / "dummy_approval.pdf"


@pytest.fixture
def parser() -> PDFParser:
    """
    创建真实的 PDFParser 实例（不使用 Mock）

    注意：此测试依赖 PyMuPDF (fitz) 库
    """
    return PDFParser(use_ocr=False)  # 禁用 OCR 以简化测试


# ============== 基础解析测试 ==============


def test_parser_instance_creation():
    """
    测试 PDFParser 实例化

    验证：
    - 可以成功创建 PDFParser 实例
    - 默认参数正确设置
    """
    parser = PDFParser(use_ocr=False)

    assert parser.use_ocr is False
    assert parser.ocr_dpi == 200
    assert parser._ocr_engine is None


def test_parse_pdf_file(parser: PDFParser, sample_pdf_path: Path):
    """
    测试解析真实 PDF 文件

    验证：
    - 能够成功读取物理文件
    - 返回 Document 类型实例
    """
    # 确保测试文件存在
    assert sample_pdf_path.exists(), f"测试文件不存在: {sample_pdf_path}"

    # 执行解析
    document = parser.parse(str(sample_pdf_path))

    # 验证返回类型
    assert isinstance(document, Document), "返回结果必须是 Document 类型"


def test_parse_returns_core_document_model(parser: PDFParser, sample_pdf_path: Path):
    """
    测试返回结果必须是 Core 层定义的 Document 模型

    验证：
    - 返回类型是 src.compliance_checker.core.document.Document
    - Document 的所有属性都正确设置
    - 嵌套模型（pages_content, metadata）也是 Core 层定义的类型
    """
    document = parser.parse(str(sample_pdf_path))

    # 验证 Document 是 Core 层定义的类型
    assert isinstance(document, Document)
    assert document.__class__.__module__ == "src.compliance_checker.core.document"

    # 验证基本属性
    assert isinstance(document.path, str)
    assert isinstance(document.name, str)
    assert isinstance(document.type, DocumentType)
    assert isinstance(document.pages, int)

    # 验证 pages_content 是 Core 层的 PageContent 列表
    assert isinstance(document.pages_content, list)
    if document.pages_content:
        first_page = document.pages_content[0]
        assert isinstance(first_page, PageContent)
        assert first_page.__class__.__module__ == "src.compliance_checker.core.document"

    # 验证 metadata 是 Core 层的 DocumentMetadata
    assert isinstance(document.metadata, DocumentMetadata)
    assert document.metadata.__class__.__module__ == "src.compliance_checker.core.document"


def test_parse_pdf_document_attributes(parser: PDFParser, sample_pdf_path: Path):
    """
    测试解析后 Document 属性的正确性

    验证：
    - path 是绝对路径
    - name 是文件名
    - type 是 PDF
    - pages 大于 0
    """
    document = parser.parse(str(sample_pdf_path))

    # 验证路径是绝对路径
    assert Path(document.path).is_absolute()
    assert document.path == str(sample_pdf_path.resolve())

    # 验证文件名
    assert document.name == sample_pdf_path.name

    # 验证文档类型
    assert document.type == DocumentType.PDF

    # 验证页数
    assert document.pages > 0

    # 验证 pages_content 数量与 pages 一致
    assert len(document.pages_content) == document.pages


def test_parse_pdf_page_content_structure(parser: PDFParser, sample_pdf_path: Path):
    """
    测试 PageContent 结构的正确性

    验证：
    - page_num 从 0 开始
    - text 字段存在
    - has_text_layer 字段存在
    """
    document = parser.parse(str(sample_pdf_path))

    for i, page in enumerate(document.pages_content):
        assert isinstance(page, PageContent)
        assert page.page_num == i, f"页码应该从 0 开始，期望 {i}，实际 {page.page_num}"
        assert isinstance(page.text, str)
        assert isinstance(page.has_text_layer, bool)


def test_parse_pdf_content_extraction(parser: PDFParser, sample_pdf_path: Path):
    """
    测试文本内容提取

    验证：
    - 能够提取 PDF 中的文本内容
    - content 属性返回所有页面合并的文本
    """
    document = parser.parse(str(sample_pdf_path))

    # 验证 content 属性
    full_content = document.content
    assert isinstance(full_content, str)

    # 如果 PDF 有文本层，应该能提取到内容
    if document.pages_content and document.pages_content[0].has_text_layer:
        # dummy_approval.pdf 包含 "Project Approval" 等文本
        # 至少应该有文本内容
        assert len(full_content.strip()) > 0


def test_parse_pdf_metadata(parser: PDFParser, sample_pdf_path: Path):
    """
    测试元数据提取

    验证：
    - metadata 是 DocumentMetadata 类型
    - metadata 的可选字段正确处理
    """
    document = parser.parse(str(sample_pdf_path))

    # 验证 metadata 类型
    assert isinstance(document.metadata, DocumentMetadata)

    # 验证 custom 字段存在
    assert isinstance(document.metadata.custom, dict)


# ============== 异常处理测试 ==============


def test_parse_nonexistent_file_raises_error(parser: PDFParser, fixtures_dir: Path):
    """
    测试解析不存在的文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息包含文件路径信息
    """
    nonexistent_path = fixtures_dir / "nonexistent_file.pdf"

    with pytest.raises(DocumentParseError) as exc_info:
        parser.parse(str(nonexistent_path))

    assert "不存在" in str(exc_info.value)


def test_parse_non_pdf_file_raises_error(parser: PDFParser, fixtures_dir: Path):
    """
    测试解析非 PDF 文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息包含格式不支持信息
    """
    # 使用已有的 docx 文件测试
    docx_path = fixtures_dir / "dummy_permit.docx"

    if docx_path.exists():
        with pytest.raises(DocumentParseError) as exc_info:
            parser.parse(str(docx_path))

        assert "不支持" in str(exc_info.value)


# ============== 便捷函数测试 ==============


def test_parse_pdf_convenience_function(sample_pdf_path: Path):
    """
    测试 parse_pdf 便捷函数

    验证：
    - 便捷函数返回正确的 Document 类型
    """
    document = parse_pdf(str(sample_pdf_path), use_ocr=False)

    assert isinstance(document, Document)
    assert document.type == DocumentType.PDF


# ============== Document 模型方法测试 ==============


def test_document_get_page_method(parser: PDFParser, sample_pdf_path: Path):
    """
    测试 Document.get_page() 方法

    验证：
    - 能正确获取指定页码的 PageContent
    - 超出范围的页码返回 None
    """
    document = parser.parse(str(sample_pdf_path))

    # 获取第一页（页码 0）
    first_page = document.get_page(0)
    assert first_page is not None
    assert isinstance(first_page, PageContent)
    assert first_page.page_num == 0

    # 获取不存在的页码
    invalid_page = document.get_page(999)
    assert invalid_page is None


def test_document_get_page_text_method(parser: PDFParser, sample_pdf_path: Path):
    """
    测试 Document.get_page_text() 方法

    验证：
    - 能正确获取指定页码的文本
    - 超出范围的页码返回空字符串
    """
    document = parser.parse(str(sample_pdf_path))

    # 获取第一页文本
    first_page_text = document.get_page_text(0)
    assert isinstance(first_page_text, str)

    # 获取不存在的页码
    invalid_text = document.get_page_text(999)
    assert invalid_text == ""


def test_document_search_text_method(parser: PDFParser, sample_pdf_path: Path):
    """
    测试 Document.search_text() 方法

    验证：
    - 能搜索关键词并返回包含关键词的页码列表
    """
    document = parser.parse(str(sample_pdf_path))

    # 搜索文档中可能存在的关键词
    # dummy_approval.pdf 包含 "Document", "Project", "Approval" 等词
    results = document.search_text("Document")

    assert isinstance(results, list)
    # 如果找到关键词，结果应该是页码列表
    for page_num in results:
        assert isinstance(page_num, int)
        assert 0 <= page_num < document.pages
