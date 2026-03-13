"""
visual.py - 视觉检查工具
实现 visual_inspection MCP 工具
用于检测文档中的印章、签名等视觉元素
"""

import os
import logging
from typing import Dict, Optional, Any

from ..visual import QwenVLClient, PDFRegionDetector, capture_page
from ..core.result_model import CheckStatus

logger = logging.getLogger(__name__)


# Qwen-VL 提示词模板 - 优化版
SEAL_DETECTION_PROMPT = """请仔细检查这张图片，判断是否存在公章（红色圆形印章）。

请按以下格式回答：
1. 是否存在公章：[是/否]
2. 置信度：[0-1之间的数值]
3. 说明：[简要说明判断依据]

注意：
- 公章通常是红色的圆形印章
- 注意区分公章和签名、手写文字
- 如果图片质量较差，请说明"无法辨认"
"""

SIGNATURE_DETECTION_PROMPT = """请仔细检查这张图片，判断是否存在手写签名。

请按以下格式回答：
1. 是否存在手写签名：[是/否]
2. 置信度：[0-1之间的数值]
3. 说明：[简要说明判断依据]

注意：
- 手写签名通常是个性化的笔迹
- 注意区分手写签名和打印文字
- 如果图片质量较差，请说明"无法辨认"
"""

BOTH_DETECTION_PROMPT = """请仔细检查这张图片，判断是否存在公章和手写签名。

请按以下格式回答：

【公章检查】
1. 是否存在公章：[是/否]
2. 置信度：[0-1]

【签名检查】
1. 是否存在手写签名：[是/否]
2. 置信度：[0-1]

【说明】
简要说明判断依据
"""


class VisualInspector:
    """视觉检查器 - 两阶段检测：OCR 定位 → 视觉确认"""

    def __init__(self):
        self.qwen_client = QwenVLClient()
        self.region_detector = PDFRegionDetector()

    async def inspect(
        self,
        document_path: str,
        check_type: str = "both",
        search_context: Optional[str] = None,
        page_hint: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        执行视觉检查

        两阶段检测流程：
        1. OCR 定位：如提供 search_context，先用 OCR 定位大概区域
        2. 视觉确认：截取相关区域图片，调用 Qwen-VL 判断印章/签名是否存在

        Args:
            document_path: 文档路径
            check_type: 检查类型 ("seal" | "signature" | "both")
            search_context: OCR 定位的上下文文字（如"公章"、"法定代表人"）
            page_hint: 建议查找的页码（从0开始）

        Returns:
            {
                "document_path": str,
                "check_type": str,
                "found": bool,
                "confidence": float,
                "location": {"page": int, "bbox": [...], "description": str},
                "screenshot_path": str,
                "reasoning": str
            }
        """
        # 检查 Qwen-VL 是否可用
        if not self.qwen_client.is_available():
            return {
                "document_path": document_path,
                "check_type": check_type,
                "found": False,
                "confidence": 0.0,
                "error": "Qwen-VL API 未配置",
                "message": "请设置 QWEN_API_KEY 环境变量以启用视觉检查",
            }

        # 阶段1: OCR 定位区域
        page_num = page_hint or 0
        bbox = None
        location_info = None

        if search_context and self.region_detector.is_available():
            location_info = self.region_detector.locate_by_text(
                document_path, search_context, page_hint=page_hint, margin=100
            )
            if location_info:
                page_num = location_info["page"]
                bbox = location_info["bbox"]
                logger.info(f"通过 OCR 定位到区域: 第{page_num+1}页, bbox={bbox}")

        # 阶段2: 截图并视觉确认
        try:
            # 截取图片（整页或指定区域）
            image_path = capture_page(document_path, page_num, dpi=150, bbox=bbox)

            # 选择提示词
            if check_type == "seal":
                prompt = SEAL_DETECTION_PROMPT
            elif check_type == "signature":
                prompt = SIGNATURE_DETECTION_PROMPT
            else:
                prompt = BOTH_DETECTION_PROMPT

            # 调用 Qwen-VL 进行视觉确认
            response = await self.qwen_client.chat(image_path, prompt)

            if not response.get("success"):
                return {
                    "document_path": document_path,
                    "check_type": check_type,
                    "found": False,
                    "confidence": 0.0,
                    "error": response.get("error", "API 调用失败"),
                    "location": {"page": page_num, "bbox": bbox},
                    "screenshot_path": image_path,
                }

            # 返回结果
            return {
                "document_path": document_path,
                "check_type": check_type,
                "found": response.get("found", False),
                "confidence": response.get("confidence", 0.0),
                "location": {
                    "page": page_num,
                    "bbox": bbox,
                    "description": location_info.get("text", "") if location_info else "整页检查",
                },
                "screenshot_path": image_path,
                "reasoning": response.get("reasoning", ""),
            }

        except Exception as e:
            logger.error(f"视觉检查失败: {e}")
            return {
                "document_path": document_path,
                "check_type": check_type,
                "found": False,
                "confidence": 0.0,
                "error": str(e),
                "location": {"page": page_num, "bbox": bbox},
            }


async def visual_inspection(
    document_path: str,
    check_type: str = "both",
    search_context: Optional[str] = None,
    page_hint: Optional[int] = None,
) -> Dict[str, Any]:
    """
    视觉检查工具（MCP工具入口）

    使用视觉模型（Qwen-VL）检查文档中的印章/签名。

    实现逻辑：
    1. 如提供 search_context，先用 OCR 定位大概区域
    2. 截取相关区域图片
    3. 调用 Qwen-VL 判断印章/签名是否存在

    Args:
        document_path: 文档路径（PDF 文件）
        check_type: 检查类型 ("seal" | "signature" | "both")
            - seal: 仅检查公章
            - signature: 仅检查签名
            - both: 同时检查公章和签名（默认）
        search_context: OCR 定位的上下文文字（如"公章"、"法定代表人"）
            提供此参数可提高检测精度和速度
        page_hint: 建议查找的页码（从0开始），默认从第0页开始搜索

    Returns:
        {
            "document_path": "/data/立项批复.pdf",
            "check_type": "seal",
            "found": true,
            "confidence": 0.95,
            "location": {
                "page": 3,
                "bbox": [100, 200, 300, 400],
                "description": "公章区域"
            },
            "screenshot_path": "/tmp/compliance_page3.png",
            "reasoning": "在页面右下角发现红色圆形印章，文字清晰可辨"
        }
    """
    inspector = VisualInspector()
    return await inspector.inspect(
        document_path=document_path,
        check_type=check_type,
        search_context=search_context,
        page_hint=page_hint,
    )
