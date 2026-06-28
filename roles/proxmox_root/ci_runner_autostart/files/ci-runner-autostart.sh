#!/usr/bin/env bash
#
# CI Runner autostart watchdog.
# Config is sourced from EnvironmentFile (/etc/ci-runner-autostart.env):
#   GH_PAT, GH_USER, REPOS (space-separated), VMID, IDLE_MINUTES, STATE_DIR
#
# Powers the CI runner VM on when GitHub has queued/in-progress jobs and shuts it
# down after it has been idle for IDLE_MINUTES. Logs to the journal via logger.
set -euo pipefail

: "${GH_PAT:?}" "${GH_USER:?}" "${REPOS:?}" "${VMID:?}" "${IDLE_MINUTES:?}" "${STATE_DIR:?}"

mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/last_active"
now=$(date +%s)

log() { logger -t ci-runner-autostart "$*"; }

# Count queued + in-progress workflow runs across all watched repos.
active=0
for repo in $REPOS; do
  for st in queued in_progress; do
    cnt=$(curl -fsS \
      -H "Authorization: Bearer $GH_PAT" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com/repos/$GH_USER/$repo/actions/runs?status=$st&per_page=1" \
      2>/dev/null | jq -r '.total_count // 0' 2>/dev/null || echo 0)
    active=$((active + cnt))
  done
done

vmstatus=$(qm status "$VMID" 2>/dev/null | awk '{print $2}')

if [ "$active" -gt 0 ]; then
  echo "$now" > "$STATE_FILE"
  if [ "$vmstatus" != "running" ]; then
    log "active runs=$active -> starting VM $VMID"
    qm start "$VMID"
  fi
else
  if [ "$vmstatus" = "running" ]; then
    # Initialise the timer on first sight (e.g. VM started manually) so we never
    # shut a freshly-started runner down on the very next tick.
    [ -f "$STATE_FILE" ] || echo "$now" > "$STATE_FILE"
    last=$(cat "$STATE_FILE" 2>/dev/null || echo "$now")
    idle_min=$(( (now - last) / 60 ))
    if [ "$idle_min" -ge "$IDLE_MINUTES" ]; then
      log "idle ${idle_min}m >= ${IDLE_MINUTES}m -> shutting down VM $VMID"
      qm shutdown "$VMID" --timeout 120 || true
    fi
  fi
fi
