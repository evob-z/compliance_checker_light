"""
检查器注册表模块

管理所有检查器的注册和发现
"""

import logging
import threading
from typing import Dict, List, Optional, Set

from .checker_base import BaseChecker, UnavailableChecker

logger = logging.getLogger(__name__)


class CheckerRegistry:
    """
    检查器注册表 - 单例模式（线程安全）
    
    管理所有检查器的注册、发现和获取。
    支持标记未实现的功能，实现优雅降级。
    
    使用双重检查锁定确保线程安全。
    """
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # 双重检查锁定
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 确保初始化只执行一次
        if not CheckerRegistry._initialized:
            with CheckerRegistry._lock:
                if not CheckerRegistry._initialized:
                    self._checkers: Dict[str, BaseChecker] = {}
                    self._unavailable_checkers: Set[str] = set()
                    CheckerRegistry._initialized = True
    
    def register(self, checker: BaseChecker):
        """
        注册检查器
        
        Args:
            checker: 检查器实例
        """
        self._checkers[checker.name] = checker
        logger.info(f"✓ 注册检查器: {checker.name} v{checker.version}")
    
    def register_unavailable(self, check_type: str):
        """
        标记某检查类型为未实现（开发占位）
        
        Args:
            check_type: 检查类型名称
        """
        self._unavailable_checkers.add(check_type)
        logger.info(f"○ 标记待开发: {check_type}")
    
    def get(self, check_type: str) -> BaseChecker:
        """
        获取检查器
        
        获取逻辑：
        - 已注册且可用 → 返回检查器
        - 已注册但不可用 → 返回 UnavailableChecker
        - 标记为未实现 → 返回 UnavailableChecker
        - 未知类型 → 返回 UnavailableChecker
        
        Args:
            check_type: 检查类型名称
            
        Returns:
            BaseChecker: 检查器实例或 UnavailableChecker
        """
        if check_type in self._checkers:
            checker = self._checkers[check_type]
            if checker.is_available():
                return checker
            else:
                logger.debug(f"检查器 {check_type} 不可用")
                return UnavailableChecker(check_type)
        
        if check_type in self._unavailable_checkers:
            return UnavailableChecker(check_type)
        
        # 完全未知的检查类型
        logger.warning(f"未知检查类型: {check_type}")
        return UnavailableChecker(check_type)
    
    def list_available(self) -> List[str]:
        """
        列出所有可用检查器
        
        Returns:
            可用检查器名称列表
        """
        return [
            name for name, checker in self._checkers.items()
            if checker.is_available()
        ]
    
    def list_all(self) -> Dict[str, str]:
        """
        列出所有检查器状态
        
        Returns:
            检查器名称到状态的映射
            状态值: "available", "unavailable", "not_implemented"
        """
        result = {}
        for name, checker in self._checkers.items():
            result[name] = "available" if checker.is_available() else "unavailable"
        for name in self._unavailable_checkers:
            result[name] = "not_implemented"
        return result
    
    def unregister(self, check_type: str):
        """
        注销检查器
        
        Args:
            check_type: 检查类型名称
        """
        if check_type in self._checkers:
            del self._checkers[check_type]
            logger.info(f"✗ 注销检查器: {check_type}")
        if check_type in self._unavailable_checkers:
            self._unavailable_checkers.discard(check_type)
    
    def clear(self):
        """清空所有注册"""
        self._checkers.clear()
        self._unavailable_checkers.clear()
        logger.info("✗ 清空所有检查器注册")


def get_initialized_registry() -> CheckerRegistry:
    """
    初始化并返回配置好的注册表
    
    此函数会：
    1. 创建注册表实例
    2. 注册所有已实现的检查器
    3. 标记已规划但未实现的功能
    
    Returns:
        初始化好的 CheckerRegistry 实例
    """
    registry = CheckerRegistry()
    
    # 注册已实现的检查器
    try:
        from ..checkers.completeness_checker import CompletenessChecker
        registry.register(CompletenessChecker())
    except ImportError as e:
        logger.warning(f"CompletenessChecker 未注册: {e}")
        registry.register_unavailable("completeness")
    
    try:
        from ..checkers.timeliness_checker import TimelinessChecker
        registry.register(TimelinessChecker())
    except ImportError as e:
        logger.warning(f"TimelinessChecker 未注册: {e}")
        registry.register_unavailable("timeliness")
    
    try:
        from ..checkers.compliance_checker import ComplianceChecker
        registry.register(ComplianceChecker())
    except ImportError as e:
        logger.warning(f"ComplianceChecker 未注册: {e}")
        registry.register_unavailable("compliance")
    
    try:
        from ..checkers.visual_checker import VisualChecker
        registry.register(VisualChecker())
    except ImportError as e:
        logger.warning(f"VisualChecker 未注册: {e}")
        registry.register_unavailable("visual")
    
    # 标记已规划但未实现的功能（占位）
    registry.register_unavailable("authenticity")      # 真实性检查
    registry.register_unavailable("cross_reference")   # 交叉核对
    registry.register_unavailable("blockchain_verify") # 区块链验证
    registry.register_unavailable("ai_content_check")  # AI内容检测
    
    return registry
