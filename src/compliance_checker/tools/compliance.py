"""
compliance.py - 基础合规检查工具
实现 check_compliance MCP 工具
用于检查公章、签字、文件编号等合规要点
"""

import re
import logging
from typing import List, Dict, Optional, Any, Tuple

from ..core.document import Document
from ..core.checklist_model import Checklist, CompliancePoint, CheckMethod
from ..core.result_model import (
    ComplianceResult,
    DocumentCompliance,
    ComplianceCheckItem,
    CheckStatus
)

logger = logging.getLogger(__name__)

# 尝试导入视觉检查模块
try:
    from ..visual.qwen_client import QwenVLClient
    _has_qwen = True
except ImportError:
    _has_qwen = False
    logger.warning("Qwen-VL client not available, visual inspection will be disabled")


# 合规检查关键词
COMPLIANCE_KEYWORDS = {
    "公章": ["公章", "印章", "盖章", "红章", "单位章", "公司章", "局章", "厅章"],
    "签字": ["签字", "签名", "签署", "签章", "手写", "负责人", "法定代表人", "经办人"],
    "文件编号": ["文件编号", "编号", "文号", "批复号", "证书编号", "字号"],
    "日期": ["日期", "签发日期", "发布日期", "印发日期"],
}

# 常见文件编号格式
DOCUMENT_NUMBER_PATTERNS = {
    "standard": r"\d{4}-\d{2,4}",           # 2024-015
    "year_seq": r"\d{4}\d{2,4}号",          # 2024015号
    "dept_year": r"[\u4e00-\u9fa5]+\d{4}\d{2,4}",  # 部门2024015
    "full": r"[\u4e00-\u9fa5]+\[\d{4}\]\d+号",   # 部门[2024]15号
}


