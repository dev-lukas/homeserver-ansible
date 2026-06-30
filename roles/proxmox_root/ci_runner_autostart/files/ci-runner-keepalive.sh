#!/usr/bin/env bash
#
# CI Runner keepalive.
# Config is sourced from EnvironmentFile (/etc/ci-runner-autostart.env):
#   VMID, STATE_DIR (the autostart watchdog's env file is reused).
#
# GitHub auto-deletes the registration of any self-hosted runner that has not
# connected for ~14 days. The runner VM is on-demand (onboot 0) and may sit
# powered off far longer than that for a quiet repo, so its runner silently
# loses its registration. This timer-driven keepalive powers the VM on well
# inside that window so every runner reconnects and refreshes its "last seen".
#
# Shutdown is left to the autostart watchdog: we stamp the shared idle clock to
# "now" so the VM stays up for IDLE_MINUTES (plenty for the runners to check in)
# and is then powered off again by the watchdog's normal idle path.
set -euo pipefail

: "${VMID:?}" "${STATE_DIR:?}"

now=$(date +%s)
log() { logger -t ci-runner-keepalive "$*"; }

mkdir -p "$STATE_DIR"
# Reset the idle clock so the watchdog does not shut the VM down on its next tick
# before the runners have had a chance to reconnect.
echo "$now" > "$STATE_DIR/last_active"

vmstatus=$(qm status "$VMID" 2>/dev/null | awk '{print $2}')

if [ "$vmstatus" != "running" ]; then
  log "keepalive -> starting VM $VMID so runners can refresh their registration"
  qm start "$VMID"
else
  log "keepalive -> VM $VMID already running; refreshed idle clock"
fi
