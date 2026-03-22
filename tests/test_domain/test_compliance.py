"""
VisualChecker（合规性/视觉检查器）单元测试

测试视觉检查器的核心逻辑，不依赖真实的 Infrastructure 层。
使用 MockVisualClient 模拟视觉检测功能。

遵循 architecture.md 中『10.2 Domain 层测试示例』规范：
- 不引入真实 infrastructure
- 手写 Mock 类实现协议接口
- 使用内存对象构造测试输入
- 至少包含 PASS 和 FAIL 两种核心场景用例
- 详尽的 assert 校验返回字段、异常类型和错误信息
"""

import pytest
from typing import Dict, Any, Optional, List

from src.compliance_checker.core.checker_base import CheckStatus, CheckResult
from src.compliance_checker.core.document import Document
from src.compliance_checker.core.checklist_model import Checklist
from src.compliance_checker.domain.checkers.compliance import VisualChecker, VisualCheckType


class MockVisualClient:
    """
    Mock 视觉检测客户端 - 实现 VisualCheckerProtocol 接口

    使用简单的规则模拟印章和签名检测：
    - 如果文件名包含 "seal" 或 "印章"，返回检测到印章
    - 如果文件名包含 "sign" 或 "签名"，返回检测到签名
    - 否则返回未检测到

    支持从字节流检测（detect_seal_from_bytes, detect_signature_from_bytes）

    不依赖真实的视觉模型（如 Qwen-VL）。
    """

    def __init__(self, available: bool = True):
        """
        初始化 Mock 客户端

        Args:
            available: 是否模拟服务可用
        """
        self._available = available

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._available

    async def detect_seal(self, image_path: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        检测图片中的公章（模拟）

        Args:
            image_path: 图片文件路径
            context: 上下文信息

        Returns:
            检测结果字典
        """
        if not self._available:
            return {
                "success": False,
                "error": "服务不可用",
            }

        # 从文件路径中提取文件名
        file_name = image_path.lower().split("/")[-1].split("\\")[-1]

        # 模拟检测逻辑：文件名包含特定关键词则认为检测到
        found = "seal" in file_name or "印章" in file_name or "公章" in file_name

        # 计算置信度
        confidence = 0.95 if found else 0.1

        return {
            "success": True,
            "found": found,
            "confidence": confidence,
            "reasoning": f"模拟检测: {'检测到' if found else '未检测到'}公章",
            "location": "右下角" if found else None,
        }

    async def detect_signature(
        self, image_path: str, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检测图片中的签名（模拟）

        Args:
            image_path: 图片文件路径
            context: 上下文信息

        Returns:
            检测结果字典
        """
        if not self._available:
            return {
                "success": False,
                "error": "服务不可用",
            }

        # 从文件路径中提取文件名
        file_name = image_path.lower().split("/")[-1].split("\\")[-1]

        # 模拟检测逻辑
        found = "sign" in file_name or "签名" in file_name or "签字" in file_name

        # 计算置信度
        confidence = 0.92 if found else 0.1

        return {
            "success": True,
            "found": found,
            "confidence": confidence,
            "reasoning": f"模拟检测: {'检测到' if found else '未检测到'}签名",
            "location": "底部" if found else None,
        }

    async def detect_seal_from_bytes(
        self, image_bytes: bytes, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从字节流检测公章（模拟）

        Args:
            image_bytes: 图片字节流
            context: 上下文信息

        Returns:
            检测结果字典
        """
        # 对于 Mock，我们假设字节流中包含印章（用于测试 PDF 转换后的检测）
        if not self._available:
            return {
                "success": False,
                "error": "服务不可用",
            }

        # 模拟：假设字节流有效就检测到印章
        found = len(image_bytes) > 0
        confidence = 0.9 if found else 0.1

        return {
            "success": True,
            "found": found,
            "confidence": confidence,
            "reasoning": f"字节流检测: {'检测到' if found else '未检测到'}公章",
            "location": "右下角" if found else None,
        }

    async def detect_signature_from_bytes(
        self, image_bytes: bytes, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从字节流检测签名（模拟）

        Args:
            image_bytes: 图片字节流
            context: 上下文信息

        Returns:
            检测结果字典
        """
        if not self._available:
            return {
                "success": False,
                "error": "服务不可用",
            }

        found = len(image_bytes) > 0
        confidence = 0.88 if found else 0.1

        return {
            "success": True,
            "found": found,
            "confidence": confidence,
            "reasoning": f"字节流检测: {'检测到' if found else '未检测到'}签名",
            "location": "底部" if found else None,
        }


# ============== 测试 Fixtures ==============


@pytest.fixture
def mock_visual_client():
    """创建可用的 Mock 视觉客户端"""
    return MockVisualClient(available=True)


@pytest.fixture
def unavailable_visual_client():
    """创建不可用的 Mock 视觉客户端"""
    return MockVisualClient(available=False)


class MockPDFConverter:
    """
    Mock PDF 转换器 - 实现 PDFConverterProtocol 接口

    用于测试 PDF 文件处理逻辑，不依赖真实的 PyMuPDF。
    """

    def __init__(self, num_pages: int = 1):
        """
        初始化 Mock 转换器

        Args:
            num_pages: 模拟的 PDF 页数
        """
        self.num_pages = num_pages

    async def convert_to_images(self, file_path_or_bytes: str | bytes) -> List[bytes]:
        """
        模拟将 PDF 转换为图片

        Returns:
            模拟的图片字节流列表
        """
        # 返回模拟的 PNG 图片字节流（PNG 魔数 + 一些数据）
        mock_image = b"\x89PNG\r\n\x1a\n" + b"MOCK_IMAGE_DATA" * 100
        return [mock_image for _ in range(self.num_pages)]


@pytest.fixture
def mock_pdf_converter():
    """创建 Mock PDF 转换器"""
    return MockPDFConverter(num_pages=1)


@pytest.fixture
def mock_pdf_converter_multi_page():
    """创建多页 Mock PDF 转换器"""
    return MockPDFConverter(num_pages=3)


@pytest.fixture
def checker(mock_visual_client, mock_pdf_converter):
    """创建视觉检查器实例（带 PDF 转换器，用于测试图片和 PDF）"""
    return VisualChecker(
        visual_client=mock_visual_client,
        pdf_converter=mock_pdf_converter,
        default_check_type="both",
        confidence_threshold=0.7,
        enabled=True,
    )


@pytest.fixture
def checker_without_pdf_converter(mock_visual_client):
    """创建不带 PDF 转换器的视觉检查器实例（用于测试 PDF 错误场景）"""
    return VisualChecker(
        visual_client=mock_visual_client,
        pdf_converter=None,
        default_check_type="both",
        confidence_threshold=0.7,
        enabled=True,
    )


@pytest.fixture
def sample_checklist():
    """创建示例审核清单"""
    return Checklist(
        id="test_checklist_002",
        name="测试用审核清单",
        version="1.0",
    )


def create_document(file_name: str, file_path: str = None) -> Document:
    """
    创建测试用 Document 对象

    Args:
        file_name: 文件名
        file_path: 文件路径（可选）

    Returns:
        Document 实例
    """
    return Document(
        path=file_path or f"/test/documents/{file_name}",
        name=file_name,
    )


# ============== 测试用例 ==============


@pytest.mark.asyncio
async def test_visual_check_seal_found(checker, sample_checklist):
    """
    测试场景：检测到印章

    预期结果：
    - check_type 为 "compliance"
    - status 为 PASS
    - seal_result 显示检测到印章
    - details 包含完整的统计信息
    """
    # 准备测试数据：文件名包含印章关键词（使用图片格式测试图片检测逻辑）
    documents = [
        create_document("立项批复_印章.jpg"),
    ]

    # 执行检查（仅检查印章）
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # ========== 验证 CheckResult 基础字段 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "compliance", "check_type 应为 'compliance'"
    assert result.status == CheckStatus.PASS, "检测到印章应为 PASS"

    # 验证 message 字段
    assert isinstance(result.message, str), "message 应为字符串类型"
    assert len(result.message) > 0, "message 不应为空"

    # 验证 details 字段结构
    assert isinstance(result.details, dict), "details 应为字典类型"
    assert "check_type" in result.details, "details 应包含 check_type"
    assert "total_documents" in result.details, "details 应包含 total_documents"
    assert "valid_count" in result.details, "details 应包含 valid_count"
    assert "missing_count" in result.details, "details 应包含 missing_count"
    assert "error_count" in result.details, "details 应包含 error_count"
    assert "unclear_count" in result.details, "details 应包含 unclear_count"
    assert "document_results" in result.details, "details 应包含 document_results"

    # 验证统计信息
    assert result.details["total_documents"] == 1, "总文档数应为 1"
    assert result.details["valid_count"] == 1, "有效文档数应为 1"
    assert result.details["missing_count"] == 0, "缺失文档数应为 0"

    # ========== 验证印章检测结果 ==========
    doc_result = result.details["document_results"][0]
    assert "document_name" in doc_result, "结果应包含 document_name"
    assert "seal_result" in doc_result, "结果应包含 seal_result"
    assert "status" in doc_result, "结果应包含 status"

    assert doc_result["seal_result"]["found"] is True, "应检测到印章"
    assert doc_result["seal_result"]["confidence"] >= 0.7, "置信度应 >= 0.7"
    assert "reasoning" in doc_result["seal_result"], "结果应包含 reasoning"


@pytest.mark.asyncio
async def test_visual_check_signature_found(checker, sample_checklist):
    """
    测试场景：检测到签名

    预期结果：
    - status 为 PASS
    - signature_result 显示检测到签名
    - details 包含完整的统计信息
    """
    # 准备测试数据：文件名包含签名关键词（使用图片格式测试图片检测逻辑）
    documents = [
        create_document("合同_签名页.png"),
    ]

    # 执行检查（仅检查签名）
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "signature"},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "compliance", "check_type 应为 'compliance'"
    assert result.status == CheckStatus.PASS, "检测到签名应为 PASS"
    assert result.details["valid_count"] == 1, "有效文档数应为 1"

    # 验证签名检测结果
    doc_result = result.details["document_results"][0]
    assert doc_result["signature_result"]["found"] is True, "应检测到签名"
    assert doc_result["signature_result"]["confidence"] >= 0.7, "置信度应 >= 0.7"
    assert "reasoning" in doc_result["signature_result"], "结果应包含 reasoning"


@pytest.mark.asyncio
async def test_visual_check_both_found(checker, sample_checklist):
    """
    测试场景：同时检测印章和签名

    预期结果：
    - status 为 VALID
    - 印章和签名都检测到
    """
    # 准备测试数据：文件名同时包含印章和签名关键词（使用图片格式）
    documents = [
        create_document("批复文件_印章_签名.jpg"),
    ]

    # 执行检查（检查印章和签名）
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "both"},
    )

    # 验证结果
    assert result.check_type == "compliance"
    assert result.status == CheckStatus.PASS

    # 验证两种检测结果
    doc_result = result.details["document_results"][0]
    assert doc_result["seal_result"]["found"] is True
    assert doc_result["signature_result"]["found"] is True


