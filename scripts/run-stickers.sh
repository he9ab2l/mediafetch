#!/data/data/com.termux/files/usr/bin/bash
# 抓一批帖子的表情（帖子 + 回复 + 作者/评论者主页），只留 gif。
# 用法：./scripts/run-stickers.sh OUTDIR URL [URL...]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="$1"; shift
exec python3 -u -m mediafetch archive "$@" --archive "$OUT" \
     --scene full --only sticker --reply-pages 10
