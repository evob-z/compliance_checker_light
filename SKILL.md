---
name: compliance-checker
version: 1.0.0
license: MIT
description: >
  AI 驱动的项目手续合规审查 Skill。通过 CLI 子命令检查 PDF/Word/图片文档的
  完整性、时效性和合规性（印章/签名）。当用户需要审查项目文档是否齐全、有效、
  合规时使用。典型场景：建设工程手续审查、发票合规检查、行政审批材料审查。
allowed-tools:
  - Bash
  - Read
  - Glob
metadata:
  openclaw:
    requires:
      bins: [python, pip]
      install: pip install compliance-checker
      env:
        # LLM 核心配置
        - LLM_API_KEY
        - LLM_BASE_URL
        - LLM_MODEL
        # LLM 可选配置
        - LLM_TIMEOUT
        - LLM_MAX_RETRIES
        # 嵌入模型配置（可选，用于语义匹配）
        - EMBED_API_KEY
        - EMBED_BASE_URL
        - EMBED_MODEL
        # 视觉模型配置（可选，用于印章/签名检测）
        - VISION_API_KEY
        - VISION_MODEL
        # OCR 配置（可选）
        - OCR_BACKEND
        - ALIBABA_CLOUD_ACCESS_KEY_ID
        - ALIBABA_CLOUD_ACCESS_KEY_SECRET
        - ALIBABA_CLOUD_OCR_ENDPOINT
        # 功能开关配置（可选）
        - CC_SIMILARITY_THRESHOLD
        - CC_USE_SEMANTIC
        - CC_VISUAL_ENABLED
        - CC_VISUAL_CONFIDENCE_THRESHOLD
        - CC_VISUAL_CHECK_TYPE
        - CC_PDF_ZOOM_FACTOR
        - CC_OUTPUT_DIR
        - CC_DOCUMENT_PATH
---

# Compliance Checker - 项目手续合规审查 CLI

## 核心能力

- 资料完整性核对（精确+语义匹配文件名）
- 资料时效性核对（有效期判定）
- 视觉合规检测（Qwen-VL 识别印章/签名）

## CLI 子命令

本工具提供 3 个原子子命令，所有输出均为 JSON（stdout），日志写 stderr。

### 1. completeness - 文档批量嗅探

扫描目录中的文件，与给定文档名称列表做精确+语义匹配。

```bash
compliance-checker completeness --path <目录路径> --documents <逗号分隔的文档名>
```

**参数：**

| 参数 | 必需 | 说明 |
|------|------|------|
| --path | 是 | 项目文件夹路径 |
| --documents | 是 | 逗号分隔的文档名称列表 |

**输出示例：**

```json
{
  "立项批复": {
    "path": "D:/docs/立项批复.pdf",
    "similarity": 1.0,
    "match_type": "exact"
  },
  "环评报告": {
    "path": "D:/docs/环境评价报告.pdf",
    "similarity": 0.85,
    "match_type": "semantic"
  },
  "施工许可证": null
}
```

- `match_type` 为 `exact` 表示精确匹配（子串包含），`semantic` 表示语义匹配
- 值为 `null` 表示目录中未找到匹配文件

### 2. timeliness - 时效性计算

解析单个文件，提取日期信息，判定文档时效性状态。

```bash
compliance-checker timeliness --file <文件路径> [--reference-time YYYY-MM-DD]
```

**参数：**

| 参数 | 必需 | 说明 |
|------|------|------|
| --file | 是 | 文件路径（.pdf / .docx / .doc / 图片） |
| --reference-time | 否 | 校验基准时间（YYYY-MM-DD），默认为当前时间 |

**输出示例：**

```json
{
  "status": "VALID",
  "sign_date": "2025-06-15",
  "expiry_date": "2026-06-15",
  "validity": "365天",
  "branch": "HAS_EXPIRY",
  "reason": "文件在有效期内"
}
```

- `status`: `VALID`（有效）/ `EXPIRED`（过期）/ `UNKNOWN`（无法判定）

### 3. visual - 视觉质检

检测文档中的印章、签名等视觉元素。

```bash
compliance-checker visual --file <文件路径> --targets <逗号分隔的检测目标>
```

**参数：**

| 参数 | 必需 | 说明 |
|------|------|------|
| --file | 是 | 文件路径（.pdf / 图片） |
| --targets | 是 | 逗号分隔的检测目标（如"公章,法人签字"） |

**targets 命名规则：**

- 含"章"的视为印章检测（如"公章"、"发票专用章"、"骑缝章"）
- 含"签"的视为签名检测（如"法人签字"、"经办人签名"）
- 用户的原始 target 字符串会透传到 Qwen-VL 的 Prompt 中

**输出示例：**

```json
{
  "公章": {
    "found": true,
    "confidence": 0.95,
    "location": "右下角",
    "reasoning": "检测到红色圆形公章"
  },
  "法人签字": {
    "found": false,
    "confidence": 0.0,
    "location": "",
    "reasoning": "已检查 2 页，未找到法人签字"
  }
}
```

