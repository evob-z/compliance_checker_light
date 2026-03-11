"""Qwen-VL 客户端 - 视觉模型 API 调用封装"""

import os
import re
import base64
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class QwenVLClient:
    """Qwen-VL 视觉模型客户端"""
    
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    DEFAULT_MODEL = "qwen-vl-plus"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 Qwen-VL 客户端
        
        Args:
            api_key: API密钥，默认从环境变量 QWEN_API_KEY 获取
            base_url: API基础URL，默认从环境变量 QWEN_BASE_URL 获取
            model: 模型名称，默认 qwen-vl-plus
        """
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        self.base_url = base_url or os.getenv("QWEN_BASE_URL", self.DEFAULT_BASE_URL)
        self.model = model or self.DEFAULT_MODEL
        
        if not self.api_key:
            logger.debug("QWEN_API_KEY not set, visual inspection will be unavailable")
    
    def is_available(self) -> bool:
        """检查客户端是否可用（API key 是否配置）"""
        return self.api_key is not None and len(self.api_key) > 0
    
    async def chat(
        self,
        image_path: str,
        prompt: str,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        发送图片和提示词到 Qwen-VL
        
        Args:
            image_path: 图片文件路径
            prompt: 文本提示词
            temperature: 采样温度
            
        Returns:
            {
                "success": bool,
                "found": bool,       # 是否找到目标
                "confidence": float, # 置信度 0-1
                "reasoning": str,    # 推理说明
                "content": str,      # 原始响应内容
                "raw": dict          # 原始响应
            }
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "QWEN_API_KEY not configured",
                "found": False,
                "confidence": 0.0,
                "reasoning": "QWEN_API_KEY not configured",
                "content": None
            }
        
        try:
            # 读取图片并转为 base64
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to read image {image_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to read image: {e}",
                "found": False,
                "confidence": 0.0,
                "reasoning": f"Failed to read image: {e}",
                "content": None
            }
        
        # 构建请求
        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": f"data:image/png;base64,{image_base64}"},
                            {"text": prompt}
                        ]
                    }
                ]
            },
            "parameters": {
                "temperature": temperature
            }
        }
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Qwen-VL API error: {resp.status} - {text}")
                        return {
                            "success": False,
                            "error": f"API error: {resp.status} - {text}",
                            "found": False,
                            "confidence": 0.0,
                            "reasoning": f"API error: {resp.status}",
                            "content": None
                        }
                    
                    result = await resp.json()
                    
                    # 解析响应
                    if "output" in result and "choices" in result["output"]:
                        content = result["output"]["choices"][0]["message"]["content"]
                        # 处理列表格式（新版 API）
                        if isinstance(content, list):
                            content = "\n".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
                        # 解析检测结果
                        parsed = self.parse_detection_result(content)
                        return {
                            "success": True,
                            "found": parsed["found"],
                            "confidence": parsed["confidence"],
                            "reasoning": parsed["reasoning"],
                            "content": content,
                            "raw": result
                        }
                    
                    return {
                        "success": False,
                        "error": "Unexpected response format",
                        "found": False,
                        "confidence": 0.0,
                        "reasoning": "Unexpected response format",
                        "content": None,
                        "raw": result
                    }
        except Exception as e:
            logger.error(f"Qwen-VL request failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": None
            }
    
    async def detect_seal(
        self,
        image_path: str,
        search_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检测公章
        
        Args:
            image_path: 图片文件路径
            search_context: 上下文信息（如"立项批复文件"）
            
        Returns:
            检测结果字典
        """
        prompt = f"""请仔细检查这张图片，判断是否存在公章（红色圆形印章）。

{f'图片上下文：{search_context}' if search_context else ''}

请按以下格式回答：
1. 是否存在公章：[是/否]
2. 置信度：[高/中/低]
3. 位置描述：[如"右下角"、"页面中央"等]
4. 说明：[简要说明判断依据]

请确保回答简洁明确。"""
        
        return await self.chat(image_path, prompt)
    
    async def detect_signature(
        self,
        image_path: str,
        search_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检测签名
        
        Args:
            image_path: 图片文件路径
            search_context: 上下文信息
            
        Returns:
            检测结果字典
        """
        prompt = f"""请仔细检查这张图片，判断是否存在手写签名。

{f'图片上下文：{search_context}' if search_context else ''}

请按以下格式回答：
1. 是否存在签名：[是/否]
2. 置信度：[高/中/低]
3. 位置描述：[如"签字栏"、"页面底部"等]
4. 说明：[简要说明判断依据]

请确保回答简洁明确。"""
        
        return await self.chat(image_path, prompt)
    
    def parse_detection_result(self, content) -> Dict[str, Any]:
        """
        解析 Qwen-VL 的检测结果
        
        Args:
            content: API 返回的文本内容（字符串或列表）
            
        Returns:
            {
                "found": bool,
                "confidence": float,  # 0-1
                "location": str,
                "reasoning": str
            }
        """
        # 处理列表格式（新版 API 返回的是列表）
        if isinstance(content, list):
            content = "\n".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
        
        if not content or not isinstance(content, str):
            return {
                "found": False,
                "confidence": 0.0,
                "location": "",
                "reasoning": "Empty response"
            }
        
        content_lower = content.lower()
        
        # 判断是否存在
        found = False
        # 检查是否包含肯定表述（在明确回答区域）
        # 提取"是否存在"后面的回答（支持"是否存在："和"是否存在公章："等格式）
        existence_match = re.search(r'是否存在\w*[：:]\s*\[?(是|否|有|无|存在|不存在)\]?', content)
        if existence_match:
            answer = existence_match.group(1)
            found = answer in ["是", "有", "存在"]
        else:
            # 回退到关键词匹配
            positive_patterns = ["存在", "发现", "找到"]
            negative_patterns = ["不存在", "未找到", "未发现", "没有"]
            
            # 避免"是否"被误判为"否"
            has_positive = any(p in content for p in positive_patterns)
            has_negative = any(p in content for p in negative_patterns)
            
            if has_negative:
                found = False
            elif has_positive:
                found = True
        
        # 提取置信度
        confidence = 0.5
        if "高" in content:
            confidence = 0.9
        elif "中" in content:
            confidence = 0.6
        elif "低" in content:
            confidence = 0.3
        
        # 尝试提取数字置信度（支持 [0.95] 格式）
        num_match = re.search(r'置信度[:：]?\s*\[?(0?\.\d+|1\.0|1)\]?', content)
        if num_match:
            try:
                confidence = float(num_match.group(1))
            except ValueError:
                pass
        
        # 提取位置（简单实现）
        location = ""
        location_keywords = ["右下角", "左下角", "右上角", "左上角", "中央", "底部", "顶部", "页面中央"]
        for kw in location_keywords:
            if kw in content:
                location = kw
                break
        
        return {
            "found": found,
            "confidence": confidence,
            "location": location,
            "reasoning": content[:300]  # 前300字符作为说明
        }
