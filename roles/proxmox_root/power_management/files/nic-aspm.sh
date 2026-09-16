#!/bin/sh
# Kernel-native ASPM/PM for the RTL8127 uplink; requires the hidden BIOS "Native
# ASPM" = Enabled (Setup EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9 @0x51 = 0x01).
set -eu

NIC=$(lspci -Dn 2>/dev/null | awk '/10ec:8127/{print $1; exit}')
[ -n "$NIC" ] || exit 0
LINK="/sys/bus/pci/devices/$NIC/link"
if [ ! -d "$LINK" ]; then
  echo "nic-aspm: no ASPM sysfs under $NIC - BIOS-owned ASPM? (check Setup@0x51)" >&2
  exit 1
fi

# Keep the sole uplink out of PCI runtime PM (cheap insurance, PBS lesson).
echo on > "/sys/bus/pci/devices/$NIC/power/control"

# Re-assert root-port LTR enable (masked, idempotent); the kernel already sets it.
PORT=$(basename "$(dirname "$(readlink -f "/sys/bus/pci/devices/$NIC")")")
setpci -s "$PORT" CAP_EXP+0x28.w=0400:0400

# Knobs only exist when both link ends support the capability.
enable_knob() {
  if [ -e "$LINK/$1" ]; then
    echo 1 > "$LINK/$1"
  fi
}

REV=$(setpci -s "$NIC" REVISION.b)
case "$REV" in
  05)
    # RJ45 (RTL8127A): proven full depth - ClockPM + L1 + ASPM L1.2 -> C10.
    enable_knob clkpm
    enable_knob l1_aspm
    enable_knob l1_2_aspm
    ;;
  *)
    # rev 08 (SFP+ ATF) and unknown: plain L1 only, FINAL. L1.1 exit is broken in
    # hardware on this card/board pair - never enable l1_1/l1_2/clkpm here.
    enable_knob l1_aspm
    ;;
esac
