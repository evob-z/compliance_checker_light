"""
ComplianceSkill - 对外暴露的简单接口（Facade 模式）

提供向后兼容的 API，隐藏内部复杂的依赖组装逻辑。
遵循 architecture.md 的『第 9.2 节 与旧目录的映射』。
"""

import logging
from typing import Dict, Any, Optional

from .bootstrap import initialize_app, Container
from .formatter import format_simple_result, format_issues_description
from .use_cases.project_check import ProjectCheckUseCase
from ..core.checker_registry import CheckerRegistry
from ..domain.engine.declarative import DeclarativeCheckEngine
from ..infrastructure.parsers import PDFParser, DocxParser, ImageParser

logger = logging.getLogger(__name__)


class ComplianceSkill:
    """
    合规检查技能（Facade 模式）

    提供简单的对外接口，隐藏内部复杂的依赖组装逻辑。
    在 __init__ 中完成所有初始化工作，对外暴露简单的 check 方法。

    使用示例:
        skill = ComplianceSkill()
        result = await skill.check(
            project_path="/path/to/project",
            requirements="检查项目立项批复文件是否齐全"
        )

    Attributes:
        registry: 检查器注册表
        container: 依赖注入容器
        engine: 声明式检查引擎
        use_case: 项目检查用例
    """

    def __init__(self, config: Optional[Any] = None):
        """
        初始化 ComplianceSkill

        完成所有依赖的组装：
        1. 调用 bootstrap 初始化 registry 和 container
        2. 创建声明式检查引擎
        3. 创建解析器字典
        4. 组装 ProjectCheckUseCase

        Args:
            config: 可选的配置对象（CheckerConfig 实例），
                   默认从环境变量加载
        """
        # 1. 调用 bootstrap 初始化
        self.registry: CheckerRegistry
        self.container: Container
        self.registry, self.container = initialize_app(config)

        # 2. 创建声明式检查引擎（注入 registry）
        self.engine = DeclarativeCheckEngine(
            registry=self.registry,
            concurrency_config={
                "max_concurrent_checks": 5,
                "check_timeout": 300,
            },
        )

        # 3. 创建解析器字典，注入 OCR 引擎
        ocr_engine = self.container.ocr_engine
        self.parsers: Dict[str, Any] = {
            ".pdf": PDFParser(ocr_engine=ocr_engine, use_ocr=True),
            ".docx": DocxParser(),
            ".doc": DocxParser(),  # .doc 也用 DocxParser 处理
            ".png": ImageParser(ocr_engine=ocr_engine),
            ".jpg": ImageParser(ocr_engine=ocr_engine),
            ".jpeg": ImageParser(ocr_engine=ocr_engine),
        }

        # 4. 组装 ProjectCheckUseCase
        self.use_case = ProjectCheckUseCase(
            engine=self.engine,
            parsers=self.parsers,
            llm_client=self.container.llm_client,
        )

        logger.info("ComplianceSkill 初始化完成")

    async def check(
        self,
        project_path: str,
        requirements: str,
        project_period: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        执行合规检查

        简单委托给 use_case.execute()，然后格式化结果。

        Args:
            project_path: 项目手续文件夹路径
            requirements: 自然语言描述的检查要求
            project_period: 可选的项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}

        Returns:
            检查结果字典，包含：
            - success: 是否成功
            - summary: 检查统计摘要
            - issues_count: 问题数量
            - issues: 问题列表
            - issues_description: 问题描述的中文描述字符串
            - messages: 提示信息
            - execution_time: 执行耗时
            - project_id: 项目标识
        """
        # 委托给 use_case 执行
        raw_result = await self.use_case.execute(project_path, requirements, project_period)

        # 格式化结果
        execution_result = raw_result.get("execution_result")
        formatted = format_simple_result(execution_result)

        # 添加中文描述字符串
        formatted["issues_description"] = format_issues_description(execution_result)

        # 添加分项结论
        formatted["itemized_conclusions"] = raw_result.get("itemized_conclusions", [])

        # 保留原始返回中的其他字段
        formatted["project_id"] = raw_result.get("project_id")
        formatted["checklist"] = raw_result.get("checklist")

        return formatted
