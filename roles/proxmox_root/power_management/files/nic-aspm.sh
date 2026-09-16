#!/bin/sh
# Kernel-native ASPM/PM policy for the RTL8127 uplink NIC.
#
# PREREQUISITE (BIOS): hidden Setup option "Native ASPM" = Enabled
# (Setup varstore EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9, offset 0x51 = 0x01;
# written via efivarfs 2026-08-14; byte-exact NVRAM backups on the host in
# /root/efivar-backups-20260813/ and off-host in the operator's projects
# folder). With OS-controlled ASPM the kernel sets root-port LTR natively at
# enumeration, exposes writable /sys/.../link/ ASPM knobs, and r8169 probes
# with aspm_manageable=1, so it configures the chip-side CLKREQ/LTR/L1.2
# machinery in-tree. This script replaced the old setpci-based autoaspm.py
# (see git history): hand-forged register writes are unnecessary and would
# fight the kernel under this regime.
#
# If the sysfs writes fail, the BIOS owns ASPM again (Setup option
# reverted?) - fail loudly so cron/ansible output shows it.
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

# Belt-and-suspenders: root-port LTR enable, masked and idempotent. The
# kernel already sets this natively at boot; re-asserting guards against the
# board's (historic, now likely moot) spontaneous clears without fighting
# the kernel - it writes the same value the kernel wants.
PORT=$(basename "$(dirname "$(readlink -f "/sys/bus/pci/devices/$NIC")")")
setpci -s "$PORT" CAP_EXP+0x28.w=0400:0400

# Knobs only exist when both link ends support the capability (e.g. some
# PCH root ports lack L1 substates / ClockPM) - enable what is available.
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
    # rev 08 (SFP+ ATF) and unknown revisions: plain L1 only - FINAL.
    # 2026-08-14: L1.1 exit is broken at the hardware level of this
    # card/board pairing (hard link death with fully configured chip,
    # kernel-managed links, no storm). Never enable l1_1/l1_2 here.
    # clkpm uses the same CLKREQ wake path - presumed fatal, keep off.
    enable_knob l1_aspm
    ;;
esac
