# ComplianceSkill 完整逻辑架构

## 1. 总体架构概览

```
用户/AI Agent
    │
    │ 自然语言需求 + 文件夹路径
    ▼
┌─────────────────────────────────────────────────────┐
│  MCP Server (server.py)                              │
│  @mcp.tool() check_with_description                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  ComplianceSkill (skill.py)                          │
│  skill.check(project_path, requirements, period)     │
└──┬────────────────────────────────────────────┬──────┘
   │                                            │
   ▼                                            ▼
文档解析层                                  清单生成层
PDFParser / DocxParser              LLM → YAML Checklist
   │                                            │
   └──────────────┬─────────────────────────────┘
                  ▼
   ┌──────────────────────────────────────────┐
   │  DeclarativeCheckEngine (engine)          │
   │  _build_check_plan → _execute_parallel   │
   └──┬────────────┬─────────────┬────────────┘
      │            │             │
      ▼            ▼             ▼
CompletenessChecker  TimelinessChecker  ComplianceChecker
   （完整性）          （时效性）           （合规性）
                                        │
                                        ▼
                                  VisualChecker
                                  QwenVLClient
                                   （视觉检测）
                  │
                  ▼
   ┌──────────────────────────────────────────┐
   │  skill_formatter.py                       │
   │  format_check_result / format_simple_result│
   └──────────────────────────────────────────┘
                  │
                  ▼
         文本格式结果输出
```

---

## 2. 完整执行流程

### 2.1 入口：MCP Tool 调用

`server.py` 中用 `@mcp.tool()` 暴露给 AI Agent 的主入口：

```python
@mcp.tool()
async def check_with_description(
    project_path: str,
    requirements: str,
    project_period: Optional[Dict[str, str]] = None
) -> dict:
    skill = ComplianceSkill()
    return await skill.check(project_path, requirements, project_period)
```

错误统一在此捕获并转换为结构化返回值（`FileNotFoundError`、`ValueError`、`Exception`）。

---

### 2.2 ComplianceSkill.check() 六步流程

**文件**: `skill.py`

| 步骤 | 操作 | 关键方法 |
|------|------|---------|
| 1 | 验证路径存在且为目录 | `Path.exists()` / `Path.is_dir()` |
| 2 | 扫描文档（PDF/DOCX/DOC） | `_scan_documents()` |
| 3 | 解析文档内容 | `_parse_documents()` → `PDFParser` / `DocxParser` |
| 4 | LLM 生成检查清单 | `async_generate_checklist_with_period()` |
| 5 | 执行检查引擎 | `engine.execute(documents, checklist)` |
| 6 | 格式化并返回结果 | `format_check_result()` / `format_simple_result()` |

**返回字段**：

```python
{
    "success": bool,
    "summary": {"total_checks": int, "passed": int, "failed": int, "errors": int, "unavailable": int},
    "issues_description": str,     # 文本格式，供 AI 直接阅读
    "issues_simple": List[dict],   # 结构化问题列表
    "generated_checklist": dict,   # 生成的 YAML 清单
    "document_count": int,
    "execution_time": float,
    "project_id": str
}
```

---

### 2.3 文档解析层

**文件**: `parsers/pdf_parser.py`, `parsers/docx_parser.py`

- `PDFParser.parse(path)` — 基于 PyMuPDF (`fitz`) 提取文本，在线程池中异步调用
- `DocxParser.parse(path)` — 解析 Word 文档内容
- 可选 OCR（由 `OCR_BACKEND` 环境变量控制）：
  - `none`（默认）：仅处理可编辑 PDF
  - `paddle`：本地 PaddleOCR
  - `aliyun`：阿里云 OCR API

所有解析结果封装为 `Document` 对象：

```python
Document(
    path: str,
    name: str,
    type: str,          # pdf / docx
    pages: int,
    pages_content: List[str],   # 每页文本
    metadata: dict
)
```

---

### 2.4 LLM 清单生成层

**文件**: `prompts/checklist_generator.py`, `llm/client.py`

```
用户需求(中文) → generate_checklist_prompt() → Prompt字符串
    → LLMClient.complete() → LLM API (OpenAI兼容)
    → YAML文本 → yaml.safe_load() → Checklist对象
```

