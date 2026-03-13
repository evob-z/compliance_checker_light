"""
清单生成器 Prompt 模板

使用方式：
    from compliance_checker.prompts import generate_checklist_prompt
    
    prompt = generate_checklist_prompt("我要审查建设工程项目...")
    yaml_content = await external_llm.complete(prompt)

或者直接使用异步生成函数：
    from compliance_checker.prompts import async_generate_checklist_from_description
    
    checklist = await async_generate_checklist_from_description("我要审查...")
"""

from typing import Optional

CHECKLIST_GENERATION_PROMPT = """你是一个专业的合规审查清单生成助手。

请将用户的自然语言描述转换为标准的合规审查清单 YAML 格式。

## 可用检查类型

| 检查类型 | 说明 | 适用场景 |
|----------|------|----------|
| `completeness` | 检查文档是否上传 | 所有必需文档，**必须包含** |
| `timeliness` | 检查日期有效性 | 有有效期的证件、批复文件 |
| `compliance` | 检查要素完整性（公章、签字等） | 批文、合同、证书 |
| `visual` | 视觉检测印章/签名 | 需要验章的重要文件 |
| `authenticity` | 真实性验证（数字签名、防伪） | 高价值文件验证 |
| `cross_reference` | 交叉核对多个文档 | 验证文档间一致性 |

## 文档类型知识库

常见工程项目的文档类型：
- 立项批复: ["立项批复", "立项文件", "项目核准"]
- 环评批复: ["环评批复", "环境影响评价", "环评文件"]
- 土地证: ["土地使用证", "不动产权证", "土地证"]
- 规划许可: ["规划许可证", "建设工程规划许可证"]
- 施工许可: ["施工许可证", "建筑施工许可证"]
- 竣工验收: ["竣工验收报告", "验收备案"]

## 输出格式

```yaml
checklist:
  id: "{{使用英文小写和下划线}}"
  name: "{{清单名称}}"
  version: "1.0.0"
  description: "{{清单用途描述}}"
  
  project_period:
    start: "{{YYYY-MM，可选}}"
    end: "{{YYYY-MM，可选}}"
  
  required_documents:
    - name: "{{文档标准名称}}"
      aliases: ["{{别名1}}", "{{别名2}}"]
      description: "{{文档说明}}"
      checks:
        - type: "completeness"
          required: true
        - type: "timeliness"
          required: {{true/false}}
          date_rules:
            - type: "valid_period"
              field: "{{日期字段关键词，如'有效期至'}}"
        - type: "compliance"
          required: {{true/false}}
          points: [{{检查要点，如"公章", "签字", "文号"}}]
        - type: "visual"
          required: false
          target: "seal"  # seal | signature | both
```

## 生成规则

1. **id**: 使用英文小写和下划线，如 `construction_project`, `it_service_contract`
2. **checks**: 默认包含 `completeness`，其他根据文档类型推断
3. **timeliness**: 有有效期的证件类文档需要，合同类不需要
4. **compliance**: 批文、证书需要检查公章签字，普通文件不需要
5. **visual**: 重要批文、合同建议启用，增加可信度
6. **required**: 关键检查设为 true，辅助检查可设为 false

## 用户描述

{user_description}

## 请生成 YAML

只输出 YAML 内容，不要有其他解释：
"""


def generate_checklist_prompt(user_description: str) -> str:
    """
    生成清单转换 Prompt

    Args:
        user_description: 用户的自然语言描述

    Returns:
        完整的 Prompt 字符串
    """
    return CHECKLIST_GENERATION_PROMPT.format(user_description=user_description)