@pytest.mark.asyncio
async def test_visual_check_not_found(checker, sample_checklist):
    """
    测试场景：未检测到印章或签名

    预期结果：
    - status 为 FAIL
    - missing_count 为 1
    - issues 列表包含缺失信息
    """
    # 准备测试数据：文件名不包含任何关键词（使用图片格式）
    documents = [
        create_document("普通文档.jpg"),
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "compliance", "check_type 应为 'compliance'"
    assert result.status == CheckStatus.FAIL, "未检测到印章应为 FAIL"
    assert result.details["missing_count"] == 1, "缺失文档数应为 1"
    assert result.details["valid_count"] == 0, "有效文档数应为 0"

    # 验证 issues 列表
    assert isinstance(result.issues, list), "issues 应为列表类型"
    assert len(result.issues) == 1, "应有 1 个 issue"
    assert "document" in result.issues[0], "issue 应包含 document 字段"
    assert "status" in result.issues[0], "issue 应包含 status 字段"
    assert "message" in result.issues[0], "issue 应包含 message 字段"


@pytest.mark.asyncio
async def test_visual_check_unavailable_service(unavailable_visual_client, sample_checklist):
    """
    测试场景：视觉检测服务不可用

    预期结果：
    - status 为 UNAVAILABLE
    - message 提示服务不可用
    - details 包含 reason 字段
    """
    # 创建使用不可用服务的检查器
    checker = VisualChecker(
        visual_client=unavailable_visual_client,
        enabled=True,
    )

    documents = [
        create_document("测试文档.pdf"),
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.status == CheckStatus.UNAVAILABLE, "服务不可用应为 UNAVAILABLE"
    assert "不可用" in result.message, "message 应包含 '不可用'"
    assert "reason" in result.details, "details 应包含 reason 字段"
    assert (
        result.details["reason"] == "visual_client_unavailable"
    ), "reason 应为 visual_client_unavailable"


@pytest.mark.asyncio
async def test_visual_check_disabled(checker, sample_checklist):
    """
    测试场景：视觉检查被禁用

    预期结果：
    - status 为 UNAVAILABLE
    - message 提示已禁用
    - details 包含 reason 字段
    """
    documents = [
        create_document("测试文档.pdf"),
    ]

    # 执行检查（通过配置禁用）
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"enabled": False},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.status == CheckStatus.UNAVAILABLE, "禁用状态应为 UNAVAILABLE"
    assert "禁用" in result.message, "message 应包含 '禁用'"
    assert result.details["reason"] == "disabled_by_config", "reason 应为 disabled_by_config"


@pytest.mark.asyncio
async def test_visual_check_empty_documents(checker, sample_checklist):
    """
    测试场景：文档列表为空

    预期结果：
    - status 为 ERROR
    - message 提示没有可检查的文档
    """
    # 执行检查（空文档列表）
    result = await checker.check(
        documents=[],
        checklist=sample_checklist,
        doc_checks={},
    )

    # ========== 验证结果 ==========
    assert isinstance(result, CheckResult), "返回结果应为 CheckResult 类型"
    assert result.check_type == "compliance", "check_type 应为 'compliance'"
    assert result.status == CheckStatus.ERROR, "空文档列表应为 ERROR"
    assert "没有可检查的文档" in result.message, "message 应包含 '没有可检查的文档'"


@pytest.mark.asyncio
async def test_visual_check_target_documents(checker, sample_checklist):
    """
    测试场景：指定目标文档进行检查

    预期结果：
    - 只检查指定的文档
    - 其他文档被忽略
    """
    documents = [
        create_document("文档A_印章.jpg"),
        create_document("文档B.png"),  # 这个不应该被检查
    ]

    # 执行检查，只检查文档A
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={
            "visual_type": "seal",
            "target_documents": ["文档A_印章.jpg"],
        },
    )

    # 验证结果
    assert result.status == CheckStatus.PASS
    # 只检查了 1 个文档
    assert result.details["total_documents"] == 1
    assert result.details["valid_count"] == 1


