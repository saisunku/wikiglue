#!/usr/bin/env bash
# Commit the vault to a git history kept outside it (so it isn't synced to Drive),
# if anything changed. Run every 15 minutes by /etc/cron.d/wiki-history.
#
#   examples/history/snapshot.sh <vault> [git-dir]     (default /var/lib/wiki/history.git)
#
# To get a file back:
#   H="git --git-dir=/var/lib/wiki/history.git --work-tree=<vault>"
#   $H log --format='%h %ci' -- wiki/log.md        the versions of a file
#   $H show <hash>:wiki/log.md > /tmp/log.md        one version, to compare or copy back
set -euo pipefail

VAULT="$1"; GIT_DIR="${2:-/var/lib/wiki/history.git}"

if [[ ! -f $GIT_DIR/HEAD ]]; then
  git init -q --bare "$GIT_DIR"
  git --git-dir="$GIT_DIR" config core.bare false
  git --git-dir="$GIT_DIR" config user.name "wiki history"
  git --git-dir="$GIT_DIR" config user.email "wiki-history@localhost"
  # Obsidian's window layout changes all the time and isn't content.
  printf '%s\n' '.obsidian/workspace*.json' '.trash/' > "$GIT_DIR/info/exclude"
fi

export GIT_DIR GIT_WORK_TREE="$VAULT"

git add -A
git diff --cached --quiet || git commit -q -m "snapshot $(date '+%F %T')"
