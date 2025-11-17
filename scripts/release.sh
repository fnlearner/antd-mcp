#!/usr/bin/env zsh
# Automated release script for antd-mcp-server
# 功能:
# 1. 检查工作区是否干净 (git status)
# 2. 运行测试
# 3. 版本号更新 (pyproject.toml)
# 4. 构建 (python -m build)
# 5. 校验 (twine check)
# 6. 上传到 PyPI (twine upload)
#
# 使用方式:
#   scripts/release.sh 0.1.1            # 正常发布
#   scripts/release.sh 0.1.1 --dry-run   # 不上传, 只构建与检查
#
# 凭证:
#   推荐使用 PyPI token:
#     export TWINE_USERNAME="__token__"
#     export TWINE_PASSWORD="<pypi-token>"
# 或者设置 TWINE_API_TOKEN 并在 ~/.pypirc 中配置.
#
# 依赖: build, twine, jq (可选), git 已初始化.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
PYPROJECT="$ROOT_DIR/pyproject.toml"

if [[ $# -lt 1 ]]; then
  echo "用法: $0 <new-version> [--dry-run]" >&2
  exit 1
fi

NEW_VERSION="$1"
DRY_RUN="false"
if [[ $# -ge 2 && "$2" == "--dry-run" ]]; then
  DRY_RUN="true"
fi

echo "==> Target version: $NEW_VERSION (dry_run=$DRY_RUN)"

echo "==> Checking git status"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "工作区存在未提交更改, 请先提交或暂存." >&2
  exit 1
fi

echo "==> Running tests"
pytest -q || { echo "测试失败" >&2; exit 1; }

echo "==> Bumping version in pyproject.toml"
# 简单替换 version 行, 假设格式保持
sed -i '' "s/^version = \"[0-9A-Za-z\.-]\+\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"

echo "==> Committing version bump"
git add "$PYPROJECT"
git commit -m "chore: release $NEW_VERSION"
git tag "v$NEW_VERSION"

echo "==> Cleaning dist/"
rm -rf "$ROOT_DIR/dist" "$ROOT_DIR/build"

echo "==> Building package"
python -m build

echo "==> Checking artifacts"
python -m twine check dist/*

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run 完成: 不上传、不推送 tag。"
  exit 0
fi

if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
  echo "未检测到 TWINE_USERNAME/TWINE_PASSWORD 环境变量, 请设置后重试." >&2
  exit 1
fi

echo "==> Uploading to PyPI"
python -m twine upload dist/*

echo "==> Pushing commits and tags"
git push origin HEAD
git push origin "v$NEW_VERSION"

echo "发布完成: $NEW_VERSION"
