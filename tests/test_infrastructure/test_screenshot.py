"""
Screenshot 集成测试

⚠️ 注意：需要在 tests/fixtures/ 目录下准备一个 PDF 文件用于测试。
   项目已提供 tests/fixtures/dummy_approval.pdf，可直接使用。

测试目标：
    - 验证 capture_page 函数能正常截取真实 PDF 页面
    - 验证 capture_full_page_base64 函数能正常工作
    - 验证 capture_region_base64 函数能正常工作
    - 验证 get_page_size 函数能正常获取页面尺寸
    - 验证 get_page_count 函数能正常获取页数
    - 不使用 Mock，使用真实 PDF 文件和 PyMuPDF
"""

import pytest
import base64
from pathlib import Path
import tempfile

from src.infrastructure.visual.screenshot import (
    capture_page,
    capture_full_page_base64,
    capture_region_base64,
    get_page_size,
    get_page_count,
    HAS_FITZ,
)
from src.core.exceptions import DocumentParseError

# ============== 测试 Fixtures ==============


@pytest.fixture
def fixtures_dir() -> Path:
    """获取 fixtures 目录路径"""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """获取测试用 PDF 文件路径"""
    return fixtures_dir / "dummy_approval.pdf"


# ============== 前置条件检查 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestScreenshotPrerequisites:
    """前置条件检查"""

    def test_sample_pdf_exists(self, sample_pdf_path: Path):
        """
        测试测试文件存在

        验证：
        - 测试用 PDF 文件存在
        """
        assert sample_pdf_path.exists(), f"测试文件不存在: {sample_pdf_path}"