class TextComplianceChecker:
    """文本层面合规检查器"""
    
    # 否定词列表
    NEGATION_WORDS = ["没有", "无", "未", "不含", "不存在", "缺乏", "缺失", "缺少"]
    
    def __init__(self):
        self.keywords = COMPLIANCE_KEYWORDS
        self.number_patterns = DOCUMENT_NUMBER_PATTERNS
    
    def _has_negation_context(self, text: str, keyword: str, window: int = 10) -> bool:
        """
        检查关键词附近是否有否定词
        
        Args:
            text: 文本内容
            keyword: 关键词
            window: 检查窗口大小（字符数）
        
        Returns:
            是否有否定上下文
        """
        # 找到所有关键词位置
        for match in re.finditer(re.escape(keyword), text):
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            context = text[start:end]
            
            # 检查否定词
            for neg_word in self.NEGATION_WORDS:
                if neg_word in context:
                    # 确保否定词在关键词之前或紧邻
                    neg_pos = context.find(neg_word)
                    keyword_pos = context.find(keyword)
                    if neg_pos < keyword_pos or abs(neg_pos - keyword_pos) <= 5:
                        return True
        
        return False
    
    def check_seal(self, text: str) -> ComplianceCheckItem:
        """
        检查公章（文本层面）
        
        通过关键词判断文档中是否提及公章相关内容
        同时检测否定词（如"没有印章"表示缺少公章）
        """
        seal_keywords = self.keywords["公章"]
        found_keywords = []
        has_negation = False
        
        for keyword in seal_keywords:
            if keyword in text:
                # 检查是否有否定上下文
                if self._has_negation_context(text, keyword):
                    has_negation = True
                else:
                    found_keywords.append(keyword)
        
        # 如果所有匹配都有否定上下文，视为未找到
        if has_negation and not found_keywords:
            context = self._find_context(text, seal_keywords[0], window=50)
            return ComplianceCheckItem(
                point="公章",
                found=False,
                status=CheckStatus.MISSING,
                evidence=context,
                message="文本中提到公章但表示缺少或未盖章"
            )
        
        if found_keywords:
            # 查找上下文
            context = self._find_context(text, found_keywords[0], window=50)
            return ComplianceCheckItem(
                point="公章",
                found=True,
                status=CheckStatus.PASS,
                evidence=context,
                message=f"发现公章相关关键词: {', '.join(found_keywords[:3])}"
            )
        
        return ComplianceCheckItem(
            point="公章",
            found=False,
            status=CheckStatus.MISSING,
            message="文本中未发现公章相关关键词，建议进行视觉检查"
        )
    
    def check_signature(self, text: str) -> ComplianceCheckItem:
        """
        检查签字（文本层面）
        
        通过关键词判断文档中是否提及签字相关内容
        同时检测否定词（如"未签署"表示缺少签字）
        """
        sig_keywords = self.keywords["签字"]
        found_keywords = []
        has_negation = False
        
        for keyword in sig_keywords:
            if keyword in text:
                # 检查是否有否定上下文
                if self._has_negation_context(text, keyword):
                    has_negation = True
                else:
                    found_keywords.append(keyword)
        
        # 如果所有匹配都有否定上下文，视为未找到
        if has_negation and not found_keywords:
            context = self._find_context(text, sig_keywords[0], window=50)
            return ComplianceCheckItem(
                point="签字",
                found=False,
                status=CheckStatus.MISSING,
                evidence=context,
                message="文本中提到签字但表示缺少或未签署"
            )
        
        if found_keywords:
            context = self._find_context(text, found_keywords[0], window=50)
            return ComplianceCheckItem(
                point="签字",
                found=True,
                status=CheckStatus.PASS,
                evidence=context,
                message=f"发现签字相关关键词: {', '.join(found_keywords[:3])}"
            )
        
        return ComplianceCheckItem(
            point="签字",
            found=False,
            status=CheckStatus.MISSING,
            message="文本中未发现签字相关关键词，建议进行视觉检查"
        )
    
    def check_document_number(self, text: str, pattern: Optional[str] = None) -> ComplianceCheckItem:
        """
        检查文件编号
        
        Args:
            text: 文档文本
            pattern: 自定义正则表达式模式（可选）
        """
        # 编号关键词上下文
        number_keywords = self.keywords["文件编号"]
        
        # 使用自定义模式或默认模式
        if pattern:
            patterns = [("custom", pattern)]
        else:
            patterns = list(self.number_patterns.items())
        
        # 优先在关键词附近搜索
        for keyword in number_keywords:
            # 检查是否有否定上下文
            if self._has_negation_context(text, keyword):
                continue
            
            # 构建关键词上下文搜索模式
            context_pattern = rf"{keyword}[：:\s]*([\w\-\[\]\(\)（）]+)"
            match = re.search(context_pattern, text)
            if match:
                value = match.group(1).strip()
                # 验证是否符合某种编号格式
                for name, num_pattern in patterns:
                    if re.search(num_pattern, value):
                        return ComplianceCheckItem(
                            point="文件编号",
                            found=True,
                            status=CheckStatus.PASS,
                            value=value,
                            pattern=num_pattern,
                            evidence=match.group(0),
                            message=f"发现文件编号: {value}"
                        )
                # 即使格式不匹配，也记录找到的编号
                return ComplianceCheckItem(
                    point="文件编号",
                    found=True,
                    status=CheckStatus.WARNING,
                    value=value,
                    pattern=context_pattern,
                    evidence=match.group(0),
                    message=f"发现疑似文件编号: {value}，但格式未完全匹配"
                )
        
        # 全文搜索编号格式
        for name, num_pattern in patterns:
            matches = re.finditer(num_pattern, text)
            for match in matches:
                value = match.group(0)
                # 验证周围是否有编号相关上下文
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                context = text[start:end]
                
                # 检查是否有否定词
                has_negation = any(self._has_negation_context(text, kw) for kw in number_keywords)
                if has_negation:
                    continue
                
                if any(kw in context for kw in number_keywords):
                    return ComplianceCheckItem(
                        point="文件编号",
                        found=True,
                        status=CheckStatus.PASS,
                        value=value,
                        pattern=num_pattern,
                        evidence=context,
                        message=f"发现文件编号: {value}"
                    )
        
        return ComplianceCheckItem(
            point="文件编号",
            found=False,
            status=CheckStatus.MISSING,
            pattern=pattern or list(self.number_patterns.values())[0],
            message="未发现文件编号"
        )
    
    def check_date(self, text: str) -> ComplianceCheckItem:
        """检查日期是否存在"""
        date_keywords = self.keywords["日期"]
        found_keywords = []
        has_negation = False
        
        for keyword in date_keywords:
            if keyword in text:
                # 检查是否有否定上下文
                if self._has_negation_context(text, keyword):
                    has_negation = True
                else:
                    found_keywords.append(keyword)
        
        # 如果所有匹配都有否定上下文，视为未找到
        if has_negation and not found_keywords:
            context = self._find_context(text, date_keywords[0], window=50)
            return ComplianceCheckItem(
                point="日期",
                found=False,
                status=CheckStatus.WARNING,
                evidence=context,
                message="文本中提到日期但表示缺少或无日期"
            )
        
        if found_keywords:
            context = self._find_context(text, found_keywords[0], window=50)
            return ComplianceCheckItem(
                point="日期",
                found=True,
                status=CheckStatus.PASS,
                evidence=context,
                message="文档中包含日期信息"
            )
        
        return ComplianceCheckItem(
            point="日期",
            found=False,
            status=CheckStatus.WARNING,
            message="未发现明确的日期信息"
        )
    
    def _find_context(self, text: str, keyword: str, window: int = 50) -> str:
        """查找关键词的上下文"""
        idx = text.find(keyword)
        if idx == -1:
            return ""
        
        start = max(0, idx - window)
        end = min(len(text), idx + len(keyword) + window)
        return text[start:end].replace("\n", " ")


