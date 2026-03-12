# MCP Server Skill 开发教程

以 ComplianceSkill（文档合规审查）为例，讲解如何开发一个完整的 MCP Server Skill。

---

## 1. MCP Server 基本概念

### 1.1 什么是 MCP

MCP（Model Context Protocol）是一种让 AI Agent 与外部工具交互的协议。AI Agent（如 Claude、Qwen）通过 MCP Server 暴露的工具完成超出自身能力范围的任务，例如：读取本地文件、调用外部 API、执行复杂计算。

```
AI Agent
  │
  │  发送工具调用请求（JSON）
  ▼
MCP Server（你开发的 Python 程序）
  │
  │  执行具体逻辑后返回结果
  ▼
AI Agent（将结果整合到回答中）
```

### 1.2 FastMCP 框架

本项目使用 `fastmcp` 库，它是对 MCP 协议的轻量封装，类似 FastAPI 风格：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-skill")

@mcp.tool()
async def my_tool(param: str) -> dict:
    """工具描述（AI 会读取这段文档字符串来决定何时调用）"""
    return {"result": param}

def main():
    mcp.run(transport="stdio")  # 通过标准输入输出与 AI 通信
```

### 1.3 工具暴露原则

- **只暴露 AI Agent 需要直接调用的工具**：避免暴露内部实现细节
- **工具数量精简**：本项目只暴露 3 个核心工具（`check_with_description`、`run_compliance_check`、`list_available_checkers`）
- **文档字符串要清晰**：AI 根据 docstring 决定调用哪个工具

---

## 2. 项目结构设计

### 2.1 推荐的目录结构

```
my_skill/
├── src/my_skill/
│   ├── server.py          # MCP Server 入口（只暴露工具）
│   ├── skill.py           # Skill 主模块（业务逻辑入口）
│   ├── skill_formatter.py # 结果格式化（自然语言输出）
│   ├── core/              # 数据模型（Pydantic）
│   ├── engine/            # 执行引擎
│   ├── checkers/          # 各功能检查器
│   ├── parsers/           # 数据解析
│   ├── llm/               # LLM 客户端
│   └── config/            # 配置管理
├── .env                   # 环境变量
├── pyproject.toml
└── run_check.py           # 本地测试脚本
```

**关键设计原则**：
- `server.py` 只做路由和错误处理，不含业务逻辑
- `skill.py` 是业务入口，可独立于 MCP 使用
- `core/` 中的数据模型使用 Pydantic，确保类型安全

### 2.2 pyproject.toml 配置

```toml
[project]
name = "my-skill"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]",
    "fastmcp",
    "python-dotenv",
    "pydantic>=2.0",
    "openai",
    "pymupdf",       # PDF 解析
    "aiohttp",       # 异步 HTTP
]

[project.scripts]
my-skill = "my_skill.server:main"  # pip install 后可直接运行

[project.optional-dependencies]
local-ocr = ["paddleocr", "paddlepaddle"]
cloud-ocr = ["alibabacloud-ocr-api20210707"]
```

---

## 3. 定义 Skill 接口

### 3.1 设计原则

好的 Skill 接口应该：
1. **输入是自然语言**：AI 能直接从对话中提取参数
2. **输出是自然语言**：AI 可以直接将结果告诉用户
3. **参数尽量少**：减少 AI 填错参数的概率
4. **错误优雅处理**：不抛异常，用返回值传递错误

### 3.2 最简 Skill 接口示例

```python
# server.py
@mcp.tool()
async def check_with_description(
    project_path: str,                              # 必须：文件夹路径
    requirements: str,                              # 必须：自然语言需求
    project_period: Optional[Dict[str, str]] = None # 可选：项目周期
) -> dict:
    """
    自然语言合规审查（Skill 接口）
    
    通过自然语言描述检查要求，自动：
    1. 扫描文件夹中的文档
    2. 使用 LLM 生成检查清单
    3. 执行完整检查流程
    4. 返回文本格式的问题描述
    
    Args:
        project_path: 项目手续文件夹路径（绝对路径）
        requirements: 自然语言描述的检查要求
            例如："审查建设工程项目，需要立项批复、环评批复，检查公章和有效期"
        project_period: 可选的项目周期
            格式：{"start": "YYYY-MM", "end": "YYYY-MM"}
    """
    from .skill import ComplianceSkill
    
    try:
        skill = ComplianceSkill()
        return await skill.check(project_path, requirements, project_period)
    except FileNotFoundError as e:
        return {"success": False, "error": str(e), "error_type": "file_not_found"}
    except Exception as e:
        return {"success": False, "error": str(e), "error_type": type(e).__name__}