@pytest.mark.asyncio
async def test_visual_check_partial_pass(checker, sample_checklist):
    """
    测试场景：部分文档检测通过，部分未通过

    预期结果：
    - status 为 HAS_ISSUES
    - valid_count 和 missing_count 都大于 0
    """
    documents = [
        create_document("文档A_印章.jpg"),  # 有印章
        create_document("文档B.png"),  # 无印章
        create_document("文档C_公章.jpg"),  # 有印章
    ]

    # 执行检查
    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # 验证结果
    assert result.status == CheckStatus.HAS_ISSUES
    assert result.details["valid_count"] == 2
    assert result.details["missing_count"] == 1


@pytest.mark.asyncio
async def test_visual_check_parse_check_type(checker):
    """
    测试场景：解析检查类型配置

    预期结果：
    - 正确解析各种检查类型
    """
    # 测试默认值
    assert checker._parse_check_type({}) == VisualCheckType.BOTH

    # 测试 seal 类型
    assert checker._parse_check_type({"visual_type": "seal"}) == VisualCheckType.SEAL

    # 测试 signature 类型
    assert checker._parse_check_type({"visual_type": "signature"}) == VisualCheckType.SIGNATURE

    # 测试 both 类型
    assert checker._parse_check_type({"visual_type": "both"}) == VisualCheckType.BOTH


