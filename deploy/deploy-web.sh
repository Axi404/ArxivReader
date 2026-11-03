#!/usr/bin/env bash
# 发布网页：在本机构建 web/、跑检查和测试，再用 rsync 传到服务器上 nginx 的目录。服务器上不需要 Node。
# 用法：deploy/deploy-web.sh [ssh 主机，默认 vultr]
# 后端（/api）另外发：ssh vultr 'cd /opt/arxiv-reader && git pull --ff-only && systemctl restart arxiv-web'
set -euo pipefail

HOST="${1:-vultr}"
DEST=/var/www/paper.axi404.top

cd "$(dirname "$0")/../web"
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
pnpm exec playwright test

# 先传完所有文件再一起换上（--delay-updates），旧文件最后删
rsync -rtz --delete-after --delay-updates --chmod=D755,F644 dist/ "$HOST:$DEST/"
echo "已发布到 $HOST:$DEST"