```

**注意**：`server.py` 中的工具函数只负责路由和错误处理，所有业务逻辑放在 `skill.py`。

### 3.3 Skill 主模块设计

```python
# skill.py
class ComplianceSkill:
    def __init__(self):
        self.registry = get_initialized_registry()
        self.engine = DeclarativeCheckEngine(registry=self.registry)
        self.parsers = {".pdf": PDFParser(), ".docx": DocxParser()}
    
    async def check(
        self,
        project_path: str,
        requirements: str,
        project_period: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """业务逻辑主入口"""
        # 步骤1：验证输入
        # 步骤2：扫描文档
        # 步骤3：解析文档
        # 步骤4：LLM 生成清单
        # 步骤5：执行检查
        # 步骤6：格式化输出
        ...
```

这种设计让 `ComplianceSkill` 可以在不启动 MCP Server 的情况下直接调用：

```python
# 直接使用（测试场景）
skill = ComplianceSkill()
result = await skill.check("/path/to/docs", "检查发票")
```

---

## 4. 处理自然语言输入

### 4.1 LLM 驱动的中间层转换

将自然语言需求转换为结构化执行计划，是本 Skill 的核心设计：

```
"审查建设工程项目，需要立项批复、环评批复，所有文件需要有公章和有效期"
    │
    │ 发送给 LLM（带 Prompt 模板）
    ▼
YAML 检查清单（结构化规则）
    │
    │ 传给声明式检查引擎
    ▼
并行执行各检查器
```

### 4.2 Prompt 工程技巧

```python
CHECKLIST_GENERATION_PROMPT = """你是一个专业的合规审查清单生成助手。

## 可用检查类型

| 检查类型 | 说明 |
|----------|------|
| `completeness` | 检查文档是否上传（所有文档必须包含）|
| `timeliness` | 检查日期有效性（有有效期的证件）|
| `compliance` | 检查要素完整性（公章、签字等）|
| `visual` | 视觉检测印章/签名 |

## 输出格式

```yaml
checklist:
  id: "{{英文小写下划线}}"
  required_documents:
    - name: "{{文档名}}"
      checks:
        - type: "completeness"
          required: true
        - type: "compliance"
          points: ["公章", "签字"]
```

## 用户描述

{user_description}

只输出 YAML，不要有其他解释：
"""
```

**关键技巧**：
- 提供**枚举可用类型**，防止 LLM 自创类型
- 提供**输出格式模板**，确保结构一致
- 末尾加"只输出 YAML"，减少多余文字
- 提供**少样本示例**（可选），提高生成质量

### 4.3 LLM 输出清理

LLM 经常在 YAML 外加 ` ```yaml ``` ` 标记，需要清理：

```python
def _clean_yaml_content(self, content: str) -> str:
    lines = content.strip().split('\n')
    # 跳过开头的 ``` 行
    start_idx = next(
        (i for i, l in enumerate(lines) if l.strip() and not l.strip().startswith('```')),
        0
    )
    # 跳过结尾的 ``` 行
    end_idx = next(
        (i+1 for i in range(len(lines)-1, -1, -1) if lines[i].strip() and not lines[i].strip().startswith('```')),
        len(lines)
    )
    return '\n'.join(lines[start_idx:end_idx])
```

---

## 5. 集成多种 AI 模型

### 5.1 统一 API Key 管理

本项目采用**两级优先级**配置：

```
通用配置（简单模式）: LLM_API_KEY + LLM_BASE_URL
    ↓ 被覆盖
专用配置（高级模式）: VISION_API_KEY + VISION_BASE_URL
                       EMBED_API_KEY + EMBED_BASE_URL
```

这样用户可以：
- **简单模式**：只配一个 API Key，所有模型共用
- **高级模式**：不同模型用不同厂商，单独配置

```python
class QwenVLClient:
    def __init__(self):
        # 优先使用专用配置，回退到通用配置
        vision_api_key = os.getenv("VISION_API_KEY", "").strip()
        self.api_key = vision_api_key if vision_api_key else os.getenv("LLM_API_KEY", "").strip() or None
        
        vision_base_url = os.getenv("VISION_BASE_URL", "").strip()
        llm_base_url = os.getenv("LLM_BASE_URL", "").strip()
        self.base_url = vision_base_url or llm_base_url or self.DEFAULT_BASE_URL
```

### 5.2 OpenAI 兼容模式适配

国内 API（DashScope、Moonshot、DeepSeek）都兼容 OpenAI 格式，通过 `base_url` 区分：

```python
# LLM 调用（统一用 openai 库）
client = openai.AsyncOpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"  # 阿里云
)
response = await client.chat.completions.create(model="qwen-max", ...)
```

对于视觉模型，需要区分 OpenAI 兼容模式和原生 API：

```python
# 自动检测端点类型
self.use_openai_format = (
    "compatible-mode" in self.base_url or
    self.base_url.rstrip("/").endswith("/v1")
)

