#!/usr/bin/env bash
# GitHub deletes the registration of a runner offline for ~14 days, and this VM
# is on-demand, so wake it periodically to let the runners check in.
set -euo pipefail

: "${VMID:?}" "${STATE_DIR:?}"

now=$(date +%s)
log() { logger -t ci-runner-keepalive "$*"; }

mkdir -p "$STATE_DIR"
# Reset the shared idle clock; the autostart watchdog handles the shutdown.
echo "$now" > "$STATE_DIR/last_active"

vmstatus=$(qm status "$VMID" 2>/dev/null | awk '{print $2}')

if [ "$vmstatus" != "running" ]; then
  log "keepalive -> starting VM $VMID so runners can refresh their registration"
  qm start "$VMID"
else
  log "keepalive -> VM $VMID already running; refreshed idle clock"
fi
