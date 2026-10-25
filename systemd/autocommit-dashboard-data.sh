#!/usr/bin/env bash
# Auto-commit the exported dashboard data (dashboard/data/*.json) to origin/main.
#
# Triggered by (a) meridian-dashboard-publish.service on success (OnSuccess=) and (b) a
# 20-minute timer, so exports made while offline get committed once the network is back.
#
# Safety design:
#   * Works in its OWN git worktree (~/.local/share/meridian-autocommit/worktree), reset to
#     origin/main on every run. It never touches your working copy, your current branch, your
#     staged files or your other uncommitted changes.
#   * Only dashboard/data/*.json is ever copied in, so nothing else can be committed.
#   * Skips while the publish job is running (files may be half-written), when origin is not
#     reachable (offline), and when nothing differs from origin/main.
#   * Never force-pushes. On a rejected push it re-syncs once and retries; otherwise it exits
#     non-zero and the timer simply tries again later.
#
# Every commit to main also triggers the Render and Vercel deploys. See docs/SETUP.md.
set -Eeuo pipefail

REPO=/home/chirag/Desktop/Meridian
WT="$HOME/.local/share/meridian-autocommit/worktree"
MSG_PREFIX="Update exported dashboard data (auto-commit)"

exec 9>/tmp/meridian-autocommit.lock
if ! flock -n 9; then echo "another auto-commit run is in progress; exiting"; exit 0; fi

cd "$REPO"

if systemctl --user is-active --quiet meridian-dashboard-publish.service; then
  echo "publish job is running; will retry on the next trigger"; exit 0
fi

compgen -G "dashboard/data/*.json" > /dev/null || { echo "no dashboard/data/*.json present; nothing to do"; exit 0; }

# Files written in the last few seconds may still be in flight: give them a moment.
newest=$(find dashboard/data -maxdepth 1 -name '*.json' -printf '%T@\n' | sort -n | tail -1)
if (( $(date +%s) - ${newest%.*} < 15 )); then sleep 20; fi

# Internet / remote reachability check (also confirms credentials work for reads).
if ! timeout 20 git ls-remote --exit-code -q origin HEAD > /dev/null 2>&1; then
  echo "origin not reachable (offline?); will retry on the next trigger"; exit 0
fi

sync_worktree() {
  git fetch -q origin main
  if [ ! -d "$WT/.git" ] && [ ! -f "$WT/.git" ]; then
    mkdir -p "$(dirname "$WT")"
    git worktree prune
    git worktree add -q --detach "$WT" origin/main
  fi
  git -C "$WT" checkout -q --detach origin/main
  git -C "$WT" reset -q --hard origin/main
  git -C "$WT" clean -fdq
  mkdir -p "$WT/dashboard/data"
  cp -f "$REPO"/dashboard/data/*.json "$WT/dashboard/data/"
}

commit_and_push() {
  if git -C "$WT" diff --quiet -- dashboard/data && [ -z "$(git -C "$WT" ls-files --others --exclude-standard dashboard/data)" ]; then
    echo "dashboard data already matches origin/main; nothing to commit"; return 2
  fi
  exported=$(python3 -c "import json,sys;print(json.load(open('$WT/dashboard/data/metadata.json'))['exported_at'])" 2>/dev/null || echo unknown)
  git -C "$WT" add -- dashboard/data
  git -C "$WT" commit -q -m "$MSG_PREFIX" -m "Export time: $exported"
  git -C "$WT" push -q origin HEAD:main
}

# Keep your working copy pull-able. After a bot commit your working files hold the same data as
# uncommitted modifications, which makes a plain `git pull` abort. When (and only when) you are on
# main, behind origin/main by fast-forward only, and the ONLY uncommitted tracked changes are
# dashboard/data files, adopt origin/main's copies of them and fast-forward. Anything else
# (another branch, other edits in progress, diverged history) is left completely alone.
fast_forward_main() {
  [ "$(git -C "$REPO" branch --show-current)" = main ] || return 0
  git -C "$REPO" merge-base --is-ancestor HEAD origin/main || return 0
  [ "$(git -C "$REPO" rev-parse HEAD)" != "$(git -C "$REPO" rev-parse origin/main)" ] || return 0
  if [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no | grep -v ' dashboard/data/' || true)" ]; then
    return 0
  fi
  git -C "$REPO" checkout -q origin/main -- dashboard/data && git -C "$REPO" merge -q --ff-only origin/main \
    && echo "fast-forwarded local main to origin/main" || true
}

sync_worktree
rc=0; commit_and_push || rc=$?
if [ "$rc" = 2 ]; then fast_forward_main; exit 0; fi
if [ "$rc" != 0 ]; then
  echo "push failed (main moved?); re-syncing once and retrying"
  sync_worktree
  commit_and_push || { echo "retry failed; will try again on the next trigger"; exit 1; }
fi
echo "committed and pushed dashboard data to origin/main"
fast_forward_main
