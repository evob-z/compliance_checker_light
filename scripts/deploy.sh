#!/bin/bash
# =============================================================================
# Compliance Checker 部署脚本
# =============================================================================
# 用法:
#   ./scripts/deploy.sh [options]
#
# 选项:
#   -e, --env <environment>  部署环境: dev|staging|prod (默认: dev)
#   -t, --tag <tag>          镜像标签 (默认: latest)
#   -o, --ocr <backend>      OCR后端: none|local|cloud (默认: none)
#   -m, --method <method>    部署方式: compose|k8s|swarm (默认: compose)
#   -f, --file <file>        docker-compose 文件路径
#   -d, --dry-run            仅预览，不实际执行
#   -h, --help               显示帮助
#
# 示例:
#   ./scripts/deploy.sh -e dev -t develop
#   ./scripts/deploy.sh -e prod -t v1.0.0 -o local
#   ./scripts/deploy.sh -e prod -t v1.0.0 -m k8s
# =============================================================================

set -e

# 默认配置
ENVIRONMENT="dev"
TAG="latest"
OCR_BACKEND="none"
DEPLOY_METHOD="compose"
COMPOSE_FILE=""
DRY_RUN=false

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

log_debug() {
  echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 显示帮助
show_help() {
  echo "用法: $0 [options]"
  echo ""
  echo "选项:"
  echo "  -e, --env <environment>  部署环境: dev|staging|prod (默认: dev)"
  echo "  -t, --tag <tag>          镜像标签 (默认: latest)"
  echo "  -o, --ocr <backend>      OCR后端: none|local|cloud (默认: none)"
  echo "  -m, --method <method>    部署方式: compose|k8s|swarm (默认: compose)"
  echo "  -f, --file <file>        docker-compose 文件路径"
  echo "  -d, --dry-run            仅预览，不实际执行"
  echo "  -h, --help               显示帮助"
  echo ""
  echo "示例:"
  echo "  $0 -e dev -t develop"
  echo "  $0 -e prod -t v1.0.0 -o local"
  echo "  $0 -e prod -t v1.0.0 -m k8s"
}

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    -e|--env)
      ENVIRONMENT="$2"
      shift 2
      ;;
    -t|--tag)
      TAG="$2"
      shift 2
      ;;
    -o|--ocr)
      OCR_BACKEND="$2"
      shift 2
      ;;
    -m|--method)
      DEPLOY_METHOD="$2"
      shift 2
      ;;
    -f|--file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    -d|--dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      log_error "未知选项: $1"
      show_help
      exit 1
      ;;
  esac
done

# 验证环境
validate_environment() {
  case $ENVIRONMENT in
    dev|development)
      ENVIRONMENT="dev"
      ;;
    staging|test)
      ENVIRONMENT="staging"
      ;;
    prod|production)
      ENVIRONMENT="prod"
      ;;
    *)
      log_error "未知的环境: $ENVIRONMENT"
      exit 1
      ;;
  esac
}

# 验证 OCR 后端
validate_ocr() {
  case $OCR_BACKEND in
    none|local|cloud)
      ;;
    *)
      log_error "未知的 OCR 后端: $OCR_BACKEND"
      exit 1
      ;;
  esac
}

# 加载环境变量
load_env() {
  local env_file=".env.${ENVIRONMENT}"
  
  if [ -f "$env_file" ]; then
    log_info "加载环境配置: $env_file"
    export $(grep -v '^#' "$env_file" | xargs)
  elif [ -f ".env" ]; then
    log_info "加载环境配置: .env"
    export $(grep -v '^#' ".env" | xargs)
  else
    log_warn "未找到环境配置文件"
  fi
}

