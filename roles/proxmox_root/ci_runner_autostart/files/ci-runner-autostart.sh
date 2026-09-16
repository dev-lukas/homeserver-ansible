#!/usr/bin/env bash
# Powers the CI runner VM on when GitHub has queued jobs and off after
# IDLE_MINUTES idle. Config comes from /etc/ci-runner-autostart.env.
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
    # -L: a renamed repo answers 301, and without it we silently see zero runs.
    cnt=$(curl -fsSL \
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
    # Initialise on first sight so a manually started VM survives the next tick.
    [ -f "$STATE_FILE" ] || echo "$now" > "$STATE_FILE"
    last=$(cat "$STATE_FILE" 2>/dev/null || echo "$now")
    idle_min=$(( (now - last) / 60 ))
    if [ "$idle_min" -ge "$IDLE_MINUTES" ]; then
      log "idle ${idle_min}m >= ${IDLE_MINUTES}m -> shutting down VM $VMID"
      qm shutdown "$VMID" --timeout 120 || true
    fi
  fi
fi
