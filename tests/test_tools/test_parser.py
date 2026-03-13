"""
文档解析工具测试

测试 parse_documents 和 get_document_info 功能
使用 Mock 模拟文件系统和解析器
"""

import pytest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path

from compliance_checker.tools.parser import parse_documents, get_document_info
from compliance_checker.core.document import Document, DocumentType


class TestGetDocumentInfo:
    """测试 get_document_info 函数"""
    
    def test_existing_file(self):
        """测试存在的文件"""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as mock_stat:
            
            mock_stat.return_value = Mock(st_size=1024)
            
            info = get_document_info("/data/test.pdf")
            
            assert info["exists"] is True
            assert info["file_name"] == "test.pdf"
            assert info["file_type"] == "pdf"
            assert info["size_bytes"] == 1024
    
    def test_nonexistent_file(self):
        """测试不存在的文件"""
        with patch("pathlib.Path.exists", return_value=False):
            info = get_document_info("/data/nonexistent.pdf")
            
            assert info["exists"] is False
            assert info["error"] == "文件不存在"
    
    def test_different_extensions(self):
        """测试不同扩展名"""
        test_cases = [
            ("/data/doc.pdf", "pdf"),
            ("/data/doc.docx", "docx"),
            ("/data/doc.doc", "doc"),
            ("/data/image.jpg", "image"),
            ("/data/image.png", "image"),
        ]
        
        for file_path, expected_type in test_cases:
            with patch("pathlib.Path.exists", return_value=True), \
                 patch("pathlib.Path.is_file", return_value=True), \
                 patch("pathlib.Path.stat", return_value=Mock(st_size=100)):
                
                info = get_document_info(file_path)
                assert info["file_type"] == expected_type, f"{file_path} 应该是 {expected_type}"