- Prompt 包含：可用检查类型说明、常见文档类型知识库、输出格式规范
- `_clean_yaml_content()` 去除 LLM 返回的 ` ```yaml ``` ` 代码块标记
- 如果提供了 `project_period`，注入到生成的清单中

清单数据结构（YAML → Pydantic `Checklist`）：

```yaml
checklist:
  id: "construction_project"
  name: "建设工程项目合规审查"
  required_documents:
    - name: "立项批复"
      aliases: ["立项文件", "批复"]
      checks:
        - type: "completeness"
          required: true
        - type: "timeliness"
          required: true
        - type: "compliance"
          required: true
          points: ["公章", "签字", "文号"]
        - type: "visual"
          required: false
          target: "seal"
```

---

### 2.5 声明式检查引擎

**文件**: `engine/declarative_engine.py`

#### 步骤 1：构建检查计划 `_build_check_plan()`

将清单 + 文档列表 → `List[CheckTask]`

**文档匹配规则**（`_match_document_to_checklist()`）：
1. 文档文件名包含清单中的标准名称（大小写不敏感）
2. 文档文件名包含清单中的任一别名

**任务分级**：
- `completeness` → **项目级别**（`doc_name="__PROJECT_LEVEL__"`），传入所有文档，只创建一次
- `timeliness` / `compliance` / `visual` → **文档级别**，每个匹配文档各创建一次

`CheckTask` 字段：
```python
CheckTask(
    doc_name: str,        # 文档名或 "__PROJECT_LEVEL__"
    doc_type: str,        # 文档类型（清单中的 name）
    check_type: str,      # 检查类型
    documents: List[Document],
    config: dict,         # 检查配置（来自清单 checks 项）
    required: bool        # 是否必需
)
```

#### 步骤 2：并行执行 `_execute_parallel()`

- 使用 `asyncio.Semaphore` 控制最大并发数（默认 3）
- 每个任务有超时控制（默认 300 秒）
- 执行逻辑：

```
registry.get(check_type)
    ├── 若是 UnavailableChecker → 直接执行，返回 UNAVAILABLE
    └── 若是真实检查器
            ├── validate_config() 验证配置
            └── checker.check(documents, checklist, config)
```

#### 步骤 3：汇总结果 `_aggregate_results()`

状态统计：

| 状态 | 计数字段 | 是否阻断 |
|------|---------|---------|
| `PASS` | `passed` | 否 |
| `FAIL` | `failed` | 仅当 `required=True` |
| `UNAVAILABLE` | `unavailable` | **否**（不阻断流程） |
| 其他（`ERROR`、`UNCLEAR` 等） | `errors` | 仅当 `required=True` |

`success = not has_blocking_error`

---

## 3. 各检查器工作原理

### 3.1 完整性检查器（CompletenessChecker）

**文件**: `checkers/completeness_checker.py`

项目级别检查，遍历清单中所有 `required_documents`，对每个文档执行：

1. **精确匹配**：文档文件名包含清单名称或别名
2. **语义匹配**（若 `use_semantic=True`）：使用嵌入模型计算文件名相似度
   - 嵌入模型配置：`EMBED_MODEL` + `EMBED_API_KEY`（默认回退到 `LLM_API_KEY`）
   - 相似度阈值：`CC_SIMILARITY_THRESHOLD`（默认 0.75）
3. 若都未匹配 → 标记为 `MISSING`

输出：缺失文档列表、匹配文档列表、整体状态（`PASS` / `FAIL`）

---

### 3.2 时效性检查器（TimelinessChecker）

**文件**: `checkers/timeliness_checker.py`

从文档文本中提取日期信息，支持格式：
- `2024年3月15日`、`2024-03-15`、`2024/03/15`
- `有效期至 2026年5月`
- `有效期一年`（相对有效期）

与 `project_period`（项目周期）对比，判断：
- 文件有效期是否覆盖项目周期
- 签发日期是否在合理范围

---

### 3.3 合规性检查器（ComplianceChecker）

**文件**: `checkers/compliance_checker.py`，核心逻辑在 `tools/compliance.py`

遍历清单 `checks.points` 列表，对每个检查点：

