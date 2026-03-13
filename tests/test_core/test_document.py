"""
文档数据模型测试

测试 Document、PageContent、DocumentMetadata、ParseResult 等核心模型的功能
"""

import pytest
from datetime import datetime

from compliance_checker.core.document import (
    Document,
    PageContent,
    DocumentMetadata,
    ParseResult,
    DocumentType,
)


class TestPageContent:
    """测试 PageContent 模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        page = PageContent(
            page_num=0,
            text="测试文本"
        )
        
        assert page.page_num == 0
        assert page.text == "测试文本"
        assert page.ocr_text is None
        assert page.has_text_layer is True
    
    def test_get_full_text_with_text_layer(self):
        """测试有文本层时获取全文"""
        page = PageContent(
            page_num=0,
            text="原始文本",
            ocr_text=None,
            has_text_layer=True
        )
        
        assert page.get_full_text() == "原始文本"
    
    def test_get_full_text_with_ocr(self):
        """测试有 OCR 结果时优先使用 OCR"""
        page = PageContent(
            page_num=0,
            text="",
            ocr_text="OCR识别文本",
            has_text_layer=False
        )
        
        # OCR 文本优先
        assert page.get_full_text() == "OCR识别文本"
    
    def test_get_full_text_both_present(self):
        """测试同时存在文本和 OCR 时优先 OCR"""
        page = PageContent(
            page_num=0,
            text="原始文本",
            ocr_text="OCR文本",
            has_text_layer=True
        )
        
        # 只要有 OCR 就优先使用
        assert page.get_full_text() == "OCR文本"


class TestDocumentMetadata:
    """测试 DocumentMetadata 模型"""
    
    def test_default_creation(self):
        """测试默认创建"""
        metadata = DocumentMetadata()
        
        assert metadata.title is None
        assert metadata.author is None
        assert metadata.custom == {}
    
    def test_full_creation(self):
        """测试完整字段创建"""
        metadata = DocumentMetadata(
            title="测试文档",
            author="测试作者",
            subject="测试主题",
            creation_date=datetime(2024, 1, 15),
            issue_date="2024-03-15",
            valid_from="2024-01",
            valid_to="2025-12",
            document_number="DOC-2024-001",
            custom={"key": "value"}
        )
        
        assert metadata.title == "测试文档"
        assert metadata.issue_date == "2024-03-15"
        assert metadata.document_number == "DOC-2024-001"
        assert metadata.custom["key"] == "value"


class TestDocument:
    """测试 Document 模型"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            file_type=DocumentType.PDF,
            pages=5
        )
        
        assert doc.name == "test.pdf"
        assert doc.type == DocumentType.PDF
        assert doc.pages == 5
    
    def test_alias_fields(self):
        """测试别名字段（path/file_path, name/file_name）"""
        # 使用别名创建
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            file_type=DocumentType.PDF
        )
        
        # 可以通过原名或别名访问
        assert doc.path == "/data/test.pdf"
        assert doc.name == "test.pdf"
        assert doc.type == DocumentType.PDF
    
    def test_content_property_empty(self):
        """测试空文档的 content 属性"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf"
        )
        
        assert doc.content == ""
    
    def test_content_property_with_pages(self):
        """测试多页文档的 content 属性"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="第一页"),
                PageContent(page_num=1, text="第二页"),
                PageContent(page_num=2, text="第三页"),
            ]
        )
        
        content = doc.content
        assert "第一页" in content
        assert "第二页" in content
        assert "第三页" in content
        # 页面之间用空行分隔
        assert "\n\n" in content
    
    def test_content_property_sorted_by_page_num(self):
        """测试 content 属性按页码排序"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=2, text="第三页"),
                PageContent(page_num=0, text="第一页"),
                PageContent(page_num=1, text="第二页"),
            ]
        )
        
        content = doc.content
        # 应该按页码排序
        assert content.index("第一页") < content.index("第二页")
        assert content.index("第二页") < content.index("第三页")
    
    def test_content_property_ocr_priority(self):
        """测试 content 属性优先使用 OCR 文本"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="原始文本", ocr_text="OCR文本"),
            ]
        )
        
        assert doc.content == "OCR文本"
    
    def test_get_page_existing(self):
        """测试获取存在的页面"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="第0页"),
                PageContent(page_num=1, text="第1页"),
            ]
        )
        
        page = doc.get_page(1)
        assert page is not None
        assert page.page_num == 1
        assert page.text == "第1页"
    
    def test_get_page_nonexistent(self):
        """测试获取不存在的页面"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="第0页"),
            ]
        )
        
        page = doc.get_page(99)
        assert page is None
    
    def test_get_page_text_existing(self):
        """测试获取存在页面的文本"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="页面内容"),
            ]
        )
        
        text = doc.get_page_text(0)
        assert text == "页面内容"
    
    def test_get_page_text_nonexistent(self):
        """测试获取不存在页面的文本返回空字符串"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf"
        )
        
        text = doc.get_page_text(0)
        assert text == ""
    
    def test_search_text_found(self):
        """测试搜索存在的文本"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="包含关键词"),
                PageContent(page_num=1, text="不包含"),
                PageContent(page_num=2, text="也包含关键词"),
            ]
        )
        
        matched = doc.search_text("关键词")
        assert matched == [0, 2]
    
    def test_search_text_not_found(self):
        """测试搜索不存在的文本"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="页面内容"),
            ]
        )
        
        matched = doc.search_text("不存在的词")
        assert matched == []
    
    def test_search_text_ocr_content(self):
        """测试在 OCR 文本中搜索"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            pages_content=[
                PageContent(page_num=0, text="", ocr_text="OCR关键词"),
            ]
        )
        
        matched = doc.search_text("OCR关键词")
        assert matched == [0]
    
    def test_document_type_enum(self):
        """测试文档类型枚举"""
        assert DocumentType.PDF == "pdf"
        assert DocumentType.DOCX == "docx"
        assert DocumentType.DOC == "doc"
        assert DocumentType.IMAGE == "image"
        assert DocumentType.UNKNOWN == "unknown"


class TestParseResult:
    """测试 ParseResult 模型"""
    
    def test_default_creation(self):
        """测试默认创建"""
        result = ParseResult()
        
        assert result.documents == []
        assert result.errors == []
        assert result.is_success() is True
    
    def test_add_document(self):
        """测试添加文档"""
        result = ParseResult()
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf"
        )
        
        result.add_document(doc)
        
        assert len(result.documents) == 1
        assert result.documents[0].name == "test.pdf"
    
    def test_add_error(self):
        """测试添加错误"""
        result = ParseResult()
        
        result.add_error("/data/error.pdf", "解析失败")
        
        assert len(result.errors) == 1
        assert result.errors[0]["file_path"] == "/data/error.pdf"
        assert result.errors[0]["error"] == "解析失败"
        assert result.is_success() is False
    
    def test_is_success_with_errors(self):
        """测试有错误时 is_success 返回 False"""
        result = ParseResult()
        result.add_error("/data/error.pdf", "错误")
        
        assert result.is_success() is False
    
    def test_get_document_by_name_found(self):
        """测试通过名称获取存在的文档"""
        result = ParseResult()
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf"
        )
        result.add_document(doc)
        
        found = result.get_document_by_name("test.pdf")
        assert found is not None
        assert found.name == "test.pdf"
    
    def test_get_document_by_name_not_found(self):
        """测试通过名称获取不存在的文档"""
        result = ParseResult()
        
        found = result.get_document_by_name("不存在.pdf")
        assert found is None
    
    def test_multiple_documents_and_errors(self):
        """测试混合场景：多个文档和错误"""
        result = ParseResult()
        
        # 添加成功文档
        result.add_document(Document(
            file_path="/data/doc1.pdf",
            file_name="doc1.pdf"
        ))
        result.add_document(Document(
            file_path="/data/doc2.pdf",
            file_name="doc2.pdf"
        ))
        
        # 添加错误
        result.add_error("/data/error1.pdf", "格式错误")
        result.add_error("/data/error2.pdf", "文件损坏")
        
        assert len(result.documents) == 2
        assert len(result.errors) == 2
        assert result.is_success() is False


class TestDocumentSerialization:
    """测试文档模型序列化"""
    
    def test_document_to_dict(self):
        """测试文档转字典"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            file_type=DocumentType.PDF,
            pages=5,
            metadata=DocumentMetadata(title="测试")
        )
        
        data = doc.model_dump()
        
        # 使用 by_alias=True 来获取别名
        data_by_alias = doc.model_dump(by_alias=True)
        assert data_by_alias["file_path"] == "/data/test.pdf"
        assert data_by_alias["file_name"] == "test.pdf"
        assert data_by_alias["file_type"] == "pdf"
        assert data_by_alias["pages"] == 5
    
    def test_document_to_json(self):
        """测试文档转 JSON"""
        doc = Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            file_type=DocumentType.PDF
        )
        
        json_str = doc.model_dump_json()
        
        assert "test.pdf" in json_str
        assert "pdf" in json_str
    
    def test_document_from_dict(self):
        """测试从字典创建文档"""
        data = {
            "file_path": "/data/test.pdf",
            "file_name": "test.pdf",
            "file_type": "pdf",
            "pages": 3
        }
        
        doc = Document.model_validate(data)
        
        assert doc.name == "test.pdf"
        assert doc.type == DocumentType.PDF
        assert doc.pages == 3
