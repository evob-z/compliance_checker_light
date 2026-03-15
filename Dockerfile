# Compliance Checker MCP Service - 智能构建 Dockerfile
# =============================================================================
# 构建参数:
#   OCR_BACKEND: OCR后端类型 [none|local|cloud]，默认 none
#
# 构建示例:
#   # 基础镜像（无OCR，最小化）
#   docker build -t compliance-checker:latest .
#
#   # 带本地OCR（PaddleOCR，体积大）
#   docker build --build-arg OCR_BACKEND=local -t compliance-checker:local-ocr .
#
#   # 带云端OCR（阿里云OCR，轻量）
#   docker build --build-arg OCR_BACKEND=cloud -t compliance-checker:cloud-ocr .
# =============================================================================

FROM python:3.11-slim

# 构建参数定义
ARG OCR_BACKEND=none

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 复制项目配置文件和源代码
COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# 安装基础依赖（使用 pyproject.toml）
RUN pip install --no-cache-dir -e .

# 根据 OCR_BACKEND 参数条件安装 OCR 依赖
RUN if [ "${OCR_BACKEND}" = "local" ]; then \
        echo "Installing PaddleOCR (local OCR)..." && \
        pip install --no-cache-dir -e ".[local-ocr]"; \
    elif [ "${OCR_BACKEND}" = "cloud" ]; then \
        echo "Installing Aliyun OCR (cloud OCR)..." && \
        pip install --no-cache-dir -e ".[cloud-ocr]"; \
    else \
        echo "OCR disabled (minimal image)"; \
    fi

# 复制环境配置示例
COPY .env.example .

# 设置 Python 路径
ENV PYTHONPATH=/app/src

# 暴露端口（MCP Server 默认使用 stdio，但预留 HTTP 端口）
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import compliance_checker" || exit 1

# 默认启动命令
CMD ["compliance-checker"]