if self.use_openai_format:
    # OpenAI 兼容格式
    url = f"{self.base_url}/chat/completions"
    payload = {
        "model": self.model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
            {"type": "text", "text": prompt}
        ]}]
    }
else:
    # 阿里云原生格式
    url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
    payload = {"model": self.model, "input": {"messages": [...]}}
```

### 5.3 模型可用性检查

每个 AI 模型客户端都应实现 `is_available()` 方法，在功能不可用时优雅降级而不是报错：

```python
class QwenVLClient:
    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 0

class EmbeddingClient:
    def is_available(self) -> bool:
        return self.api_key is not None and self.model is not None
```

使用模式：

```python
if self.visual_client.is_available():
    result = await self.visual_client.detect_seal(image_path)
else:
    result = {"found": None, "status": "UNAVAILABLE"}  # 优雅降级
```

---

## 6. 异步操作和并发控制

### 6.1 异步基础

MCP Server 天然异步，所有工具函数都应是 `async def`：

```python
@mcp.tool()
async def check_with_description(project_path: str, requirements: str) -> dict:
    skill = ComplianceSkill()
    return await skill.check(project_path, requirements)
```

对于 CPU 密集型或阻塞 I/O（如 PyMuPDF 解析 PDF），使用线程池：

```python
import asyncio

async def parse_pdf(self, file_path: str) -> Document:
    # 在线程池中运行同步的 PDF 解析，避免阻塞事件循环
    return await asyncio.get_event_loop().run_in_executor(
        None,           # 使用默认线程池
        self.parser.parse,  # 同步方法
        file_path
    )
```

### 6.2 并行执行多个检查

使用 `asyncio.gather` 并行执行独立任务：

```python
# 并发执行所有检查任务
tasks = [run_with_limit(plan) for plan in check_plan]
results = await asyncio.gather(*tasks)
```

使用 `asyncio.Semaphore` 控制并发上限：

```python
semaphore = asyncio.Semaphore(max_concurrent)  # 默认 3

async def run_with_limit(task):
    async with semaphore:  # 同时最多 3 个任务
        return await asyncio.wait_for(
            run_single(task),
            timeout=300  # 超时保护
        )
```

### 6.3 超时处理

每个检查都应有超时保护，防止单个检查卡死整个流程：

```python
try:
    return await asyncio.wait_for(run_single(task), timeout=timeout)
except asyncio.TimeoutError:
    return task, CheckResult(
        status=CheckStatus.ERROR,
        message=f"检查超时（超过{timeout}秒）"
    )