## 全局选项

```bash
compliance-checker --version        # 输出版本号
compliance-checker --health-check   # 输出 JSON 格式的健康状态
```

## 路径规则

传递路径参数时，**建议使用正斜杠 (/)**：

- 推荐：`D:/projects/docs`
- 可用但不推荐：`D:\projects\docs`

## 典型工作流

当用户要求审查文档时，按以下步骤执行：

1. **验证安装**：首次使用前运行 `compliance-checker --version` 确认可用
2. **确认文件位置**：**优先使用用户明确提供的具体路径**
   - 如用户已提供路径，直接使用，不进行扫描
   - 如用户未提供路径，可询问或进行**有限范围**的路径探测
3. **分析用户意图**：从用户描述中提取检查维度：
   - 需要检查哪些文件 -> 使用 `completeness`
   - 需要检查有效期 -> 使用 `timeliness`
   - 需要检查印章/签名 -> 使用 `visual`
4. **执行子命令**：根据需要调用一个或多个子命令
5. **汇总结果**：解析 JSON 输出，向用户汇报

### 路径探测约束（安全规范）

仅在用户未提供路径时，允许使用 Glob/Bash 进行**有限范围**的路径探测：

- **范围限制**：仅扫描当前工作目录及其**一级子目录**（`./` 和 `./*/`)）
- **禁止递归**：不允许使用 `**/` 等递归模式进行无限制扫描
- **文件类型限制**：仅扫描支持的文档格式（.pdf, .docx, .doc, .png, .jpg, .jpeg）
- **用户确认**：扫描结果应展示给用户，由用户确认后再执行检查

**推荐做法**：
```bash
# 优先询问用户
"请提供文档所在路径，或确认是否扫描当前目录？"

# 有限范围扫描示例（仅一级子目录）
glob "*.pdf" "*.docx"          # 当前目录
glob "*/*.pdf" "*/*.docx"      # 一级子目录（不推荐）
```

### 示例：发票审查

```bash
# 步骤1：检查发票文件是否存在
compliance-checker completeness --path "D:/finance/invoices" --documents "增值税发票,收据"

# 步骤2：检查时效性
compliance-checker timeliness --file "D:/finance/invoices/增值税发票.pdf" --reference-time 2026-03-15

# 步骤3：检查印章
compliance-checker visual --file "D:/finance/invoices/增值税发票.pdf" --targets "发票专用章"
```

### 示例：工程手续审查

```bash
# 步骤1：批量检查文件完整性
compliance-checker completeness --path "D:/projects/building" --documents "立项批复,环评批复,施工许可证"

# 步骤2：对每个找到的文件逐一检查时效性
compliance-checker timeliness --file "D:/projects/building/立项批复.pdf"
compliance-checker timeliness --file "D:/projects/building/环评批复.pdf"

# 步骤3：检查是否盖有公章
compliance-checker visual --file "D:/projects/building/立项批复.pdf" --targets "公章"
```

## 错误处理

所有错误以 JSON 格式输出到 stdout，CLI 返回非零退出码：

```json
{
  "error": "目录不存在: D:/nonexistent",
  "error_type": "FileNotFoundError"
}
```

| 错误类型 | 含义 | 恢复策略 |
|----------|------|----------|
| FileNotFoundError | 文件/目录不存在 | 用 Glob/Bash 确认路径 |
| ValueError | 参数格式错误 | 检查参数格式（逗号分隔、日期格式等） |
| InternalError | 内部异常 | 运行 `--health-check` 检查环境配置 |

## 支持的文档格式

- PDF（支持 OCR 识别扫描件）
- Word（.docx, .doc）
- 图片（.png, .jpg, .jpeg）

## 支持的日期格式（timeliness 命令）

- `2024年3月15日`
- `2024-03-15`
- `2024/03/15`
- `2024年3月`（自动补全为3月31日）

---

# 安装与配置（给用户）

## 安装

**步骤 1：创建并激活虚拟环境（venv）**

```bash
# 创建虚拟环境
python -m venv .venv

# Windows PowerShell 激活
.venv\Scripts\activate

# 或 Windows CMD 激活
.venv\Scripts\activate.bat

# 或 Linux/Mac 激活
source .venv/bin/activate
```

**步骤 2：安装 compliance-checker**

```bash
pip install compliance-checker
```

## 验证安装

```bash
compliance-checker --version
compliance-checker --health-check
```

## 环境变量配置

### 必需

```bash
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max
```

可将以上变量配置为系统环境变量，或写入 `~/.compliance-checker/.env` 文件。

### 可选

```bash
EMBED_MODEL=text-embedding-v1          # 嵌入模型（语义匹配文件名）
VISION_MODEL=qwen3-vl-flash            # 视觉模型（印章/签名检测）
# EMBED_API_KEY=your-embed-key         # 嵌入模型独立 API Key
# VISION_API_KEY=your-vision-key       # 视觉模型独立 API Key
# OCR_BACKEND=none                     # none / paddle / aliyun
```
