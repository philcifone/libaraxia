#!/usr/bin/env bash
# Pull-based deploy for Libaraxia, run on prod by libaraxia-deploy.timer.
#
# Every run: fetch main; if there's a new commit AND its CI run ("test") on
# GitHub passed, fast-forward to it, install requirements if they changed,
# apply migrations (manage.py backs the DB up first), restart gunicorn and
# check it answers. If any step fails, the code goes back to the previous
# commit and that commit is remembered so it isn't retried every 5 minutes.
#
# Nothing here needs secrets: the repo is public, so the GitHub API call is
# unauthenticated (60 requests/hour; this makes at most 12).
#
# Safe to update itself: git replaces this file with a new inode, and the
# running bash keeps reading the old one.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/phil/library-catalog}"
VENV="${VENV:-$APP_DIR/venv}"
SERVICE="${SERVICE:-library-catalog.service}"
REPO="${REPO:-philcifone/libaraxia}"
BRANCH="${BRANCH:-main}"
CHECK_NAME="${CHECK_NAME:-test}"                       # job name in basic-tests.yml
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/auth/login}"
FAILED_FILE="$APP_DIR/.deploy-failed"                  # git-ignored

log() { echo "deploy: $*"; }                           # stdout goes to the journal

cd "$APP_DIR"

git fetch --quiet origin "$BRANCH"
current=$(git rev-parse HEAD)
target=$(git rev-parse "origin/$BRANCH")
[ "$current" = "$target" ] && exit 0

if [ -f "$FAILED_FILE" ] && [ "$(cat "$FAILED_FILE")" = "$target" ]; then
    exit 0   # already failed once; wait for a new commit
fi

# Never deploy over local edits or a diverged history: fix those by hand.
if ! git diff --quiet HEAD; then
    log "local changes in $APP_DIR, not deploying"; exit 1
fi
if ! git merge-base --is-ancestor "$current" "$target"; then
    log "origin/$BRANCH is not a fast-forward of HEAD, not deploying"; exit 1
fi

# CI must have passed for exactly this commit.
conclusion=$(curl -fsS -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/commits/$target/check-runs?check_name=$CHECK_NAME" |
    "$VENV/bin/python" -c 'import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
print(runs[0]["conclusion"] or "pending" if runs else "none")')
case "$conclusion" in
    success) ;;
    pending|none) exit 0 ;;                            # CI still running or not started
    *) log "CI for ${target:0:7} is '$conclusion', not deploying"; exit 0 ;;
esac

changed=$(git diff --name-only "$current" "$target")
needs_pip() { grep -qx 'requirements.txt' <<<"$changed"; }

healthy() {
    for _ in $(seq 1 15); do
        curl -fsS -o /dev/null "$HEALTH_URL" && return 0
        sleep 2
    done
    return 1
}

log "deploying ${current:0:7} -> ${target:0:7}"
git merge --ff-only --quiet "$target"

if { ! needs_pip || "$VENV/bin/pip" install --quiet -r requirements.txt; } &&
   "$VENV/bin/python" manage.py migrate -y &&
   sudo -n systemctl restart "$SERVICE" &&
   healthy; then
    rm -f "$FAILED_FILE"
    log "deployed ${target:0:7}"
    exit 0
fi

# Something failed: put the old code back. Migrations run in transactions,
# so a failed one changed nothing; one that applied stays (they're additive,
# and manage.py left a backup next to the DB).
log "deploy of ${target:0:7} FAILED, rolling back to ${current:0:7}"
echo "$target" > "$FAILED_FILE"
git reset --hard --quiet "$current"
if needs_pip; then "$VENV/bin/pip" install --quiet -r requirements.txt || true; fi
sudo -n systemctl restart "$SERVICE" || true
healthy && log "rolled back, ${current:0:7} is serving" || log "rollback restart is ALSO unhealthy, check $SERVICE"
exit 1
