# Dev VM power button (Home Assistant)

The dev VM (VMID 107) runs with `onboot: 0` so the host can reach deep C-states
while nobody is developing. This makes it switchable from the Home Assistant
dashboard instead of requiring an SSH session on the Proxmox host.

## How it works

Home Assistant calls the Proxmox API directly — no polling daemon, no agent on
the host:

```
input_boolean.dev_vm  --(automation)-->  rest_command  --HTTPS-->  Proxmox API
        ^                                                    /vms/107 status/start
        |                                                    /vms/107 status/shutdown
        +---(automation)--- binary_sensor.dev_vm_erreichbar (ping 192.168.178.12)
```

- **`input_boolean.dev_vm`** is the intent (the switch you flip).
- **`binary_sensor.dev_vm_erreichbar`** is the reality (Ping integration).
- Three automations connect them: *Dev-VM einschalten*, *Dev-VM
  herunterfahren*, and *Dev-VM Schalter abgleichen*, which follows the ping
  status when the VM is started or stopped outside Home Assistant (an Ansible
  run, `qm start`, `poweroff` in the guest, a shutdown that timed out).

The two command automations are guarded by the ping sensor, so the sync
automation writing the switch can never bounce back into a power call.

## The token

`roles/proxmox_root/ha_vm_control` creates a Proxmox identity that can do
exactly one thing:

| Object | Value |
|--------|-------|
| Role | `HAVMPower` — `VM.Audit`, `VM.PowerMgmt` |
| User | `hass@pve` (token-only, no password, cannot log into the UI) |
| Token | `hass@pve!dev-vm`, `privsep=1` |
| ACL | `/vms/107` only, for both the user and the token |

Verified against the live API when it was issued:

| Call | Result |
|------|--------|
| `GET  /nodes/pve/qemu/107/status/current` | 200 |
| `POST /nodes/pve/qemu/107/status/start` | 200 |
| `GET  /nodes/pve/qemu/101/status/current` (Home Assistant's own VM) | 403 |
| `GET  /nodes/pve/status` (the host) | 403 |
| `POST /nodes/pve/qemu/107/snapshot` | 403 |

Widening `ha_vm_control_privs` widens all of that — issue a second, separately
scoped token instead.

Proxmox shows a token secret exactly once, at creation. The Ansible task prints
it when it creates one; if it is lost, remove the token and re-run the play:

```bash
pveum user token remove hass@pve dev-vm
ansible-playbook playbooks/proxmox.yml --tags ha_vm_control --ask-vault-pass
```

## Home Assistant configuration

`rest_command` is a YAML-only integration, so this part lives in
`configuration.yaml` (via the Terminal & SSH app or the File editor):

```yaml
rest_command:
  dev_vm_start:
    url: "https://192.168.178.56:8006/api2/json/nodes/pve/qemu/107/status/start"
    method: post
    headers:
      Authorization: !secret pve_dev_vm_token
    # The Proxmox host serves its own self-signed certificate on 8006.
    verify_ssl: false

  dev_vm_shutdown:
    url: "https://192.168.178.56:8006/api2/json/nodes/pve/qemu/107/status/shutdown"
    method: post
    headers:
      Authorization: !secret pve_dev_vm_token
    content_type: "application/x-www-form-urlencoded"
    # forceStop=0: never escalate to a hard stop. An unresponsive guest here
    # means work in flight; the switch flipping back is the better signal.
    payload: "timeout=120&forceStop=0"
    verify_ssl: false
```

and in `secrets.yaml`:

```yaml
pve_dev_vm_token: "PVEAPIToken=hass@pve!dev-vm=<secret shown at creation>"
```

Then reload without restarting: Developer Tools → Actions →
`rest_command.reload`.

The direct IP is deliberate — routing this through the reverse proxy would make
VM power depend on the proxy LXC being healthy.

## Behaviour worth knowing

- **Shutdown is graceful only** (ACPI + qemu-guest-agent, 120s). If the guest
  does not go down, the VM keeps running and *Dev-VM Schalter abgleichen* flips
  the switch back to `on` — that flip is the error signal.
- **Turning the switch off kills SSH and Claude Code sessions on the VM.** The
  dashboard tile asks for confirmation on tap.
- **A restart of Home Assistant does not power anything.** Both command
  automations ignore transitions out of `unknown`/`unavailable`.
- The switch is intent, the ping tile next to it is truth. They disagree for a
  minute or two while the VM boots or shuts down.

## Verifying

```bash
# on the Proxmox host: what the token actually did
grep 'hass@pve!dev-vm' /var/log/pve/tasks/index | tail -5
```

In Home Assistant: Settings → Automations → *Dev-VM einschalten* → Traces.
