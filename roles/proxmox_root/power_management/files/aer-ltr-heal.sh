#!/bin/sh
# AER instant-heal: re-assert the uplink root port's LTR-enable within ~1s
# of the first AER kernel message, capping LTR-UR storms at sub-second
# instead of the */5 cron's up-to-5-minute window.
#
# Background: this board's firmware spontaneously clears the root port's
# DevCtl2 LTR-enable bit (writer unknown, SMM suspected; clears cluster in
# the minutes after boot but can strike any time). An LTR-emitting NIC then
# floods the port with Unsupported-Request errors until the bit is re-set:
# the link survives under r8169, but C-states die, the journal fills, and
# the RTL8127 stops emitting LTR until healed. Sub-second healing keeps all
# of that invisible. The grep -m1 pattern exits on first match (SIGPIPE
# terminates the follower), we heal, pause briefly, and re-attach with no
# backlog (-n 0) so a running storm triggers one heal per pass, not one
# per logged line.
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