```
检查点 → 判断 check_method
    ├── TEXT / BOTH → 文本关键词检查（公章/签字/编号/日期）
    └── VISUAL / BOTH → 视觉检查
            ├── 视觉可用 → 调用 VisualInspector（截图 + Qwen-VL）
            └── 视觉不可用 → 无论文本是否通过，都标记为 UNCLEAR
```

**关键行为**：当 `check_method=BOTH` 且视觉检查不可用时：
- 文本检查结果 `PASS` → 降级为 `UNCLEAR`（附加"建议启用视觉检查确认"）
- 文本检查结果 `FAIL` → 保持 `UNCLEAR`

---

### 3.4 视觉检查器（VisualChecker + QwenVLClient）

**文件**: `checkers/visual_checker.py`, `visual/qwen_client.py`

两阶段检测：

```
阶段1（可选）: OCR 定位
    search_context → PaddleOCRRegionDetector.locate_by_text()
    → 获取目标区域 bbox

阶段2: 视觉确认
    capture_page(pdf_path, page_num, bbox) → PNG 截图
    → base64 编码
    → QwenVLClient.chat(image_path, prompt)
    → 解析检测结果（found, confidence, reasoning）
```

**API 调用格式自动检测**（`qwen_client.py`）：

| 端点特征 | 请求格式 | API 路径 |
|---------|---------|---------|
| 含 `compatible-mode` 或以 `/v1` 结尾 | OpenAI 格式 | `/chat/completions` |
| 其他 | 阿里云原生格式 | `/services/aigc/multimodal-generation/generation` |

**响应解析**（`_extract_content_from_response()`）：
- 兼容 OpenAI 格式：`choices[0].message.content`
- 兼容阿里云格式：`output.choices[0].message.content`
- 支持列表类型内容（新版 API）

**API Key 优先级**：`VISION_API_KEY` > `LLM_API_KEY`  
**Base URL 优先级**：`VISION_BASE_URL` > `LLM_BASE_URL` > 默认值

---

## 4. 检查器注册机制

**文件**: `core/checker_registry.py`

`CheckerRegistry` 采用**单例模式**（双重检查锁定，线程安全）：

```
get_initialized_registry()
    ├── register(CompletenessChecker)
    ├── register(TimelinessChecker)
    ├── register(ComplianceChecker)
    ├── register(VisualChecker)
    └── register_unavailable("authenticity", "cross_reference", ...)

engine.registry.get(check_type)
    ├── 检查器存在且 is_available() → 返回真实检查器
    ├── 检查器存在但不可用 → 返回 UnavailableChecker
    ├── 标记为待开发 → 返回 UnavailableChecker
    └── 完全未知 → 返回 UnavailableChecker（宽容处理）
```

`UnavailableChecker` 是占位实现，执行时直接返回 `UNAVAILABLE` 状态，不抛异常。

---

## 5. 环境变量配置

### 5.1 加载机制

有两处加载点：

| 加载位置 | 时机 | 适用场景 |
|---------|------|---------|
| `server.py` 顶部 `load_dotenv()` | MCP 服务启动时 | Cherry Studio 等外部启动 |
| `skill.py` 顶部 `load_dotenv()` | Skill 导入时 | 直接 Python 调用 |

`.env` 文件需放在项目根目录。

### 5.2 配置优先级（各模型）

```
视觉模型:
  API Key:  VISION_API_KEY  >  LLM_API_KEY
  Base URL: VISION_BASE_URL >  LLM_BASE_URL  >  默认值
  模型名:   VISION_MODEL    >  "qwen3-vl-flash"（默认）

嵌入模型:
  API Key:  EMBED_API_KEY   >  LLM_API_KEY
  Base URL: LLM_BASE_URL
  模型名:   EMBED_MODEL     >  简单字符匹配（降级）

LLM（清单生成）:
  API Key:  LLM_API_KEY
  Base URL: LLM_BASE_URL    >  OpenAI 默认
  模型名:   LLM_MODEL
```

