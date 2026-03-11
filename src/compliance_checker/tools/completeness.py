"""
完整性检查工具
实现 check_completeness MCP 工具
"""

import os
import re
import asyncio
from typing import List, Dict, Optional, Any
import logging

from compliance_checker.core.document import Document
from compliance_checker.core.checklist_model import Checklist, RequiredDocument
from compliance_checker.core.result_model import (
    CompletenessResult,
    DocumentMatch,
    CheckStatus,
    MatchType
)

logger = logging.getLogger(__name__)


class LLMSemanticMatcher:
    """语义匹配器 - 使用 LLM 嵌入模型计算文件名相似度"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self._client = None
        self._cache = {}  # 简单的嵌入缓存
    
    def _get_client(self):
        """延迟加载 LLM 客户端"""
        if self._client is None:
            try:
                from ..llm.client import get_llm_client
                self._client = get_llm_client()
            except Exception as e:
                logger.warning(f"LLM 客户端初始化失败: {e}")
                raise
        return self._client
    
    async def _get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量
        
        使用 LLM API 的嵌入功能（如果支持），否则使用简单的字符级特征
        """
        # 检查缓存
        if text in self._cache:
            return self._cache[text]
        
        try:
            client = self._get_client()
            # 尝试使用嵌入 API
            # 使用专门的嵌入模型（ DashScope 的 text-embedding-v1 ）
            embed_model = os.getenv("EMBED_MODEL", "text-embedding-v1")
            response = await client.client.embeddings.create(
                model=embed_model,
                input=text
            )
            embedding = response.data[0].embedding
            self._cache[text] = embedding
            return embedding
        except Exception as e:
            logger.debug(f"嵌入 API 调用失败，使用备用方法: {e}")
            # 备用：使用简单的字符级特征
            return self._simple_embedding(text)
    
    def _simple_embedding(self, text: str) -> List[float]:
        """
        简单的字符级嵌入（备用方法）
        
        基于字符 n-gram 频率的简化嵌入
        """
        text = text.lower()
        # 使用字符 trigram 作为特征
        features = {}
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            features[trigram] = features.get(trigram, 0) + 1
        
        # 转换为固定长度的向量
        import hashlib
        vector = [0.0] * 128
        for trigram, count in features.items():
            idx = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % 128
            vector[idx] = count / len(text)
        
        # 归一化
        norm = sum(x**2 for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]
        
        return vector
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a**2 for a in vec1) ** 0.5
        norm2 = sum(b**2 for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
    
    async def calculate_similarity(self, file_name: str, target_names: List[str]) -> float:
        """
        计算文件名与目标名称的语义相似度
        
        Args:
            file_name: 实际文件名
            target_names: 清单名称及别名列表
            
        Returns:
            最高相似度分数 (0-1)
        """
        if not target_names:
            return 0.0
        
        try:
            file_embedding = await self._get_embedding(file_name)
            
            max_similarity = 0.0
            for target in target_names:
                target_embedding = await self._get_embedding(target)
                similarity = self._cosine_similarity(file_embedding, target_embedding)
                max_similarity = max(max_similarity, similarity)
            
            return max_similarity
        except Exception as e:
            logger.warning(f"语义相似度计算失败: {e}")
            return 0.0
    
    async def find_best_match(self, file_name: str, target_names: List[str]) -> tuple:
        """
        找到最佳匹配
        
        Returns:
            (最佳匹配名称, 相似度分数)
        """
        if not target_names:
            return None, 0.0
        
        try:
            file_embedding = await self._get_embedding(file_name)
            
            best_match = None
            best_similarity = 0.0
            
            for target in target_names:
                target_embedding = await self._get_embedding(target)
                similarity = self._cosine_similarity(file_embedding, target_embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = target
            
            return best_match, best_similarity
        except Exception as e:
            logger.warning(f"最佳匹配查找失败: {e}")
            return None, 0.0


class CompletenessChecker:
    """完整性检查器"""
    
    def __init__(self, similarity_threshold: float = 0.75, use_semantic: bool = True):
        """
        初始化检查器
        
        Args:
            similarity_threshold: 语义匹配阈值（默认0.75）
            use_semantic: 是否使用语义匹配
        """
        self.similarity_threshold = similarity_threshold
        self.use_semantic = use_semantic
        self._semantic_matcher: Optional[LLMSemanticMatcher] = None
        
        if self.use_semantic:
            try:
                self._semantic_matcher = LLMSemanticMatcher()
            except Exception as e:
                logger.warning(f"语义匹配器初始化失败: {e}")
                self.use_semantic = False
    
    def _exact_match(self, file_name: str, required_doc: RequiredDocument) -> Optional[DocumentMatch]:
        """
        精确匹配检查
        
        匹配逻辑：
        1. 文件名包含清单名称
        2. 文件名包含任一别名
        3. 去除扩展名后匹配
        """
        names = [required_doc.name] + required_doc.aliases
        clean_file_name = re.sub(r'\.(pdf|docx?|jpg|jpeg|png|tiff|bmp)$', '', file_name, flags=re.IGNORECASE)
        
        for name in names:
            # 直接包含匹配
            if name in file_name:
                return DocumentMatch(
                    document_name=required_doc.name,
                    status=CheckStatus.VALID,
                    matched_file=file_name,
                    match_type=MatchType.EXACT,
                    similarity=1.0,
                    requirement="必须上传"
                )
            
            # 清理后匹配
            clean_name = re.sub(r'\.(pdf|docx?|jpg|jpeg|png|tiff|bmp)$', '', name, flags=re.IGNORECASE)
            if clean_name in clean_file_name or clean_file_name in clean_name:
                return DocumentMatch(
                    document_name=required_doc.name,
                    status=CheckStatus.VALID,
                    matched_file=file_name,
                    match_type=MatchType.ALIAS,
                    similarity=0.95,
                    requirement="必须上传"
                )
        
        return None
    
    async def _semantic_match(self, file_name: str, required_doc: RequiredDocument) -> Optional[DocumentMatch]:
        """语义匹配检查"""
        if not self.use_semantic or self._semantic_matcher is None:
            return None
        
        names = [required_doc.name] + required_doc.aliases
        
        try:
            best_match, similarity = await self._semantic_matcher.find_best_match(file_name, names)
            
            if similarity >= self.similarity_threshold:
                return DocumentMatch(
                    document_name=required_doc.name,
                    status=CheckStatus.VALID,
                    matched_file=file_name,
                    match_type=MatchType.SEMANTIC,
                    similarity=round(similarity, 2),
                    requirement="必须上传"
                )
        except Exception as e:
            logger.warning(f"语义匹配失败: {e}")
        
        return None
    
    async def match_document(self, file_name: str, required_doc: RequiredDocument) -> DocumentMatch:
        """
        匹配单个文档
        
        匹配优先级：
        1. 精确匹配
        2. 语义匹配
        3. 未匹配
        """
        # 1. 尝试精确匹配
        exact_result = self._exact_match(file_name, required_doc)
        if exact_result:
            return exact_result
        
        # 2. 尝试语义匹配
        if self.use_semantic:
            semantic_result = await self._semantic_match(file_name, required_doc)
            if semantic_result:
                return semantic_result
        
        # 3. 未匹配
        return DocumentMatch(
            document_name=required_doc.name,
            status=CheckStatus.MISSING,
            matched_file=None,
            match_type=MatchType.NONE,
            similarity=0.0,
            requirement="必须上传"
        )
    
    async def check(self, documents: List[Document], checklist: Checklist) -> CompletenessResult:
        """
        执行完整性检查
        
        Args:
            documents: 已上传的文档列表
            checklist: 审核清单
            
        Returns:
            完整性检查结果
        """
        file_names = [doc.name for doc in documents]
        required_docs = checklist.required_documents
        
        details: List[DocumentMatch] = []
        uploaded_count = 0
        missing_count = 0
        
        # 为每个必需文档寻找匹配
        for req_doc in required_docs:
            if not req_doc.required:
                continue
            
            matched = False
            best_match: Optional[DocumentMatch] = None
            
            for file_name in file_names:
                match_result = await self.match_document(file_name, req_doc)
                
                if match_result.status != CheckStatus.MISSING:
                    matched = True
                    if (best_match is None or 
                        match_result.similarity > best_match.similarity):
                        best_match = match_result
            
            if matched and best_match:
                details.append(best_match)
                uploaded_count += 1
            else:
                # 未找到匹配
                details.append(DocumentMatch(
                    document_name=req_doc.name,
                    status=CheckStatus.MISSING,
                    matched_file=None,
                    match_type=MatchType.NONE,
                    similarity=0.0,
                    requirement="必须上传"
                ))
                missing_count += 1
        
        # 确定整体状态
        total_required = len([d for d in required_docs if d.required])
        
        if missing_count == 0:
            status = CheckStatus.PASS
        elif uploaded_count == 0:
            status = CheckStatus.INCOMPLETE
        else:
            status = CheckStatus.INCOMPLETE
        
        return CompletenessResult(
            status=status,
            total_required=total_required,
            uploaded=uploaded_count,
            missing=missing_count,
            details=details
        )


async def check_completeness(
    documents: List[Document],
    checklist: Checklist,
    similarity_threshold: float = 0.75,
    use_semantic: bool = True
) -> CompletenessResult:
    """
    核对资料完整性（MCP工具入口）
    
    支持文件名语义匹配。
    
    匹配逻辑：
    1. 优先按"文件名称"精准匹配（文件名包含清单名称或别名）
    2. 名称不匹配时，使用 LLM 嵌入模型计算语义相似度
    3. 相似度 >= threshold 时，判定为匹配
    
    Args:
        documents: 已上传的文档列表
        checklist: 审核清单
        similarity_threshold: 语义匹配阈值（默认0.75）
        use_semantic: 是否使用语义匹配
        
    Returns:
        完整性检查结果
    """
    checker = CompletenessChecker(
        similarity_threshold=similarity_threshold,
        use_semantic=use_semantic
    )
    
    return await checker.check(documents, checklist)
