"""
Parsers 模块初始化
"""
from pathlib import Path
from typing import Union

from ..core.document import Document, DocumentType
from .pdf_parser import PDFParser, parse_pdf
from .docx_parser import DocxParser, parse_docx


def get_document_type(file_path: str) -> DocumentType:
    """
    根据文件扩展名判断文档类型
    
    Args:
        file_path: 文件路径
        
    Returns:
        DocumentType枚举值
    """
    suffix = Path(file_path).suffix.lower()
    
    if suffix == '.pdf':
        return DocumentType.PDF
    elif suffix == '.docx':
        return DocumentType.DOCX
    elif suffix == '.doc':
        return DocumentType.DOC
    elif suffix in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
        return DocumentType.IMAGE
    else:
        return DocumentType.UNKNOWN


def parse_document(file_path: str, use_ocr: bool = True) -> Document:
    """
    自动识别文件类型并解析
    
    Args:
        file_path: 文件路径
        use_ocr: 是否对扫描件使用OCR（仅PDF有效）
        
    Returns:
        Document对象
        
    Raises:
        ValueError: 不支持的文件格式
        FileNotFoundError: 文件不存在
    """
    doc_type = get_document_type(file_path)
    
    if doc_type == DocumentType.PDF:
        parser = PDFParser(use_ocr=use_ocr)
        return parser.parse(file_path)
    
    elif doc_type == DocumentType.DOCX:
        parser = DocxParser()
        return parser.parse(file_path)
    
    elif doc_type == DocumentType.DOC:
        raise ValueError(
            ".doc格式暂不支持，请先转换为.docx格式。"
            "可以使用LibreOffice或Microsoft Word进行转换。"
        )
    
    elif doc_type == DocumentType.IMAGE:
        # 图片文件，使用OCR解析
        from .ocr_engine import get_ocr_engine
        from ..core.document import PageContent, DocumentMetadata
        
        ocr_engine = get_ocr_engine()
        text = ocr_engine.recognize_image(file_path)
        
        path = Path(file_path)
        return Document(
            file_path=str(path.absolute()),
            file_name=path.name,
            file_type=DocumentType.IMAGE,
            pages=1,
            pages_content=[PageContent(
                page_num=0,
                text="",
                ocr_text=text,
                has_text_layer=False
            )],
            metadata=DocumentMetadata()
        )
    
    else:
        raise ValueError(f"不支持的文件格式: {Path(file_path).suffix}")


__all__ = [
    'PDFParser',
    'DocxParser',
    'parse_pdf',
    'parse_docx',
    'parse_document',
    'get_document_type',
]
