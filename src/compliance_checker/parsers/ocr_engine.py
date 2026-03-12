"""
OCR 引擎封装 - 支持多种 OCR 后端
- PaddleOCR（本地，体积大，无需网络）
- 阿里云 OCR（云端，轻量，需网络和付费）
- 无 OCR（默认，仅处理可编辑 PDF）
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

# OCR 后端类型
OCR_BACKEND = os.getenv("OCR_BACKEND", "none").lower()


@contextlib.contextmanager
def _suppress_output():
    """静默 stdout/stderr 输出（用于 PaddleOCR）"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        old_stdout_fd = os.dup(1)
        old_stderr_fd = os.dup(2)
        has_fd_dup = True
    except Exception:
        has_fd_dup = False

    silenced_loggers = []
    for name in logging.root.manager.loggerDict:
        if any(name.startswith(p) for p in ("paddle", "ppocr", "paddleocr")):
            lg = logging.getLogger(name)
            silenced_loggers.append((lg, lg.level))
            lg.setLevel(logging.CRITICAL + 1)

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
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        devnull.close()

        if has_fd_dup:
            os.dup2(old_stdout_fd, 1)
            os.dup2(old_stderr_fd, 2)
            os.close(old_stdout_fd)
            os.close(old_stderr_fd)

        for lg, lvl in silenced_loggers:
            lg.setLevel(lvl)


