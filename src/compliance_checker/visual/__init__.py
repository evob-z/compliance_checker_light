"""Visual inspection module - 视觉检测模块"""

from .qwen_client import QwenVLClient
from .region_detector import RegionDetector, TextRegion, PDFRegionDetector, PaddleOCRRegionDetector
from .screenshot import (
    capture_page, 
    capture_full_page_base64, 
    capture_region_base64,
    get_page_size, 
    get_page_count
)

__all__ = [
    "QwenVLClient",
    "RegionDetector",
    "TextRegion",
    "PDFRegionDetector",
    "PaddleOCRRegionDetector",
    "capture_page",
    "capture_full_page_base64",
    "capture_region_base64",
    "get_page_size",
    "get_page_count",
]
