#!/usr/bin/env bash
# 便捷脚本：把项目内置的便携 Node 22 加入 PATH（系统 Node < 20.9 时使用）
# 用法：source scripts/use-node.sh
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$REPO_ROOT/.tools/node:$PATH"
echo "node $(node --version) @ $REPO_ROOT/.tools/node"
