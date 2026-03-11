"""
合规性检查器 - 适配新架构

包装原有的 check_compliance 功能为检查器类
"""

import logging
from typing import Any, Dict, List, Optional

from ..core.checker_base import BaseChecker, CheckResult, CheckStatus
from ..core.document import Document
from ..core.checklist_model import Checklist
from ..tools.compliance import ComplianceChecker as LegacyChecker

logger = logging.getLogger(__name__)


class ComplianceChecker(BaseChecker):
    """
    合规性检查器
    
    检查公章、签字、文件编号等合规要点。
    """
    
    @property
    def name(self) -> str:
        return "compliance"
    
    @property
    def description(self) -> str:
        return "检查公章、签字、文件编号等合规要点"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any]
    ) -> CheckResult:
        """
        执行合规性检查
        
        Args:
            documents: 文档列表
            checklist: 审核清单（用于获取合规要点）
            doc_checks: 检查配置
                - points: 检查要点列表（如 ["公章", "签字", "文号"]）
                - use_visual: 是否启用视觉检查辅助（默认False）
        
        Returns:
            CheckResult: 检查结果
        """
        if not documents:
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.PASS,
                message="没有文档需要检查合规性",
                details={}
            )
        
        # 获取配置
        points = doc_checks.get("points", ["公章", "签字", "文号"])
        # 如果检查要点包含印章/公章/签字，自动启用视觉检查
        visual_points = ["公章", "印章", "章", "签字", "签名", "签署"]
        use_visual = doc_checks.get("use_visual", any(p in visual_points for p in points))
        
        try:
            # 使用原有的检查逻辑，传入 points 配置
            legacy_checker = LegacyChecker(use_visual=use_visual, points=points)
            result = await legacy_checker.check(documents, checklist)
            
            # 转换结果为新的格式
            if result.status.value in ("PASS", "VALID"):
                status = CheckStatus.PASS
            elif result.status.value in ("FAIL", "HAS_ISSUES", "MISSING"):
                status = CheckStatus.FAIL
            else:
                status = CheckStatus.FAIL
            
            # 构建详细信息
            doc_details = []
            for doc_comp in result.details:
                checks = []
                for check in doc_comp.checks:
                    checks.append({
                        "point": check.point,
                        "found": check.found,
                        "status": check.status.value,
                        "value": check.value,
                        "message": check.message
                    })
                
                doc_details.append({
                    "document_name": doc_comp.document_name,
                    "checks": checks
                })
            
            details = {
                "documents": doc_details,
                "points_checked": points
            }
            
            # 构建问题列表
            issues = []
            for doc_comp in result.details:
                for check in doc_comp.checks:
                    if check.status.value in ("FAIL", "MISSING"):
                        issues.append({
                            "type": "compliance_issue",
                            "document": doc_comp.document_name,
                            "point": check.point,
                            "message": check.message
                        })
            
            failed_count = len([i for i in issues if i.get("type") == "compliance_issue"])
            message = f"合规性检查完成: 检查了 {len(documents)} 个文档"
            if failed_count > 0:
                message += f", 发现 {failed_count} 个问题"
            else:
                message += ", 未发现明显问题"
            
            return CheckResult(
                check_type=self.name,
                status=status,
                message=message,
                details=details,
                issues=issues
            )
            
        except Exception as e:
            logger.exception(f"合规性检查失败: {e}")
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {str(e)}",
                details={"error": str(e)}
            )
    
    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证配置"""
        points = config.get("points", [])
        if points and not isinstance(points, list):
            return False, "points 必须是列表"
        return True, ""
