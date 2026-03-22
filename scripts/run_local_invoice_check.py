"""
本地发票/目录合规检查示例（调用当前 CLI，无硬编码路径）。

用法（先 pip install -e ".[dev]" 或确保能 import compliance_checker）:
  设置环境变量后运行:
    LOCAL_INVOICE_DIR   项目/资料目录（默认: 当前工作目录）
    LOCAL_INVOICE_FILE  单个 PDF/图片路径（必填）
    LOCAL_REFERENCE_DATE  时效基准日 YYYY-MM-DD（可选，传给 timeliness）

  python scripts/run_local_invoice_check.py

或:
    python scripts/run_local_invoice_check.py "D:/path/to/invoice.pdf"

依赖 .env 中的 LLM / VISION 等密钥（与主项目一致）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "compliance_checker.cli", *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(_project_root() / ".env", override=False)

    invoice_file = os.environ.get("LOCAL_INVOICE_FILE") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not invoice_file:
        print(
            "请设置 LOCAL_INVOICE_FILE 或传入参数: 发票/扫描件路径",
            file=sys.stderr,
        )
        return 1

    path = Path(invoice_file).expanduser().resolve()
    if not path.is_file():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1

    doc_dir = os.environ.get("LOCAL_INVOICE_DIR")
    scan_dir = str(Path(doc_dir).expanduser().resolve()) if doc_dir else str(path.parent)

    ref = os.environ.get("LOCAL_REFERENCE_DATE", "2026-03-12")

    file_posix = path.as_posix()

    steps = [
        (
            "completeness",
            ["completeness", "--path", scan_dir, "--documents", "发票,invoice"],
        ),
        (
            "timeliness",
            ["timeliness", "--file", file_posix, "--reference-time", ref],
        ),
        (
            "visual",
            ["visual", "--file", file_posix, "--targets", "印章,签名"],
        ),
    ]

    print("=" * 60)
    print("本地 CLI 检查（completeness → timeliness → visual）")
    print("=" * 60)
    print(f"目录: {scan_dir}")
    print(f"文件: {file_posix}")
    print(f"基准日: {ref}")
    print()

    exit_code = 0
    for name, argv in steps:
        print("-" * 60)
        print(f"[{name}]")
        print("-" * 60)
        proc = _run_cli(argv)
        if proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
                print(json.dumps(data, ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print(proc.stdout)
        if proc.stderr.strip():
            print(proc.stderr, file=sys.stderr)
        if proc.returncode != 0:
            exit_code = proc.returncode

    print("=" * 60)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
