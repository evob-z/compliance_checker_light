"""
CLI 健康检查测试

测试 compliance-checker 命令行的 --version 和 --health-check 功能。
"""

import json
import subprocess
import sys

import pytest


def _run_cli(*args, timeout=15):
    """运行 compliance-checker CLI 命令"""
    cmd = [sys.executable, "-m", "compliance_checker.cli", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent),
    )


class TestVersion:
    def test_version_output(self):
        result = _run_cli("--version")
        assert result.returncode == 0
        version = result.stdout.strip()
        # 版本号格式：x.y.z
        assert len(version.split(".")) == 3, f"Version must be semver: {version}"

    def test_version_matches_module(self):
        from compliance_checker.cli import __version__

        result = _run_cli("--version")
        assert __version__ in result.stdout


class TestHealthCheck:
    def test_health_check_returns_json(self):
        result = _run_cli("--health-check")
        output = result.stdout.strip()
        health = json.loads(output)
        assert isinstance(health, dict)
        assert "status" in health
        assert "version" in health
        assert "checks" in health

    def test_health_check_has_api_key_checks(self):
        result = _run_cli("--health-check")
        health = json.loads(result.stdout)
        checks = health["checks"]
        assert "llm_api_key" in checks, "Health check must include 'llm_api_key'"
        assert "embed_api_key" in checks, "Health check must include 'embed_api_key'"
        assert "vision_api_key" in checks, "Health check must include 'vision_api_key'"

    def test_health_check_has_pymupdf_check(self):
        result = _run_cli("--health-check")
        health = json.loads(result.stdout)
        checks = health["checks"]
        assert "pymupdf" in checks, "Health check must include 'pymupdf'"

    def test_health_check_has_python_version(self):
        result = _run_cli("--health-check")
        health = json.loads(result.stdout)
        assert "python_version" in health, "Health check must include 'python_version'"
