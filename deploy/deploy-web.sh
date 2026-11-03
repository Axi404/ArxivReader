#!/usr/bin/env bash
# 发布网页：把已提交的 web/ 导出到临时目录，在那里装依赖、检查、测试、构建，再 rsync 到服务器上 nginx 的目录。
# 只发已提交的内容：没提交的改动、被 .gitignore 挡掉的文件都不会混进去，缺了文件这里就会构建失败。服务器上不需要 Node。
# 用法：deploy/deploy-web.sh [ssh 主机，默认 vultr]
# 后端（/api）另外发：ssh vultr 'cd /opt/arxiv-reader && git pull --ff-only && systemctl restart arxiv-web'
set -euo pipefail

HOST="${1:-vultr}"
DEST=/var/www/paper.axi404.top
REPO="$(cd "$(dirname "$0")/.." && pwd)"
REV="$(git -C "$REPO" rev-parse --short HEAD)"

if [ -n "$(git -C "$REPO" status --porcelain -- web)" ]; then
  echo "注意：web/ 里有没提交的改动，这次只发已提交的 $REV" >&2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git -C "$REPO" archive HEAD web | tar -x -C "$WORK"
cd "$WORK/web"
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
# CI=1：不借用已经开着的本地服务器，测的一定是这次构建出来的 dist/
CI=1 pnpm exec playwright test --reporter=list

# 先传完所有文件再一起换上（--delay-updates），旧文件最后删。
# 权限写成 u=rwX,go=rX：macOS 自带的 rsync 是 openrsync，不认 GNU 的 D755,F644 写法
rsync -rtz --delete-after --delay-updates --chmod=u=rwX,go=rX dist/ "$HOST:$DEST/"
echo "已发布 $REV 到 $HOST:$DEST"
