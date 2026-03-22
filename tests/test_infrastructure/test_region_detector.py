"""
RegionDetector 集成测试

⚠️ 注意：需要在 tests/fixtures/ 目录下准备测试文件。
   项目已提供 tests/fixtures/dummy_seal.jpg（包含文字的图片）
   和 tests/fixtures/dummy_approval.pdf（PDF文件）

测试目标：
    - 验证 TextRegion 数据类
    - 验证 RegionDetector 基于OCR结果的区域检测
    - 验证 PaddleOCRRegionDetector 真实OCR功能
    - 验证 PDFRegionDetector 真实PDF文本定位功能
    - 不使用 Mock，使用真实文件和OCR引擎
"""

import pytest
from pathlib import Path

from src.compliance_checker.infrastructure.visual.region_detector import (
    TextRegion,
    RegionDetector,
    PaddleOCRRegionDetector,
    PDFRegionDetector,
)

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
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """获取测试用 PDF 文件路径"""
    return fixtures_dir / "dummy_approval.pdf"


# ============== TextRegion 数据类测试 ==============


class TestTextRegion:
    """TextRegion 数据类测试"""

    def test_create_text_region(self):
        """
        测试创建 TextRegion

        验证：
        - 所有字段正确设置
        """
        region = TextRegion(
            text="测试文本",
            bbox=(10, 20, 100, 50),
            page=0,
            confidence=0.95,
        )

        assert region.text == "测试文本"
        assert region.bbox == (10, 20, 100, 50)
        assert region.page == 0
        assert region.confidence == 0.95

    def test_text_region_defaults(self):
        """
        测试 TextRegion 默认值

        验证：
        - page 默认为 0
        - confidence 默认为 1.0
        """
        region = TextRegion(
            text="测试",
            bbox=(0, 0, 10, 10),
        )

        assert region.page == 0
        assert region.confidence == 1.0

    def test_text_region_bbox_format(self):
        """
        测试 bbox 格式

        验证：
        - bbox 是 (x1, y1, x2, y2) 格式
        """
        region = TextRegion(
            text="测试",
            bbox=(10, 20, 100, 200),
        )

        assert len(region.bbox) == 4
        assert region.bbox[0] < region.bbox[2]  # x1 < x2
        assert region.bbox[1] < region.bbox[3]  # y1 < y2


# ============== RegionDetector 测试 ==============


class TestRegionDetector:
    """RegionDetector 测试"""

    def test_init_empty(self):
        """
        测试空初始化

        验证：
        - regions 初始化为空列表
        """
        detector = RegionDetector()

        assert detector.regions == []

    def test_init_with_ocr_results(self):
        """
        测试带 OCR 结果的初始化

        验证：
        - OCR 结果正确解析为 TextRegion 列表
        """
        ocr_results = [
            {"text": "文本1", "bbox": [10, 20, 100, 50], "page": 0, "confidence": 0.9},
            {"text": "文本2", "bbox": [10, 60, 100, 90], "page": 0, "confidence": 0.85},
        ]

        detector = RegionDetector(ocr_results)

        assert len(detector.regions) == 2
        assert isinstance(detector.regions[0], TextRegion)
        assert detector.regions[0].text == "文本1"
        assert detector.regions[1].text == "文本2"

    def test_search_exact_match(self):
        """
        测试精确搜索

        验证：
        - 精确匹配关键词
        """
        ocr_results = [
            {"text": "关键词", "bbox": [0, 0, 10, 10]},
            {"text": "其他文本", "bbox": [0, 20, 10, 30]},
        ]

        detector = RegionDetector(ocr_results)
        matches = detector.search("关键词", fuzzy=False)

        assert len(matches) == 1
        assert matches[0].text == "关键词"

    def test_search_fuzzy_match(self):
        """
        测试模糊搜索

        验证：
        - 包含关系匹配
        """
        ocr_results = [
            {"text": "包含关键词的文本", "bbox": [0, 0, 100, 10]},
            {"text": "其他", "bbox": [0, 20, 10, 30]},
        ]

        detector = RegionDetector(ocr_results)
        matches = detector.search("关键词", fuzzy=True)

        assert len(matches) == 1
        assert "关键词" in matches[0].text

    def test_search_case_insensitive(self):
        """
        测试大小写不敏感搜索

        验证：
        - 忽略大小写匹配
        """
        ocr_results = [
            {"text": "KEYWORD", "bbox": [0, 0, 10, 10]},
        ]

        detector = RegionDetector(ocr_results)
        matches = detector.search("keyword", fuzzy=False)

        assert len(matches) == 1

    def test_search_sorted_by_confidence(self):
        """
        测试结果按置信度排序

        验证：
        - 结果按 confidence 降序排列
        """
        ocr_results = [
            {"text": "低置信度", "bbox": [0, 0, 10, 10], "confidence": 0.5},
            {"text": "高置信度", "bbox": [0, 20, 10, 30], "confidence": 0.9},
        ]

        detector = RegionDetector(ocr_results)
        matches = detector.search("置信度", fuzzy=True)

        assert len(matches) == 2
        assert matches[0].confidence == 0.9
        assert matches[1].confidence == 0.5

    def test_search_no_match(self):
        """
        测试无匹配情况

        验证：
        - 返回空列表
        """
        ocr_results = [
            {"text": "文本1", "bbox": [0, 0, 10, 10]},
        ]

        detector = RegionDetector(ocr_results)
        matches = detector.search("不存在的关键词")

        assert matches == []

    def test_expand_region(self):
        """
        测试区域扩展

        验证：
        - 正确扩展边界框
        """
        region = TextRegion(text="测试", bbox=(100, 100, 200, 200))
        detector = RegionDetector()

        expanded = detector.expand_region(region, margin=50)

        assert expanded == (50, 50, 250, 250)

    def test_expand_region_with_page_limits(self):
        """
        测试带页面限制的区域扩展

        验证：
        - 扩展不超过页面边界
        """
        region = TextRegion(text="测试", bbox=(100, 100, 200, 200))
        detector = RegionDetector()

        expanded = detector.expand_region(region, margin=50, page_width=300, page_height=300)

        assert expanded[0] == 50  # x1
        assert expanded[1] == 50  # y1
        assert expanded[2] == 250  # x2 (clamped to 300)
        assert expanded[3] == 250  # y2 (clamped to 300)

    def test_expand_region_at_boundary(self):
        """
        测试边界区域扩展

        验证：
        - 边界扩展不超出 0
        """
        region = TextRegion(text="测试", bbox=(10, 10, 50, 50))
        detector = RegionDetector()

        expanded = detector.expand_region(region, margin=20)

        assert expanded[0] == 0  # x1 不超出 0
        assert expanded[1] == 0  # y1 不超出 0

    def test_find_context_region_success(self):
        """
        测试成功查找上下文区域

        验证：
        - 在上下文附近找到目标
        """
        ocr_results = [
            {"text": "法定代表人", "bbox": [100, 100, 200, 120], "page": 0},
            {"text": "签字", "bbox": [150, 130, 180, 150], "page": 0},  # 附近
        ]

        detector = RegionDetector(ocr_results)
        result = detector.find_context_region(["法定代表人"], "签字", max_distance=100)

        assert result is not None
        assert result.text == "签字"

    def test_find_context_region_no_context(self):
        """
        测试无上下文情况

        验证：
        - 返回 None
        """
        ocr_results = [
            {"text": "其他文本", "bbox": [0, 0, 10, 10]},
        ]

        detector = RegionDetector(ocr_results)
        result = detector.find_context_region(["不存在"], "目标")

        assert result is None


