"""
PDF 解析器 - 支持文本提取和OCR识别
"""
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import re

try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    FITZ_AVAILABLE = False

from ..core.document import Document, DocumentType, PageContent, DocumentMetadata
from .ocr_engine import get_ocr_engine

logger = logging.getLogger(__name__)


class PDFParser:
    """
    PDF文档解析器

    功能：
    - 提取PDF文本内容
    - 自动检测扫描件并使用OCR
    - 提取PDF元数据
    - 提取签发日期、有效期等关键信息
    """

    def __init__(self, use_ocr: bool = True, ocr_dpi: int = 200):
        """
        初始化PDF解析器

        Args:
            use_ocr: 是否对扫描件使用OCR
            ocr_dpi: OCR时PDF转图片的分辨率
        """
        if not FITZ_AVAILABLE:
            raise ImportError("PyMuPDF 未安装，请运行: pip install PyMuPDF")

        self.use_ocr = use_ocr
        self.ocr_dpi = ocr_dpi
        self._ocr_engine = None

    def _get_ocr_engine(self):
        """获取OCR引擎实例"""
        if self._ocr_engine is None and self.use_ocr:
            self._ocr_engine = get_ocr_engine()
        return self._ocr_engine

    def parse(self, file_path: str) -> Document:
        """
        解析PDF文件

        Args:
            file_path: PDF文件路径

        Returns:
            Document对象
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if not path.suffix.lower() in [".pdf"]:
            raise ValueError(f"不支持的文件格式: {path.suffix}")

        logger.info(f"开始解析PDF: {file_path}")

        doc = fitz.open(file_path)

        try:
            # 提取元数据
            metadata = self._extract_metadata(doc, file_path)

            # 检测是否为扫描件
            is_scanned = self._is_scanned_document(doc)

            # 提取页面内容
            pages_content = []

            if is_scanned and self.use_ocr:
                # 扫描件使用OCR
                logger.info("检测到扫描件，使用OCR识别")
                pages_content = self._extract_with_ocr(file_path, len(doc))
            else:
                # 正常提取文本层
                pages_content = self._extract_text_content(doc)

            # 从内容中提取日期信息
            self._extract_dates_from_content(metadata, pages_content)

            document = Document(
                file_path=str(path.absolute()),
                file_name=path.name,
                file_type=DocumentType.PDF,
                pages=len(doc),
                pages_content=pages_content,
                metadata=metadata,
            )

            logger.info(f"PDF解析完成: {path.name}, 共{len(doc)}页")
            return document

        finally:
            doc.close()

    def _extract_metadata(self, doc, file_path: str) -> DocumentMetadata:
        """提取PDF元数据"""
        meta = doc.metadata

        metadata = DocumentMetadata(
            title=meta.get("title"),
            author=meta.get("author"),
            subject=meta.get("subject"),
            creator=meta.get("creator"),
            producer=meta.get("producer"),
        )

        # 解析日期
        if meta.get("creationDate"):
            metadata.creation_date = self._parse_pdf_date(meta["creationDate"])
        if meta.get("modDate"):
            metadata.modification_date = self._parse_pdf_date(meta["modDate"])

        return metadata

    def _parse_pdf_date(self, date_str: str) -> Optional[datetime]:
        """解析PDF日期格式"""
        # PDF日期格式: D:20240315120000+08'00'
        try:
            if date_str.startswith("D:"):
                date_str = date_str[2:]
            # 提取年月日时分秒
            match = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", date_str)
            if match:
                year, month, day, hour, minute, second = map(int, match.groups())
                return datetime(year, month, day, hour, minute, second)
        except Exception as e:
            logger.debug(f"日期解析失败: {date_str}, 错误: {e}")
        return None

    def _is_scanned_document(self, doc, sample_pages: int = 3) -> bool:
        """检测是否为扫描件"""
        total_pages = len(doc)
        check_pages = min(sample_pages, total_pages)

        text_lengths = []
        for i in range(check_pages):
            page = doc[i]
            text = page.get_text()
            text_lengths.append(len(text.strip()))

        # 如果采样页面的平均文本长度小于50字符，认为是扫描件
        avg_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0
        is_scanned = avg_length < 50

        return is_scanned

    def _extract_text_content(self, doc) -> List[PageContent]:
        """提取PDF文本层内容"""
        pages_content = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            pages_content.append(
                PageContent(page_num=page_num, text=text.strip(), has_text_layer=True)
            )

        return pages_content

    def _extract_with_ocr(self, file_path: str, total_pages: int) -> List[PageContent]:
        """使用OCR提取扫描件内容"""
        pages_content = []
        ocr_engine = self._get_ocr_engine()

        if ocr_engine is None:
            logger.warning("OCR引擎不可用，返回空内容")
            return [
                PageContent(page_num=i, text="", has_text_layer=False) for i in range(total_pages)
            ]

        try:
            ocr_results = ocr_engine.recognize_pdf(file_path, dpi=self.ocr_dpi)

            for page_num, ocr_text in ocr_results:
                pages_content.append(
                    PageContent(
                        page_num=page_num,
                        text="",  # 扫描件无文本层
                        ocr_text=ocr_text,
                        has_text_layer=False,
                    )
                )

        except Exception as e:
            logger.error(f"OCR识别失败: {e}")
            # OCR失败时返回空内容
            pages_content = [
                PageContent(page_num=i, text="", has_text_layer=False) for i in range(total_pages)
            ]

        return pages_content

    def _extract_dates_from_content(
        self, metadata: DocumentMetadata, pages_content: List[PageContent]
    ):
        """从内容中提取日期信息"""
        # 合并所有页面文本
        full_text = "\n".join([p.get_full_text() for p in pages_content])

        # 提取签发日期
        issue_date = self._extract_issue_date(full_text)
        if issue_date:
            metadata.issue_date = issue_date

        # 提取有效期
        valid_from, valid_to = self._extract_validity_period(full_text)
        if valid_from:
            metadata.valid_from = valid_from
        if valid_to:
            metadata.valid_to = valid_to

        # 提取文件编号
        doc_number = self._extract_document_number(full_text)
        if doc_number:
            metadata.document_number = doc_number

    def _extract_issue_date(self, text: str) -> Optional[str]:
        """提取签发日期"""
        # 常见日期格式
        patterns = [
            r"(?:签发日期|发文日期|日期|落款日期)[：:\s]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)?",
            r"(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)\s*(?:发布|印发|签发|出具)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                if date_str:
                    return self._normalize_date(date_str)

        return None

    def _extract_validity_period(self, text: str) -> tuple:
        """提取有效期"""
        valid_from = None
        valid_to = None

        # 有效期至/到
        to_patterns = [
            r"有效期[至到][：:\s]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)",
            r"有效期[至到][：:\s]*(\d{4}[年/-]\d{1,2}[月]?)",
            r"截至日期[：:\s]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)",
        ]

        for pattern in to_patterns:
            match = re.search(pattern, text)
            if match:
                valid_to = self._normalize_date(match.group(1))
                break

        # 有效期从/自
        from_patterns = [
            r"有效期[从自][：:\s]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)",
            r"生效日期[：:\s]*(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)",
        ]

        for pattern in from_patterns:
            match = re.search(pattern, text)
            if match:
                valid_from = self._normalize_date(match.group(1))
                break

        return valid_from, valid_to

    def _extract_document_number(self, text: str) -> Optional[str]:
        """提取文件编号"""
        patterns = [
            r"(?:文件编号|文号|编号|批复号|证书编号)[：:\s]*([A-Za-z0-9\-\〔\〔\【\】\[\]]+)",
            r"No[.：:\s]*([A-Za-z0-9\-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

    def _normalize_date(self, date_str: str) -> str:
        """标准化日期格式为 YYYY-MM-DD"""
        # 移除非数字字符，保留年月日
        date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "")
        date_str = date_str.replace("/", "-")

        parts = date_str.split("-")
        if len(parts) >= 2:
            year = parts[0]
            month = parts[1].zfill(2)
            day = parts[2].zfill(2) if len(parts) > 2 else "01"
            return f"{year}-{month}-{day}"

        return date_str


def parse_pdf(file_path: str, use_ocr: bool = True) -> Document:
    """
    便捷函数：解析PDF文件

    Args:
        file_path: PDF文件路径
        use_ocr: 是否对扫描件使用OCR

    Returns:
        Document对象
    """
    parser = PDFParser(use_ocr=use_ocr)
    return parser.parse(file_path)
