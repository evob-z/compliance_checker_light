"""
手动验证阿里云 OCR（RecognizeGeneral）真实调用。

用法（项目根目录）:
  python scripts/test_aliyun_ocr_live.py

依赖: .env 中已配置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET，
      且已 pip install alibabacloud_ocr_api20210707 alibabacloud-tea-openapi
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _ensure_test_image(path: Path) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (480, 160), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((24, 56), "阿里云 OCR 真实调用测试 Hello OCR", fill=(0, 0, 0))
    img.save(path, format="PNG")


def main() -> int:
    if load_dotenv:
        load_dotenv(project_root / ".env", override=True)

    if not os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID") or not os.getenv(
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
    ):
        print("错误: 请先在 .env 中配置 ALIBABA_CLOUD_ACCESS_KEY_ID 与 ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        return 1

    img_path = project_root / "tests" / "fixtures" / "ocr_live_test.png"
    _ensure_test_image(img_path)
    print(f"测试图片: {img_path}")

    from compliance_checker.infrastructure.llm.ocr_engine import AliyunOCREngine

    engine = AliyunOCREngine()
    text = engine.recognize_image(str(img_path))
    print("--- 识别结果 ---")
    print(text if text else "(空)")
    if not text.strip():
        print(
            "\n排查: 若上方日志含 ocrServiceNotOpen / not activated the OCR service，"
            "请到阿里云控制台开通「文字识别 OCR」服务并确保账号有余额/按量计费权限后再试。"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