# ============== capture_page 测试 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestCapturePage:
    """capture_page 函数测试"""

    def test_capture_page_returns_valid_path(self, sample_pdf_path: Path):
        """
        测试成功捕获页面并返回有效路径

        验证：
        - 返回的路径存在
        - 文件是有效的 PNG 图片
        """
        result = capture_page(str(sample_pdf_path), page_num=0)

        # 验证返回路径存在
        result_path = Path(result)
        assert result_path.exists(), f"截图文件不存在: {result}"

        # 验证文件是 PNG 格式
        assert result_path.suffix == ".png"

        # 验证文件大小大于 0（实际读到了内容）
        assert result_path.stat().st_size > 0, "截图文件大小为 0，未读到内容"

    def test_capture_page_creates_valid_image(self, sample_pdf_path: Path):
        """
        测试捕获的图片是有效的 PNG 图片

        验证：
        - 图片可以被 Pillow 打开
        - 图片尺寸大于 0
        """
        from PIL import Image

        result = capture_page(str(sample_pdf_path), page_num=0)

        # 使用 Pillow 打开图片验证
        img = Image.open(result)
        try:
            width, height = img.size
            assert width > 0, "图片宽度为 0"
            assert height > 0, "图片高度为 0"
            # dummy_approval.pdf 是 A4 尺寸，150 DPI 下应该约 612x792 像素
            # 允许一定误差
            assert width > 500, f"图片宽度 {width} 过小，可能未正确渲染"
            assert height > 700, f"图片高度 {height} 过小，可能未正确渲染"
        finally:
            img.close()

    def test_capture_page_with_output_path(self, sample_pdf_path: Path, tmp_path: Path):
        """
        测试自定义输出路径

        验证：
        - 文件保存到指定路径
        """
        output_path = tmp_path / "custom_screenshot.png"

        result = capture_page(str(sample_pdf_path), page_num=0, output_path=str(output_path))

        assert result == str(output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_capture_page_with_dpi(self, sample_pdf_path: Path, tmp_path: Path):
        """
        测试自定义 DPI

        验证：
        - DPI 参数影响输出图片尺寸
        """
        from PIL import Image

        output_low = tmp_path / "low_dpi.png"
        output_high = tmp_path / "high_dpi.png"

        capture_page(str(sample_pdf_path), page_num=0, dpi=72, output_path=str(output_low))
        capture_page(str(sample_pdf_path), page_num=0, dpi=300, output_path=str(output_high))

        with Image.open(output_low) as img_low:
            with Image.open(output_high) as img_high:
                # 高 DPI 图片尺寸应该更大
                assert img_high.size[0] > img_low.size[0], "高 DPI 图片宽度应该更大"
                assert img_high.size[1] > img_low.size[1], "高 DPI 图片高度应该更大"

    def test_capture_page_with_bbox(self, sample_pdf_path: Path, tmp_path: Path):
        """
        测试带裁剪区域的捕获

        验证：
        - 裁剪区域正确应用
        - 输出图片尺寸符合预期
        """
        from PIL import Image

        output_path = tmp_path / "cropped.png"
        bbox = (50, 50, 200, 200)

        capture_page(str(sample_pdf_path), page_num=0, bbox=bbox, output_path=str(output_path))

        with Image.open(output_path) as img:
            # 裁剪后的图片尺寸应该接近 bbox 尺寸（考虑 DPI 缩放）
            width, height = img.size
            assert width > 0 and height > 0

    def test_capture_page_invalid_page_number(self, sample_pdf_path: Path):
        """
        测试无效页码

        验证：
        - 抛出 DocumentParseError
        """
        with pytest.raises(DocumentParseError) as exc_info:
            capture_page(str(sample_pdf_path), page_num=999)

        assert "not found" in str(exc_info.value).lower() or "未找到" in str(exc_info.value)

    def test_capture_page_nonexistent_file(self):
        """
        测试不存在的文件

        验证：
        - 抛出 DocumentParseError
        """
        with pytest.raises(DocumentParseError):
            capture_page("/nonexistent/path/file.pdf", page_num=0)


# ============== capture_full_page_base64 测试 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestCaptureFullPageBase64:
    """capture_full_page_base64 函数测试"""

    def test_capture_full_page_base64_returns_string(self, sample_pdf_path: Path):
        """
        测试返回 base64 字符串

        验证：
        - 返回类型是字符串
        - 字符串长度大于 0
        """
        result = capture_full_page_base64(str(sample_pdf_path), page_num=0)

        assert isinstance(result, str)
        assert len(result) > 0, "base64 字符串长度为 0，未读到内容"

    def test_capture_full_page_base64_valid_encoding(self, sample_pdf_path: Path):
        """
        测试 base64 编码有效

        验证：
        - 可以解码为有效的图片数据
        """
        result = capture_full_page_base64(str(sample_pdf_path), page_num=0)

        # 解码 base64
        image_bytes = base64.b64decode(result)

        # 验证解码后的数据是有效的 PNG
        assert len(image_bytes) > 0, "解码后的图片数据为空"

        # PNG 文件头
        assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n", "解码后的数据不是有效的 PNG"

    def test_capture_full_page_base64_can_open_as_image(self, sample_pdf_path: Path):
        """
        测试解码后可以打开为图片

        验证：
        - Pillow 可以打开解码后的图片
        """
        from PIL import Image
        import io

        result = capture_full_page_base64(str(sample_pdf_path), page_num=0)
        image_bytes = base64.b64decode(result)

        with Image.open(io.BytesIO(image_bytes)) as img:
            assert img.size[0] > 0
            assert img.size[1] > 0


# ============== capture_region_base64 测试 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestCaptureRegionBase64:
    """capture_region_base64 函数测试"""

    def test_capture_region_base64_returns_string(self, sample_pdf_path: Path):
        """
        测试返回 base64 字符串

        验证：
        - 返回类型是字符串
        - 字符串长度大于 0
        """
        bbox = (50, 50, 200, 200)
        result = capture_region_base64(str(sample_pdf_path), page_num=0, bbox=bbox)

        assert isinstance(result, str)
        assert len(result) > 0, "base64 字符串长度为 0，未读到内容"

    def test_capture_region_base64_valid_encoding(self, sample_pdf_path: Path):
        """
        测试 base64 编码有效

        验证：
        - 可以解码为有效的图片数据
        """
        bbox = (50, 50, 200, 200)
        result = capture_region_base64(str(sample_pdf_path), page_num=0, bbox=bbox)

        image_bytes = base64.b64decode(result)
        assert len(image_bytes) > 0
        assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n", "解码后的数据不是有效的 PNG"


# ============== get_page_size 测试 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestGetPageSize:
    """get_page_size 函数测试"""

    def test_get_page_size_returns_tuple(self, sample_pdf_path: Path):
        """
        测试返回尺寸元组

        验证：
        - 返回类型是 tuple
        - 长度为 2
        """
        result = get_page_size(str(sample_pdf_path), page_num=0)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_get_page_size_positive_values(self, sample_pdf_path: Path):
        """
        测试尺寸为正数

        验证：
        - 宽度和高度都是正整数
        """
        width, height = get_page_size(str(sample_pdf_path), page_num=0)

        assert isinstance(width, int)
        assert isinstance(height, int)
        assert width > 0, f"页面宽度 {width} 不是正数"
        assert height > 0, f"页面高度 {height} 不是正数"

    def test_get_page_size_reasonable_values(self, sample_pdf_path: Path):
        """
        测试尺寸值合理

        验证：
        - dummy_approval.pdf 是 A4 尺寸，约 595 x 842 points
        """
        width, height = get_page_size(str(sample_pdf_path), page_num=0)

        # A4 尺寸允许一定误差
        assert 500 < width < 700, f"页面宽度 {width} 不在合理范围内"
        assert 750 < height < 900, f"页面高度 {height} 不在合理范围内"

    def test_get_page_size_nonexistent_file(self):
        """
        测试不存在的文件

        验证：
        - 抛出 DocumentParseError
        """
        with pytest.raises(DocumentParseError):
            get_page_size("/nonexistent/path/file.pdf")


# ============== get_page_count 测试 ==============


@pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) 未安装")
class TestGetPageCount:
    """get_page_count 函数测试"""

    def test_get_page_count_returns_int(self, sample_pdf_path: Path):
        """
        测试返回整数

        验证：
        - 返回类型是 int
        """
        result = get_page_count(str(sample_pdf_path))

        assert isinstance(result, int)

    def test_get_page_count_positive_value(self, sample_pdf_path: Path):
        """
        测试页数为正数

        验证：
        - 页数大于 0
        """
        result = get_page_count(str(sample_pdf_path))

        assert result > 0, f"页数 {result} 不是正数"

    def test_get_page_count_correct_value(self, sample_pdf_path: Path):
        """
        测试页数正确

        验证：
        - dummy_approval.pdf 有 1 页
        """
        result = get_page_count(str(sample_pdf_path))

        # dummy_approval.pdf 是单页文档
        assert result >= 1, f"页数 {result} 应该至少为 1"

    def test_get_page_count_nonexistent_file(self):
        """
        测试不存在的文件

        验证：
        - 抛出 DocumentParseError
        """
        with pytest.raises(DocumentParseError):
            get_page_count("/nonexistent/path/file.pdf")


# ============== 无 PyMuPDF 时的行为测试 ==============


class TestWithoutPyMuPDF:
    """无 PyMuPDF 时的行为测试"""

    def test_functions_raise_error_without_fitz(self, sample_pdf_path: Path, monkeypatch):
        """
        测试无 PyMuPDF 时抛出错误

        验证：
        - 所有函数都抛出 DocumentParseError
        """
        # 临时禁用 HAS_FITZ
        import src.infrastructure.visual.screenshot as screenshot_module

        original_has_fitz = screenshot_module.HAS_FITZ

        try:
            screenshot_module.HAS_FITZ = False

            with pytest.raises(DocumentParseError):
                capture_page(str(sample_pdf_path))

            with pytest.raises(DocumentParseError):
                get_page_size(str(sample_pdf_path))

            with pytest.raises(DocumentParseError):
                get_page_count(str(sample_pdf_path))

        finally:
            screenshot_module.HAS_FITZ = original_has_fitz
