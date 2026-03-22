"""
OCR 引擎实现 - Infrastructure 层

支持多种 OCR 后端：
- none: 无 OCR（默认，仅处理可编辑 PDF）
- paddle: PaddleOCR（本地，体积大但无需网络）
- aliyun: 阿里云 OCR（云端，轻量但需网络和付费）

实现 Core 层定义的 OCREngineProtocol 接口。
"""

import os
import sys
import logging
import contextlib
import tempfile
from typing import List, Tuple, Optional
from pathlib import Path

from ...core.interfaces import OCREngineProtocol

logger = logging.getLogger(__name__)


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

    # 静默 PaddleOCR 相关日志
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


class NoOCREngine(OCREngineProtocol):
    """
    无 OCR 引擎 - 返回空结果

    当 OCR_BACKEND=none 时使用，仅处理可编辑 PDF。
    """

    def recognize_image(self, image_path: str) -> str:
        """识别图片中的文字"""
        logger.debug("OCR 未启用，跳过图片识别")
        return ""

    def recognize_pdf(self, file_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        """识别 PDF 文件中的所有页面"""
        logger.debug("OCR 未启用，跳过 PDF 识别")
        return []


class PaddleOCREngine(OCREngineProtocol):
    """
    PaddleOCR 引擎（本地）

    需要安装: pip install paddleocr
    特点: 体积大(~500MB)，无需网络，本地运行
    """

    def __init__(self, use_gpu: bool = False, lang: str = "ch"):
        """
        初始化 PaddleOCR 引擎

        Args:
            use_gpu: 是否使用 GPU
            lang: 语言，默认中文 "ch"

        Raises:
            ImportError: 当 paddleocr 未安装时抛出，附带友好提示
        """
        self.device = "gpu" if use_gpu else "cpu"
        self.lang = lang
        self._ocr = None

        # 在初始化时检查 paddleocr 是否可用，提供即时反馈
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            raise ImportError(
                "PaddleOCR 未安装。请运行以下命令安装:\n"
                "  pip install paddleocr\n\n"
                "或者切换到其他 OCR 后端:\n"
                "  export OCR_BACKEND=none    # 禁用 OCR（仅处理可编辑 PDF）\n"
                "  export OCR_BACKEND=aliyun  # 使用阿里云 OCR"
            )

    def _get_ocr(self):
        """延迟初始化 PaddleOCR 引擎"""
        if self._ocr is None:
            try:
                with _suppress_output():
                    from paddleocr import PaddleOCR

                    self._ocr = PaddleOCR(
                        lang=self.lang,
                        device=self.device,
                        use_textline_orientation=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                    )
                logger.info("PaddleOCR 引擎初始化成功")
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
            识别出的文字，失败返回空字符串
        """
        try:
            ocr = self._get_ocr()
            with _suppress_output():
                # PaddleOCR 3.x 使用 predict 方法
                result = ocr.predict(image_path)

            if not result:
                return ""

            lines = []
            for item in result:
                rec_texts = item.get("rec_texts", [])
                rec_scores = item.get("rec_scores", [])

                for i, text in enumerate(rec_texts):
                    confidence = rec_scores[i] if i < len(rec_scores) else 0.0
                    if confidence > 0.5:
                        lines.append(text)

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"OCR 识别失败 {image_path}: {e}")
            return ""

    def recognize_pdf(self, file_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        """
        识别 PDF 文件中的所有页面

        Args:
            file_path: PDF 文件路径
            dpi: 渲染分辨率

        Returns:
            [(page_num, ocr_text), ...] 列表
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            return []

        doc = fitz.open(file_path)
        results = []

        try:
            for page_num in range(len(doc)):
                text = self._recognize_pdf_page(doc, page_num, dpi)
                results.append((page_num, text))
                logger.debug(f"PDF 第 {page_num + 1} 页 OCR 完成")
        finally:
            doc.close()

        return results

    def _recognize_pdf_page(self, doc: "fitz.Document", page_num: int, dpi: int = 200) -> str:
        """识别 PDF 指定页面的文字"""
        try:
            import fitz

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

        except Exception as e:
            logger.error(f"PDF 页面 OCR 失败: {e}")
            return ""


class AliyunOCREngine(OCREngineProtocol):
    """
    阿里云 OCR 引擎（云端）

    需要安装: pip install alibabacloud_ocr_api20210707
    需要配置: ALIBABA_CLOUD_ACCESS_KEY_ID, ALIBABA_CLOUD_ACCESS_KEY_SECRET
    特点: 轻量，需网络，按量付费
    """

    def __init__(
        self, access_key_id: Optional[str] = None, access_key_secret: Optional[str] = None
    ):
        """
        初始化阿里云 OCR 引擎

        Args:
            access_key_id: 阿里云 AccessKey ID，默认从环境变量读取
            access_key_secret: 阿里云 AccessKey Secret，默认从环境变量读取
        """
        self._access_key_id = access_key_id or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        self._access_key_secret = access_key_secret or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        self._client = None

    def _get_client(self):
        """初始化阿里云 OCR 客户端"""
        if self._client is None:
            try:
                from alibabacloud_ocr_api20210707.client import Client
                from alibabacloud_tea_openapi import models as open_api_models

                if not self._access_key_id or not self._access_key_secret:
                    raise ValueError(
                        "阿里云 OCR 需要配置 ALIBABA_CLOUD_ACCESS_KEY_ID 和 "
                        "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
                    )

                config = open_api_models.Config(
                    access_key_id=self._access_key_id,
                    access_key_secret=self._access_key_secret,
                )
                config.endpoint = "ocr-api.cn-hangzhou.aliyuncs.com"
                self._client = Client(config)
                logger.info("阿里云 OCR 客户端初始化成功")

            except ImportError:
                logger.error(
                    "阿里云 OCR SDK 未安装，请运行: pip install alibabacloud_ocr_api20210707"
                )
                raise
            except Exception as e:
                logger.error(f"阿里云 OCR 初始化失败: {e}")
                raise

        return self._client

    def recognize_image(self, image_path: str) -> str:
        """
        识别图片中的文字

        Args:
            image_path: 图片文件路径

        Returns:
            识别出的文字，失败返回空字符串
        """
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

    def recognize_pdf(self, file_path: str, dpi: int = 200) -> List[Tuple[int, str]]:
        """
        识别 PDF 文件中的所有页面

        Args:
            file_path: PDF 文件路径
            dpi: 渲染分辨率

        Returns:
            [(page_num, ocr_text), ...] 列表
        """
        try:
            import fitz
        except ImportError:
            logger.error("PyMuPDF 未安装")
            return []

        doc = fitz.open(file_path)
        results = []

        try:
            for page_num in range(len(doc)):
                text = self._recognize_pdf_page(doc, page_num, dpi)
                results.append((page_num, text))
                logger.debug(f"PDF 第 {page_num + 1} 页 OCR 完成")
        finally:
            doc.close()

        return results

    def _recognize_pdf_page(self, doc: "fitz.Document", page_num: int, dpi: int = 200) -> str:
        """识别 PDF 指定页面的文字"""
        try:
            import fitz

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

        except Exception as e:
            logger.error(f"PDF 页面 OCR 失败: {e}")
            return ""


def create_ocr_engine(backend: Optional[str] = None) -> OCREngineProtocol:
    """
    根据配置创建 OCR 引擎

    Args:
        backend: OCR 后端类型，默认从环境变量 OCR_BACKEND 读取
                可选值: "none", "paddle", "aliyun"

    Returns:
        OCREngineProtocol 实例

    Note:
        当配置的 OCR 后端依赖未安装时，会自动回退到 NoOCREngine 并记录警告日志
    """
    backend = (backend or os.getenv("OCR_BACKEND", "none")).lower()

    if backend == "paddle":
        try:
            logger.info("使用 PaddleOCR 引擎（本地）")
            return PaddleOCREngine()
        except ImportError as e:
            logger.warning(f"PaddleOCR 不可用: {e}")
            logger.warning("已自动回退到无 OCR 模式（仅处理可编辑 PDF）")
            return NoOCREngine()
    elif backend == "aliyun":
        try:
            logger.info("使用阿里云 OCR 引擎（云端）")
            return AliyunOCREngine()
        except ImportError as e:
            logger.warning(f"阿里云 OCR SDK 未安装: {e}")
            logger.warning("已自动回退到无 OCR 模式（仅处理可编辑 PDF）")
            return NoOCREngine()
        except ValueError as e:
            logger.warning(f"阿里云 OCR 配置错误: {e}")
            logger.warning("已自动回退到无 OCR 模式（仅处理可编辑 PDF）")
            return NoOCREngine()
    else:
        logger.debug("OCR 未启用（默认）")
        return NoOCREngine()
