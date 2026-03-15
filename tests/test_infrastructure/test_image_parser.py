"""
ImageParser 集成测试

⚠️ 注意：需要在 tests/fixtures/ 目录下准备一个图片文件用于测试。
   项目已提供 tests/fixtures/dummy_seal.jpg，可直接使用。
   如需生成新的测试文件，请运行：python tests/fixtures/generate_test_files.py

测试目标：
    - 验证 ImageParser 能否正常读取物理图片文件
    - 验证返回结果必须是 Core 层定义的 Document 模型
    - 不使用 Mock，实例化真实的 ImageParser
    - 注意：本测试不注入 OCR 引擎，ocr_text 将为空
"""

import pytest
from pathlib import Path

from src.infrastructure.parsers.image_parser import ImageParser, parse_image
from src.core.document import Document, DocumentType, PageContent, DocumentMetadata
from src.core.exceptions import DocumentParseError

# ============== 测试 Fixtures ==============


@pytest.fixture
def fixtures_dir() -> Path:
    """获取 fixtures 目录路径"""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_image_path(fixtures_dir: Path) -> Path:
    """获取测试用图片文件路径"""
    return fixtures_dir / "dummy_seal.jpg"


@pytest.fixture
def parser() -> ImageParser:
    """
    创建真实的 ImageParser 实例（不使用 Mock）

    注意：
    - 此测试依赖 Pillow 库
    - 不注入 OCR 引擎，ocr_text 将为空字符串
    """
    return ImageParser(ocr_engine=None)


# ============== 基础解析测试 ==============


def test_parser_instance_creation():
    """
    测试 ImageParser 实例化

    验证：
    - 可以成功创建 ImageParser 实例
    - 默认参数正确设置
    """
    parser = ImageParser()

    assert parser._ocr_engine is None


def test_supported_formats():
    """
    测试支持的图片格式

    验证：
    - SUPPORTED_FORMATS 包含常见图片格式
    """
    expected_formats = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

    assert ImageParser.SUPPORTED_FORMATS == expected_formats


def test_parse_image_file(parser: ImageParser, sample_image_path: Path):
    """
    测试解析真实图片文件

    验证：
    - 能够成功读取物理文件
    - 返回 Document 类型实例
    """
    # 确保测试文件存在
    assert sample_image_path.exists(), f"测试文件不存在: {sample_image_path}"

    # 执行解析
    document = parser.parse(str(sample_image_path))

    # 验证返回类型
    assert isinstance(document, Document), "返回结果必须是 Document 类型"


def test_parse_returns_core_document_model(parser: ImageParser, sample_image_path: Path):
    """
    测试返回结果必须是 Core 层定义的 Document 模型

    验证：
    - 返回类型是 src.core.document.Document
    - Document 的所有属性都正确设置
    - 嵌套模型（pages_content, metadata）也是 Core 层定义的类型
    """
    document = parser.parse(str(sample_image_path))

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


def test_parse_image_document_attributes(parser: ImageParser, sample_image_path: Path):
    """
    测试解析后 Document 属性的正确性

    验证：
    - path 是绝对路径
    - name 是文件名
    - type 是 IMAGE
    - pages 为 1（图片视为单页文档）
    """
    document = parser.parse(str(sample_image_path))

    # 验证路径是绝对路径
    assert Path(document.path).is_absolute()
    assert document.path == str(sample_image_path.resolve())

    # 验证文件名
    assert document.name == sample_image_path.name

    # 验证文档类型
    assert document.type == DocumentType.IMAGE

    # 验证页数（图片视为单页文档）
    assert document.pages == 1

    # 验证 pages_content 数量与 pages 一致
    assert len(document.pages_content) == 1


def test_parse_image_page_content_structure(parser: ImageParser, sample_image_path: Path):
    """
    测试 PageContent 结构的正确性

    验证：
    - page_num 为 0
    - text 为空（图片无文本层）
    - has_text_layer 为 False
    - ocr_text 存在（可能为空，因为未注入 OCR 引擎）
    """
    document = parser.parse(str(sample_image_path))

    page = document.pages_content[0]

    assert isinstance(page, PageContent)
    assert page.page_num == 0
    assert page.text == "", "图片文档的 text 应该为空"
    assert page.has_text_layer is False, "图片文档应该没有文本层"
    assert isinstance(page.ocr_text, str)