class VisualComplianceChecker:
    """视觉层面合规检查器 - 使用 Qwen-VL 进行印章/签名检测"""
    
    def __init__(self):
        self.client = QwenVLClient() if _has_qwen else None
    
    def is_available(self) -> bool:
        """检查视觉检查是否可用"""
        return self.client is not None and self.client.is_available()
    
    async def check_seal_visual(self, document: Document) -> Optional[ComplianceCheckItem]:
        """
        使用视觉模型检查公章
        
        Args:
            document: 文档对象
            
        Returns:
            检查结果或 None（如果视觉检查不可用）
        """
        if not self.is_available():
            return None
        
        if document.type != "pdf":
            return None
        
        try:
            # 将 PDF 第一页转为图片进行检查
            import asyncio
            from ..parsers.pdf_parser import PDFParser
            
            parser = PDFParser()
            # 获取 PDF 截图
            screenshot_path = await self._get_document_screenshot(document.path)
            if not screenshot_path:
                return None
            
            # 使用 Qwen-VL 检查公章
            prompt = """请仔细检查这张文档图片，回答以下问题：
1. 文档中是否有红色的圆形或椭圆形公章/印章？
2. 印章是否清晰可见？
3. 印章位于文档的什么位置（如右下角、左下角等）？

请以JSON格式回答：
{
    "has_seal": true/false,
    "is_clear": true/false,
    "location": "位置描述",
    "confidence": 0-1之间的置信度,
    "reasoning": "判断理由"
}"""
            
            result = await self.client.chat(screenshot_path, prompt)
            
            if result.get("success"):
                content = result.get("content", "")
                # 解析 JSON 响应
                try:
                    import json
                    # 尝试从响应中提取 JSON
                    json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                    if json_match:
                        visual_result = json.loads(json_match.group())
                        has_seal = visual_result.get("has_seal", False)
                        confidence = visual_result.get("confidence", 0.5)
                        reasoning = visual_result.get("reasoning", "")
                        
                        if has_seal and confidence > 0.6:
                            return ComplianceCheckItem(
                                point="公章(视觉)",
                                found=True,
                                status=CheckStatus.PASS,
                                evidence=f"视觉检测结果: {reasoning}",
                                message=f"视觉模型检测到公章，置信度: {confidence:.2f}"
                            )
                        else:
                            return ComplianceCheckItem(
                                point="公章(视觉)",
                                found=False,
                                status=CheckStatus.MISSING,
                                evidence=f"视觉检测结果: {reasoning}",
                                message=f"视觉模型未检测到公章，置信度: {confidence:.2f}"
                            )
                except json.JSONDecodeError:
                    pass
            
            return ComplianceCheckItem(
                point="公章(视觉)",
                found=False,
                status=CheckStatus.UNCLEAR,
                message=f"视觉检查无法确定: {result.get('reasoning', '未知错误')}"
            )
            
        except Exception as e:
            logger.warning(f"视觉公章检查失败: {e}")
            return None
    
    async def check_signature_visual(self, document: Document) -> Optional[ComplianceCheckItem]:
        """
        使用视觉模型检查签名
        
        Args:
            document: 文档对象
            
        Returns:
            检查结果或 None（如果视觉检查不可用）
        """
        if not self.is_available():
            return None
        
        if document.type != "pdf":
            return None
        
        try:
            screenshot_path = await self._get_document_screenshot(document.path)
            if not screenshot_path:
                return None
            
            prompt = """请仔细检查这张文档图片，回答以下问题：
1. 文档中是否有手写签名或签字？
2. 签名是否清晰可见？
3. 签名位于文档的什么位置？

请以JSON格式回答：
{
    "has_signature": true/false,
    "is_clear": true/false,
    "location": "位置描述",
    "confidence": 0-1之间的置信度,
    "reasoning": "判断理由"
}"""
            
            result = await self.client.chat(screenshot_path, prompt)
            
            if result.get("success"):
                content = result.get("content", "")
                try:
                    import json
                    json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                    if json_match:
                        visual_result = json.loads(json_match.group())
                        has_sig = visual_result.get("has_signature", False)
                        confidence = visual_result.get("confidence", 0.5)
                        reasoning = visual_result.get("reasoning", "")
                        
                        if has_sig and confidence > 0.6:
                            return ComplianceCheckItem(
                                point="签字(视觉)",
                                found=True,
                                status=CheckStatus.PASS,
                                evidence=f"视觉检测结果: {reasoning}",
                                message=f"视觉模型检测到签名，置信度: {confidence:.2f}"
                            )
                        else:
                            return ComplianceCheckItem(
                                point="签字(视觉)",
                                found=False,
                                status=CheckStatus.MISSING,
                                evidence=f"视觉检测结果: {reasoning}",
                                message=f"视觉模型未检测到签名，置信度: {confidence:.2f}"
                            )
                except json.JSONDecodeError:
                    pass
            
            return ComplianceCheckItem(
                point="签字(视觉)",
                found=False,
                status=CheckStatus.UNCLEAR,
                message=f"视觉检查无法确定: {result.get('reasoning', '未知错误')}"
            )
            
        except Exception as e:
            logger.warning(f"视觉签名检查失败: {e}")
            return None
    
    async def _get_document_screenshot(self, pdf_path: str) -> Optional[str]:
        """获取 PDF 文档截图"""
        try:
            import fitz
            import tempfile
            import os
            
            # 打开 PDF
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                return None
            
            # 获取第一页
            page = doc[0]
            
            # 渲染为图片
            mat = fitz.Matrix(2, 2)  # 2x 缩放以获得更清晰的图片
            pix = page.get_pixmap(matrix=mat)
            
            # 保存临时文件
            temp_dir = tempfile.gettempdir()
            screenshot_path = os.path.join(temp_dir, f"compliance_check_{os.path.basename(pdf_path)}.png")
            pix.save(screenshot_path)
            
            doc.close()
            return screenshot_path
            
        except Exception as e:
            logger.warning(f"生成文档截图失败: {e}")
            return None