@pytest.mark.asyncio
async def test_visual_check_determine_status(checker):
    """
    测试场景：根据检测结果确定状态

    预期结果：
    - 未检测到返回 MISSING
    - 低置信度返回 UNCLEAR
    - 正常检测到返回 VALID
    """
    check_type = VisualCheckType.SEAL

    # 未检测到
    assert (
        checker._determine_status(False, 0.9, check_type) == CheckStatus.MISSING
    ), "未检测到应返回 MISSING"

    # 低置信度
    assert (
        checker._determine_status(True, 0.5, check_type) == CheckStatus.UNCLEAR
    ), "低置信度应返回 UNCLEAR"

    # 正常检测到
    assert (
        checker._determine_status(True, 0.9, check_type) == CheckStatus.VALID
    ), "正常检测到应返回 VALID"


# ============== 新增测试用例 ==============


@pytest.mark.asyncio
async def test_visual_checker_properties(checker):
    """
    测试场景：验证检查器的基本属性

    预期结果：
    - name 属性正确
    - description 属性正确
    - is_available 方法正确
    """
    assert checker.name == "compliance", "检查器名称应为 'compliance'"
    assert isinstance(checker.description, str), "description 应为字符串"
    assert len(checker.description) > 0, "description 不应为空"
    assert (
        "印章" in checker.description
        or "签名" in checker.description
        or "视觉" in checker.description
    ), "description 应描述视觉检查"
    assert checker.is_available() is True, "检查器应可用"


