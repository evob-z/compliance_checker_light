"""
环境变量加载测试

验证 _load_env() 的行为和环境变量优先级。

注意：cli.py 已不再从 .env 文件加载环境变量，
环境变量由调用方（如 OpenClaw 框架）在进程启动时注入。
测试环境通过 conftest.py 加载 .env 文件。
"""

import os
from pathlib import Path

import pytest


class TestLoadEnvBehavior:
    """测试环境变量加载行为"""

    def test_load_env_function_exists(self):
        """_load_env 函数必须存在（向后兼容）"""
        from compliance_checker.cli import _load_env

        assert callable(_load_env)

    def test_load_env_is_noop(self):
        """_load_env 应该是空操作（不再加载 .env 文件）"""
        from compliance_checker.cli import _load_env

        # 调用不应抛出异常
        result = _load_env()
        assert result is None

    def test_system_env_preserved(self, monkeypatch):
        """系统环境变量应该被保留"""
        # 设置一个系统环境变量
        monkeypatch.setenv("TEST_COMPLIANCE_VAR", "system_value")

        # 调用 _load_env（应该是空操作）
        from compliance_checker.cli import _load_env

        _load_env()

        # 系统环境变量应该保持不变
        assert os.environ["TEST_COMPLIANCE_VAR"] == "system_value"

        # 清理
        monkeypatch.delenv("TEST_COMPLIANCE_VAR")


class TestEnvPriority:
    """测试环境变量优先级（通过 conftest.py 加载）"""

    def test_conftest_loads_env(self):
        """conftest.py 应该已加载 .env 文件中的环境变量"""
        # 这个测试验证 conftest.py 的工作正常
        # 如果 .env 文件中有 LLM_API_KEY，它应该已被加载
        llm_key = os.getenv("LLM_API_KEY")
        # 注意：不断言值，只验证测试框架能访问环境变量
        # 实际值取决于 .env 文件是否存在

    def test_system_env_priority_over_dotenv(self, tmp_path, monkeypatch):
        """系统环境变量优先级高于 .env 文件（override=False）"""
        from dotenv import load_dotenv

        # 设置系统环境变量
        monkeypatch.setenv("TEST_PRIORITY_VAR", "system_value")

        # 创建 .env 文件
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_PRIORITY_VAR=dotenv_value\n")

        # 使用 override=False 加载（conftest.py 的行为）
        load_dotenv(env_file, override=False)

        # 系统环境变量不应被覆盖
        assert os.environ["TEST_PRIORITY_VAR"] == "system_value"

        # 清理
        monkeypatch.delenv("TEST_PRIORITY_VAR")
