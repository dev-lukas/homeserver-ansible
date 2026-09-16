#!/bin/bash
# Reads NUT (upsc) data and pushes it to the Homepage API as JSON.

set -e

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

# Keep these short: the Homepage widget puts four values in one column, so past
# ~8 characters they wrap. LB outranks OL/OB because it matters most.
case "$status" in
    *LB*) power="Batt Low" ;;
    *OB*) power="Battery" ;;
    *OL*) power="Wall" ;;
    *) power="${status:-N/A}" ;;
esac

runtime_minutes=$(( ${runtime%%.*} / 60 ))

timestamp=$(date -Iseconds)

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

echo "$json" | ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes "root@${REMOTE_HOST}" "cat > ${REMOTE_PATH}"

# Also output locally for debugging
echo "$json"
