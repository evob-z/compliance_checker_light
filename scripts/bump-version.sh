#!/bin/bash
# =============================================================================
# Compliance Checker 版本发布脚本
# =============================================================================
# 用法:
#   ./scripts/bump-version.sh <version_type>
#
# 参数:
#   version_type: major|minor|patch 或具体的版本号 (如: v1.2.3)
#
# 功能:
#   - 自动更新版本号 (pyproject.toml)
#   - 生成 CHANGELOG
#   - 创建 git tag
#   - 推送代码和标签
#
# 示例:
#   ./scripts/bump-version.sh patch    # 1.0.0 -> 1.0.1
#   ./scripts/bump-version.sh minor    # 1.0.0 -> 1.1.0
#   ./scripts/bump-version.sh major    # 1.0.0 -> 2.0.0
#   ./scripts/bump-version.sh v1.2.3   # 指定版本号
# =============================================================================

set -e

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

# 获取当前版本
get_current_version() {
  grep -E '^version\s*=' pyproject.toml | head -1 | sed 's/.*=\s*"\(.*\)".*/\1/'
}

# 计算新版本
calculate_new_version() {
  local current=$1
  local type=$2
  
  # 移除 v 前缀
  current=${current#v}
  
  IFS='.' read -r major minor patch <<< "$current"
  
  case $type in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch)
      patch=$((patch + 1))
      ;;
    *)
      log_error "未知的版本类型: $type"
      exit 1
      ;;
  esac
  
  echo "v${major}.${minor}.${patch}"
}

# 更新 pyproject.toml 版本
update_version() {
  local new_version=$1
  
  # 移除 v 前缀用于 pyproject.toml
  local version_no_prefix=${new_version#v}
  
  log_info "更新 pyproject.toml 版本为: $version_no_prefix"
  
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s/^version = \".*\"/version = \"$version_no_prefix\"/" pyproject.toml
  else
    # Linux
    sed -i "s/^version = \".*\"/version = \"$version_no_prefix\"/" pyproject.toml
  fi
}

# 生成 CHANGELOG
generate_changelog() {
  local new_version=$1
  
  log_info "生成 CHANGELOG..."
  
  # 获取上一个 tag
  local last_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
  
  if [ -z "$last_tag" ]; then
    log_warn "没有找到上一个 tag，将生成完整的 CHANGELOG"
    local commit_range="HEAD"
  else
    local commit_range="${last_tag}..HEAD"
  fi
  
  # 生成临时 CHANGELOG
  local temp_changelog=$(mktemp)
  
  {
    echo "## [$new_version] - $(date +%Y-%m-%d)"
    echo ""
    
    # Features
    local features=$(git log "$commit_range" --pretty=format:"- %s" --grep="^feat" 2>/dev/null || true)
    if [ -n "$features" ]; then
      echo "### Features"
      echo "$features"
      echo ""
    fi
    
    # Bug Fixes
    local fixes=$(git log "$commit_range" --pretty=format:"- %s" --grep="^fix" 2>/dev/null || true)
    if [ -n "$fixes" ]; then
      echo "### Bug Fixes"
      echo "$fixes"
      echo ""
    fi
    
    # Documentation
    local docs=$(git log "$commit_range" --pretty=format:"- %s" --grep="^docs" 2>/dev/null || true)
    if [ -n "$docs" ]; then
      echo "### Documentation"
      echo "$docs"
      echo ""
    fi
    
    # Other
    local others=$(git log "$commit_range" --pretty=format:"- %s" --grep="^chore\|^refactor\|^style\|^test" 2>/dev/null || true)
    if [ -n "$others" ]; then
      echo "### Other Changes"
      echo "$others"
      echo ""
    fi
  } > "$temp_changelog"
  
  # 如果 CHANGELOG.md 存在，在开头插入新内容
  if [ -f CHANGELOG.md ]; then
    local old_changelog=$(mktemp)
    tail -n +2 CHANGELOG.md > "$old_changelog"  # 移除旧的标题
    
    {
      echo "# Changelog"
      echo ""
      cat "$temp_changelog"
      cat "$old_changelog"
    } > CHANGELOG.md
    
    rm "$old_changelog"
  else
    {
      echo "# Changelog"
      echo ""
      cat "$temp_changelog"
    } > CHANGELOG.md
  fi
  
  rm "$temp_changelog"
  
  log_info "CHANGELOG 已更新"
}

# 主函数
main() {
  if [ $# -eq 0 ]; then
    log_error "请指定版本类型 (major|minor|patch) 或具体版本号"
    echo "用法: $0 <major|minor|patch|v1.2.3>"
    exit 1
  fi
  
  local version_input=$1
  
  # 获取脚本所在目录
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
  
  cd "$PROJECT_ROOT"
  
  # 检查是否在 git 仓库中
  if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "当前目录不是 git 仓库"
    exit 1
  fi
  
  # 检查工作区是否干净
  if ! git diff-index --quiet HEAD --; then
    log_error "工作区有未提交的更改，请先提交或暂存"
    exit 1
  fi
  
  # 计算新版本
  local current_version=$(get_current_version)
  log_info "当前版本: $current_version"
  
  local new_version
  if [[ $version_input =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    new_version=$version_input
  elif [[ $version_input =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    new_version="v$version_input"
  else
    new_version=$(calculate_new_version "$current_version" "$version_input")
  fi
  
  log_info "新版本: $new_version"
  
  # 确认
  read -p "确认发布 $new_version? (y/N): " confirm
  if [[ ! $confirm =~ ^[Yy]$ ]]; then
    log_info "已取消"
    exit 0
  fi
  
  # 更新版本
  update_version "$new_version"
  
  # 生成 CHANGELOG
  generate_changelog "$new_version"
  
  # 提交更改
  log_info "提交版本更新..."
  git add pyproject.toml CHANGELOG.md
  git commit -m "chore(release): bump version to $new_version"
  
  # 创建 tag
  log_info "创建 tag: $new_version"
  git tag -a "$new_version" -m "Release $new_version"
  
  # 推送
  log_info "推送代码和标签..."
  git push origin HEAD
  git push origin "$new_version"
  
  echo ""
  log_info "版本 $new_version 发布成功!"
  log_info "GitHub Actions 将自动构建和发布"
}

main "$@"
