#!/bin/bash
# UPS Statistics Script
# Reads NUT (upsc) data and outputs JSON for the Homepage dashboard

set -e

# Configuration
REMOTE_HOST="${1:-192.168.178.15}"
REMOTE_PATH="${2:-/opt/stacks/homepage/api/ups.json}"
UPS_NAME="${3:-eaton}"
SSH_KEY="/root/.ssh/id_rsa"

data=$(upsc "$UPS_NAME" 2>/dev/null || echo "")

get_var() {
    echo "$data" | awk -F': ' -v key="$1" '$1 == key { print $2 }'
}

load=$(get_var ups.load)
charge=$(get_var battery.charge)
runtime=$(get_var battery.runtime)
status=$(get_var ups.status)

# Ensure numeric values (some firmwares report floats) so the JSON stays valid
is_num() { [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; }
is_num "$load" || load=0
is_num "$charge" || charge=0
is_num "$runtime" || runtime=0

# Map NUT status flags (OL/OB/LB...) to a human-readable power source
case "$status" in
    *OB*) power="On Battery" ;;
    *OL*) power="On Wall" ;;
    *) power="${status:-Unavailable}" ;;
esac
if [[ "$status" == *LB* ]]; then
    power="${power} (Low)"
fi

runtime_minutes=$(( ${runtime%%.*} / 60 ))

# Get timestamp
timestamp=$(date -Iseconds)

# Create JSON
json=$(cat <<EOF
{
  "power": "${power}",
  "load": ${load:-0},
  "charge": ${charge:-0},
  "runtime_minutes": ${runtime_minutes},
  "status_raw": "${status}",
  "timestamp": "${timestamp}"
}
EOF
)

# Write to remote host via SSH
echo "$json" | ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes "root@${REMOTE_HOST}" "cat > ${REMOTE_PATH}"

# Also output locally for debugging
echo "$json"