def test_parse_image_metadata(parser: ImageParser, sample_image_path: Path):
    """
    测试元数据提取

    验证：
    - metadata 是 DocumentMetadata 类型
    - custom 字段包含图片尺寸、格式、模式信息
    """
    document = parser.parse(str(sample_image_path))

    # 验证 metadata 类型
    assert isinstance(document.metadata, DocumentMetadata)

    # 验证 custom 字段包含图片信息
    custom = document.metadata.custom
    assert isinstance(custom, dict)

    # 验证图片元数据字段
    assert "image_width" in custom
    assert "image_height" in custom
    assert "image_format" in custom
    assert "image_mode" in custom

    # 验证尺寸是正整数
    assert isinstance(custom["image_width"], int)
    assert isinstance(custom["image_height"], int)
    assert custom["image_width"] > 0
    assert custom["image_height"] > 0

    # 验证格式是字符串
    assert isinstance(custom["image_format"], str)
    assert isinstance(custom["image_mode"], str)


def test_parse_image_metadata_title(parser: ImageParser, sample_image_path: Path):
    """
    测试元数据中的 title 字段

    验证：
    - title 是文件名（不含扩展名）
    """
    document = parser.parse(str(sample_image_path))

    assert document.metadata.title == sample_image_path.stem


def test_parse_image_content_without_ocr(parser: ImageParser, sample_image_path: Path):
    """
    测试无 OCR 引擎时的内容提取

    验证：
    - content 属性返回空字符串（无 OCR）
    - 或者返回 ocr_text（如果有）
    """
    document = parser.parse(str(sample_image_path))

    # 验证 content 属性
    full_content = document.content
    assert isinstance(full_content, str)

    # 无 OCR 引擎时，ocr_text 为空
    page = document.pages_content[0]
    assert page.ocr_text == ""


# ============== 不同图片格式测试 ==============


@pytest.mark.parametrize("image_format", [".jpg", ".png", ".jpeg", ".gif", ".bmp"])
def test_parse_different_image_formats(fixtures_dir: Path, image_format: str):
    """
    测试解析不同格式的图片文件

    验证：
    - 支持的格式都能正常解析
    """
    # 检查是否有对应格式的测试文件
    # 目前只有 dummy_seal.jpg，跳过其他格式
    if image_format not in [".jpg", ".jpeg"]:
        pytest.skip(f"缺少 {image_format} 格式的测试文件")

    image_path = fixtures_dir / f"dummy_seal{image_format}"

    if not image_path.exists():
        # 尝试使用 .jpg 文件
        image_path = fixtures_dir / "dummy_seal.jpg"
        if not image_path.exists():
            pytest.skip("测试图片文件不存在")

    parser = ImageParser()
    document = parser.parse(str(image_path))

    assert isinstance(document, Document)
    assert document.type == DocumentType.IMAGE


# ============== 异常处理测试 ==============


def test_parse_nonexistent_file_raises_error(parser: ImageParser, fixtures_dir: Path):
    """
    测试解析不存在的文件

    验证：
    - 抛出 DocumentParseError
    - 错误消息包含文件路径信息
    """
    nonexistent_path = fixtures_dir / "nonexistent_image.jpg"

    with pytest.raises(DocumentParseError) as exc_info:
        parser.parse(str(nonexistent_path))

    assert "不存在" in str(exc_info.value)


