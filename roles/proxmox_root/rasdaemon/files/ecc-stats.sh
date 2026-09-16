#!/bin/bash
# Sums rasdaemon ECC error counts and pushes them to the Homepage API as JSON.

set -e

REMOTE_HOST="${1:-192.168.178.5}"
REMOTE_PATH="${2:-/opt/stacks/homepage/api/ecc.json}"
SSH_KEY="/root/.ssh/id_rsa"

output=$(ras-mc-ctl --error-count 2>/dev/null || echo "")

total_ce=0
total_ue=0

while IFS=$'\t' read -r label ce ue; do
    [[ "$label" == "Label" ]] && continue
    [[ -z "$label" ]] && continue
    
    total_ce=$((total_ce + ce))
    total_ue=$((total_ue + ue))
done <<< "$output"

timestamp=$(date -Iseconds)

json=$(cat <<EOF
{
  "ce": ${total_ce},
  "ue": ${total_ue},
  "timestamp": "${timestamp}"
}
EOF
)

echo "$json" | ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes "root@${REMOTE_HOST}" "cat > ${REMOTE_PATH}"

# Also output locally for debugging
echo "$json"
