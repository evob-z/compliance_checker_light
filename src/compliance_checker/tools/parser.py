"""
parse_documents 工具 - MCP工具实现
用于解析项目文档，提取文字和元数据
"""
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..core.document import Document
from ..parsers import parse_document, get_document_type

# 导入配置（config 在项目根目录）
try:
    import sys
    from pathlib import Path

    config_path = Path(__file__).parent.parent.parent.parent / "config"
    if str(config_path) not in sys.path:
        sys.path.insert(0, str(config_path))
    from settings import scan_default_documents
except ImportError:
    scan_default_documents = None  # 配置不可用时的降级处理

logger = logging.getLogger(__name__)


async def parse_documents(
    file_paths: List[str], extract_options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    解析项目文档，提取文字和元数据

    Args:
        file_paths: 文件绝对路径列表。如果为空列表，将自动扫描默认文档路径
        extract_options: 提取选项
            - ocr: bool, 是否对扫描件使用OCR，默认True
            - metadata: bool, 是否提取元数据，默认True

    Returns:
        {
            "documents": [
                {
                    "file_path": "/data/立项批复.pdf",
                    "file_name": "立项批复.pdf",
                    "file_type": "pdf",
                    "pages": 5,
                    "content": "...提取的文字内容...",
                    "metadata": {
                        "title": "关于XX项目的立项批复",
                        "issue_date": "2024-03-15",
                        ...
                    }
                }
            ],
            "errors": [
                {
                    "file_path": "/data/xxx.pdf",
                    "error": "文件不存在"
                }
            ]
        }
    """
    if extract_options is None:
        extract_options = {}

    use_ocr = extract_options.get("ocr", True)
    extract_metadata = extract_options.get("metadata", True)

    # 如果 file_paths 为空，扫描默认文档路径
    if not file_paths:
        file_paths = scan_default_documents()
        if file_paths:
            logger.info(f"从默认路径扫描到 {len(file_paths)} 个文档")
        else:
            logger.warning("默认文档路径中没有找到支持的文档")

    logger.info(f"开始解析 {len(file_paths)} 个文档")

    documents = []
    errors = []

    for file_path in file_paths:
        try:
            # 检查文件是否存在
            path = Path(file_path)
            if not path.exists():
                error_msg = f"文件不存在: {file_path}"
                logger.warning(error_msg)
                errors.append({"file_path": file_path, "error": error_msg})
                continue

            # 检查是否为文件
            if not path.is_file():
                error_msg = f"路径不是文件: {file_path}"
                logger.warning(error_msg)
                errors.append({"file_path": file_path, "error": error_msg})
                continue

            # 解析文档
            logger.debug(f"解析文档: {file_path}")
            document = parse_document(file_path, use_ocr=use_ocr)

            # 转换为字典格式
            doc_dict = document.model_dump()

            # 如果不提取元数据，清空metadata
            if not extract_metadata:
                doc_dict["metadata"] = {}

            documents.append(doc_dict)
            logger.info(f"文档解析成功: {document.name}, 共{document.pages}页")

        except ValueError as e:
            # 格式错误
            error_msg = str(e)
            logger.warning(f"文档格式错误 {file_path}: {error_msg}")
            errors.append({"file_path": file_path, "error": error_msg})

        except Exception as e:
            # 其他错误
            error_msg = f"解析失败: {str(e)}"
            logger.error(f"文档解析失败 {file_path}: {e}", exc_info=True)
            errors.append({"file_path": file_path, "error": error_msg})

    result = {"documents": documents, "errors": errors}

    logger.info(f"文档解析完成: 成功 {len(documents)} 个, 失败 {len(errors)} 个")
    return result


def get_document_info(file_path: str) -> Dict[str, Any]:
    """
    获取文档基本信息（不解析内容）

    Args:
        file_path: 文件路径

    Returns:
        文档基本信息
    """
    path = Path(file_path)

    if not path.exists():
        return {"file_path": file_path, "exists": False, "error": "文件不存在"}

    doc_type = get_document_type(file_path)

    info = {
        "file_path": str(path.absolute()),
        "file_name": path.name,
        "exists": True,
        "file_type": doc_type.value,
        "size_bytes": path.stat().st_size,
    }

    return info
