"""
OCR 引擎单元测试（阿里云 RecognizeGeneral Data 解析等）
"""

import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.compliance_checker.infrastructure.llm.ocr_engine import (
    AliyunOCREngine,
    _parse_recognize_general_data,
)


class TestParseRecognizeGeneralData:
    """_parse_recognize_general_data 与阿里云 Data JSON 约定"""

    def test_empty_and_whitespace(self):
        assert _parse_recognize_general_data(None) == ""
        assert _parse_recognize_general_data("") == ""
        assert _parse_recognize_general_data("   ") == ""

    def test_invalid_json(self):
        assert _parse_recognize_general_data("not-json") == ""

    def test_content_priority(self):
        payload = {
            "content": "  整段摘要  ",
            "prism_wordsInfo": [{"word": "块"}],
        }
        assert _parse_recognize_general_data(json.dumps(payload)) == "整段摘要"

    def test_prism_words_info_lines(self):
        payload = {
            "prism_wordsInfo": [
                {"word": "第一行"},
                {"word": "第二行"},
            ]
        }
        assert _parse_recognize_general_data(json.dumps(payload)) == "第一行\n第二行"

    def test_prism_words_info_snake_case_fallback(self):
        payload = {
            "prism_words_info": [{"word": "A"}, {"word": "B"}],
        }
        assert _parse_recognize_general_data(json.dumps(payload)) == "A\nB"

    def test_skips_non_dict_items_in_words_info(self):
        payload = {
            "prism_wordsInfo": [
                "bad",
                {"word": "ok"},
                {},
                {"word": ""},
            ]
        }
        assert _parse_recognize_general_data(json.dumps(payload)) == "ok"

    def test_non_object_json(self):
        assert _parse_recognize_general_data(json.dumps([])) == ""


def _aliyun_ocr_sdk_installed() -> bool:
    return importlib.util.find_spec("alibabacloud_ocr_api20210707") is not None


@pytest.mark.skipif(
    not _aliyun_ocr_sdk_installed(),
    reason="未安装 alibabacloud_ocr_api20210707，跳过 recognize_image 集成式 mock",
)
class TestAliyunRecognizeImageMocked:
    """需要 SDK 已安装；通过 mock _get_client 避免真实 AK 与网络"""

    def test_recognize_image_uses_recognize_general_and_parse(self, tmp_path, monkeypatch):
        mock_client = MagicMock()
        mock_client.recognize_general.return_value = SimpleNamespace(
            body=SimpleNamespace(
                data=json.dumps({"content": "识别结果"}),
                code=None,
                message=None,
            )
        )

        def fake_get_client(self):
            if self._client is None:
                self._client = mock_client
            return self._client

        monkeypatch.setattr(AliyunOCREngine, "_get_client", fake_get_client)

        engine = AliyunOCREngine(access_key_id="test-id", access_key_secret="test-secret")
        img = tmp_path / "t.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        text = engine.recognize_image(str(img))
        assert text == "识别结果"
        mock_client.recognize_general.assert_called_once()
        call_req = mock_client.recognize_general.call_args[0][0]
        assert call_req.body is not None
