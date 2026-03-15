"""
项目检查用例

负责统筹整个合规检查流程：
1. 扫描并解析文档
2. 生成检查清单
3. 执行检查
4. 返回结果

架构约束：
- 只负责"呼叫部门干活"，不包含具体业务逻辑
- 通过构造函数接收所有依赖（依赖注入）
- 禁止在此类中写正则匹配或计算逻辑
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from ...core.document import Document
from ...core.checklist_model import Checklist
from ...core.interfaces import DocumentParserProtocol, LLMClientProtocol
from ...domain.engine.declarative import DeclarativeCheckEngine, ExecutionResult
from ..prompts.checklist_prompt import ChecklistPromptBuilder

logger = logging.getLogger(__name__)


class ProjectCheckUseCase:
    """
    项目检查用例

    统筹整个合规检查流程，协调各组件完成：
    - 文档扫描与解析
    - 清单生成
    - 检查执行
    - 结果汇总

    Args:
        engine: 声明式检查引擎（已注入 CheckerRegistry）
        parsers: 文档解析器字典，key 为文件扩展名（如 ".pdf"）
        llm_client: LLM 客户端，用于生成检查清单
    """

    def __init__(
        self,
        engine: DeclarativeCheckEngine,
        parsers: Dict[str, DocumentParserProtocol],
        llm_client: LLMClientProtocol,
    ):
        self.engine = engine
        self.parsers = parsers
        self.llm_client = llm_client

    async def execute(
        self,
        project_path: str,
        requirements: str,
        project_period: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        执行项目合规检查

        流程：
        1. 扫描项目目录中的文档
        2. 解析所有支持的文档
        3. 使用 LLM 生成检查清单
        4. 执行声明式检查
        5. 返回格式化结果

        Args:
            project_path: 项目手续文件夹路径
            requirements: 自然语言描述的检查要求
            project_period: 可选的项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}

        Returns:
            检查结果字典，包含：
            - success: 是否成功
            - execution_result: 执行结果对象
            - document_count: 文档数量
            - checklist: 生成的清单

        Raises:
            FileNotFoundError: 文件夹不存在
            ValueError: 未找到可解析的文档
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
            # 使用 Prompt 构建器组装提示词
            prompt_text = ChecklistPromptBuilder.build(
                requirements=requirements,
                project_period=project_period,
            )
            
            checklist_data = await self.llm_client.generate_yaml(
                prompt_text=prompt_text
            )

            # 如果提供了项目周期，注入到清单中（用于有效期约束检查）
            if project_period and "checklist" in checklist_data:
                checklist_data["checklist"]["project_period"] = project_period
                logger.info(f"已注入项目周期: {project_period}")

            checklist = Checklist.model_validate(checklist_data["checklist"])
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

        # 提取分项结论
        itemized_conclusions = self._extract_itemized_conclusions(execution_result)

        return {
            "success": execution_result.success,
            "execution_result": execution_result,
            "document_count": len(documents),
            "checklist": checklist_data,
            "execution_time": execution_time,
            "project_id": path.name,
            "itemized_conclusions": itemized_conclusions,
        }

    def _extract_itemized_conclusions(self, execution_result) -> List[str]:
        """
        从执行结果中提取分项结论

        遍历所有检查结果，提取每个检查器的 message 作为分项结论。

        Args:
            execution_result: 执行结果对象

        Returns:
            分项结论字符串列表
        """
        conclusions = []

        # 遍历所有文档的检查结果
        for doc_name, results in execution_result.document_results.items():
            for result in results:
                # 提取检查器的 message 作为结论
                if result.message:
                    conclusions.append(result.message)

        return conclusions

    async def execute_with_checklist(
        self,
        project_path: str,
        checklist: Checklist,
    ) -> ExecutionResult:
        """
        使用已有的检查清单执行检查

        Args:
            project_path: 项目手续文件夹路径
            checklist: 审核清单对象

        Returns:
            执行结果
        """
        import time

        start_time = time.time()

        # 1. 验证路径
        path = Path(project_path)
        if not path.exists():
            raise FileNotFoundError(f"路径不存在: {project_path}")

        # 2. 扫描和解析文档
        document_paths = self._scan_documents(path)
        documents = await self._parse_documents(document_paths)

        if not documents:
            raise ValueError("没有成功解析任何文档")

        # 3. 执行检查
        execution_result = await self.engine.execute(documents, checklist)
        execution_result.execution_time = time.time() - start_time

        return execution_result

    def _scan_documents(self, directory: Path) -> List[str]:
        """
        扫描目录中的文档

        Args:
            directory: 目录路径

        Returns:
            文档路径列表
        """
        supported_extensions = set(self.parsers.keys())
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
            # 根据解析器类型选择同步或异步执行
            if asyncio.iscoroutinefunction(parser.parse):
                return await parser.parse(file_path)
            else:
                # 同步解析器在线程池中执行
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, parser.parse, file_path)
        except Exception as e:
            logger.error(f"解析失败 {file_path}: {e}")
            return None
