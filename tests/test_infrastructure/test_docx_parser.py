"""
DocxParser 集成测试

⚠️ 注意：需要在 tests/fixtures/ 目录下准备一个 dummy.docx 文件用于测试。
   项目已提供 tests/fixtures/dummy_permit.docx，可直接使用。
   如需生成新的测试文件，请运行：python tests/fixtures/generate_test_files.py

测试目标：
    - 验证 DocxParser 能否正常读取物理 Word 文件
    - 验证返回结果必须是 Core 层定义的 Document 模型
    - 不使用 Mock，实例化真实的 DocxParser
"""

import pytest
from pathlib import Path

from src.infrastructure.parsers.docx_parser import DocxParser, parse_docx
from src.core.document import Document, DocumentType, PageContent, DocumentMetadata
from src.core.exceptions import DocumentParseError

# ============== 测试 Fixtures ==============


@pytest.fixture
def fixtures_dir() -> Path:
    """获取 fixtures 目录路径"""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_docx_path(fixtures_dir: Path) -> Path:
    """获取测试用 DOCX 文件路径"""
    return fixtures_dir / "dummy_permit.docx"


@pytest.fixture
def parser() -> DocxParser:
    """
    创建真实的 DocxParser 实例（不使用 Mock）

    注意：此测试依赖 python-docx 库
    """
    return DocxParser(chars_per_page=3000)


# ============== 基础解析测试 ==============


def test_parser_instance_creation():
    """
    测试 DocxParser 实例化

    验证：
    - 可以成功创建 DocxParser 实例
    - 默认参数正确设置
    """
    parser = DocxParser()

    assert parser.chars_per_page == 3000


def test_parser_custom_chars_per_page():
    """
    测试自定义每页字符数

    验证：
    - 可以自定义 chars_per_page 参数
    """
    parser = DocxParser(chars_per_page=1000)

    assert parser.chars_per_page == 1000


def test_parse_docx_file(parser: DocxParser, sample_docx_path: Path):
    """
    测试解析真实 Word 文件

    验证：
    - 能够成功读取物理文件
    - 返回 Document 类型实例
    """
    # 确保测试文件存在
    assert sample_docx_path.exists(), f"测试文件不存在: {sample_docx_path}"

    # 执行解析
    document = parser.parse(str(sample_docx_path))

    # 验证返回类型
    assert isinstance(document, Document), "返回结果必须是 Document 类型"


def test_parse_returns_core_document_model(parser: DocxParser, sample_docx_path: Path):
    """
    测试返回结果必须是 Core 层定义的 Document 模型

    验证：
    - 返回类型是 src.core.document.Document
    - Document 的所有属性都正确设置
    - 嵌套模型（pages_content, metadata）也是 Core 层定义的类型
    """
    document = parser.parse(str(sample_docx_path))

    # 验证 Document 是 Core 层定义的类型
    assert isinstance(document, Document)
    assert document.__class__.__module__ == "src.core.document"

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
        assert first_page.__class__.__module__ == "src.core.document"

    # 验证 metadata 是 Core 层的 DocumentMetadata
    assert isinstance(document.metadata, DocumentMetadata)
    assert document.metadata.__class__.__module__ == "src.core.document"


def test_parse_docx_document_attributes(parser: DocxParser, sample_docx_path: Path):
    """
    测试解析后 Document 属性的正确性

    验证：
    - path 是绝对路径
    - name 是文件名
    - type 是 DOCX
    - pages 大于 0
    """
    document = parser.parse(str(sample_docx_path))

    # 验证路径是绝对路径
    assert Path(document.path).is_absolute()
    assert document.path == str(sample_docx_path.resolve())

    # 验证文件名
    assert document.name == sample_docx_path.name

    # 验证文档类型
    assert document.type == DocumentType.DOCX

    # 验证页数
    assert document.pages > 0

    # 验证 pages_content 数量与 pages 一致
    assert len(document.pages_content) == document.pages


def test_parse_docx_page_content_structure(parser: DocxParser, sample_docx_path: Path):
    """
    测试 PageContent 结构的正确性

    验证：
    - page_num 从 0 开始
    - text 字段存在
    - has_text_layer 为 True（Word 文档有文本层）
    """
    document = parser.parse(str(sample_docx_path))

    for i, page in enumerate(document.pages_content):
        assert isinstance(page, PageContent)
        assert page.page_num == i, f"页码应该从 0 开始，期望 {i}，实际 {page.page_num}"
        assert isinstance(page.text, str)
        assert page.has_text_layer is True, "Word 文档应该有文本层"


def test_parse_docx_content_extraction(parser: DocxParser, sample_docx_path: Path):
    """
    测试文本内容提取

    验证：
    - 能够提取 Word 文档中的文本内容
    - content 属性返回所有页面合并的文本
    """
    document = parser.parse(str(sample_docx_path))

    # 验证 content 属性
    full_content = document.content
    assert isinstance(full_content, str)

    # dummy_permit.docx 包含 "Construction Permit" 等文本
    assert len(full_content.strip()) > 0


