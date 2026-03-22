"""
多路径 .env 加载测试

验证 _load_env() 的多路径搜索和优先级逻辑。
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestLoadEnvPaths:
    """测试 .env 文件搜索路径"""

    def test_load_env_function_exists(self):
        """_load_env 函数必须存在"""
        from compliance_checker.cli import _load_env

        assert callable(_load_env)

    @patch("compliance_checker.cli.load_dotenv")
    @patch("compliance_checker.cli.Path")
    def test_loads_home_env_if_exists(self, mock_path_class, mock_load_dotenv):
        """如果 ~/.compliance-checker/.env 存在，应该被加载"""
        from compliance_checker.cli import _load_env

        # 模拟 Path.home() / ".compliance-checker" / ".env" 存在
        mock_home = MagicMock()
        mock_env_path = MagicMock()
        mock_env_path.exists.return_value = True
        mock_home.__truediv__ = MagicMock(return_value=MagicMock())
        mock_home.__truediv__.return_value.__truediv__ = MagicMock(
            return_value=mock_env_path
        )
        mock_path_class.home.return_value = mock_home

        _load_env()

        # 应该被调用至少两次（home env + cwd env）
        assert mock_load_dotenv.call_count >= 2
        # 所有调用都应该使用 override=False
        for call in mock_load_dotenv.call_args_list:
            assert call.kwargs.get("override", None) is False or (
                len(call.args) == 0 and call.kwargs.get("override") is False
            )

    @patch("compliance_checker.cli.load_dotenv")
    @patch("compliance_checker.cli.Path")
    def test_skips_home_env_if_not_exists(self, mock_path_class, mock_load_dotenv):
        """如果 ~/.compliance-checker/.env 不存在，应该跳过"""
        from compliance_checker.cli import _load_env

        mock_home = MagicMock()
        mock_env_path = MagicMock()
        mock_env_path.exists.return_value = False
        mock_home.__truediv__ = MagicMock(return_value=MagicMock())
        mock_home.__truediv__.return_value.__truediv__ = MagicMock(
            return_value=mock_env_path
        )
        mock_path_class.home.return_value = mock_home

        _load_env()

        # 只应调用一次（cwd env）
        assert mock_load_dotenv.call_count == 1

    def test_system_env_not_overridden(self, tmp_path, monkeypatch):
        """系统环境变量不应被 .env 文件覆盖"""
        # 设置一个系统环境变量
        monkeypatch.setenv("TEST_COMPLIANCE_VAR", "system_value")

        # 创建一个 .env 文件试图覆盖它
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_COMPLIANCE_VAR=file_value\n")

        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

        # 系统环境变量应该保持不变
        assert os.environ["TEST_COMPLIANCE_VAR"] == "system_value"

        # 清理
        monkeypatch.delenv("TEST_COMPLIANCE_VAR")
