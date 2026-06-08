#!/bin/sh
set -eu

NIC=0000:01:00.0
ROOTPORT=$(basename "$(dirname "$(readlink -f /sys/bus/pci/devices/$NIC)")")

for DEV in "$ROOTPORT" "$NIC"; do
  OFF=$(lspci -vv -s "$DEV" | sed -n 's/.*\[\([0-9a-fA-F]\+\) v[0-9]\] L1 PM Substates.*/\1/p')
  CTL1=$(printf '0x%x' $((0x$OFF + 8)))

  echo "$DEV L1SS=$OFF L1SubCtl1=$CTL1"

  # L0s off, basic L1 on.
  setpci -s "$DEV" CAP_EXP+10.b=02:03

  # PCI-PM L1.2 off, PCI-PM L1.1 off, ASPM L1.2 on, ASPM L1.1 on.
  setpci -s "$DEV" "$CTL1.L=0000000c:0000000f"
done
