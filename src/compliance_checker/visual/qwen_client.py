"""Qwen-VL 客户端 - 视觉模型 API 调用封装"""

import os
import re
import base64
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class QwenVLClient:
    """视觉模型客户端 - 默认使用 Qwen3-VL-Flash (OpenAI 兼容模式)"""

    # 默认使用 OpenAI 兼容模式端点（支持 Qwen3-VL-Flash）
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen3-vl-flash"

    def __init__(self):
        """
        初始化视觉模型客户端

        配置优先级（从高到低）：
        1. VISION_API_KEY / VISION_BASE_URL（专用配置）
        2. LLM_API_KEY / LLM_BASE_URL（通用配置）

        默认使用 Qwen3-VL-Flash 模型和 OpenAI 兼容模式端点。
        如需使用其他视觉模型，请在 .env 中配置 VISION_MODEL 和 VISION_BASE_URL
        """
        # API Key: 优先使用 VISION_API_KEY（专用配置），其次 LLM_API_KEY
        vision_api_key = os.getenv("VISION_API_KEY", "").strip()
        self.api_key = vision_api_key if vision_api_key else os.getenv("LLM_API_KEY", "").strip() or None

        # Base URL: 优先使用 VISION_BASE_URL（专用配置），其次 LLM_BASE_URL
        vision_base_url = os.getenv("VISION_BASE_URL", "").strip()
        llm_base_url = os.getenv("LLM_BASE_URL", "").strip()

        # Model: 使用 VISION_MODEL（如果配置），否则使用默认值
        vision_model = os.getenv("VISION_MODEL", "").strip()
        self.model = vision_model if vision_model else self.DEFAULT_MODEL

        # 确定 Base URL
        if vision_base_url:
            # 用户配置了 VISION_BASE_URL，优先使用
            self.base_url = vision_base_url
        elif llm_base_url:
            # 使用 LLM_BASE_URL（通用配置）
            self.base_url = llm_base_url
        else:
            # 默认使用 OpenAI 兼容模式端点
            self.base_url = self.DEFAULT_BASE_URL

        # 判断是否使用 OpenAI 兼容模式
        # OpenAI 兼容模式端点特征：包含 "compatible-mode" 或以 "/v1" 结尾
        self.use_openai_format = (
            "compatible-mode" in self.base_url or
            self.base_url.rstrip("/").endswith("/v1")
        )

        if not self.api_key:
            logger.debug("Vision API key not set, visual inspection will be unavailable")
    
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
        
        # 构建请求（根据端点类型选择格式）
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if self.use_openai_format:
            # OpenAI 兼容格式
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "temperature": temperature
            }
        else:
            # 阿里云原生 API 格式
            url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
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
                        logger.error(f"视觉模型 API error: {resp.status} - {text}")
                        # 404 错误：模型或端点配置错误，标记为不可用
                        if resp.status == 404:
                            return {
                                "success": False,
                                "error": "视觉检查无法使用：模型或端点配置错误",
                                "found": False,
                                "confidence": 0.0,
                                "reasoning": "视觉检查无法使用：请检查 VISION_MODEL 和 VISION_BASE_URL 配置",
                                "content": None,
                                "unavailable": True
                            }
                        return {
                            "success": False,
                            "error": f"API error: {resp.status}",
                            "found": False,
                            "confidence": 0.0,
                            "reasoning": f"API error: {resp.status}",
                            "content": None
                        }
                    
                    result = await resp.json()
                    
                    # 解析响应（支持 OpenAI 兼容格式和阿里云原生格式）
                    content = self._extract_content_from_response(result)
                    if content is not None:
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
    
    def _extract_content_from_response(self, result: Dict[str, Any]) -> Optional[str]:
        """
        从 API 响应中提取内容文本
        支持 OpenAI 兼容格式和阿里云原生格式
        """
        try:
            # OpenAI 兼容格式: choices[0].message.content
            if "choices" in result:
                choice = result["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content")
                else:
                    content = choice.get("text")
                
                # 处理列表格式（新版 API）
                if isinstance(content, list):
                    content = "\n".join([
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    ])
                return content
            
            # 阿里云原生格式: output.choices[0].message.content
            if "output" in result and "choices" in result["output"]:
                content = result["output"]["choices"][0]["message"]["content"]
                # 处理列表格式
                if isinstance(content, list):
                    content = "\n".join([
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    ])
                return content
            
            return None
        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"Failed to extract content from response: {e}")
            return None
    
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
