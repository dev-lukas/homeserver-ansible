#!/bin/sh
# Proxmox hookscript: exempt the VM's QEMU process from the OOM killer.
vmid="$1"
phase="$2"
[ "$phase" = "post-start" ] || exit 0
pid=$(cat "/var/run/qemu-server/$vmid.pid" 2>/dev/null) || exit 0
echo -1000 > "/proc/$pid/oom_score_adj" && echo "VM $vmid (pid $pid): oom_score_adj -1000"
exit 0
