#!/usr/bin/env bash
# 作業ツリーに変更があれば自動でコミットする。
# Claude Code の Stop フック（各ターン終了時）から呼ばれる。
set -u

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# 変更が無ければ何もしない
if [ -z "$(git status --porcelain)" ]; then
  exit 0
fi

git add -A >/dev/null 2>&1
count=$(git diff --cached --name-only | wc -l | tr -d ' ')
if [ "$count" = "0" ]; then
  exit 0
fi
files=$(git diff --cached --name-only | head -5 | tr '\n' ' ')
stamp=$(date '+%Y-%m-%d %H:%M')

git commit -q -F - <<EOF
自動コミット: ${stamp}（${count}ファイル）

変更: ${files}

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF

if [ $? -eq 0 ]; then
  hash=$(git rev-parse --short HEAD)
  # 画面に一行だけ知らせる
  printf '{"systemMessage": "自動コミット %s（%sファイル）"}\n' "$hash" "$count"
fi
exit 0
