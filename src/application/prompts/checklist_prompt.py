"""
检查清单提示词构建器

Application 层的 Prompt 构建器，负责将业务逻辑从基础设施层剥离。
提供静态方法用于构建合规检查清单生成的提示词。
"""

from typing import Optional, Dict


class ChecklistPromptBuilder:
    """
    检查清单提示词构建器

    负责构建用于 LLM 生成合规检查清单的提示词。
    将原本在 Infrastructure 层的业务逻辑提取到这里。

    使用方式：
        prompt = ChecklistPromptBuilder.build(
            requirements="检查立项批复和环评报告",
            project_period={"start": "2024-01", "end": "2024-12"}
        )
    """

    # YAML 模板常量
    YAML_TEMPLATE = """```yaml
checklist:
  name: "清单名称"
  description: "清单描述"
  required_documents:
    - name: "文档名称"
      description: "文档描述"
      required: true
  checks:
    - type: "completeness"
      description: "检查描述"
```"""

    # 提示词模板
    PROMPT_TEMPLATE = """请根据以下描述生成一个合规检查清单的 YAML 配置：

描述：
{requirements}
{project_period_section}

请生成以下格式的 YAML：

{yaml_template}

要求：
1. 只输出 YAML 内容，不要包含其他说明
2. 确保 YAML 格式正确
3. required_documents 列出所有必需文档
4. checks 列出需要执行的检查类型（completeness, timeliness, compliance）
"""

    @staticmethod
    def build(
        requirements: str,
        project_period: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        构建检查清单生成提示词

        Args:
            requirements: 自然语言描述的检查要求
            project_period: 可选的项目周期 {"start": "YYYY-MM", "end": "YYYY-MM"}

        Returns:
            组装好的完整提示词文本
        """
        # 构建项目周期部分
        project_period_section = ""
        if project_period:
            start = project_period.get("start", "")
            end = project_period.get("end", "")
            if start or end:
                project_period_section = f"\n项目周期：{start} 至 {end}"

        return ChecklistPromptBuilder.PROMPT_TEMPLATE.format(
            requirements=requirements,
            project_period_section=project_period_section,
            yaml_template=ChecklistPromptBuilder.YAML_TEMPLATE,
        )
