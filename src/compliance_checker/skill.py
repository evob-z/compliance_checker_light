"""
Compliance Checker Skill 主模块

为 AI 助手提供自然语言接口的合规审查能力

Usage:
    from compliance_checker.skill import ComplianceSkill
    
    skill = ComplianceSkill()
    result = await skill.check(
        project_path="/data/project_123/documents",
        requirements="审查建设工程项目，需要立项批复、环评批复、施工许可证",
        project_period={"start": "2025-01", "end": "2027-12"}
    )
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# 自动加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .core.document import Document
from .core.checklist_model import Checklist
from .core.checker_registry import get_initialized_registry
from .engine.declarative_engine import DeclarativeCheckEngine
from .parsers.pdf_parser import PDFParser
from .parsers.docx_parser import DocxParser
from .prompts.checklist_generator import async_generate_checklist_with_period
from .skill_formatter import format_check_result, format_simple_result

logger = logging.getLogger(__name__)


class ComplianceSkill:
    """
    合规审查 Skill
    
    提供简化的自然语言接口，支持：
    1. 自然语言描述检查要求
    2. 文件夹路径输入
    3. 文本格式结果输出
    """
    
    def __init__(self):
        """初始化 Skill"""
        self.registry = get_initialized_registry()
        self.engine = DeclarativeCheckEngine(registry=self.registry)
        
        # 初始化文档解析器
        self.parsers = {
            ".pdf": PDFParser(),
            ".docx": DocxParser(),
            ".doc": DocxParser(),
        }
    
    async def check(
        self,
        project_path: str,
        requirements: str,
        project_period: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        执行合规审查
        
        Args:
            project_path: 项目手续文件夹路径
            requirements: 自然语言描述的检查要求
            project_period: 可选的项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}
        
        Returns:
            检查结果字典，包含：
            - success: 是否成功
            - summary: 检查摘要
            - issues_description: 问题文本描述
            - issues_simple: 简化的问题列表
            - generated_checklist: 生成的 YAML 清单
            - document_count: 文档数量
            - execution_time: 执行时间
        
        Raises:
            FileNotFoundError: 文件夹不存在
            ValueError: 未找到可解析的文档
            Exception: LLM 调用或检查执行失败
        
        Example:
            >>> skill = ComplianceSkill()
            >>> result = await skill.check(
            ...     project_path="/data/project_123",
            ...     requirements="审查建设工程项目，需要立项批复、环评批复",
            ...     project_period={"start": "2025-01", "end": "2027-12"}
            ... )
            >>> print(result["issues_description"])
        """
        import time
        start_time = time.time()
        
        # 1. 验证路径
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"路径不存在: {project_path}")
        
        if not path.is_dir():
            raise ValueError(f"路径必须是文件夹: {project_path}")
        
        logger.info(f"开始审查项目: {path.name}")
        
        # 2. 扫描文档
        document_paths = self._scan_documents(path)
        if not document_paths:
            raise ValueError(f"在 {project_path} 中未找到可解析的文档")
        
        logger.info(f"找到 {len(document_paths)} 个文档")
        
        # 3. 解析文档
        documents = await self._parse_documents(document_paths)
        if not documents:
            raise ValueError("没有成功解析任何文档")
        
        logger.info(f"成功解析 {len(documents)} 个文档")
        
        # 4. 使用 LLM 生成清单
        logger.info("正在生成检查清单...")
        try:
            checklist_data = await async_generate_checklist_with_period(
                user_description=requirements,
                project_period=project_period
            )
            checklist = Checklist.parse_obj(checklist_data["checklist"])
            logger.info(f"清单生成成功: {checklist.name}")
        except Exception as e:
            logger.error(f"清单生成失败: {e}")
            raise ValueError(f"无法从描述生成清单: {e}")
        
        # 5. 执行检查
        logger.info("开始执行检查...")
        execution_result = await self.engine.execute(documents, checklist)
        
        execution_time = time.time() - start_time
        execution_result.execution_time = execution_time
        
        logger.info(f"检查完成，耗时 {execution_time:.2f} 秒")
        
        # 6. 格式化结果
        issues_description = format_check_result(execution_result)
        simple_result = format_simple_result(execution_result)
        
        return {
            "success": execution_result.success,
            "summary": simple_result["summary"],
            "issues_description": issues_description,
            "issues_simple": simple_result["issues"],
            "generated_checklist": checklist_data,
            "document_count": len(documents),
            "execution_time": execution_time,
            "project_id": path.name
        }
    
    def _scan_documents(self, directory: Path) -> List[str]:
        """
        扫描目录中的文档
        
        Args:
            directory: 目录路径
        
        Returns:
            文档路径列表
        """
        supported_extensions = {".pdf", ".docx", ".doc"}
        document_paths = []
        
        for ext in supported_extensions:
            for file_path in directory.glob(f"*{ext}"):
                if file_path.is_file():
                    document_paths.append(str(file_path))
        
        return sorted(document_paths)
    
    async def _parse_documents(self, file_paths: List[str]) -> List[Document]:
        """
        解析文档列表
        
        Args:
            file_paths: 文件路径列表
        
        Returns:
            Document 对象列表
        """
        documents = []
        
        for file_path in file_paths:
            try:
                doc = await self._parse_single_document(file_path)
                if doc:
                    documents.append(doc)
            except Exception as e:
                logger.warning(f"解析文档失败 {file_path}: {e}")
        
        return documents
    
    async def _parse_single_document(self, file_path: str) -> Optional[Document]:
        """
        解析单个文档
        
        Args:
            file_path: 文件路径
        
        Returns:
            Document 对象或 None
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        
        if ext not in self.parsers:
            logger.warning(f"不支持的文件类型: {ext}")
            return None
        
        parser = self.parsers[ext]
        
        try:
            if ext == ".pdf":
                # PDF parser doesn't have async method, run in executor
                import asyncio
                return await asyncio.get_event_loop().run_in_executor(
                    None, parser.parse, file_path
                )
            elif ext in {".docx", ".doc"}:
                return parser.parse(file_path)
            else:
                return None
        except Exception as e:
            logger.error(f"解析失败 {file_path}: {e}")
            return None
    
    async def check_with_generated_checklist(
        self,
        project_path: str,
        checklist_yaml: str
    ) -> Dict[str, Any]:
        """
        使用已生成的 YAML 清单执行检查
        
        Args:
            project_path: 项目手续文件夹路径
            checklist_yaml: YAML 格式的清单字符串
        
        Returns:
            检查结果字典
        """
        import yaml
        import time
        
        start_time = time.time()
        
        # 1. 验证路径
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"路径不存在: {project_path}")
        
        # 2. 解析清单
        try:
            checklist_data = yaml.safe_load(checklist_yaml)
            checklist = Checklist.parse_obj(checklist_data["checklist"])
        except Exception as e:
            raise ValueError(f"清单解析失败: {e}")
        
        # 3. 扫描和解析文档
        document_paths = self._scan_documents(path)
        documents = await self._parse_documents(document_paths)
        
        if not documents:
            raise ValueError("没有成功解析任何文档")
        
        # 4. 执行检查
        execution_result = await self.engine.execute(documents, checklist)
        execution_time = time.time() - start_time
        execution_result.execution_time = execution_time
        
        # 5. 格式化结果
        issues_description = format_check_result(execution_result)
        simple_result = format_simple_result(execution_result)
        
        return {
            "success": execution_result.success,
            "summary": simple_result["summary"],
            "issues_description": issues_description,
            "issues_simple": simple_result["issues"],
            "document_count": len(documents),
            "execution_time": execution_time,
            "project_id": path.name
        }


# 便捷函数
async def check_compliance(
    project_path: str,
    requirements: str,
    project_period: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    便捷函数：执行合规审查
    
    Args:
        project_path: 项目手续文件夹路径
        requirements: 自然语言描述的检查要求
        project_period: 可选的项目周期
    
    Returns:
        检查结果字典
    
    Example:
        >>> result = await check_compliance(
        ...     "/data/project_123",
        ...     "审查建设工程项目，需要立项批复、环评批复"
        ... )
        >>> print(result["issues_description"])
    """
    skill = ComplianceSkill()
    return await skill.check(project_path, requirements, project_period)
