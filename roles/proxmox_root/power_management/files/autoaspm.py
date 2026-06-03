#!/usr/bin/env python3

import os
import platform
from pathlib import Path


PCI_DEVICES = Path("/sys/bus/pci/devices")
REALTEK_VENDOR_ID = "0x10ec"
RTL8127_DEVICE_ID = "0x8127"

LINK_SETTINGS = {
    "l0s_aspm": "0",
    "l1_aspm": "1",
    "l1_1_aspm": "1",
    "l1_2_aspm": "1",
    "l1_1_pcipm": "0",
    "l1_2_pcipm": "0",
}


def run_prerequisites():
    if platform.system() != "Linux":
        raise OSError("This script only runs on Linux-based systems")
    if os.geteuid() != 0:
        raise PermissionError("This script needs root privileges to run")
    if not PCI_DEVICES.exists():
        raise FileNotFoundError(f"{PCI_DEVICES} does not exist")


def read_sysfs_value(path):
    try:
        return path.read_text(encoding="utf-8").strip().lower()
    except FileNotFoundError:
        return None


def find_rtl8127_devices():
    devices = []
    for pci_device in PCI_DEVICES.iterdir():
        vendor = read_sysfs_value(pci_device / "vendor")
        device = read_sysfs_value(pci_device / "device")
        if vendor == REALTEK_VENDOR_ID and device == RTL8127_DEVICE_ID:
            devices.append(pci_device)
    return sorted(devices)


def find_upstream_port(pci_device):
    device_path = pci_device.resolve()
    parent = device_path.parent
    if parent.name.startswith("pci"):
        return None
    upstream_port = PCI_DEVICES / parent.name
    return upstream_port if upstream_port.exists() else None


def write_link_setting(pci_device, setting, value):
    setting_path = pci_device / "link" / setting
    if not setting_path.exists():
        print(f"{pci_device.name}: {setting} unavailable")
        return

    current_value = setting_path.read_text(encoding="utf-8").strip()
    if current_value == value:
        print(f"{pci_device.name}: {setting} already {value}")
        return

    setting_path.write_text(value, encoding="utf-8")
    print(f"{pci_device.name}: set {setting}={value}")


def configure_nic_link(nic_device):
    devices = [nic_device]
    upstream_port = find_upstream_port(nic_device)
    if upstream_port:
        devices.insert(0, upstream_port)
    else:
        print(f"{nic_device.name}: upstream PCIe port not found")

    for pci_device in devices:
        for setting, value in LINK_SETTINGS.items():
            write_link_setting(pci_device, setting, value)


def main():
    run_prerequisites()
    rtl8127_devices = find_rtl8127_devices()
    if not rtl8127_devices:
        print("No Realtek RTL8127 NIC found")
        return

    for nic_device in rtl8127_devices:
        configure_nic_link(nic_device)


if __name__ == "__main__":
    main()