def test_parse_non_image_file_raises_error(parser: ImageParser, fixtures_dir: Path):
    """
    测试解析非图片文件

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


def test_parse_unsupported_format_raises_error(parser: ImageParser, fixtures_dir: Path):
    """
    测试解析不支持的图片格式

    验证：
    - 抛出 DocumentParseError
    - 错误消息列出支持的格式
    """
    # 创建一个不支持的格式文件
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        temp_path = Path(f.name)
        f.write(b"test content")

    try:
        with pytest.raises(DocumentParseError) as exc_info:
            parser.parse(str(temp_path))

        error_msg = str(exc_info.value)
        assert "不支持" in error_msg or ".xyz" in error_msg
    finally:
        temp_path.unlink(missing_ok=True)


# ============== 便捷函数测试 ==============


def test_parse_image_convenience_function(sample_image_path: Path):
    """
    测试 parse_image 便捷函数

    验证：
    - 便捷函数返回正确的 Document 类型
    """
    document = parse_image(str(sample_image_path))

    assert isinstance(document, Document)
    assert document.type == DocumentType.IMAGE


# ============== Document 模型方法测试 ==============


def test_document_get_page_method(parser: ImageParser, sample_image_path: Path):
    """
    测试 Document.get_page() 方法

    验证：
    - 能正确获取指定页码的 PageContent
    - 超出范围的页码返回 None
    """
    document = parser.parse(str(sample_image_path))

    # 获取第一页（页码 0）
    first_page = document.get_page(0)
    assert first_page is not None
    assert isinstance(first_page, PageContent)
    assert first_page.page_num == 0

    # 获取不存在的页码
    invalid_page = document.get_page(999)
    assert invalid_page is None


def test_document_get_page_text_method(parser: ImageParser, sample_image_path: Path):
    """
    测试 Document.get_page_text() 方法

    验证：
    - 能正确获取指定页码的文本
    - 超出范围的页码返回空字符串
    """
    document = parser.parse(str(sample_image_path))

    # 获取第一页文本（无 OCR 时为空）
    first_page_text = document.get_page_text(0)
    assert isinstance(first_page_text, str)

    # 获取不存在的页码
    invalid_text = document.get_page_text(999)
    assert invalid_text == ""


def test_document_search_text_method(parser: ImageParser, sample_image_path: Path):
    """
    测试 Document.search_text() 方法

    验证：
    - 能搜索关键词并返回包含关键词的页码列表
    - 无 OCR 时搜索结果为空
    """
    document = parser.parse(str(sample_image_path))

    # 搜索任意关键词
    results = document.search_text("test")

    assert isinstance(results, list)
    # 无 OCR 时应该返回空列表
    assert results == []


# ============== 图片特性测试 ==============


def test_image_size_extraction(parser: ImageParser, sample_image_path: Path):
    """
    测试图片尺寸提取

    验证：
    - 正确提取图片宽度和高度
    """
    document = parser.parse(str(sample_image_path))

    custom = document.metadata.custom

    # dummy_seal.jpg 尺寸为 300x200（根据 generate_test_files.py）
    assert custom["image_width"] == 300
    assert custom["image_height"] == 200


def test_image_format_extraction(parser: ImageParser, sample_image_path: Path):
    """
    测试图片格式提取

    验证：
    - 正确提取图片格式（JPEG）
    """
    document = parser.parse(str(sample_image_path))

    custom = document.metadata.custom

    # JPEG 格式
    assert custom["image_format"] == "JPEG"


def test_page_content_ocr_text_field(parser: ImageParser, sample_image_path: Path):
    """
    测试 PageContent 的 ocr_text 字段

    验证：
    - ocr_text 字段存在
    - 无 OCR 引擎时为空字符串
    """
    document = parser.parse(str(sample_image_path))

    page = document.pages_content[0]

    # ocr_text 字段应该存在
    assert hasattr(page, "ocr_text")
    assert isinstance(page.ocr_text, str)

    # 无 OCR 引擎时为空
    assert page.ocr_text == ""


def test_page_content_get_full_text_method(parser: ImageParser, sample_image_path: Path):
    """
    测试 PageContent.get_full_text() 方法

    验证：
    - 无 OCR 时返回空字符串
    - 方法存在且正常工作
    """
    document = parser.parse(str(sample_image_path))

    page = document.pages_content[0]

    # get_full_text 应该返回 ocr_text（优先）或 text
    full_text = page.get_full_text()
    assert isinstance(full_text, str)

    # 无 OCR 时，text 为空，ocr_text 也为空，所以返回空字符串
    assert full_text == ""