### 5.3 完整环境变量列表

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_API_KEY` | — | 必需，LLM API 密钥 |
| `LLM_BASE_URL` | OpenAI API | API 端点 |
| `LLM_MODEL` | — | 主模型名称 |
| `EMBED_MODEL` | — | 嵌入模型（留空则字符匹配） |
| `EMBED_API_KEY` | = LLM_API_KEY | 嵌入模型独立密钥 |
| `VISION_MODEL` | `qwen3-vl-flash` | 视觉模型名称 |
| `VISION_API_KEY` | = LLM_API_KEY | 视觉模型独立密钥 |
| `VISION_BASE_URL` | = LLM_BASE_URL | 视觉模型独立端点 |
| `OCR_BACKEND` | `none` | OCR 后端：none/paddle/aliyun |
| `LLM_TIMEOUT` | 60 | LLM 请求超时（秒） |
| `LLM_MAX_RETRIES` | 3 | LLM 重试次数 |
| `CC_MAX_CONCURRENT` | 3 | 最大并发检查数 |
| `CC_CHECK_TIMEOUT` | 300 | 单个检查超时（秒） |
| `CC_SIMILARITY_THRESHOLD` | 0.75 | 语义匹配阈值 |

---

## 6. 错误处理与不可用状态

### 6.1 三级错误处理

```
Level 1: MCP 工具层 (server.py)
    捕获: FileNotFoundError / ValueError / Exception
    返回: {"success": False, "error": "...", "error_type": "..."}

Level 2: 引擎层 (declarative_engine.py)
    捕获: 检查器执行异常、超时
    返回: CheckResult(status=ERROR, message="执行异常: ...")

Level 3: 检查器层 (各 checker)
    捕获: API 调用失败、解析错误
    返回: CheckResult(status=ERROR/UNAVAILABLE, message="...")
```

### 6.2 不可用状态处理策略

| 场景 | 处理方式 | 最终状态 |
|------|---------|---------|
| 视觉 API Key 未配置 | `is_available()=False` → 不调用 API | `UNAVAILABLE` |
| 视觉检查不可用但文本通过 | 强制降级 | `UNCLEAR`（计入 errors）|
| 视觉检查不可用且文本未找到 | 创建 UNCLEAR 结果 | `UNCLEAR`（计入 errors）|
| 检查器未实现（开发中） | `UnavailableChecker` 处理 | `UNAVAILABLE`（不阻断）|
| 视觉 API 返回 404 | 标记 `unavailable: True` | 返回错误信息 |

### 6.3 UNAVAILABLE vs UNCLEAR vs ERROR

| 状态 | 含义 | 来源 | 计入统计 | 是否阻断 |
|------|------|------|---------|---------|
| `UNAVAILABLE` | 功能整体不可用（未开发/未配置） | `UnavailableChecker`、`VisualChecker.is_available()=False` | `unavailable` | **否** |
| `UNCLEAR` | 检查执行了但结论不确定 | 视觉不可用时文本检查的降级结果 | `errors` | 当 `required=True` |
| `ERROR` | 检查执行异常 | 超时、API错误、解析失败 | `errors` | 当 `required=True` |

---

## 7. 结果格式化

**文件**: `skill_formatter.py`

### `format_check_result()` → 文本格式（供 AI 读取）

```
==================================================
合规审查结果
==================================================
检查总数: 5
通过: 3 项
失败: 1 项
错误: 1 项
暂不可用: 0 项
执行时间: 8.32 秒

--------------------------------------------------
【文档: 立项批复.pdf】
--------------------------------------------------
  ❌ [合规性] 未找到公章 [建议启用视觉检查确认]
  ⚠️ [视觉检查] 视觉检查不可用，请配置 QWEN_API_KEY
```

### `format_simple_result()` → 结构化字典（供程序处理）

```python
{
    "success": bool,
    "summary": {"total_checks": 5, "passed": 3, ...},
    "issues_count": 2,
    "issues": [
        {"document": "立项批复", "check_type": "compliance", "status": "FAIL", ...}
    ]
}
```

---

## 8. MCP Server 接口一览

| 工具名 | 暴露方式 | 说明 |
|--------|---------|------|
| `check_with_description` | `@mcp.tool()` | 主入口：自然语言合规审查 |
| `run_compliance_check` | `@mcp.tool()` | 高级接口：预定义清单 |
| `list_available_checkers` | `@mcp.tool()` | 列出所有检查器状态 |
| `validate_checklist` | 未暴露为 MCP tool | 验证清单 YAML |
| `get_checklist_generation_prompt` | 未暴露为 MCP tool | 获取清单生成 Prompt |
| `visual_inspection_tool` | 未暴露为 MCP tool | 独立视觉检查 |
