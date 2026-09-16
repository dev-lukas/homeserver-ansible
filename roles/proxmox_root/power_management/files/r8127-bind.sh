#!/bin/sh
# Enforce per-revision driver policy for the RTL8127 NIC:
#   rev 05 (RJ45) -> r8169        (proven stable with ASPM L1.2 -> C10)
#   rev 08 (ATF)  -> vendor r8127 (only if r8127.ko is installed)
# Live unbind/rebind switch validated 2026-08-12. Degrades gracefully: if
# the target driver is unavailable (e.g. r8127.ko missing after a kernel
# upgrade) the current driver stays bound -> link up, never offline.
# Inert no-op while no vendor module is installed.
set -u
NIC=$(lspci -Dn 2>/dev/null | awk "/10ec:8127/{print \$1; exit}")
[ -n "$NIC" ] || exit 0
REV=$(setpci -s "$NIC" REVISION.b 2>/dev/null)
case "$REV" in
  08) WANT=r8127 ;;
  *)  WANT=r8169 ;;
esac
CUR=$(basename "$(readlink -f "/sys/bus/pci/devices/$NIC/driver" 2>/dev/null)" 2>/dev/null)
[ "$CUR" = "$WANT" ] && exit 0
modprobe "$WANT" 2>/dev/null || exit 0
[ -d "/sys/bus/pci/drivers/$WANT" ] || exit 0
if [ -n "$CUR" ] && [ "$CUR" != "." ]; then
  echo "$NIC" > "/sys/bus/pci/drivers/$CUR/unbind" 2>/dev/null
  sleep 1
fi
echo "$NIC" > "/sys/bus/pci/drivers/$WANT/bind" 2>/dev/null
sleep 3
if [ -z "$(ls "/sys/bus/pci/devices/$NIC/net" 2>/dev/null)" ]; then
  OTHER=r8169; [ "$WANT" = "r8169" ] && OTHER=r8127
  modprobe "$OTHER" 2>/dev/null
  echo "$NIC" > "/sys/bus/pci/drivers/$OTHER/bind" 2>/dev/null
  sleep 3
fi
ifreload -a