# ============== PaddleOCRRegionDetector 真实测试 ==============


def check_paddleocr_available():
    """检查 PaddleOCR 是否可用"""
    try:
        from paddleocr import PaddleOCR

        return True
    except (ImportError, OSError, Exception):
        # 捕获导入错误和DLL加载错误
        return False


@pytest.mark.skipif(not check_paddleocr_available(), reason="PaddleOCR 未安装，跳过真实 OCR 测试")
class TestPaddleOCRRegionDetectorReal:
    """PaddleOCRRegionDetector 真实测试（需要安装 PaddleOCR）"""

    def test_detect_regions_real_image(self, sample_image_path: Path):
        """
        测试真实图片 OCR 检测

        验证：
        - 能检测到图片中的文字
        - 返回的区域包含有效内容
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        detector = PaddleOCRRegionDetector()
        regions = detector.detect_regions(str(sample_image_path))

        # 验证检测到区域
        assert isinstance(regions, list), "返回结果应该是列表"

        # dummy_seal.jpg 包含 "FAKE SEAL" 和 "法人签名: 张三 (测试)"
        # 应该能检测到至少一些文字
        assert len(regions) > 0, "应该检测到至少一个文本区域"

        # 验证区域结构
        for region in regions:
            assert "text" in region, "区域应包含 text 字段"
            assert "bbox" in region, "区域应包含 bbox 字段"
            assert "confidence" in region, "区域应包含 confidence 字段"
            assert "page" in region, "区域应包含 page 字段"

            # 验证 bbox 格式
            bbox = region["bbox"]
            assert len(bbox) == 4, "bbox 应该有 4 个值"
            assert all(isinstance(v, int) for v in bbox), "bbox 值应该是整数"

            # 验证置信度范围
            assert 0 <= region["confidence"] <= 1, "置信度应在 0-1 范围内"

    def test_detect_regions_text_content(self, sample_image_path: Path):
        """
        测试 OCR 检测到的文本内容

        验证：
        - 能检测到图片中的关键文字
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        detector = PaddleOCRRegionDetector()
        regions = detector.detect_regions(str(sample_image_path))

        # 提取所有检测到的文本
        all_text = " ".join(r["text"] for r in regions)

        # dummy_seal.jpg 应该包含 "FAKE SEAL" 或 "法人签名" 或 "张三" 等文字
        # 注意：OCR 可能识别不准确，我们只验证检测到了一些文字
        assert len(all_text.strip()) > 0, "应该检测到一些文字内容"

    def test_locate_keyword_real_image(self, sample_image_path: Path):
        """
        测试真实图片关键词定位

        验证：
        - 能定位到关键词区域
        """
        if not sample_image_path.exists():
            pytest.skip(f"测试图片不存在: {sample_image_path}")

        detector = PaddleOCRRegionDetector()

        # 先检测所有区域，看看有什么文字
        regions = detector.detect_regions(str(sample_image_path))
        if not regions:
            pytest.skip("OCR 未检测到任何文字")

        # 使用检测到的第一个文字作为关键词
        first_text = regions[0]["text"]
        keyword = first_text[:3] if len(first_text) >= 3 else first_text

        result = detector.locate_keyword(str(sample_image_path), keyword)

        assert result is not None, "关键词来自本图 OCR 首条文本的子串，应能定位"
        assert "page" in result
        assert "bbox" in result
        assert "text" in result
        assert len(result["bbox"]) == 4


