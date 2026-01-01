#!/bin/bash
# ECC Memory Error Statistics Script
# Reads rasdaemon error counts and outputs JSON

set -e

# Configuration
REMOTE_HOST="${1:-192.168.178.5}"
REMOTE_PATH="${2:-/opt/stacks/homepage/api/ecc.json}"
SSH_KEY="/root/.ssh/id_rsa"

# Get error counts from ras-mc-ctl
output=$(ras-mc-ctl --error-count 2>/dev/null || echo "")

# Initialize counters
total_ce=0
total_ue=0

# Parse the output (skip header line)
while IFS=$'\t' read -r label ce ue; do
    # Skip header and empty lines
    [[ "$label" == "Label" ]] && continue
    [[ -z "$label" ]] && continue
    
    # Sum up the counts
    total_ce=$((total_ce + ce))
    total_ue=$((total_ue + ue))
done <<< "$output"

# Get timestamp
timestamp=$(date -Iseconds)

# Create JSON
json=$(cat <<EOF
{
  "ce": ${total_ce},
  "ue": ${total_ue},
  "timestamp": "${timestamp}"
}
EOF
)

# Write to remote host via SCP
echo "$json" | ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes "root@${REMOTE_HOST}" "cat > ${REMOTE_PATH}"

# Also output locally for debugging
echo "$json"
