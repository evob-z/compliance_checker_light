"""
OpenClaw 安装脚本

clawhub postinstall 自动执行，或用户手动运行：
    python scripts/setup_openclaw.py

支持 --dry-run 参数模拟安装流程。
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def check_python_version():
    """检查 Python 版本 >= 3.10"""
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info.micro}"

    if (major, minor) < (3, 10):
        print(f"[ERROR] Python >= 3.10 required, found {version_str}")
        return False

    print(f"[OK] Python {version_str}")
    return True


def install_package(dry_run=False):
    """安装 compliance-checker Python 包"""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # 检查是否有 pyproject.toml（从源码安装）
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        print("[ERROR] pyproject.toml not found. Cannot install package.")
        return False

    cmd = [sys.executable, "-m", "pip", "install", "-e", str(project_root)]

    if dry_run:
        print(f"[DRY-RUN] Would run: {' '.join(cmd)}")
        return True

    print("[INFO] Installing compliance-checker package...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] pip install failed:\n{result.stderr}")
        return False

    print("[OK] Package installed successfully")
    return True


def verify_command(dry_run=False):
    """验证 compliance-checker 命令是否可用"""
    if dry_run:
        print("[DRY-RUN] Would verify: compliance-checker --version")
        return True

    try:
        result = subprocess.run(
            ["compliance-checker", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"[OK] {result.stdout.strip()}")
            return True
        else:
            print(f"[ERROR] compliance-checker --version failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("[ERROR] compliance-checker command not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        print("[ERROR] compliance-checker --version timed out")
        return False


def setup_config_dir(dry_run=False):
    """创建用户配置目录 ~/.compliance-checker/"""
    config_dir = Path.home() / ".compliance-checker"

    if config_dir.exists():
        print(f"[OK] Config directory exists: {config_dir}")
        return True

    if dry_run:
        print(f"[DRY-RUN] Would create: {config_dir}")
        return True

    config_dir.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Created config directory: {config_dir}")

    # 创建 .env 模板
    env_template = config_dir / ".env"
    if not env_template.exists():
        env_template.write_text(
            "# Compliance Checker Configuration\n"
            "# Uncomment and fill in the values below:\n"
            "\n"
            "# Required: LLM API Key\n"
            "# LLM_API_KEY=your-api-key\n"
            "\n"
            "# Required: LLM API Base URL\n"
            "# LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            "\n"
            "# Required: LLM Model Name\n"
            "# LLM_MODEL=qwen-max\n"
            "\n"
            "# Optional: Embedding Model\n"
            "# EMBED_MODEL=text-embedding-v1\n"
            "\n"
            "# Optional: Vision Model\n"
            "# VISION_MODEL=qwen3-vl-flash\n",
            encoding="utf-8",
        )
        print(f"[OK] Created .env template: {env_template}")

    return True


def check_env_vars():
    """检查必需的环境变量"""
    required = ["LLM_API_KEY"]
    missing = [var for var in required if not os.environ.get(var)]

    if missing:
        print(f"[WARN] Missing required environment variables: {', '.join(missing)}")
        print(
            f"       Please configure them in system environment or "
            f"~/.compliance-checker/.env"
        )
        return False

    print("[OK] Required environment variables are set")
    return True


def run_health_check(dry_run=False):
    """运行 compliance-checker --health-check"""
    if dry_run:
        print("[DRY-RUN] Would run: compliance-checker --health-check")
        return True

    try:
        result = subprocess.run(
            ["compliance-checker", "--health-check"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        health = json.loads(result.stdout)
        status = health.get("status", "unknown")

        if status == "ok":
            print("[OK] Health check passed")
        else:
            print(f"[WARN] Health check status: {status}")
            # Print failed checks
            for check_name, check_info in health.get("checks", {}).items():
                if not check_info.get("ok", False):
                    error = check_info.get("error", "failed")
                    required = check_info.get("required", True)
                    level = "ERROR" if required else "WARN"
                    print(f"  [{level}] {check_name}: {error}")

        return status == "ok"
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"[WARN] Health check skipped: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN MODE ===\n")

    print("=" * 50)
    print("Compliance Checker - OpenClaw Setup")
    print("=" * 50)
    print()

    steps = [
        ("Checking Python version", check_python_version),
        ("Installing package", lambda: install_package(dry_run)),
        ("Verifying command", lambda: verify_command(dry_run)),
        ("Setting up config directory", lambda: setup_config_dir(dry_run)),
        ("Checking environment variables", check_env_vars),
        ("Running health check", lambda: run_health_check(dry_run)),
    ]

    results = []
    for step_name, step_func in steps:
        print(f"\n--- {step_name} ---")
        results.append(step_func())

    print("\n" + "=" * 50)
    if all(results):
        print("Setup completed successfully!")
    else:
        print("Setup completed with warnings.")
        print(
            "Please check the output above and configure any missing items."
        )
    print("=" * 50)


if __name__ == "__main__":
    main()