class BaseOCREngine:
    """OCR 引擎基类"""

    def recognize_image(self, image_path: str) -> str:
        """识别图片中的文字"""
        raise NotImplementedError

    def recognize_pdf_page(self, pdf_path: str, page_num: int, dpi: int = 200) -> str:
        """识别 PDF 指定页面的文字"""
        raise NotImplementedError

    def recognize_pdf(self, pdf_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        """识别整个 PDF 的所有页面"""
        raise NotImplementedError


class NoOCREngine(BaseOCREngine):
    """无 OCR 引擎 - 返回空结果"""

    def recognize_image(self, image_path: str) -> str:
        logger.debug("OCR 未启用，跳过图片识别")
        return ""

    def recognize_pdf_page(self, pdf_path: str, page_num: int, dpi: int = 200) -> str:
        logger.debug("OCR 未启用，跳过 PDF 页面识别")
        return ""

    def recognize_pdf(self, pdf_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        logger.debug("OCR 未启用，跳过 PDF 识别")
        return []


class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎（本地）"""

    def __init__(self, use_gpu: bool = False, lang: str = "ch", show_log: bool = False):
        self.use_gpu = use_gpu
        self.lang = lang
        self.show_log = show_log
        self._ocr = None

    def _get_ocr(self):
        """延迟初始化 PaddleOCR 引擎"""
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
                logger.error("PaddleOCR 未安装，请运行: pip install 'compliance-checker[local-ocr]'")
                raise
            except Exception as e:
                logger.error(f"PaddleOCR 初始化失败: {e}")
                raise
        return self._ocr

    def recognize_image(self, image_path: str) -> str:
        ocr = self._get_ocr()
        try:
            with _suppress_output():
                result = ocr.ocr(image_path, cls=True)

            if not result or not result[0]:
                return ""

            lines = []
            for line in result[0]:
                if line:
                    text = line[1][0]
                    confidence = line[1][1]
                    if confidence > 0.5:
                        lines.append(text)

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"OCR 识别失败 {image_path}: {e}")
            return ""

    def recognize_pdf_page(self, pdf_path: str, page_num: int, dpi: int = 200) -> str:
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            raise

        doc = fitz.open(pdf_path)
        try:
            if page_num >= len(doc):
                logger.warning(f"页码 {page_num} 超出范围")
                return ""

            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name

            pix.save(tmp_path)
            text = self.recognize_image(tmp_path)

            try:
                os.unlink(tmp_path)
            except:
                pass

            return text

        finally:
            doc.close()

    def recognize_pdf(self, pdf_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            raise

        doc = fitz.open(pdf_path)
        results = []

        try:
            for page_num in range(len(doc)):
                text = self.recognize_pdf_page(pdf_path, page_num, dpi)
                results.append((page_num, text))
                logger.debug(f"PDF 第 {page_num + 1} 页 OCR 完成")
        finally:
            doc.close()

        return results


class AliyunOCREngine(BaseOCREngine):
    """阿里云 OCR 引擎（云端）"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """初始化阿里云 OCR 客户端"""
        if self._client is None:
            try:
                from alibabacloud_ocr_api20210707.client import Client
                from alibabacloud_tea_openapi import models as open_api_models

                access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
                access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")

                if not access_key_id or not access_key_secret:
                    raise ValueError(
                        "阿里云 OCR 需要配置 ALIBABA_CLOUD_ACCESS_KEY_ID 和 "
                        "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
                    )

                config = open_api_models.Config(
                    access_key_id=access_key_id,
                    access_key_secret=access_key_secret,
                )
                config.endpoint = "ocr-api.cn-hangzhou.aliyuncs.com"
                self._client = Client(config)
                logger.info("阿里云 OCR 客户端初始化成功")

            except ImportError:
                logger.error(
                    "阿里云 OCR SDK 未安装，请运行: pip install 'compliance-checker[cloud-ocr]'"
                )
                raise
            except Exception as e:
                logger.error(f"阿里云 OCR 初始化失败: {e}")
                raise

        return self._client

    def recognize_image(self, image_path: str) -> str:
        try:
            from alibabacloud_ocr_api20210707 import models as ocr_models

            client = self._get_client()

            with open(image_path, "rb") as f:
                image_bytes = f.read()

            import base64
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            body = ocr_models.RecognizeGeneralTextRequestBody(
                content=image_base64,
                output_probability=True,
            )
            request = ocr_models.RecognizeGeneralTextRequest(body=body)
            response = client.recognize_general_text(request)

            # 解析结果
            results = []
            if response.body and response.body.data:
                for word in response.body.data.words:
                    if word and word.word:
                        results.append(word.word)

            return "\n".join(results)

        except Exception as e:
            logger.error(f"阿里云 OCR 识别失败 {image_path}: {e}")
            return ""

    def recognize_pdf_page(self, pdf_path: str, page_num: int, dpi: int = 200) -> str:
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            raise

        doc = fitz.open(pdf_path)
        try:
            if page_num >= len(doc):
                logger.warning(f"页码 {page_num} 超出范围")
                return ""

            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name

            pix.save(tmp_path)
            text = self.recognize_image(tmp_path)

            try:
                os.unlink(tmp_path)
            except:
                pass

            return text

        finally:
            doc.close()

    def recognize_pdf(self, pdf_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            raise

        doc = fitz.open(pdf_path)
        results = []

        try:
            for page_num in range(len(doc)):
                text = self.recognize_pdf_page(pdf_path, page_num, dpi)
                results.append((page_num, text))
                logger.debug(f"PDF 第 {page_num + 1} 页 OCR 完成")
        finally:
            doc.close()

        return results


def get_ocr_engine() -> BaseOCREngine:
    """
    根据配置获取 OCR 引擎

    环境变量 OCR_BACKEND 可选值：
    - none: 无 OCR（默认）
    - paddle: PaddleOCR（本地）
    - aliyun: 阿里云 OCR（云端）
    """
    backend = os.getenv("OCR_BACKEND", "none").lower()

    if backend == "paddle":
        logger.info("使用 PaddleOCR 引擎（本地）")
        return PaddleOCREngine()
    elif backend == "aliyun":
        logger.info("使用阿里云 OCR 引擎（云端）")
        return AliyunOCREngine()
    else:
        logger.debug("OCR 未启用（默认）")
        return NoOCREngine()


def is_scanned_pdf(pdf_path: str, sample_pages: int = 3) -> bool:
    """
    检测 PDF 是否为扫描件（无文本层）

    Args:
        pdf_path: PDF 文件路径
        sample_pages: 采样页数

    Returns:
        True 如果是扫描件，False 如果有文本层
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

        avg_length = sum(text_lengths) / len(text_lengths)
        is_scanned = avg_length < 50

        logger.debug(f"PDF 文本层检测: 平均长度={avg_length}, 是否扫描件={is_scanned}")
        return is_scanned

    finally:
        doc.close()


# 全局 OCR 引擎实例（单例模式）
_ocr_engine: Optional[BaseOCREngine] = None


def get_global_ocr_engine() -> BaseOCREngine:
    """获取全局 OCR 引擎实例"""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = get_ocr_engine()
    return _ocr_engine


def reset_ocr_engine():
    """重置 OCR 引擎（用于测试或重新配置）"""
    global _ocr_engine
    _ocr_engine = None