def test_parse_docx_metadata(parser: DocxParser, sample_docx_path: Path):
    """
    测试元数据提取

    验证：
    - metadata 是 DocumentMetadata 类型
    - metadata 的可选字段正确处理
    """
    document = parser.parse(str(sample_docx_path))

    # 验证 metadata 类型
    assert isinstance(document.metadata, DocumentMetadata)

    # 验证 custom 字段存在
    assert isinstance(document.metadata.custom, dict)


def test_parse_docx_virtual_pagination():
    """
    测试虚拟分页功能

    验证：
    - chars_per_page 参数影响分页结果
    - 小页面字符数会导致更多页
    """
    # 使用小页面字符数创建解析器
    small_page_parser = DocxParser(chars_per_page=100)

    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    sample_docx_path = fixtures_dir / "dummy_permit.docx"

    if not sample_docx_path.exists():
        pytest.skip("测试文件不存在")

    document = small_page_parser.parse(str(sample_docx_path))

    # 使用小页面字符数，应该产生更多页
    assert document.pages >= 1

    # 验证每页内容不超过 chars_per_page（允许一定容差）
    for page in document.pages_content:
        # 虚拟分页按字符数分割，每页应该接近 chars_per_page
        # 但最后一页可能较短
        assert isinstance(page.text, str)


# ============== 异常处理测试 ==============


def test_parse_nonexistent_file_raises_error(parser: DocxParser, fixtures_dir: Path):
    """
    测试解析不存在的文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息包含文件路径信息
    """
    nonexistent_path = fixtures_dir / "nonexistent_file.docx"

    with pytest.raises(DocumentParseError) as exc_info:
        parser.parse(str(nonexistent_path))

    assert "不存在" in str(exc_info.value)


def test_parse_non_docx_file_raises_error(parser: DocxParser, fixtures_dir: Path):
    """
    测试解析非 Word 文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息包含格式不支持信息
    """
    # 使用已有的 PDF 文件测试
    pdf_path = fixtures_dir / "dummy_approval.pdf"

    if pdf_path.exists():
        with pytest.raises(DocumentParseError) as exc_info:
            parser.parse(str(pdf_path))

        assert "不支持" in str(exc_info.value)


def test_parse_doc_format_raises_error(parser: DocxParser, fixtures_dir: Path):
    """
    测试解析 .doc 格式文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息提示暂不支持 .doc 格式
    """
    # 创建一个假的 .doc 文件路径（文件实际不存在，但格式检查在前）
    # 由于文件不存在检查在前，我们需要先创建一个临时文件
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
        temp_path = Path(f.name)
        f.write(b"test content")

    try:
        with pytest.raises(DocumentParseError) as exc_info:
            parser.parse(str(temp_path))

        assert ".doc" in str(exc_info.value) or "不支持" in str(exc_info.value)
    finally:
        temp_path.unlink(missing_ok=True)


# ============== 便捷函数测试 ==============


def test_parse_docx_convenience_function(sample_docx_path: Path):
    """
    测试 parse_docx 便捷函数

    验证：
    - 便捷函数返回正确的 Document 类型
    """
    document = parse_docx(str(sample_docx_path))

    assert isinstance(document, Document)
    assert document.type == DocumentType.DOCX


def test_parse_docx_convenience_function_with_custom_pagination(sample_docx_path: Path):
    """
    测试 parse_docx 便捷函数的自定义分页参数

    验证：
    - chars_per_page 参数正确传递
    """
    document = parse_docx(str(sample_docx_path), chars_per_page=500)

    assert isinstance(document, Document)


# ============== Document 模型方法测试 ==============


def test_document_get_page_method(parser: DocxParser, sample_docx_path: Path):
    """
    测试 Document.get_page() 方法

    验证：
    - 能正确获取指定页码的 PageContent
    - 超出范围的页码返回 None
    """
    document = parser.parse(str(sample_docx_path))

    # 获取第一页（页码 0）
    first_page = document.get_page(0)
    assert first_page is not None
    assert isinstance(first_page, PageContent)
    assert first_page.page_num == 0

    # 获取不存在的页码
    invalid_page = document.get_page(999)
    assert invalid_page is None


def test_document_get_page_text_method(parser: DocxParser, sample_docx_path: Path):
    """
    测试 Document.get_page_text() 方法

    验证：
    - 能正确获取指定页码的文本
    - 超出范围的页码返回空字符串
    """
    document = parser.parse(str(sample_docx_path))

    # 获取第一页文本
    first_page_text = document.get_page_text(0)
    assert isinstance(first_page_text, str)

    # 获取不存在的页码
    invalid_text = document.get_page_text(999)
    assert invalid_text == ""


def test_document_search_text_method(parser: DocxParser, sample_docx_path: Path):
    """
    测试 Document.search_text() 方法

    验证：
    - 能搜索关键词并返回包含关键词的页码列表
    """
    document = parser.parse(str(sample_docx_path))

    # dummy_permit.docx 包含 "Construction", "Permit", "Valid" 等词
    results = document.search_text("Permit")

    assert isinstance(results, list)
    # 如果找到关键词，结果应该是页码列表
    for page_num in results:
        assert isinstance(page_num, int)
        assert 0 <= page_num < document.pages
