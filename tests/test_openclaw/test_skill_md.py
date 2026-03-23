"""
SKILL.md 格式验证测试

确保 SKILL.md 文件符合 OpenClaw Skill 规范：
- 存在 YAML frontmatter
- 必填字段完整
- metadata 配置正确
"""

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_MD_PATH = PROJECT_ROOT / "SKILL.md"


@pytest.fixture
def skill_content():
    """读取 SKILL.md 原始内容"""
    assert SKILL_MD_PATH.exists(), f"SKILL.md not found at {SKILL_MD_PATH}"
    return SKILL_MD_PATH.read_text(encoding="utf-8")


@pytest.fixture
def frontmatter(skill_content):
    """解析 SKILL.md 的 YAML frontmatter"""
    content = skill_content
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter (---)"

    # 找到第二个 --- 的位置
    end_index = content.index("---", 3)
    yaml_str = content[3:end_index].strip()

    return yaml.safe_load(yaml_str)


class TestSkillMdExists:
    def test_skill_md_exists(self):
        assert SKILL_MD_PATH.exists(), "SKILL.md must exist at project root"

    def test_skill_md_not_empty(self, skill_content):
        assert len(skill_content.strip()) > 0, "SKILL.md must not be empty"


class TestFrontmatter:
    def test_has_yaml_frontmatter(self, skill_content):
        assert skill_content.startswith("---"), (
            "SKILL.md must start with YAML frontmatter delimited by ---"
        )

    def test_frontmatter_parseable(self, frontmatter):
        assert isinstance(frontmatter, dict), "Frontmatter must be a valid YAML dict"

    def test_has_name(self, frontmatter):
        assert "name" in frontmatter, "Frontmatter must include 'name'"
        name = frontmatter["name"]
        assert isinstance(name, str), "'name' must be a string"
        assert len(name) <= 64, "'name' must be <= 64 characters"
        # OpenClaw requires lowercase, digits, hyphens only
        assert all(
            c.isalnum() or c == "-" for c in name
        ), "'name' must contain only lowercase letters, digits, and hyphens"

    def test_has_description(self, frontmatter):
        assert "description" in frontmatter, "Frontmatter must include 'description'"
        desc = frontmatter["description"]
        assert isinstance(desc, str), "'description' must be a string"
        assert len(desc) > 10, "'description' must be meaningful (>10 chars)"

    def test_has_allowed_tools(self, frontmatter):
        assert "allowed-tools" in frontmatter, (
            "Frontmatter must include 'allowed-tools'"
        )
        tools = frontmatter["allowed-tools"]
        assert isinstance(tools, list), "'allowed-tools' must be a list"
        assert len(tools) > 0, "'allowed-tools' must not be empty"

    def test_allowed_tools_contains_bash_read_glob(self, frontmatter):
        tools = frontmatter["allowed-tools"]
        for expected in ["Bash", "Read", "Glob"]:
            assert expected in tools, (
                f"allowed-tools must include '{expected}'"
            )

    def test_allowed_tools_no_mcp_prefix(self, frontmatter):
        tools = frontmatter["allowed-tools"]
        mcp_tools = [t for t in tools if str(t).startswith("mcp__")]
        assert len(mcp_tools) == 0, (
            f"allowed-tools must not include MCP-prefixed tool names, "
            f"found: {mcp_tools}"
        )


class TestMetadata:
    def test_has_metadata(self, frontmatter):
        assert "metadata" in frontmatter, "Frontmatter must include 'metadata'"

    def test_has_openclaw_metadata(self, frontmatter):
        metadata = frontmatter["metadata"]
        assert "openclaw" in metadata, "metadata must include 'openclaw' section"

    def test_has_requires(self, frontmatter):
        openclaw = frontmatter["metadata"]["openclaw"]
        assert "requires" in openclaw, "openclaw metadata must include 'requires'"

    def test_requires_bins(self, frontmatter):
        requires = frontmatter["metadata"]["openclaw"]["requires"]
        assert "bins" in requires, "requires must include 'bins'"
        bins = requires["bins"]
        assert isinstance(bins, list), "'bins' must be a list"
        assert "python" in bins, "'bins' must include 'python'"
        assert "compliance-checker" in bins, (
            "'bins' must include 'compliance-checker'"
        )

    def test_requires_env(self, frontmatter):
        requires = frontmatter["metadata"]["openclaw"]["requires"]
        # SKILL.md 使用 env_required 表示必需的环境变量
        assert "env_required" in requires, "requires must include 'env_required'"
        env_required = requires["env_required"]
        assert isinstance(env_required, list), "'env_required' must be a list"
        assert "LLM_API_KEY" in env_required, "'env_required' must include 'LLM_API_KEY'"


class TestBody:
    def test_body_has_content(self, skill_content):
        """SKILL.md body 部分不能为空"""
        # 找到 frontmatter 结束位置
        end_index = skill_content.index("---", 3) + 3
        body = skill_content[end_index:].strip()
        assert len(body) > 100, "SKILL.md body must have substantial content"

    def test_body_mentions_tool_name(self, skill_content):
        """Body 中必须提到工具名称"""
        assert "compliance_check" in skill_content or "compliance-checker" in skill_content, (
            "SKILL.md body must mention the tool name"
        )

    def test_body_mentions_cli_subcommands(self, skill_content):
        """Body 中必须包含三个 CLI 子命令"""
        for cmd in ["completeness", "timeliness", "visual"]:
            assert cmd in skill_content, (
                f"SKILL.md body must mention '{cmd}' subcommand"
            )

    def test_body_mentions_install_verification(self, skill_content):
        """Body 中必须包含安装验证步骤"""
        assert "compliance-checker --version" in skill_content, (
            "SKILL.md body must include installation verification step"
        )
