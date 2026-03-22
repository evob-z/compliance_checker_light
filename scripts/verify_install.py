"""
安装验证脚本

验证 compliance-checker 是否正确安装并可用。
用法：
    python scripts/verify_install.py
"""

import shutil
import subprocess
import sys


def check_python_version():
    """检查 Python 版本 >= 3.10"""
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info.micro}"

    if (major, minor) < (3, 10):
        print(f"[FAIL] Python >= 3.10 required, found {version_str}")
        return False

    print(f"[OK] Python {version_str}")
    return True


def check_command_available():
    """检查 compliance-checker 命令是否在 PATH 中"""
    path = shutil.which("compliance-checker")
    if path:
        print(f"[OK] compliance-checker found: {path}")
        return True

    print("[FAIL] compliance-checker command not found in PATH")
    print("       Install with: pip install -e .")
    return False


def check_version_output():
    """运行 compliance-checker --version 并验证输出"""
    try:
        result = subprocess.run(
            ["compliance-checker", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"[FAIL] compliance-checker --version exited with code {result.returncode}")
            if result.stderr:
                print(f"       stderr: {result.stderr.strip()}")
            return False

        output = result.stdout.strip()
        parts = output.split()
        if len(parts) != 2 or parts[0] != "compliance-checker":
            print(f"[FAIL] Unexpected version output: {output}")
            return False

        version = parts[1]
        if len(version.split(".")) != 3:
            print(f"[FAIL] Invalid version format: {version}")
            return False

        print(f"[OK] {output}")
        return True
    except FileNotFoundError:
        print("[FAIL] compliance-checker command not found")
        return False
    except subprocess.TimeoutExpired:
        print("[FAIL] compliance-checker --version timed out")
        return False


def check_module_import():
    """验证 Python 模块可以正常导入"""
    try:
        from compliance_checker.interface import mcp_server  # noqa: F401

        print("[OK] compliance_checker module importable")
        return True
    except ImportError as e:
        print(f"[FAIL] Cannot import compliance_checker: {e}")
        return False


def main():
    print("=" * 50)
    print("Compliance Checker - Installation Verification")
    print("=" * 50)
    print()

    checks = [
        ("Python version", check_python_version),
        ("Module import", check_module_import),
        ("Command available", check_command_available),
        ("Version output", check_version_output),
    ]

    results = []
    for name, check_fn in checks:
        print(f"--- {name} ---")
        results.append(check_fn())
        print()

    print("=" * 50)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"All {total} checks passed. Installation is ready.")
        return 0
    else:
        print(f"{passed}/{total} checks passed.")
        print("Fix the issues above, then re-run this script.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