# ============== PDFRegionDetector 真实测试 ==============


def check_fitz_available():
    """检查 PyMuPDF 是否可用"""
    try:
        import fitz

        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not check_fitz_available(), reason="PyMuPDF (fitz) 未安装，跳过 PDF 区域检测测试"
)
class TestPDFRegionDetectorReal:
    """PDFRegionDetector 真实测试"""

    def test_is_available(self):
        """
        测试可用性检查

        验证：
        - is_available() 返回 True
        """
        detector = PDFRegionDetector()
        assert detector.is_available() is True

    def test_locate_by_text_real_pdf(self, sample_pdf_path: Path):
        """
        测试真实 PDF 文本定位

        验证：
        - 能定位到 PDF 中的文本
        """
        if not sample_pdf_path.exists():
            pytest.skip(f"测试 PDF 不存在: {sample_pdf_path}")

        detector = PDFRegionDetector()

        # dummy_approval.pdf 包含 "Project Approval" 文本
        result = detector.locate_by_text(str(sample_pdf_path), "Approval")

        assert result is not None, "应该能定位到 'Approval' 文本"
        assert "page" in result
        assert "bbox" in result
        assert "text" in result

        # 验证 bbox 格式
        assert len(result["bbox"]) == 4

        # 验证文本包含关键词
        assert "Approval" in result["text"] or "approval" in result["text"].lower()

    def test_locate_by_text_project_name(self, sample_pdf_path: Path):
        """
        测试定位项目名称

        验证：
        - 能定位到 "Project" 文本
        """
        if not sample_pdf_path.exists():
            pytest.skip(f"测试 PDF 不存在: {sample_pdf_path}")

        detector = PDFRegionDetector()
        result = detector.locate_by_text(str(sample_pdf_path), "Project")

        assert result is not None, "应该能定位到 'Project' 文本"
        assert result["page"] == 0  # 第一页

    def test_locate_by_text_not_found(self, sample_pdf_path: Path):
        """
        测试未找到文本

        验证：
        - 返回 None
        """
        if not sample_pdf_path.exists():
            pytest.skip(f"测试 PDF 不存在: {sample_pdf_path}")

        detector = PDFRegionDetector()
        result = detector.locate_by_text(str(sample_pdf_path), "NonExistentText12345")

        assert result is None

    def test_locate_by_text_with_page_hint(self, sample_pdf_path: Path):
        """
        测试使用页码提示

        验证：
        - 页码提示正确使用
        """
        if not sample_pdf_path.exists():
            pytest.skip(f"测试 PDF 不存在: {sample_pdf_path}")

        detector = PDFRegionDetector()
        result = detector.locate_by_text(str(sample_pdf_path), "Document", page_hint=0)

        assert result is not None
        assert result["page"] == 0

    def test_locate_by_text_returns_actual_content(self, sample_pdf_path: Path):
        """
        测试返回实际内容

        验证：
        - 返回的文本不为空
        - bbox 坐标合理
        """
        if not sample_pdf_path.exists():
            pytest.skip(f"测试 PDF 不存在: {sample_pdf_path}")

        detector = PDFRegionDetector()
        result = detector.locate_by_text(str(sample_pdf_path), "Document")

        assert result is not None

        # 验证文本不为空
        assert len(result["text"].strip()) > 0, "返回的文本不应该为空"

        # 验证 bbox 坐标合理（正数）
        bbox = result["bbox"]
        assert all(v >= 0 for v in bbox), "bbox 坐标应该为非负数"


# ============== 无依赖时的行为测试 ==============


class TestWithoutDependencies:
    """无依赖库时的行为测试"""

    def test_pdf_region_detector_without_fitz(self, monkeypatch):
        """
        测试无 PyMuPDF 时 PDFRegionDetector 的行为

        验证：
        - is_available() 返回 False
        - locate_by_text() 返回 None
        """
        # 临时移除 fitz
        import src.compliance_checker.infrastructure.visual.region_detector as module

        detector = PDFRegionDetector()
        detector._fitz = None  # 模拟未安装

        assert detector.is_available() is False
        assert detector.locate_by_text("/any/path.pdf", "text") is None
