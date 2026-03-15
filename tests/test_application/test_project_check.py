"""
Application 层 ProjectCheckUseCase 单元测试

测试范围：
- execute 方法完整流程
- execute_with_checklist 方法
- 文档扫描和解析
- 异常处理和错误类型

测试策略：
- Mock 所有外部依赖（engine, parsers, llm_client）
- 使用临时文件系统测试文档扫描
- 验证异常类型和错误信息
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from datetime import datetime

from src.application.use_cases.project_check import ProjectCheckUseCase
from src.core.document import Document, DocumentType, PageContent, DocumentMetadata
from src.core.checklist_model import Checklist, RequiredDocument, DocumentCheck
from src.domain.engine.declarative import ExecutionResult, CheckResult
from src.core.checker_base import CheckStatus


class MockExecutionResult:
    """Mock 执行结果"""
    def __init__(self, success=True):
        self.success = success
        self.summary = {"total": 3, "passed": 3, "failed": 0, "errors": 0}
        self.document_results = {}
        self.messages = []
        self.unavailable_features = []
        self.execution_time = 1.0


@pytest.fixture
def mock_engine():
    """Mock 声明式检查引擎"""
    engine = MagicMock()
    engine.execute = AsyncMock(return_value=MockExecutionResult(success=True))
    return engine


@pytest.fixture
def mock_parsers():
    """Mock 解析器字典"""
    pdf_parser = MagicMock()
    pdf_parser.parse = MagicMock(return_value=Document(
        path="/test/test.pdf",
        name="test.pdf",
        type=DocumentType.PDF,
        pages=1,
        pages_content=[PageContent(page_num=0, text="测试内容")],
        metadata=DocumentMetadata(),
    ))
    
    docx_parser = MagicMock()
    docx_parser.parse = MagicMock(return_value=Document(
        path="/test/test.docx",
        name="test.docx",
        type=DocumentType.DOCX,
        pages=1,
        pages_content=[PageContent(page_num=0, text="测试内容")],
        metadata=DocumentMetadata(),
    ))
    
    return {
        ".pdf": pdf_parser,
        ".docx": docx_parser,
        ".doc": docx_parser,
    }


@pytest.fixture
def mock_llm_client():
    """Mock LLM 客户端"""
    client = MagicMock()
    client.generate_yaml = AsyncMock(return_value={
        "checklist": {
            "id": "test_checklist",
            "name": "测试清单",
            "version": "1.0",
            "required_documents": [
                {
                    "name": "立项批复",
                    "aliases": ["立项"],
                    "required": True,
                }
            ],
        }
    })
    return client


@pytest.fixture
def use_case(mock_engine, mock_parsers, mock_llm_client):
    """创建测试用的 UseCase 实例"""
    return ProjectCheckUseCase(
        engine=mock_engine,
        parsers=mock_parsers,
        llm_client=mock_llm_client,
    )


class TestProjectCheckUseCaseInit:
    """测试 ProjectCheckUseCase 初始化"""

    def test_init_with_dependencies(self, mock_engine, mock_parsers, mock_llm_client):
        """测试使用依赖初始化"""
        use_case = ProjectCheckUseCase(
            engine=mock_engine,
            parsers=mock_parsers,
            llm_client=mock_llm_client,
        )
        
        assert use_case.engine == mock_engine
        assert use_case.parsers == mock_parsers
        assert use_case.llm_client == mock_llm_client

    def test_init_empty_parsers(self, mock_engine, mock_llm_client):
        """测试空解析器字典"""
        use_case = ProjectCheckUseCase(
            engine=mock_engine,
            parsers={},
            llm_client=mock_llm_client,
        )
        
        assert use_case.parsers == {}


class TestExecuteMethod:
    """测试 execute 方法"""

    @pytest.mark.asyncio
    async def test_execute_success(self, use_case, tmp_path):
        """测试执行成功流程"""
        # 创建测试文件
        test_file = tmp_path / "test.pdf"
        test_file.write_text("dummy content")
        
        result = await use_case.execute(
            project_path=str(tmp_path),
            requirements="检查立项批复",
        )
        
        # 验证返回结果结构
        assert isinstance(result, dict)
        assert "success" in result
        assert "execution_result" in result
        assert "document_count" in result
        assert "checklist" in result
        assert "execution_time" in result
        assert "project_id" in result
        
        # 验证字段值
        assert result["success"] is True
        assert result["document_count"] >= 0
        assert result["project_id"] == tmp_path.name
        assert isinstance(result["execution_time"], float)

    @pytest.mark.asyncio
    async def test_execute_with_project_period(self, use_case, tmp_path):
        """测试传入项目周期参数"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("dummy content")
        
        project_period = {"start": "2024-01", "end": "2024-12"}
        
        result = await use_case.execute(
            project_path=str(tmp_path),
            requirements="检查立项批复",
            project_period=project_period,
        )
        
        # 验证 LLM 被调用时传入了项目周期
        call_args = use_case.llm_client.generate_yaml.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, use_case):
        """测试路径不存在异常"""
        with pytest.raises(FileNotFoundError) as exc_info:
            await use_case.execute(
                project_path="/nonexistent/path",
                requirements="检查立项批复",
            )
        
        # 验证异常信息
        assert "路径不存在" in str(exc_info.value)
        assert "/nonexistent/path" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_not_a_directory(self, use_case, tmp_path):
        """测试路径不是目录异常"""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")
        
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute(
                project_path=str(test_file),
                requirements="检查立项批复",
            )
        
        # 验证异常信息
        assert "路径必须是文件夹" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_no_documents_found(self, use_case, tmp_path):
        """测试未找到可解析文档异常"""
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute(
                project_path=str(tmp_path),
                requirements="检查立项批复",
            )
        
        # 验证异常信息
        assert "未找到可解析的文档" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_no_documents_parsed(self, use_case, tmp_path):
        """测试没有成功解析任何文档"""
        # 创建文件但让解析器返回 None
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        # 修改解析器返回 None
        use_case.parsers[".pdf"].parse = MagicMock(return_value=None)
        
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute(
                project_path=str(tmp_path),
                requirements="检查立项批复",
            )
        
        # 验证异常信息
        assert "没有成功解析任何文档" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_checklist_generation_failure(self, use_case, tmp_path):
        """测试清单生成失败"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        # 让 LLM 抛出异常
        use_case.llm_client.generate_yaml = AsyncMock(side_effect=Exception("API Error"))
        
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute(
                project_path=str(tmp_path),
                requirements="检查立项批复",
            )
        
        # 验证异常信息
        assert "无法从描述生成清单" in str(exc_info.value)
        assert "API Error" in str(exc_info.value)


class TestExecuteWithChecklist:
    """测试 execute_with_checklist 方法"""

    @pytest.mark.asyncio
    async def test_execute_with_checklist_success(self, use_case, tmp_path):
        """测试使用已有清单执行检查"""
        # 创建测试文件
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        # 创建清单对象
        checklist = Checklist(
            id="test",
            name="测试清单",
            required_documents=[
                RequiredDocument(name="立项批复", required=True)
            ],
        )
        
        result = await use_case.execute_with_checklist(
            project_path=str(tmp_path),
            checklist=checklist,
        )
        
        # 验证返回结果
        assert isinstance(result, MockExecutionResult)
        assert hasattr(result, "execution_time")

    @pytest.mark.asyncio
    async def test_execute_with_checklist_path_not_found(self, use_case):
        """测试路径不存在"""
        checklist = Checklist(id="test", name="测试清单")
        
        with pytest.raises(FileNotFoundError) as exc_info:
            await use_case.execute_with_checklist(
                project_path="/nonexistent/path",
                checklist=checklist,
            )
        
        assert "路径不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_with_checklist_no_documents(self, use_case, tmp_path):
        """测试没有文档可解析"""
        checklist = Checklist(id="test", name="测试清单")
        
        with pytest.raises(ValueError) as exc_info:
            await use_case.execute_with_checklist(
                project_path=str(tmp_path),
                checklist=checklist,
            )
        
        assert "没有成功解析任何文档" in str(exc_info.value)


class TestScanDocuments:
    """测试文档扫描功能"""

    def test_scan_documents(self, use_case, tmp_path):
        """测试扫描文档"""
        # 创建测试文件
        (tmp_path / "doc1.pdf").write_text("content")
        (tmp_path / "doc2.docx").write_text("content")
        (tmp_path / "doc3.txt").write_text("content")  # 不支持
        
        paths = use_case._scan_documents(tmp_path)
        
        # 验证只返回支持的文件类型
        assert len(paths) == 2
        assert any("doc1.pdf" in p for p in paths)
        assert any("doc2.docx" in p for p in paths)
        assert not any("doc3.txt" in p for p in paths)

    def test_scan_documents_empty_directory(self, use_case, tmp_path):
        """测试空目录"""
        paths = use_case._scan_documents(tmp_path)
        assert paths == []

    def test_scan_documents_sorted(self, use_case, tmp_path):
        """测试结果排序"""
        (tmp_path / "b.pdf").write_text("content")
        (tmp_path / "a.pdf").write_text("content")
        (tmp_path / "c.pdf").write_text("content")
        
        paths = use_case._scan_documents(tmp_path)
        
        # 验证按字母顺序排序
        assert paths == sorted(paths)


class TestParseDocuments:
    """测试文档解析功能"""

    @pytest.mark.asyncio
    async def test_parse_documents_success(self, use_case):
        """测试成功解析文档"""
        file_paths = ["/test/doc1.pdf", "/test/doc2.docx"]
        
        documents = await use_case._parse_documents(file_paths)
        
        # 验证返回文档列表
        assert len(documents) == 2
        assert all(isinstance(doc, Document) for doc in documents)

    @pytest.mark.asyncio
    async def test_parse_documents_with_failure(self, use_case):
        """测试部分解析失败"""
        # 让第一个解析器失败
        use_case.parsers[".pdf"].parse = MagicMock(side_effect=Exception("Parse error"))
        
        file_paths = ["/test/doc1.pdf", "/test/doc2.docx"]
        
        documents = await use_case._parse_documents(file_paths)
        
        # 验证只返回成功解析的文档
        assert len(documents) == 1
        assert documents[0].name == "test.docx"

    @pytest.mark.asyncio
    async def test_parse_documents_empty_list(self, use_case):
        """测试空文件列表"""
        documents = await use_case._parse_documents([])
        assert documents == []

    @pytest.mark.asyncio
    async def test_parse_documents_all_fail(self, use_case):
        """测试全部解析失败"""
        use_case.parsers[".pdf"].parse = MagicMock(side_effect=Exception("Error"))
        use_case.parsers[".docx"].parse = MagicMock(side_effect=Exception("Error"))
        
        file_paths = ["/test/doc1.pdf", "/test/doc2.docx"]
        
        documents = await use_case._parse_documents(file_paths)
        assert documents == []


class TestParseSingleDocument:
    """测试单个文档解析"""

    @pytest.mark.asyncio
    async def test_parse_single_async(self, use_case):
        """测试异步解析器"""
        async def async_parse(path):
            return Document(
                path=path,
                name=Path(path).name,
                type=DocumentType.PDF,
                pages=1,
            )
        
        use_case.parsers[".pdf"].parse = async_parse
        
        doc = await use_case._parse_single_document("/test/file.pdf")
        
        assert doc is not None
        assert doc.name == "file.pdf"

    @pytest.mark.asyncio
    async def test_parse_single_sync(self, use_case):
        """测试同步解析器"""
        doc = await use_case._parse_single_document("/test/file.pdf")
        
        assert doc is not None
        assert doc.name == "test.pdf"

    @pytest.mark.asyncio
    async def test_parse_single_unsupported_extension(self, use_case):
        """测试不支持的文件扩展名"""
        doc = await use_case._parse_single_document("/test/file.txt")
        assert doc is None

    @pytest.mark.asyncio
    async def test_parse_single_exception(self, use_case):
        """测试解析异常"""
        use_case.parsers[".pdf"].parse = MagicMock(side_effect=Exception("Parse error"))
        
        doc = await use_case._parse_single_document("/test/file.pdf")
        assert doc is None


class TestExecuteEdgeCases:
    """测试 execute 方法边界情况"""

    @pytest.mark.asyncio
    async def test_execute_with_empty_requirements(self, use_case, tmp_path):
        """测试空要求字符串"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        # 空要求应该也能执行（由 LLM 处理）
        result = await use_case.execute(
            project_path=str(tmp_path),
            requirements="",
        )
        
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_execution_time_set(self, use_case, tmp_path):
        """测试执行时间被设置"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        result = await use_case.execute(
            project_path=str(tmp_path),
            requirements="检查立项批复",
        )
        
        # 验证执行时间大于 0
        assert result["execution_time"] > 0
        assert isinstance(result["execution_time"], float)

    @pytest.mark.asyncio
    async def test_execute_checklist_in_result(self, use_case, tmp_path):
        """测试返回结果包含清单数据"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        result = await use_case.execute(
            project_path=str(tmp_path),
            requirements="检查立项批复",
        )
        
        # 验证 checklist 字段
        assert "checklist" in result
        assert isinstance(result["checklist"], dict)


class TestChecklistPromptBuilderIntegration:
    """测试 ChecklistPromptBuilder 集成"""

    @pytest.mark.asyncio
    async def test_prompt_builder_called(self, use_case, tmp_path):
        """测试 PromptBuilder 被调用"""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("content")
        
        with patch("src.application.use_cases.project_check.ChecklistPromptBuilder") as mock_builder:
            mock_builder.build.return_value = "测试提示词"
            
            await use_case.execute(
                project_path=str(tmp_path),
                requirements="检查立项批复",
                project_period={"start": "2024-01", "end": "2024-12"},
            )
            
            # 验证 build 方法被调用
            mock_builder.build.assert_called_once()
            call_kwargs = mock_builder.build.call_args.kwargs
            assert call_kwargs["requirements"] == "检查立项批复"
            assert call_kwargs["project_period"] == {"start": "2024-01", "end": "2024-12"}