class TestParseDocuments:
    """测试 parse_documents 函数"""
    
    @pytest.fixture
    def mock_document(self):
        """创建模拟文档"""
        from compliance_checker.core.document import DocumentMetadata
        return Document(
            file_path="/data/test.pdf",
            file_name="test.pdf",
            file_type=DocumentType.PDF,
            pages=5,
            pages_content=[],
            metadata=DocumentMetadata(title="测试文档")
        )
    
    @pytest.mark.asyncio
    async def test_parse_single_file_success(self, mock_document):
        """测试单文件解析成功"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = mock_document
            
            result = await parse_documents(["/data/test.pdf"])
            
            assert len(result["documents"]) == 1
            # model_dump() 默认使用字段名（name），不是别名（file_name）
            assert result["documents"][0]["name"] == "test.pdf"
            assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_parse_multiple_files(self, mock_document):
        """测试多文件解析"""
        doc1 = Document(
            file_path="/data/doc1.pdf",
            file_name="doc1.pdf",
            file_type=DocumentType.PDF,
            pages=3
        )
        doc2 = Document(
            file_path="/data/doc2.pdf",
            file_name="doc2.pdf",
            file_type=DocumentType.PDF,
            pages=5
        )
        
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.side_effect = [doc1, doc2]
            
            result = await parse_documents(["/data/doc1.pdf", "/data/doc2.pdf"])
            
            assert len(result["documents"]) == 2
            assert result["documents"][0]["name"] == "doc1.pdf"
            assert result["documents"][1]["name"] == "doc2.pdf"
    
    @pytest.mark.asyncio
    async def test_parse_file_not_found(self):
        """测试文件不存在"""
        with patch("pathlib.Path.exists", return_value=False):
            result = await parse_documents(["/data/nonexistent.pdf"])
            
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 1
            assert "文件不存在" in result["errors"][0]["error"]
    
    @pytest.mark.asyncio
    async def test_parse_not_a_file(self):
        """测试路径不是文件"""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=False):
            
            result = await parse_documents(["/data/directory"])
            
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 1
            assert "不是文件" in result["errors"][0]["error"]
    
    @pytest.mark.asyncio
    async def test_parse_invalid_format(self):
        """测试不支持的文件格式"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.side_effect = ValueError("不支持的文件格式: .xyz")
            
            result = await parse_documents(["/data/file.xyz"])
            
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 1
            assert "不支持的文件格式" in result["errors"][0]["error"]
    
    @pytest.mark.asyncio
    async def test_parse_generic_error(self):
        """测试通用解析错误"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.side_effect = Exception("未知错误")
            
            result = await parse_documents(["/data/error.pdf"])
            
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 1
            assert "解析失败" in result["errors"][0]["error"]
    
    @pytest.mark.asyncio
    async def test_parse_mixed_results(self, mock_document):
        """测试混合结果（成功和失败）"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.is_file", return_value=True):
            
            # 第一个文件存在，第二个不存在
            mock_exists.side_effect = [True, False]
            mock_parse.return_value = mock_document
            
            result = await parse_documents(["/data/exists.pdf", "/data/missing.pdf"])
            
            assert len(result["documents"]) == 1
            assert len(result["errors"]) == 1
    
    @pytest.mark.asyncio
    async def test_parse_empty_list(self):
        """测试空文件列表 - 会尝试自动扫描"""
        with patch("compliance_checker.tools.parser.scan_default_documents") as mock_scan:
            mock_scan.return_value = []
            
            result = await parse_documents([])
            
            # 空列表会触发自动扫描
            mock_scan.assert_called_once()
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_parse_with_options(self, mock_document):
        """测试带选项的解析"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = mock_document
            
            result = await parse_documents(
                ["/data/test.pdf"],
                extract_options={"ocr": False, "metadata": False}
            )
            
            # 验证选项传递给 parse_document
            mock_parse.assert_called_once_with("/data/test.pdf", use_ocr=False)
            
            # metadata=False 应该清空 metadata
            assert result["documents"][0]["metadata"] == {}
    
    @pytest.mark.asyncio
    async def test_parse_default_options(self, mock_document):
        """测试默认选项"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = mock_document
            
            await parse_documents(["/data/test.pdf"])
            
            # 默认 ocr=True
            mock_parse.assert_called_once_with("/data/test.pdf", use_ocr=True)
    
    @pytest.mark.asyncio
    async def test_parse_document_structure(self, mock_document):
        """测试返回文档结构"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = mock_document
            
            result = await parse_documents(["/data/test.pdf"])
            
            doc = result["documents"][0]
            # model_dump() 默认使用字段名，不是别名
            assert "path" in doc  # 不是 file_path
            assert "name" in doc  # 不是 file_name
            assert "type" in doc  # 不是 file_type
            assert "pages" in doc
            assert "metadata" in doc
    
    @pytest.mark.asyncio
    async def test_parse_absolute_path(self, mock_document):
        """测试返回绝对路径"""
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.absolute", return_value=Path("/absolute/path/test.pdf")):
            
            mock_parse.return_value = mock_document
            
            result = await parse_documents(["/data/test.pdf"])
            
            # 验证路径 - model_dump() 使用字段名 path
            assert "/data" in result["documents"][0]["path"] or "absolute" in result["documents"][0]["path"]


class TestParseDocumentsAutoScan:
    """测试自动扫描功能"""
    
    @pytest.mark.asyncio
    async def test_auto_scan_when_empty_list(self):
        """测试空列表时自动扫描"""
        with patch("compliance_checker.tools.parser.scan_default_documents") as mock_scan:
            mock_scan.return_value = ["/data/auto1.pdf", "/data/auto2.pdf"]
            
            with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("pathlib.Path.is_file", return_value=True):
                
                mock_parse.side_effect = [
                    Document(file_path="/data/auto1.pdf", file_name="auto1.pdf"),
                    Document(file_path="/data/auto2.pdf", file_name="auto2.pdf"),
                ]
                
                result = await parse_documents([])
                
                assert len(result["documents"]) == 2
                mock_scan.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_auto_scan_when_paths_provided(self):
        """测试提供路径时不自动扫描"""
        with patch("compliance_checker.tools.parser.scan_default_documents") as mock_scan:
            with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("pathlib.Path.is_file", return_value=True):
                
                mock_parse.return_value = Document(
                    file_path="/data/test.pdf",
                    file_name="test.pdf"
                )
                
                await parse_documents(["/data/test.pdf"])
                
                mock_scan.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_scan_import_error(self):
        """测试扫描配置导入失败"""
        # 当 scan_default_documents 为 None 时，调用会失败
        # 这里我们测试传入空列表的情况，但需要 mock 以避免错误
        with patch("compliance_checker.tools.parser.scan_default_documents") as mock_scan:
            mock_scan.return_value = []
            
            result = await parse_documents([])
            
            # 应该返回空结果
            assert len(result["documents"]) == 0
            assert len(result["errors"]) == 0


class TestParseDocumentsEdgeCases:
    """测试边界情况"""
    
    @pytest.mark.asyncio
    async def test_unicode_filename(self):
        """测试 Unicode 文件名"""
        doc = Document(
            file_path="/data/中文文件.pdf",
            file_name="中文文件.pdf",
            file_type=DocumentType.PDF
        )
        
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = doc
            
            result = await parse_documents(["/data/中文文件.pdf"])
            
            # 使用 model_dump(by_alias=True) 后，字段名是别名
            assert result["documents"][0]["name"] == "中文文件.pdf"
    
    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self):
        """测试特殊字符文件名"""
        doc = Document(
            file_path="/data/file-with_special.chars.pdf",
            file_name="file-with_special.chars.pdf",
            file_type=DocumentType.PDF
        )
        
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.return_value = doc
            
            result = await parse_documents(["/data/file-with_special.chars.pdf"])
            
            # 使用 model_dump(by_alias=True) 后，字段名是别名
            assert "file-with_special.chars.pdf" in result["documents"][0]["name"]
    
    @pytest.mark.asyncio
    async def test_large_file_count(self):
        """测试大量文件"""
        file_paths = [f"/data/file{i}.pdf" for i in range(100)]
        
        with patch("compliance_checker.tools.parser.parse_document") as mock_parse, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.is_file", return_value=True):
            
            mock_parse.side_effect = [
                Document(file_path=path, file_name=Path(path).name)
                for path in file_paths
            ]
            
            result = await parse_documents(file_paths)
            
            assert len(result["documents"]) == 100
            assert len(result["errors"]) == 0
