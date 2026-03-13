"""
完整性检查器 - 适配新架构

包装原有的 check_completeness 功能为检查器类
"""

import logging
from typing import Any, Dict, List, Optional

from ..core.checker_base import BaseChecker, CheckResult, CheckStatus
from ..core.document import Document
from ..core.checklist_model import Checklist
from ..tools.completeness import CompletenessChecker as LegacyChecker

logger = logging.getLogger(__name__)


class CompletenessChecker(BaseChecker):
    """
    完整性检查器

    检查文档是否完整上传，支持文件名语义匹配。
    """

    @property
    def name(self) -> str:
        return "completeness"

    @property
    def description(self) -> str:
        return "检查必需文档是否已上传，支持文件名语义匹配"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def check(
        self, documents: List[Document], checklist: Optional[Checklist], doc_checks: Dict[str, Any]
    ) -> CheckResult:
        """
        执行完整性检查

        Args:
            documents: 已上传的文档列表
            checklist: 审核清单
            doc_checks: 检查配置
                - similarity_threshold: 语义匹配阈值（默认0.75）
                - use_semantic: 是否使用语义匹配（默认True）

        Returns:
            CheckResult: 检查结果
        """
        if not checklist:
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message="缺少审核清单，无法执行完整性检查",
                details={},
            )

        # 获取配置参数
        similarity_threshold = doc_checks.get("similarity_threshold", 0.75)
        use_semantic = doc_checks.get("use_semantic", True)

        try:
            # 使用原有的检查逻辑
            legacy_checker = LegacyChecker(
                similarity_threshold=similarity_threshold, use_semantic=use_semantic
            )
            result = await legacy_checker.check(documents, checklist)

            # 转换结果为新的格式
            # 将 Legacy CheckStatus 转换为新的 CheckStatus
            if result.status.value in ("PASS", "VALID"):
                status = CheckStatus.PASS
            elif result.status.value == "FAIL":
                status = CheckStatus.FAIL
            else:
                status = CheckStatus.FAIL

            # 构建详细信息
            details = {
                "total_required": result.total_required,
                "uploaded": result.uploaded,
                "missing": result.missing,
                "matches": [
                    {
                        "document_name": d.document_name,
                        "status": d.status.value,
                        "matched_file": d.matched_file,
                        "match_type": d.match_type.value,
                        "similarity": d.similarity,
                    }
                    for d in result.details
                ],
            }

            # 构建问题列表
            issues = []
            for detail in result.details:
                if detail.status.value in ("MISSING", "INCOMPLETE"):
                    issues.append(
                        {
                            "type": "missing_document",
                            "document": detail.document_name,
                            "message": f"未找到文档: {detail.document_name}",
                        }
                    )

            message = f"完整性检查完成: {result.uploaded}/{result.total_required} 文档已上传"
            if result.missing > 0:
                message += f", 缺失 {result.missing} 个文档"

            return CheckResult(
                check_type=self.name, status=status, message=message, details=details, issues=issues
            )

        except Exception as e:
            logger.exception(f"完整性检查失败: {e}")
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {str(e)}",
                details={"error": str(e)},
            )

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证配置"""
        similarity_threshold = config.get("similarity_threshold", 0.75)
        if not 0 <= similarity_threshold <= 1:
            return False, f"similarity_threshold 必须在 0-1 之间: {similarity_threshold}"
        return True, ""