@pytest.mark.asyncio
async def test_visual_check_target_documents_not_found(checker, sample_checklist):
    """
    测试场景：指定的目标文档不存在

    预期结果：
    - status 为 ERROR
    - message 提示未找到目标文档
    """
    documents = [
        create_document("文档A.pdf"),
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={
            "visual_type": "seal",
            "target_documents": ["不存在的文档.pdf"],
        },
    )

    assert result.status == CheckStatus.ERROR, "目标文档不存在应为 ERROR"
    assert "未找到目标文档" in result.message, "message 应包含 '未找到目标文档'"
    assert "requested" in result.details, "details 应包含 requested 字段"
    assert "available" in result.details, "details 应包含 available 字段"


@pytest.mark.asyncio
async def test_visual_check_unclear_result(mock_visual_client, sample_checklist):
    """
    测试场景：检测结果置信度较低

    预期结果：
    - status 为 UNCLEAR
    - unclear_count 为 1
    """

    # 创建返回低置信度的 Mock
    class LowConfidenceMockClient:
        def is_available(self) -> bool:
            return True

        async def detect_seal(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            return {
                "success": True,
                "found": True,
                "confidence": 0.5,  # 低置信度
                "reasoning": "置信度较低",
            }

        async def detect_signature(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            return {
                "success": True,
                "found": False,
                "confidence": 0.5,
                "reasoning": "置信度较低",
            }

    checker = VisualChecker(
        visual_client=LowConfidenceMockClient(),
        pdf_converter=MockPDFConverter(),  # 提供 PDF 转换器
        confidence_threshold=0.7,  # 阈值高于返回的置信度
    )

    documents = [create_document("测试文档.jpg")]  # 使用图片格式避免 PDF 转换

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    assert result.details["unclear_count"] == 1, "应有 1 个不明确结果"


@pytest.mark.asyncio
async def test_visual_check_both_partial(mock_visual_client, sample_checklist):
    """
    测试场景：同时检查印章和签名，但只检测到其中一个

    预期结果：
    - status 为 VALID（至少检测到一个）
    """

    # 创建只检测到印章的 Mock
    class PartialMockClient:
        def is_available(self) -> bool:
            return True

        async def detect_seal(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            return {
                "success": True,
                "found": True,
                "confidence": 0.9,
                "reasoning": "检测到印章",
            }

        async def detect_signature(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            return {
                "success": True,
                "found": False,
                "confidence": 0.9,
                "reasoning": "未检测到签名",
            }

    checker = VisualChecker(
        visual_client=PartialMockClient(),
        pdf_converter=MockPDFConverter(),  # 提供 PDF 转换器
        confidence_threshold=0.7,
    )

    documents = [create_document("测试文档.jpg")]  # 使用图片格式避免 PDF 转换

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "both"},
    )

    # 至少检测到一个，状态应为 VALID
    assert result.status == CheckStatus.PASS, "检测到至少一个应为 PASS"


@pytest.mark.asyncio
async def test_visual_check_error_in_detection(mock_visual_client, sample_checklist):
    """
    测试场景：检测过程中发生错误

    预期结果：
    - status 为 ERROR
    - message 包含错误信息
    """

    # 创建会抛出异常的 Mock
    class ErrorMockClient:
        def is_available(self) -> bool:
            return True

        async def detect_seal(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            raise RuntimeError("检测失败")

        async def detect_signature(
            self, image_path: str, context: Optional[str] = None
        ) -> Dict[str, Any]:
            return {"success": True, "found": False, "confidence": 0.5}

    checker = VisualChecker(
        visual_client=ErrorMockClient(),
        confidence_threshold=0.7,
    )

    documents = [create_document("测试文档.pdf")]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # 检测过程中发生错误
    assert result.details["error_count"] == 1, "应有 1 个错误"


@pytest.mark.asyncio
async def test_visual_check_parse_unknown_type(checker):
    """
    测试场景：解析未知的检查类型

    预期结果：
    - 返回默认类型
    """
    # 传入未知类型
    result = checker._parse_check_type({"visual_type": "unknown_type"})

    # 应返回默认类型
    assert result == VisualCheckType.BOTH, "未知类型应返回默认类型 BOTH"


@pytest.mark.asyncio
async def test_visual_check_multiple_documents_mixed_results(checker, sample_checklist):
    """
    测试场景：多个文档，结果混合

    预期结果：
    - status 为 HAS_ISSUES
    - valid_count 和 missing_count 都大于 0
    """
    documents = [
        create_document("文档A_印章.jpg"),  # 有印章
        create_document("文档B.png"),  # 无印章
        create_document("文档C_公章.jpg"),  # 有印章
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    assert result.status == CheckStatus.HAS_ISSUES, "混合结果应为 HAS_ISSUES"
    assert result.details["valid_count"] == 2, "应有 2 个有效"
    assert result.details["missing_count"] == 1, "应有 1 个缺失"
    assert len(result.issues) == 1, "应有 1 个 issue"


# ============== PDF 文件支持测试 ==============


@pytest.mark.asyncio
async def test_visual_check_pdf_file_with_converter(checker, sample_checklist):
    """
    测试场景：检查 PDF 文件（带 PDF 转换器）

    预期结果：
    - 正确将 PDF 转换为图片并检测
    - status 为 PASS
    """
    documents = [
        create_document("立项批复.pdf"),  # PDF 文件
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    assert isinstance(result, CheckResult)
    assert result.check_type == "compliance"
    # Mock 会检测到印章（因为字节流有效）
    assert result.status == CheckStatus.PASS
    assert result.details["total_documents"] == 1


@pytest.mark.asyncio
async def test_visual_check_pdf_file_without_converter(
    checker_without_pdf_converter, sample_checklist
):
    """
    测试场景：检查 PDF 文件（无 PDF 转换器）

    预期结果：
    - 文档级别返回错误
    - 整体 status 为 ERROR（因为有文档检测失败）
    """
    documents = [
        create_document("立项批复.pdf"),
    ]

    result = await checker_without_pdf_converter.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # 整体状态为 ERROR，因为文档检测失败
    assert result.status == CheckStatus.ERROR
    # 验证文档级别的错误信息
    doc_result = result.details["document_results"][0]
    assert "pdf_converter" in doc_result["message"].lower() or "PDF 转换器" in doc_result["message"]


@pytest.mark.asyncio
async def test_visual_check_pdf_multi_page(checker, sample_checklist):
    """
    测试场景：检查多页 PDF 文件

    预期结果：
    - 检查所有页面
    - 只要有任何一页通过，整体就通过
    """

    # 使用多页转换器
    class MultiPageMockConverter:
        async def convert_to_images(self, file_path_or_bytes: str | bytes) -> List[bytes]:
            # 返回 3 页，其中第 2 页模拟检测到印章
            return [
                b"\x89PNG\r\n\x1a\nPAGE1",  # 第 1 页：无印章
                b"\x89PNG\r\n\x1a\nPAGE2_SEAL",  # 第 2 页：有印章（文件名包含关键词）
                b"\x89PNG\r\n\x1a\nPAGE3",  # 第 3 页：无印章
            ]

    checker_with_multi = VisualChecker(
        visual_client=checker.visual_client,
        pdf_converter=MultiPageMockConverter(),
        enabled=True,
    )

    documents = [
        create_document("多页文档.pdf"),
    ]

    result = await checker_with_multi.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # 应该通过，因为至少有一页检测到
    assert result.status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_visual_check_pdf_with_page_hint(checker, sample_checklist):
    """
    测试场景：检查 PDF 时提供页码提示

    预期结果：
    - 优先检查提示的页码
    """
    documents = [
        create_document("合同.pdf"),
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={
            "visual_type": "seal",
            "page_hint": 2,  # 提示检查第 2 页
        },
    )

    assert isinstance(result, CheckResult)
    # 验证检查完成
    assert result.details["total_documents"] == 1


@pytest.mark.asyncio
async def test_visual_check_mixed_image_and_pdf(checker, sample_checklist):
    """
    测试场景：同时检查图片和 PDF 文件

    预期结果：
    - 正确处理两种类型的文件
    - 汇总结果正确
    """
    documents = [
        create_document("图片_印章.jpg"),  # 图片文件
        create_document("文档.pdf"),  # PDF 文件
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    assert isinstance(result, CheckResult)
    assert result.details["total_documents"] == 2


@pytest.mark.asyncio
async def test_visual_check_unsupported_file_type(checker, sample_checklist):
    """
    测试场景：检查不支持的文件类型

    预期结果：
    - 文档级别返回错误
    - 整体 status 为 ERROR
    """
    documents = [
        create_document("文档.txt"),  # 不支持的类型
    ]

    result = await checker.check(
        documents=documents,
        checklist=sample_checklist,
        doc_checks={"visual_type": "seal"},
    )

    # 整体状态为 ERROR，因为有文档检测失败
    assert result.status == CheckStatus.ERROR
    # 验证文档级别的错误信息
    doc_result = result.details["document_results"][0]
    assert "不支持" in doc_result["message"]


@pytest.mark.asyncio
async def test_is_pdf_file_method(checker):
    """
    测试 _is_pdf_file 方法

    预期结果：
    - 正确识别 PDF 文件
    """
    assert checker._is_pdf_file("document.pdf") is True
    assert checker._is_pdf_file("document.PDF") is True
    assert checker._is_pdf_file("document.Pdf") is True
    assert checker._is_pdf_file("document.jpg") is False
    assert checker._is_pdf_file("document.png") is False


@pytest.mark.asyncio
async def test_is_image_file_method(checker):
    """
    测试 _is_image_file 方法

    预期结果：
    - 正确识别图片文件
    """
    assert checker._is_image_file("document.jpg") is True
    assert checker._is_image_file("document.JPG") is True
    assert checker._is_image_file("document.png") is True
    assert checker._is_image_file("document.jpeg") is True
    assert checker._is_image_file("document.bmp") is True
    assert checker._is_image_file("document.gif") is True
    assert checker._is_image_file("document.pdf") is False
    assert checker._is_image_file("document.docx") is False
