"""
视觉检查器 - 适配新架构

包装原有的 visual_inspection 功能为检查器类
"""

import logging
from typing import Any, Dict, List, Optional

from ..core.checker_base import BaseChecker, CheckResult, CheckStatus
from ..core.document import Document
from ..core.checklist_model import Checklist
from ..tools.visual import VisualInspector

logger = logging.getLogger(__name__)


class VisualChecker(BaseChecker):
    """
    视觉检查器

    使用视觉模型检查文档中的印章、签名等视觉元素。
    """

    @property
    def name(self) -> str:
        return "visual"

    @property
    def description(self) -> str:
        return "使用视觉模型检测印章、签名等视觉元素"

    @property
    def version(self) -> str:
        return "1.0.0"

    def is_available(self) -> bool:
        """检查视觉检查是否可用（需要Qwen-VL API配置）"""
        try:
            inspector = VisualInspector()
            return inspector.qwen_client.is_available()
        except Exception:
            return False

    async def check(
        self, documents: List[Document], checklist: Optional[Checklist], doc_checks: Dict[str, Any]
    ) -> CheckResult:
        """
        执行视觉检查

        Args:
            documents: 文档列表
            checklist: 审核清单
            doc_checks: 检查配置
                - target: 检查目标 ("seal" | "signature" | "both")
                - search_context: OCR定位关键词（如"公章"）
                - page_hint: 建议页码（从0开始）

        Returns:
            CheckResult: 检查结果
        """
        if not documents:
            return CheckResult(
                check_type=self.name, status=CheckStatus.PASS, message="没有文档需要视觉检查", details={}
            )

        # 获取配置
        target = doc_checks.get("target", "both")
        search_context = doc_checks.get("search_context")
        page_hint = doc_checks.get("page_hint")

        # 检查可用性
        if not self.is_available():
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.UNAVAILABLE,
                message="视觉检查不可用，请配置 QWEN_API_KEY 环境变量",
                details={"reason": "API未配置", "setup_guide": "设置 QWEN_API_KEY 和 QWEN_BASE_URL 环境变量"},
            )

        try:
            inspector = VisualInspector()

            # 对每个文档执行视觉检查
            doc_results = []
            all_issues = []
            passed_count = 0
            failed_count = 0

            for doc in documents:
                # 只检查PDF和图像文件
                if not doc.path.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                    continue

                result = await inspector.inspect(
                    document_path=doc.path,
                    check_type=target,
                    search_context=search_context,
                    page_hint=page_hint,
                )

                doc_results.append(
                    {
                        "document_name": doc.name,
                        "found": result.get("found", False),
                        "confidence": result.get("confidence", 0.0),
                        "location": result.get("location"),
                        "screenshot_path": result.get("screenshot_path"),
                        "reasoning": result.get("reasoning", ""),
                        "error": result.get("error"),
                    }
                )

                if result.get("found", False):
                    passed_count += 1
                else:
                    failed_count += 1
                    all_issues.append(
                        {
                            "type": "visual_check_failed",
                            "document": doc.name,
                            "target": target,
                            "message": result.get("reasoning", "未找到目标视觉元素"),
                        }
                    )

            # 确定状态
            if failed_count == 0:
                status = CheckStatus.PASS
            elif passed_count == 0:
                status = CheckStatus.FAIL
            else:
                status = CheckStatus.FAIL  # 部分失败也算失败

            details = {
                "documents_checked": len(doc_results),
                "passed": passed_count,
                "failed": failed_count,
                "target": target,
                "results": doc_results,
            }

            message = f"视觉检查完成: 检查了 {len(doc_results)} 个文档"
            if passed_count > 0:
                message += f", {passed_count} 个通过"
            if failed_count > 0:
                message += f", {failed_count} 个未通过"

            return CheckResult(
                check_type=self.name,
                status=status,
                message=message,
                details=details,
                issues=all_issues,
            )

        except Exception as e:
            logger.exception(f"视觉检查失败: {e}")
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {str(e)}",
                details={"error": str(e)},
            )

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证配置"""
        target = config.get("target", "both")
        valid_targets = ["seal", "signature", "both"]
        if target not in valid_targets:
            return False, f"target 必须是 {valid_targets} 之一: {target}"
        return True, ""