```

---

## 7. 声明式检查引擎设计

### 7.1 核心概念

声明式引擎将**"做什么"**（清单 YAML）和**"怎么做"**（检查器实现）分离：

```
清单 YAML（What）           检查器（How）
-------------------         ---------------
type: "completeness"    →   CompletenessChecker
type: "timeliness"      →   TimelinessChecker
type: "compliance"      →   ComplianceChecker
type: "visual"          →   VisualChecker
type: "authenticity"    →   UnavailableChecker（待开发）
```

### 7.2 检查器注册表

单例模式管理所有检查器，支持"已实现"和"待开发"两种状态：

```python
def get_initialized_registry() -> CheckerRegistry:
    registry = CheckerRegistry()
    
    # 注册已实现的检查器
    try:
        from ..checkers.completeness_checker import CompletenessChecker
        registry.register(CompletenessChecker())
    except ImportError:
        registry.register_unavailable("completeness")  # 降级处理
    
    # 标记待开发功能（占位，不报错）
    registry.register_unavailable("authenticity")
    registry.register_unavailable("blockchain_verify")
    
    return registry
```

### 7.3 检查器接口规范

所有检查器继承 `BaseChecker`：

```python
class BaseChecker(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...          # 唯一标识，对应 YAML type
    
    @property
    @abstractmethod
    def description(self) -> str: ...   # 描述
    
    def is_available(self) -> bool:     # 依赖检查（可选覆盖）
        return True
    
    @abstractmethod
    async def check(
        self,
        documents: List[Document],
        checklist: Optional[Checklist],
        doc_checks: Dict[str, Any]      # 来自清单的检查配置
    ) -> CheckResult: ...
    
    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        return True, ""  # 配置验证（可选覆盖）
```

**实现示例**：

```python
class MyChecker(BaseChecker):
    @property
    def name(self) -> str:
        return "my_check"
    
    @property
    def description(self) -> str:
        return "自定义检查"
    
    def is_available(self) -> bool:
        # 检查依赖是否满足
        try:
            import some_required_library
            return True
        except ImportError:
            return False
    
    async def check(self, documents, checklist, doc_checks) -> CheckResult:
        try:
            # 执行检查逻辑
            passed = self._do_check(documents, doc_checks)
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.PASS if passed else CheckStatus.FAIL,
                message="检查通过" if passed else "检查失败",
                details={"custom_key": "custom_value"}
            )
        except Exception as e:
            return CheckResult(
                check_type=self.name,
                status=CheckStatus.ERROR,
                message=f"检查执行异常: {e}"
            )
```

---

## 8. 结果格式化

### 8.1 双格式输出策略

向 AI 返回两种格式：

| 格式 | 用途 | 特点 |
|------|------|------|
| `issues_description`（文本） | AI 直接阅读并转述给用户 | 中文，易读，含状态图标 |
| `issues_simple`（结构化） | 程序处理、进一步分析 | JSON，精确，含完整字段 |

### 8.2 文本格式化规范

```python
def format_check_result(execution_result: ExecutionResult) -> str:
    lines = []
    summary = execution_result.summary
    
    # 统计摘要
    lines.append(f"检查总数: {summary.get('total', 0)}")
    lines.append(f"通过: {summary.get('passed', 0)} 项")
    lines.append(f"失败: {summary.get('failed', 0)} 项")
    lines.append(f"错误: {summary.get('errors', 0)} 项")
    if summary.get('unavailable', 0) > 0:
        lines.append(f"暂不可用: {summary.get('unavailable', 0)} 项")  # 只有非零才显示
    
    # 按文档分组显示问题（只显示非通过项）
    for doc_name, results in doc_results.items():
        issues = [r for r in results if r.status not in (CheckStatus.PASS, CheckStatus.VALID)]
        if issues:
            lines.append(f"【文档: {doc_name}】")
            for result in issues:
                icon = {"PASS": "✅", "FAIL": "❌", "UNAVAILABLE": "⚠️"}.get(result.status, "💥")
                lines.append(f"  {icon} [{type_name}] {result.message}")
    
    # 全部通过时的提示
    if summary.get('failed', 0) == 0 and summary.get('errors', 0) == 0:
        lines.append("✅ 所有检查通过，未发现问题")
    
    return "\n".join(lines)
```

**关键设计**：
- `UNAVAILABLE` 只有数量非零时才显示，不干扰正常结果
- 通过状态（`PASS`）不显示详情，减少噪音
- 全部通过时有明确提示

### 8.3 状态计数注意事项

`UNCLEAR` 状态（视觉检查不可用时文本检查的降级结果）会被计入 `errors` 而不是 `passed`：

```python
if result.status == CheckStatus.PASS:
    summary["passed"] += 1
