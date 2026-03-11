"""
PaddleOCR 封装 - 提供OCR识别功能
支持中文识别，用于扫描件文字提取
"""
import os
import sys
import logging
import contextlib
from typing import List, Tuple, Optional
from pathlib import Path
import tempfile

# 配置日志
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _suppress_output():
    """
    完全静默 PaddleOCR / PaddlePaddle 的 stdout / stderr 输出。

    实现方式：
    1. 将 sys.stdout / sys.stderr 重定向到 os.devnull（Python 层拦截）
    2. 同时将底层 C 层文件描述符 1/2 重定向（Paddle 内部 C++ 打印）
    3. 将 paddle / ppocr / paddleocr 相关 logger 的级别临时调高到 CRITICAL
    """
    # ── 1. 保存原始 Python 流 ──────────────────────────────────────────
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    # ── 2. 保存原始 C 层 fd ───────────────────────────────────────────
    try:
        old_stdout_fd = os.dup(1)
        old_stderr_fd = os.dup(2)
        has_fd_dup = True
    except Exception:
        has_fd_dup = False

    # ── 3. 静默 paddle / ppocr 日志 logger ──────────────────────────
    silenced_loggers = []
    for name in logging.root.manager.loggerDict:
        if any(name.startswith(p) for p in ("paddle", "ppocr", "paddleocr")):
            lg = logging.getLogger(name)
            silenced_loggers.append((lg, lg.level))
            lg.setLevel(logging.CRITICAL + 1)
    # 同时静默 root logger 中可能被 paddleocr 用到的部分
    root_logger = logging.getLogger()
    original_root_level = root_logger.level

    try:
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = devnull
        sys.stderr = devnull

        if has_fd_dup:
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
            os.close(devnull_fd)

        yield

    finally:
        # ── 还原 Python 流 ──────────────────────────────────────────
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        devnull.close()

        # ── 还原 C 层 fd ─────────────────────────────────────────────
        if has_fd_dup:
            os.dup2(old_stdout_fd, 1)
            os.dup2(old_stderr_fd, 2)
            os.close(old_stdout_fd)
            os.close(old_stderr_fd)

        # ── 还原 logger 级别 ─────────────────────────────────────────
        for lg, lvl in silenced_loggers:
            lg.setLevel(lvl)


class OCREngine:
    """
    PaddleOCR 引擎封装
    
    功能：
    - 图片OCR识别
    - PDF页面OCR识别（先将PDF转为图片）
    - 支持中文识别
    """
    
    def __init__(self, 
                 use_gpu: bool = False,
                 lang: str = "ch",
                 show_log: bool = False):
        """
        初始化OCR引擎
        
        Args:
            use_gpu: 是否使用GPU
            lang: 识别语言，默认中文(ch)
            show_log: 是否显示PaddleOCR日志
        """
        self.use_gpu = use_gpu
        self.lang = lang
        self.show_log = show_log
        self._ocr = None
        
    def _get_ocr(self):
        """延迟初始化OCR引擎"""
        if self._ocr is None:
            try:
                with _suppress_output():
                    from paddleocr import PaddleOCR
                    self._ocr = PaddleOCR(
                        use_angle_cls=True,
                        lang=self.lang,
                        use_gpu=self.use_gpu,
                        show_log=self.show_log
                    )
                logger.info("PaddleOCR 引擎初始化成功")
            except ImportError:
                logger.error("PaddleOCR 未安装，请运行: pip install paddleocr")
                raise
            except Exception as e:
                logger.error(f"PaddleOCR 初始化失败: {e}")
                raise
        return self._ocr
    
    def recognize_image(self, image_path: str) -> str:
        """
        识别图片中的文字
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            识别出的文字内容
        """
        ocr = self._get_ocr()
        
        try:
            with _suppress_output():
                result = ocr.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return ""
            
            # 提取文字，按行组织
            lines = []
            for line in result[0]:
                if line:
                    text = line[1][0]  # 文字内容
                    confidence = line[1][1]  # 置信度
                    if confidence > 0.5:  # 过滤低置信度结果
                        lines.append(text)
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"OCR识别失败 {image_path}: {e}")
            return ""
    
    def recognize_pdf_page(self, pdf_path: str, page_num: int, dpi: int = 200) -> str:
        """
        识别PDF指定页面的文字
        
        Args:
            pdf_path: PDF文件路径
            page_num: 页码（从0开始）
            dpi: 转换图片的分辨率
            
        Returns:
            识别出的文字内容
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF 未安装，请运行: pip install PyMuPDF")
            raise
        
        # 将PDF页面转为图片
        doc = fitz.open(pdf_path)
        try:
            if page_num >= len(doc):
                logger.warning(f"页码 {page_num} 超出范围，PDF共 {len(doc)} 页")
                return ""
            
            page = doc[page_num]
            
            # 设置缩放矩阵提高清晰度
            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat)
            
            # 保存为临时文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
            
            pix.save(tmp_path)
            
            # OCR识别
            text = self.recognize_image(tmp_path)
            
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass
            
            return text
            
        finally:
            doc.close()
    
    def recognize_pdf(self, pdf_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        """
        识别整个PDF的所有页面
        
        Args:
            pdf_path: PDF文件路径
            dpi: 转换图片的分辨率
            
        Returns:
            列表，每项为 (页码, 识别文字)
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装，请运行: pip install PyMuPDF")
            raise
        
        doc = fitz.open(pdf_path)
        results = []
        
        try:
            for page_num in range(len(doc)):
                text = self.recognize_pdf_page(pdf_path, page_num, dpi)
                results.append((page_num, text))
                logger.debug(f"PDF第{page_num+1}页OCR完成")
        finally:
            doc.close()
        
        return results
    
    def is_scanned_pdf(self, pdf_path: str, sample_pages: int = 3) -> bool:
        """
        检测PDF是否为扫描件（无文本层）
        
        Args:
            pdf_path: PDF文件路径
            sample_pages: 采样页数
            
        Returns:
            True如果是扫描件，False如果有文本层
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            return False
        
        doc = fitz.open(pdf_path)
        try:
            total_pages = len(doc)
            check_pages = min(sample_pages, total_pages)
            
            text_lengths = []
            for i in range(check_pages):
                page = doc[i]
                text = page.get_text()
                text_lengths.append(len(text.strip()))
            
            # 如果采样页面的平均文本长度小于50字符，认为是扫描件
            avg_length = sum(text_lengths) / len(text_lengths)
            is_scanned = avg_length < 50
            
            logger.debug(f"PDF文本层检测: 平均长度={avg_length}, 是否扫描件={is_scanned}")
            return is_scanned
            
        finally:
            doc.close()


# 全局OCR引擎实例（单例模式）
_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine(use_gpu: bool = False, lang: str = "ch") -> OCREngine:
    """
    获取全局OCR引擎实例
    
    Args:
        use_gpu: 是否使用GPU
        lang: 识别语言
        
    Returns:
        OCREngine实例
    """
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = OCREngine(use_gpu=use_gpu, lang=lang)
    return _ocr_engine


def reset_ocr_engine():
    """重置OCR引擎（用于测试或重新配置）"""
    global _ocr_engine
    _ocr_engine = None
