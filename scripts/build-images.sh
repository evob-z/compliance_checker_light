#!/bin/bash
# =============================================================================
# Compliance Checker Docker 镜像构建脚本
# =============================================================================
# 用法:
#   ./scripts/build-images.sh [options]
#
# 选项:
#   -t, --tag <tag>          镜像标签 (默认: latest)
#   -r, --registry <url>     镜像仓库 (默认: ghcr.io)
#   -o, --ocr <backend>      OCR后端: none|local|cloud (默认: none)
#   -p, --push               构建后推送镜像
#   -a, --all                构建所有 OCR 变体
#   -h, --help               显示帮助
#
# 示例:
#   ./scripts/build-images.sh -t v1.0.0 -p
#   ./scripts/build-images.sh -t v1.0.0 -o local -p
#   ./scripts/build-images.sh -t v1.0.0 -a -p
# =============================================================================

set -e

# 默认配置
REGISTRY="ghcr.io"
IMAGE_NAME="evob-z/compliance_checker_light"
TAG="latest"
OCR_BACKEND="none"
PUSH=false
BUILD_ALL=false

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    -t|--tag)
      TAG="$2"
      shift 2
      ;;
    -r|--registry)
      REGISTRY="$2"
      shift 2
      ;;
    -o|--ocr)
      OCR_BACKEND="$2"
      shift 2
      ;;
    -p|--push)
      PUSH=true
      shift
      ;;
    -a|--all)
      BUILD_ALL=true
      shift
      ;;
    -h|--help)
      echo "用法: $0 [options]"
      echo ""
      echo "选项:"
      echo "  -t, --tag <tag>          镜像标签 (默认: latest)"
      echo "  -r, --registry <url>     镜像仓库 (默认: ghcr.io)"
      echo "  -o, --ocr <backend>      OCR后端: none|local|cloud (默认: none)"
      echo "  -p, --push               构建后推送镜像"
      echo "  -a, --all                构建所有 OCR 变体"
      echo "  -h, --help               显示帮助"
      echo ""
      echo "示例:"
      echo "  $0 -t v1.0.0 -p"
      echo "  $0 -t v1.0.0 -o local -p"
      echo "  $0 -t v1.0.0 -a -p"
      exit 0
      ;;
    *)
      echo "未知选项: $1"
      exit 1
      ;;
  esac
done

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# 构建单个镜像
build_image() {
  local ocr=$1
  local tag_suffix=""
  
  case $ocr in
    none)
      tag_suffix=""
      ;;
    local)
      tag_suffix="-local-ocr"
      ;;
    cloud)
      tag_suffix="-cloud-ocr"
      ;;
    *)
      log_error "未知的 OCR 后端: $ocr"
      exit 1
      ;;
  esac
  
  local full_tag="${REGISTRY}/${IMAGE_NAME}:${TAG}${tag_suffix}"
  
  log_info "构建镜像: $full_tag (OCR_BACKEND=$ocr)"
  
  docker build \
    --build-arg OCR_BACKEND=$ocr \
    -t $full_tag \
    -f Dockerfile \
    .
  
  if [ "$PUSH" = true ]; then
    log_info "推送镜像: $full_tag"
    docker push $full_tag
  fi
  
  echo ""
}

# 主逻辑
main() {
  log_info "开始构建 Docker 镜像"
  log_info "Registry: $REGISTRY"
  log_info "Image: $IMAGE_NAME"
  log_info "Tag: $TAG"
  log_info "Push: $PUSH"
  echo ""
  
  # 检查 Docker 是否可用
  if ! command -v docker &> /dev/null; then
    log_error "Docker 未安装"
    exit 1
  fi
  
  # 获取脚本所在目录
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
  
  cd "$PROJECT_ROOT"
  
  if [ "$BUILD_ALL" = true ]; then
    log_info "构建所有 OCR 变体..."
    build_image "none"
    build_image "local"
    build_image "cloud"
  else
    build_image "$OCR_BACKEND"
  fi
  
  log_info "镜像构建完成!"
  
  # 显示构建的镜像
  echo ""
  log_info "已构建的镜像:"
  docker images "${REGISTRY}/${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep "$TAG"
}

main "$@"