elif result.status == CheckStatus.FAIL:
    summary["failed"] += 1
elif result.status == CheckStatus.UNAVAILABLE:
    summary["unavailable"] += 1
else:  # UNCLEAR、ERROR 等
    summary["errors"] += 1
```

这确保了"视觉检查未执行但文本检查通过"的情况不会被错误地计入通过数量。

---

## 9. 环境变量和配置管理

### 9.1 .env 文件加载

在 MCP Server 启动时和 Skill 模块导入时各加载一次，覆盖所有使用场景：

```python
# server.py（顶部，最先执行）
from dotenv import load_dotenv
load_dotenv()

# skill.py（顶部）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv 可选依赖，失败静默处理
```

### 9.2 配置读取最佳实践

使用专用配置函数，而不是到处散落 `os.getenv`：

```python
# config/settings.py
def get_llm_config() -> LLMConfig:
    return LLMConfig(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        timeout=int(os.getenv("LLM_TIMEOUT", 60)),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", 3))
    )
```

### 9.3 .env.example 文件

始终提供 `.env.example`，注明每个变量的用途和示例值：

```bash
# 基础配置（必需）
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max

# 视觉模型（可选，用于印章/签名检测）
VISION_MODEL=qwen3-vl-flash
# VISION_API_KEY=your-vision-key    # 默认使用 LLM_API_KEY
# VISION_BASE_URL=https://...       # 默认使用 LLM_BASE_URL
```

---

## 10. 可选依赖管理

### 10.1 依赖分层策略

并非所有功能都需要安装，使用 `try/except ImportError` 做运行时检测：

```python
# ocr_engine.py
try:
    from paddleocr import PaddleOCR
    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False
    # 不用 logger.warning！避免模块导入时向 stderr 输出，
    # 否则会导致 MCP Server 启动失败（ExitCode=1）

class PaddleOCREngine:
    def is_available(self) -> bool:
        return HAS_PADDLE
```

**重要警告**：不要在模块顶层使用 `logger.warning()`，只能用 `logging.warning()` 或完全不输出。模块顶层向 stderr 输出会让 MCP Server 误判为启动失败。

### 10.2 pyproject.toml 可选依赖

```toml
[project.optional-dependencies]
local-ocr = ["paddleocr>=2.7", "paddlepaddle"]
cloud-ocr = ["alibabacloud-ocr-api20210707"]

# 用户安装时选择：
# pip install -e .              # 基础（无OCR）
# pip install -e ".[local-ocr]" # 本地OCR
# pip install -e ".[cloud-ocr]" # 云端OCR
```

---

## 11. 本地测试

### 11.1 不启动 MCP Server 直接测试

```python
# run_check.py
import asyncio
from dotenv import load_dotenv
load_dotenv()  # 必须先加载！

from compliance_checker.skill import ComplianceSkill

async def main():
    skill = ComplianceSkill()
    result = await skill.check(
        project_path="./docs",
        requirements="检查是否有发票，验证日期是否有效，是否有印章",
        project_period={"start": "2026-01", "end": "2026-12"}
    )
    print(result["issues_description"])
    print(f"\n执行时间: {result['execution_time']:.2f}s")

asyncio.run(main())
```

### 11.2 在 Cherry Studio 中配置

```json
{
  "mcpServers": {
    "compliance-checker": {
      "command": "python",
      "args": ["-m", "compliance_checker.server"],
      "cwd": "/path/to/compliance_checker_light",
      "env": {
        "PYTHONPATH": "/path/to/compliance_checker_light/src"
      }
    }
  }
}
```

或直接用安装后的命令：

```json
{
  "mcpServers": {
    "compliance-checker": {
      "command": "compliance-checker"
    }
  }
}
```

---

## 12. 常见问题解决

### Q1：MCP Server 启动失败（ExitCode=1）

**原因**：模块导入时有内容输出到 stderr。

**排查**：
```bash
python -m compliance_checker.server 2>&1 | head -20
```

**常见原因和修复**：

```python
# ❌ 错误：模块顶层 logger.warning 向 stderr 输出
import logging
logger = logging.getLogger(__name__)
try:
    import paddleocr
