#!/bin/sh
# This board's firmware spontaneously clears the root port's LTR-enable bit; the
# NIC then floods it with URs until re-set, killing C-states. Re-assert in ~1s.
set -u
while true; do
  journalctl -kf -o cat -n 0 2>/dev/null | \
    grep -q -m1 -E "Unsupported Request|Header Log Overflow|AER: .*error message received"
  NIC=$(lspci -Dn 2>/dev/null | awk '/10ec:8127/{print $1; exit}')
  if [ -n "$NIC" ]; then
    PORT=$(basename "$(dirname "$(readlink -f "/sys/bus/pci/devices/$NIC")")")
    setpci -s "$PORT" CAP_EXP+0x28.w=0400:0400 2>/dev/null
    logger -t aer-ltr-heal "AER seen - re-asserted LTR enable on $PORT"
  fi
  sleep 3
done