# 可选：提供少样本示例
CHECKLIST_EXAMPLES = [
    {
        "input": "审查建设工程项目，需要立项批复、环评批复和施工许可证",
        "output": """
checklist:
  id: "construction_project"
  name: "建设工程项目合规审查"
  version: "1.0.0"
  description: "建设工程项目全套文档合规检查"
  
  required_documents:
    - name: "立项批复"
      aliases: ["立项文件", "项目批复", "核准批复"]
      checks:
        - type: "completeness"
          required: true
        - type: "timeliness"
          required: true
          date_rules:
            - type: "valid_period"
              field: "有效期"
        - type: "compliance"
          required: true
          points: ["公章", "签字", "文号"]
        - type: "visual"
          required: true
          target: "seal"
    
    - name: "环评批复"
      aliases: ["环境影响评价批复", "环评文件"]
      checks:
        - type: "completeness"
          required: true
        - type: "timeliness"
          required: true
        - type: "compliance"
          required: true
          points: ["公章", "文号"]
    
    - name: "施工许可证"
      aliases: ["建筑施工许可证"]
      checks:
        - type: "completeness"
          required: true
        - type: "timeliness"
          required: true
          date_rules:
            - type: "valid_period"
              field: "有效期"
        - type: "compliance"
          required: true
          points: ["公章", "编号"]
""",
    }
]


def generate_checklist_prompt_with_examples(user_description: str, num_examples: int = 1) -> str:
    """
    生成带示例的清单转换 Prompt

    Args:
        user_description: 用户的自然语言描述
        num_examples: 示例数量

    Returns:
        完整的 Prompt 字符串（包含示例）
    """
    prompt = CHECKLIST_GENERATION_PROMPT.format(user_description=user_description)

    if num_examples > 0:
        prompt += "\n\n## 示例\n\n"
        for i, example in enumerate(CHECKLIST_EXAMPLES[:num_examples]):
            prompt += f"### 示例 {i+1}\n\n"
            prompt += f"输入: {example['input']}\n\n"
            prompt += f"输出:\n{example['output']}\n\n"

    return prompt


# ==================== 异步生成功能 ====================


async def async_generate_checklist_from_description(
    user_description: str, use_examples: bool = False, num_examples: int = 1
) -> dict:
    """
    异步从自然语言描述生成清单

    此函数使用 LLM 客户端将自然语言转换为 YAML 清单

    Args:
        user_description: 用户的自然语言描述
        use_examples: 是否使用少样本示例
        num_examples: 示例数量（仅在 use_examples=True 时有效）

    Returns:
        解析后的清单字典，包含 'checklist' 键

    Raises:
        ImportError: 未安装 openai
        ValueError: LLM 配置缺失或 YAML 解析失败
        Exception: LLM API 调用失败

    Example:
        >>> checklist = await async_generate_checklist_from_description(
        ...     "审查建设工程项目，需要立项批复、环评批复"
        ... )
        >>> print(checklist['checklist']['name'])
    """
    from ..llm.client import generate_checklist_from_description

    # 如果需要使用示例，先生成带示例的 prompt
    if use_examples:
        prompt = generate_checklist_prompt_with_examples(user_description, num_examples)

        # 临时使用 LLM 客户端，但传入自定义 prompt
        from ..llm.client import LLMClient

        client = LLMClient()

        content = await client.complete(prompt)

        # 清理和解析 YAML
        content = client._clean_yaml_content(content)
        import yaml

        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict) or "checklist" not in data:
                raise ValueError("生成的 YAML 缺少 'checklist' 根节点")
            return data
        except yaml.YAMLError as e:
            raise ValueError(f"LLM 生成的内容不是有效的 YAML: {e}")
    else:
        # 使用默认的生成函数
        return await generate_checklist_from_description(user_description)


async def async_generate_checklist_with_period(
    user_description: str, project_period: Optional[dict] = None
) -> dict:
    """
    异步生成清单，并可选地注入项目周期

    Args:
        user_description: 用户的自然语言描述
        project_period: 项目周期，格式 {"start": "YYYY-MM", "end": "YYYY-MM"}

    Returns:
        解析后的清单字典
    """
    checklist = await async_generate_checklist_from_description(user_description)

    # 如果提供了项目周期，注入到清单中
    if project_period and "checklist" in checklist:
        checklist["checklist"]["project_period"] = project_period

    return checklist
