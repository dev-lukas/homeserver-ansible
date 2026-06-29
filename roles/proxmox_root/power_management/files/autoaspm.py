#!/bin/sh
set -eu

NIC=0000:01:00.0
ROOTPORT=$(basename "$(dirname "$(readlink -f /sys/bus/pci/devices/$NIC)")")

# Enable LTR on the root port BEFORE turning on ASPM L1.2.
# The RTL8127 NIC has LTR enabled (by firmware/driver), but the mainboard
# leaves its upstream root port's LTR disabled. Per the PCIe spec a device may
# only send LTR messages if every upstream port up to the root has LTR enabled;
# otherwise the root port rejects each LTR message as an Unsupported Request.
# ASPM L1.2 makes the NIC emit LTR, so without this the link floods the root
# port with UR errors -> AER/rasdaemon/journald storm that pins a core and
# kills ALL package C-states. Enabling LTR top-down makes the messages legal.
# (DevCtl2 = CAP_EXP+0x28, bit 10 = LTR Enable.)
setpci -s "$ROOTPORT" CAP_EXP+0x28.w=0400:0400

for DEV in "$ROOTPORT" "$NIC"; do
  OFF=$(lspci -vv -s "$DEV" | sed -n 's/.*\[\([0-9a-fA-F]\+\) v[0-9]\] L1 PM Substates.*/\1/p')
  CTL1=$(printf '0x%x' $((0x$OFF + 8)))

  echo "$DEV L1SS=$OFF L1SubCtl1=$CTL1"

  # L0s off, basic L1 on.
  setpci -s "$DEV" CAP_EXP+10.b=02:03

  # PCI-PM L1.2 off, PCI-PM L1.1 off, ASPM L1.2 on, ASPM L1.1 on.
  setpci -s "$DEV" "$CTL1.L=0000000c:0000000f"
done