except ImportError:
    logger.warning("PaddleOCR 未安装")  # 这会导致 ExitCode=1！

# ✅ 正确：只设置标志，不输出
try:
    import paddleocr
    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False  # 静默处理
```

### Q2：AI 不知道调用哪个工具

**原因**：工具的 docstring 不够清晰。

**修复**：在 docstring 中明确说明使用场景、参数格式、返回值结构：

```python
@mcp.tool()
async def check_with_description(project_path: str, requirements: str) -> dict:
    """
    自然语言合规审查 - 最常用的审查接口
    
    当用户说"帮我检查 /path/to/docs 文件夹中的文件是否合规"时使用此工具。
    
    Args:
        project_path: 文件夹的绝对路径，如 "/data/project/documents"
        requirements: 用中文描述检查要求，如"检查是否有公章和有效期"
    
    Returns: {"success": bool, "issues_description": "文字描述", ...}
    """
```

### Q3：视觉检查不可用但结果显示全部通过

**原因**：当文本检查通过而视觉检查不可用时，之前的实现没有将状态降级。

**修复**（已在本项目实现）：
```python
# 无论文本检查是否通过，视觉检查不可用时都标记为 UNCLEAR
if check_item:
    check_item.message += " [建议启用视觉检查确认]"
    if check_item.status == CheckStatus.PASS:
        check_item.status = CheckStatus.UNCLEAR  # 强制降级
```

### Q4：API 端点配置错误导致 404

**原因**：不同厂商的视觉 API 端点和请求格式不同。

**解决方案**：自动检测端点类型并切换请求格式：

```python
# 检测是否为 OpenAI 兼容模式
self.use_openai_format = (
    "compatible-mode" in self.base_url or
    self.base_url.rstrip("/").endswith("/v1")
)

# 根据端点类型构造不同的请求
if self.use_openai_format:
    url = f"{self.base_url}/chat/completions"
    # OpenAI 格式请求体
else:
    url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
    # 阿里云原生格式请求体
```

### Q5：LLM 生成的 YAML 解析失败

**原因**：LLM 输出的 YAML 可能带有 ` ```yaml ``` ` 标记，或格式不规范。

**处理**：

```python
def _clean_yaml_content(self, content: str) -> str:
    # 去除 markdown 代码块
    lines = content.strip().split('\n')
    start = next((i for i, l in enumerate(lines) 
                  if l.strip() and not l.strip().startswith('`')), 0)
    end = next((i+1 for i in range(len(lines)-1, -1, -1)
                if lines[i].strip() and not lines[i].strip().startswith('`')), len(lines))
    return '\n'.join(lines[start:end])

# 解析时提供友好错误
try:
    data = yaml.safe_load(cleaned)
    if "checklist" not in data:
        raise ValueError("缺少 'checklist' 根节点")
except yaml.YAMLError as e:
    raise ValueError(f"LLM 生成了无效的 YAML: {e}\n原始内容: {content[:200]}")
```

### Q6：异步环境中使用同步库

**原因**：某些库（如 PyMuPDF、PaddleOCR）只有同步接口。

**解决**：用线程池包装：

```python
import asyncio

async def parse_pdf_async(file_path: str) -> Document:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_pdf_sync, file_path)
```

---

## 13. 最佳实践总结

| 类别 | 实践 |
|------|------|
| 接口设计 | 自然语言输入 + 文本格式输出，参数尽量少 |
| 错误处理 | 不抛异常，用返回值传递错误；提供 `error_type` 字段 |
| 模型集成 | 两级优先级配置；自动检测端点格式；实现 `is_available()` |
| 并发控制 | 用 `asyncio.gather` 并行；用 `Semaphore` 限流；每个任务设超时 |
| 降级策略 | 不可用功能返回 `UNAVAILABLE`，不阻断整体流程 |
| 状态准确性 | 视觉检查不可用时强制降级为 `UNCLEAR`，不允许错误的 `PASS` |
| 依赖管理 | 可选依赖用 `try/except`；模块顶层不向 stderr 输出 |
| 测试 | 提供 `run_check.py` 可不启动 MCP 直接测试 Skill 逻辑 |
