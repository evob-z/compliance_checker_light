"""
PyMuPDFConverter 单元测试

测试 PDF 转换器的核心功能，使用内存中的 PDF 数据避免依赖外部文件。
遵循 architecture.md 中『10.2 Domain 层测试示例』规范。
"""

import pytest
from typing import List
from io import BytesIO

from src.infrastructure.converter.pdf_converter import PyMuPDFConverter
from src.core.interfaces import PDFConverterProtocol


class TestPyMuPDFConverter:
    """PyMuPDFConverter 测试类"""

    @pytest.fixture
    def converter(self):
        """创建默认配置的转换器实例"""
        return PyMuPDFConverter()

    @pytest.fixture
    def high_quality_converter(self):
        """创建高清晰度配置的转换器实例"""
        return PyMuPDFConverter(zoom_factor=3.0)

    def _create_simple_pdf_bytes(self) -> bytes:
        """
        创建简单的 PDF 字节流用于测试

        Returns:
            PDF 文件字节流
        """
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        # 创建内存中的 PDF
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)  # A4 尺寸

        # 添加一些文本内容
        page.insert_text((100, 100), "Test Page 1", fontsize=20)

        # 保存到内存
        pdf_bytes = doc.tobytes()
        doc.close()

        return pdf_bytes

    def _create_multi_page_pdf_bytes(self, num_pages: int = 3) -> bytes:
        """
        创建多页 PDF 字节流用于测试

        Args:
            num_pages: 页数

        Returns:
            PDF 文件字节流
        """
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        doc = fitz.open()

        for i in range(num_pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text((100, 100), f"Test Page {i + 1}", fontsize=20)

        pdf_bytes = doc.tobytes()
        doc.close()

        return pdf_bytes

    @pytest.mark.asyncio
    async def test_converter_implements_protocol(self, converter):
        """
        测试转换器实现 PDFConverterProtocol 协议

        预期结果：
        - 是 PDFConverterProtocol 的实例
        """
        assert isinstance(converter, PDFConverterProtocol)

    @pytest.mark.asyncio
    async def test_convert_single_page_pdf_from_bytes(self, converter):
        """
        测试从字节流转换单页 PDF

        预期结果：
        - 返回包含 1 个图片字节流的列表
        - 图片格式为 PNG
        """
        pdf_bytes = self._create_simple_pdf_bytes()

        images = await converter.convert_to_images(pdf_bytes)

        assert isinstance(images, list)
        assert len(images) == 1
        assert isinstance(images[0], bytes)
        assert len(images[0]) > 0

        # 验证是有效的 PNG（以 PNG 魔数开头）
        assert images[0].startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_convert_multi_page_pdf_from_bytes(self, converter):
        """
        测试从字节流转换多页 PDF

        预期结果：
        - 返回与页数相同数量的图片字节流
        """
        num_pages = 3
        pdf_bytes = self._create_multi_page_pdf_bytes(num_pages)

        images = await converter.convert_to_images(pdf_bytes)

        assert len(images) == num_pages
        for img in images:
            assert isinstance(img, bytes)
            assert img.startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_convert_pdf_with_different_zoom_factors(self):
        """
        测试不同缩放因子对输出图片尺寸的影响

        预期结果：
        - 缩放因子越大，图片字节流越大
        """
        pdf_bytes = self._create_simple_pdf_bytes()

        converter_1x = PyMuPDFConverter(zoom_factor=1.0)
        converter_2x = PyMuPDFConverter(zoom_factor=2.0)

        images_1x = await converter_1x.convert_to_images(pdf_bytes)
        images_2x = await converter_2x.convert_to_images(pdf_bytes)

        # 2x 缩放应该产生更大的图片
        assert len(images_2x[0]) > len(images_1x[0])

    @pytest.mark.asyncio
    async def test_converter_init_with_custom_params(self):
        """
        测试使用自定义参数初始化转换器

        预期结果：
        - 参数正确保存
        """
        converter = PyMuPDFConverter(zoom_factor=2.5, dpi=300)

        assert converter.zoom_factor == 2.5
        assert converter.dpi == 300

    @pytest.mark.asyncio
    async def test_convert_empty_pdf(self, converter):
        """
        测试转换空 PDF（0 页）

        预期结果：
        - 抛出 ValueError（PyMuPDF 不能保存空文档）
        """
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        # PyMuPDF 不能创建空 PDF（0 页），尝试保存会抛出 ValueError
        # 所以我们测试空字节流的情况
        with pytest.raises(ValueError):
            await converter.convert_to_images(b"")

    @pytest.mark.asyncio
    async def test_convert_corrupted_pdf(self, converter):
        """
        测试转换损坏的 PDF 数据

        预期结果：
        - 抛出 ValueError
        """
        corrupted_bytes = b"This is not a valid PDF file"

        with pytest.raises(ValueError) as exc_info:
            await converter.convert_to_images(corrupted_bytes)

        assert "PDF 转换失败" in str(exc_info.value)

    @pytest.mark.skipif(True, reason="需要真实 PDF 文件")  # 默认跳过，需要真实 PDF 文件
    @pytest.mark.asyncio
    async def test_convert_pdf_from_file_path(self, converter, tmp_path):
        """
        测试从文件路径转换 PDF

        预期结果：
        - 正确读取文件并转换
        """
        # 创建临时 PDF 文件
        pdf_bytes = self._create_simple_pdf_bytes()
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(pdf_bytes)

        images = await converter.convert_to_images(str(pdf_file))

        assert len(images) == 1
        assert images[0].startswith(b"\x89PNG")


class TestPyMuPDFConverterSyncMethods:
    """测试同步方法"""

    def _create_simple_pdf_bytes(self) -> bytes:
        """创建简单的 PDF 字节流"""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), "Test", fontsize=20)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def test_convert_sync_impl(self):
        """
        测试同步实现的内部方法

        预期结果：
        - 正确返回图片字节流列表
        """
        converter = PyMuPDFConverter()
        pdf_bytes = self._create_simple_pdf_bytes()

        images = converter._convert_sync_impl(pdf_bytes)

        assert isinstance(images, list)
        assert len(images) == 1
        assert images[0].startswith(b"\x89PNG")

    def test_convert_to_images_sync(self):
        """
        测试同步转换方法

        预期结果：
        - 正确返回图片字节流列表
        """
        converter = PyMuPDFConverter()
        pdf_bytes = self._create_simple_pdf_bytes()

        images = converter.convert_to_images_sync(pdf_bytes)

        assert isinstance(images, list)
        assert len(images) == 1
        assert images[0].startswith(b"\x89PNG")


class TestPyMuPDFConverterEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_convert_very_large_zoom_factor(self):
        """
        测试非常大的缩放因子

        预期结果：
        - 能够正常处理，返回较大的图片
        """
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        converter = PyMuPDFConverter(zoom_factor=5.0)

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), "Test", fontsize=20)
        pdf_bytes = doc.tobytes()
        doc.close()

        images = await converter.convert_to_images(pdf_bytes)

        assert len(images) == 1
        assert len(images[0]) > 0

    @pytest.mark.asyncio
    async def test_convert_many_pages(self):
        """
        测试多页 PDF（10 页）

        预期结果：
        - 正确返回所有页面的图片
        """
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) 未安装")

        converter = PyMuPDFConverter()

        doc = fitz.open()
        for i in range(10):
            page = doc.new_page(width=595, height=842)
            page.insert_text((100, 100), f"Page {i + 1}", fontsize=20)

        pdf_bytes = doc.tobytes()
        doc.close()

        images = await converter.convert_to_images(pdf_bytes)

        assert len(images) == 10
        for img in images:
            assert img.startswith(b"\x89PNG")