# Docker Compose 部署
deploy_compose() {
  log_info "使用 Docker Compose 部署到 $ENVIRONMENT 环境"
  
  local compose_file="${COMPOSE_FILE:-docker-compose.yml}"
  local project_name="compliance-checker-${ENVIRONMENT}"
  
  # 设置环境变量
  export IMAGE_TAG="$TAG"
  export OCR_BACKEND="$OCR_BACKEND"
  export COMPOSE_PROJECT_NAME="$project_name"
  
  log_debug "Compose 文件: $compose_file"
  log_debug "项目名称: $project_name"
  log_debug "镜像标签: $TAG"
  log_debug "OCR 后端: $OCR_BACKEND"
  
  if [ "$DRY_RUN" = true ]; then
    log_info "【预览模式】将要执行的命令:"
    echo "  docker-compose -f $compose_file -p $project_name up -d"
    return
  fi
  
  # 拉取最新镜像
  log_info "拉取镜像..."
  docker-compose -f "$compose_file" pull
  
  # 启动服务
  log_info "启动服务..."
  docker-compose -f "$compose_file" up -d
  
  # 等待服务就绪
  log_info "等待服务就绪..."
  sleep 10
  
  # 健康检查
  log_info "执行健康检查..."
  if docker-compose -f "$compose_file" ps | grep -q "Up"; then
    log_info "服务部署成功!"
    docker-compose -f "$compose_file" ps
  else
    log_error "服务启动失败"
    docker-compose -f "$compose_file" logs --tail=50
    exit 1
  fi
}

# Kubernetes 部署
deploy_k8s() {
  log_info "使用 Kubernetes 部署到 $ENVIRONMENT 环境"
  
  local namespace="compliance-checker-${ENVIRONMENT}"
  local deployment_file="k8s/${ENVIRONMENT}/deployment.yaml"
  
  if [ ! -f "$deployment_file" ]; then
    log_error "未找到 K8s 部署文件: $deployment_file"
    exit 1
  fi
  
  log_debug "Namespace: $namespace"
  log_debug "部署文件: $deployment_file"
  
  if [ "$DRY_RUN" = true ]; then
    log_info "【预览模式】将要执行的命令:"
    echo "  kubectl apply -f $deployment_file -n $namespace"
    return
  fi
  
  # 确保 namespace 存在
  kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
  
  # 更新镜像标签
  sed -i "s|image:.*compliance-checker:.*|image: ghcr.io/evob-z/compliance_checker_light:${TAG}|" "$deployment_file"
  
  # 应用配置
  kubectl apply -f "$deployment_file" -n "$namespace"
  
  # 等待部署完成
  kubectl rollout status deployment/compliance-checker -n "$namespace" --timeout=300s
  
  log_info "K8s 部署完成!"
}

# Docker Swarm 部署
deploy_swarm() {
  log_info "使用 Docker Swarm 部署到 $ENVIRONMENT 环境"
  
  local stack_name="compliance-checker-${ENVIRONMENT}"
  local compose_file="${COMPOSE_FILE:-docker-compose.yml}"
  
  export IMAGE_TAG="$TAG"
  export OCR_BACKEND="$OCR_BACKEND"
  
  if [ "$DRY_RUN" = true ]; then
    log_info "【预览模式】将要执行的命令:"
    echo "  docker stack deploy -c $compose_file $stack_name"
    return
  fi
  
  # 部署 stack
  docker stack deploy -c "$compose_file" "$stack_name"
  
  # 等待服务就绪
  sleep 10
  
  # 检查服务状态
  docker stack ps "$stack_name"
  
  log_info "Swarm 部署完成!"
}

# 主函数
main() {
  log_info "开始部署 Compliance Checker"
  log_info "环境: $ENVIRONMENT"
  log_info "标签: $TAG"
  log_info "OCR: $OCR_BACKEND"
  log_info "方法: $DEPLOY_METHOD"
  
  if [ "$DRY_RUN" = true ]; then
    log_warn "【预览模式】不会实际执行部署"
  fi
  
  echo ""
  
  # 验证
  validate_environment
  validate_ocr
  
  # 加载环境变量
  load_env
  
  # 执行部署
  case $DEPLOY_METHOD in
    compose|docker-compose)
      deploy_compose
      ;;
    k8s|kubernetes)
      deploy_k8s
      ;;
    swarm)
      deploy_swarm
      ;;
    *)
      log_error "未知的部署方法: $DEPLOY_METHOD"
      exit 1
      ;;
  esac
  
  echo ""
  log_info "部署流程完成!"
}

main "$@"
