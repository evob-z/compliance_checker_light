"""
Compliance Checker CLI 入口

纯 CLI 工具，暴露 3 个原子子命令：
- completeness: 文档批量嗅探（文件名匹配）
- timeliness: 时效性计算（有效期判定）
- visual: 视觉质检（印章/签名检测）

所有输出为 JSON（stdout），日志写 stderr。
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

__version__ = "2.0.0"

logger = logging.getLogger(__name__)


def _load_env():
    """
    多路径 .env 加载，兼容多种部署场景。

    加载顺序（不覆盖已有环境变量）：
    1. 系统环境变量（最高优先级，始终保留）
    2. ~/.compliance-checker/.env（用户配置目录）
    3. cwd/.env（保持向后兼容）
    """
    home_env = Path.home() / ".compliance-checker" / ".env"
    if home_env.exists():
        load_dotenv(home_env, override=False)

    load_dotenv(override=False)


def _setup_logging():
    """配置日志输出到 stderr，确保 stdout 只有纯 JSON"""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(name)s - %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.WARNING)


def _output_json(data: dict):
    """输出 JSON 到 stdout"""
    # Windows 终端编码处理：强制使用 UTF-8 编码输出
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        # 尝试直接输出
        print(json_str)
    except UnicodeEncodeError:
        # 如果终端不支持 UTF-8，使用 sys.stdout.buffer 直接写入
        encoded = json_str.encode('utf-8')
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.write(b'\n')


def _output_error(error_type: str, message: str):
    """输出错误 JSON 到 stdout"""
    _output_json({"error": message, "error_type": error_type})


def _health_check() -> dict:
    """执行健康检查，返回 JSON 格式的系统状态"""
    import os

    result = {
        "status": "ok",
        "version": __version__,
        "python_version": sys.version,
        "checks": {},
    }

    # 检查 LLM API Key
    llm_key = os.getenv("LLM_API_KEY", "")
    result["checks"]["llm_api_key"] = {
        "configured": bool(llm_key),
        "model": os.getenv("LLM_MODEL", "未配置"),
    }

    # 检查嵌入模型
    embed_key = os.getenv("EMBED_API_KEY", "") or llm_key
    result["checks"]["embed_api_key"] = {
        "configured": bool(embed_key),
        "model": os.getenv("EMBED_MODEL", "text-embedding-v1"),
    }

    # 检查视觉模型
    vision_key = os.getenv("VISION_API_KEY", "") or llm_key
    result["checks"]["vision_api_key"] = {
        "configured": bool(vision_key),
        "model": os.getenv("VISION_MODEL", "qwen3-vl-flash"),
    }

    # 检查 PyMuPDF
    try:
        import fitz

        result["checks"]["pymupdf"] = {"available": True, "version": fitz.version[0]}
    except ImportError:
        result["checks"]["pymupdf"] = {"available": False}

    if not llm_key:
        result["status"] = "degraded"

    return result


def _build_parser() -> argparse.ArgumentParser:
    """构建 argparse 解析器"""
    parser = argparse.ArgumentParser(
        prog="compliance-checker",
        description="项目手续合规审查 CLI 工具",
    )
    parser.add_argument("--version", action="store_true", help="显示版本号")
    parser.add_argument("--health-check", action="store_true", help="执行健康检查")

    subparsers = parser.add_subparsers(dest="command")

    # completeness 子命令
    p_comp = subparsers.add_parser("completeness", help="文档批量嗅探（文件名匹配）")
    p_comp.add_argument("--path", required=True, help="项目文件夹路径")
    p_comp.add_argument("--documents", required=True, help="逗号分隔的文档名称列表")

    # timeliness 子命令
    p_time = subparsers.add_parser("timeliness", help="时效性计算（有效期判定）")
    p_time.add_argument("--file", required=True, help="文件路径")
    p_time.add_argument("--reference-time", default=None, help="校验基准时间 (YYYY-MM-DD)")

    # visual 子命令
    p_vis = subparsers.add_parser("visual", help="视觉质检（印章/签名检测）")
    p_vis.add_argument("--file", required=True, help="文件路径")
    p_vis.add_argument("--targets", required=True, help="逗号分隔的检测目标列表")

    return parser


def main():
    _load_env()
    _setup_logging()

    parser = _build_parser()
    args = parser.parse_args()

    # 全局选项
    if args.version:
        print(__version__)
        return

    if args.health_check:
        _output_json(_health_check())
        return

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # 分发到子命令
    try:
        if args.command == "completeness":
            from .application.commands.completeness_cmd import run_completeness

            path = args.path.replace("\\", "/")
            documents = [d.strip() for d in args.documents.split(",") if d.strip()]
            result = asyncio.run(run_completeness(path, documents))

        elif args.command == "timeliness":
            from .application.commands.timeliness_cmd import run_timeliness

            file_path = args.file.replace("\\", "/")
            result = asyncio.run(run_timeliness(file_path, args.reference_time))

        elif args.command == "visual":
            from .application.commands.visual_cmd import run_visual

            file_path = args.file.replace("\\", "/")
            targets = [t.strip() for t in args.targets.split(",") if t.strip()]
            result = asyncio.run(run_visual(file_path, targets))

        else:
            parser.print_help(sys.stderr)
            sys.exit(1)

        _output_json(result)

    except FileNotFoundError as e:
        _output_error("FileNotFoundError", str(e))
        sys.exit(1)
    except ValueError as e:
        _output_error("ValueError", str(e))
        sys.exit(1)
    except Exception as e:
        logger.exception(f"命令执行失败: {e}")
        _output_error("InternalError", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