class ComplianceChecker:
    """合规检查器"""
    
    def __init__(self, use_visual: bool = False, points: Optional[List[str]] = None):
        """
        初始化检查器
        
        Args:
            use_visual: 是否启用视觉检查辅助
            points: 自定义检查要点列表，None 使用默认值
        """
        self.text_checker = TextComplianceChecker()
        self.visual_checker = VisualComplianceChecker()
        self.use_visual = use_visual
        self.points = points  # 保存自定义检查要点
    
    async def check_with_rules(self, document: Document, compliance_points: List[CompliancePoint]) -> DocumentCompliance:
        """
        根据指定的合规要点进行检查
        
        Args:
            document: 文档对象
            compliance_points: 合规要点列表
            
        Returns:
            单个文档的合规检查结果
        """
        text = document.content
        checks: List[ComplianceCheckItem] = []
        
        for point in compliance_points:
            check_item = None
            visual_check_item = None
            
            # 根据检查方法选择检查方式
            if point.check_method in (CheckMethod.TEXT, CheckMethod.BOTH):
                if point.point == "公章":
                    check_item = self.text_checker.check_seal(text)
                elif point.point == "签字":
                    check_item = self.text_checker.check_signature(text)
                elif point.point == "文件编号":
                    check_item = self.text_checker.check_document_number(text, point.pattern)
                elif point.point == "日期":
                    check_item = self.text_checker.check_date(text)
                else:
                    # 通用关键词检查
                    check_item = self._check_generic(text, point)
            
            # 如果需要视觉检查
            if point.check_method in (CheckMethod.VISUAL, CheckMethod.BOTH):
                # 如果启用了视觉检查且文本检查未通过或要求视觉确认
                if self.use_visual and self.visual_checker.is_available():
                    if point.point in ["公章", "印章"]:
                        visual_check_item = await self.visual_checker.check_seal_visual(document)
                    elif point.point in ["签字", "签名", "签署"]:
                        visual_check_item = await self.visual_checker.check_signature_visual(document)
                    
                    # 如果视觉检查有结果，优先使用视觉检查结果
                    if visual_check_item:
                        checks.append(visual_check_item)
                        # 如果文本检查也有结果，保留文本检查作为参考
                        if check_item:
                            check_item.point = f"{check_item.point}(文本)"
                            checks.append(check_item)
                        check_item = None  # 已添加，避免重复
                else:
                    # 视觉检查未启用或不可用，标记需要视觉检查
                    # 无论文本检查是否通过，都需要视觉确认，标记为 UNCLEAR
                    if check_item:
                        check_item.message += " [建议启用视觉检查确认]"
                        if check_item.status == CheckStatus.PASS:
                            check_item.status = CheckStatus.UNCLEAR
                    else:
                        check_item = ComplianceCheckItem(
                            point=point.point,
                            found=False,
                            status=CheckStatus.UNCLEAR,
                            message="建议启用视觉检查确认" + (" (QWEN_API_KEY未配置)" if not self.visual_checker.is_available() else ""),
                            pattern=point.pattern
                        )
            
            if check_item:
                checks.append(check_item)
        
        return DocumentCompliance(
            document_name=document.name,
            file_path=document.path,
            checks=checks
        )
    
    def _check_generic(self, text: str, point: CompliancePoint) -> ComplianceCheckItem:
        """通用检查逻辑"""
        search_term = point.search_context or point.point
        
        if search_term in text:
            context = self.text_checker._find_context(text, search_term, window=50)
            return ComplianceCheckItem(
                point=point.point,
                found=True,
                status=CheckStatus.PASS,
                evidence=context,
                message=f"发现关键词: {search_term}"
            )
        
        return ComplianceCheckItem(
            point=point.point,
            found=False,
            status=CheckStatus.MISSING,
            message=f"未发现关键词: {search_term}"
        )
    
    async def check_document(self, document: Document, checklist: Optional[Checklist] = None) -> DocumentCompliance:
        """
        检查单个文档的合规性
        
        Args:
            document: 文档对象
            checklist: 审核清单（用于获取合规要点）
            
        Returns:
            单个文档的合规检查结果
        """
        # 如果提供了清单，尝试匹配文档对应的合规要点
        if checklist:
            for req_doc in checklist.required_documents:
                # 匹配文档
                is_match = (
                    req_doc.name in document.name or
                    any(alias in document.name for alias in req_doc.aliases)
                )
                
                if is_match and req_doc.compliance_points:
                    return await self.check_with_rules(document, req_doc.compliance_points)
        
        # 优先使用传入的自定义 points 配置
        if self.points:
            custom_points = []
            for p in self.points:
                # 对于印章/公章/签字等，自动使用视觉检查
                if p in ["公章", "印章", "章"]:
                    custom_points.append(CompliancePoint(point=p, required=True, check_method=CheckMethod.VISUAL))
                elif p in ["签字", "签名", "签署"]:
                    custom_points.append(CompliancePoint(point=p, required=True, check_method=CheckMethod.VISUAL))
                else:
                    custom_points.append(CompliancePoint(point=p, required=True, check_method=CheckMethod.TEXT))
            return await self.check_with_rules(document, custom_points)
        
        # 默认检查：公章、签字、文件编号、日期
        default_points = [
            CompliancePoint(point="公章", required=True, check_method=CheckMethod.BOTH),
            CompliancePoint(point="签字", required=True, check_method=CheckMethod.BOTH),
            CompliancePoint(point="文件编号", required=True, check_method=CheckMethod.TEXT),
            CompliancePoint(point="日期", required=True, check_method=CheckMethod.TEXT),
        ]
        
        return await self.check_with_rules(document, default_points)
    
    async def check(self, documents: List[Document], checklist: Optional[Checklist] = None) -> ComplianceResult:
        """
        执行合规性检查
        
        Args:
            documents: 文档列表
            checklist: 审核清单（可选）
            
        Returns:
            合规性检查结果
        """
        details: List[DocumentCompliance] = []
        has_issues = False
        
        for doc in documents:
            doc_compliance = await self.check_document(doc, checklist)
            details.append(doc_compliance)
            
            # 检查是否有失败项
            failed_checks = doc_compliance.get_failed_checks()
            if failed_checks:
                has_issues = True
        
        # 确定整体状态
        status = CheckStatus.HAS_ISSUES if has_issues else CheckStatus.PASS
        
        return ComplianceResult(
            status=status,
            details=details
        )


async def check_compliance(
    documents: List[Document],
    checklist: Optional[Checklist] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
    use_visual: bool = False
) -> ComplianceResult:
    """
    基础合规性核对（MCP工具入口）
    
    功能：
    - 检查公章、签字等合规要点（文本层面）
    - 文件编号格式验证（正则匹配）
    - 调用视觉检查辅助（可选）
    
    Args:
        documents: 文档列表
        checklist: 审核清单（用于获取合规要点）
        rules: 自定义合规规则列表（可选）
        use_visual: 是否启用视觉检查辅助
        
    Returns:
        合规性检查结果
        
    Example:
        {
            "status": "HAS_ISSUES",
            "details": [
                {
                    "document_name": "立项批复",
                    "file_path": "/data/立项批复.pdf",
                    "checks": [
                        {"point": "公章", "found": true, "evidence": "..."},
                        {"point": "签字", "found": false, "status": "MISSING"},
                        {"point": "文件编号", "found": true, "value": "2024-015"}
                    ]
                }
            ]
        }
    """
    checker = ComplianceChecker(use_visual=use_visual)
    return await checker.check(documents, checklist)
