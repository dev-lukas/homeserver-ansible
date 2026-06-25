# Homeserver Ansible

Ansible configuration for managing Proxmox homeserver infrastructure.

## Project Structure

```
.
├── ansible.cfg              # Ansible configuration
├── inventory/
│   ├── hosts.yml            # Host definitions
│   └── group_vars/
│       ├── all.yml          # Variables for all hosts
│       └── proxmox.yml      # Proxmox-specific variables
├── playbooks/
│   ├── site.yml             # Main entry point
│   └── proxmox.yml          # Proxmox playbook
├── roles/
│   ├── common/              # Common tasks (SSH, etc.)
│   │   └── tasks/
│   │       ├── main.yml
│   │       └── ssh.yml
│   └── power_management/    # Power optimization
│       ├── tasks/
│       │   ├── main.yml
│       │   ├── powertop.yml
│       │   └── ltr_ignore.yml
│       └── handlers/
│           └── main.yml
└── requirements.yml         # Ansible Galaxy dependencies
```

## Prerequisites

1. Install Ansible:
   ```bash
   pip install ansible
   ```

2. Install required collections:
   ```bash
   ansible-galaxy collection install -r requirements.yml
   ```

## Configuration

1. Edit `inventory/hosts.yml` and set your Proxmox server IP
2. Edit `inventory/group_vars/all.yml` and add your SSH public key

## Usage

### Run all playbooks
```bash
ansible-playbook playbooks/site.yml
```

### Run only Proxmox configuration
```bash
ansible-playbook playbooks/proxmox.yml
```

### Verify reverse proxy and safety mechanisms
```bash
ansible-playbook playbooks/reverse_proxy_verify.yml --ask-vault-pass
```

### Run with specific tags
```bash
# Only SSH configuration
ansible-playbook playbooks/site.yml --tags ssh

# Only power management
ansible-playbook playbooks/site.yml --tags power
```

### Dry run (check mode)
```bash
ansible-playbook playbooks/site.yml --check
```

## Expanding the Project

### Adding new roles
Create a new role directory under `roles/`:
```
roles/
└── new_role/
    ├── tasks/
    │   └── main.yml
    ├── handlers/
    │   └── main.yml
    ├── templates/
    ├── files/
    └── defaults/
        └── main.yml
```

### Adding new host groups
1. Add the group to `inventory/hosts.yml`
2. Create `inventory/group_vars/<group_name>.yml`
3. Create a playbook in `playbooks/<group_name>.yml`
4. Import it in `playbooks/site.yml`

## Maintenance

Run the full fleet update (Proxmox host + all LXCs/VMs):

```bash
ansible-playbook playbooks/maintenance.yml --ask-vault-pass
# Target a single component via tags, e.g.:
ansible-playbook playbooks/maintenance.yml --ask-vault-pass --tags media_services
```

### Upgrade reliability

The apt upgrade routine for every Debian guest is defined once as
`apt_maintenance_script` in `inventory/group_vars/all.yml` and reused via
`playbooks/tasks/maintenance_apt.yml`. It is designed to survive the
"too many updates" failures:

- **Lock-aware** — `DPkg::Lock::Timeout=600` makes apt *wait* for a running
  `unattended-upgrades`/`apt-daily` run instead of failing instantly on the
  dpkg lock. This was the main cause of the upgrade step failing.
- **Self-healing** — runs `dpkg --configure -a` first to recover from any
  previously interrupted run.
- **Non-interactive** — `--force-confdef/--force-confold` so a changed config
  file never blocks the run on a prompt.
- **Retried** — transient apt/network errors are retried (3×, 30s apart).

### Reboot policy

When an update sets `/var/run/reboot-required`, the playbook:

- **Auto-reboots** Local Services, Media Services, Immich and CI Runner VMs,
  then waits for them to finish booting before continuing.
- **Reports only** (never reboots) the Proxmox host and the Development VM.

Toggle per host with `maint_auto_reboot` in the relevant play. The final
"Maintenance summary" play prints, per host, whether packages were upgraded,
whether a reboot is required, and whether it was rebooted — plus an
`ACTION NEEDED` line listing any hosts with a still-pending reboot.

## Features

- **SSH Key Management**: Automatically deploys SSH keys to all hosts
- **CI Runner Registry Retention**:
  - Keeps `latest` and other non-SHA tags in the self-hosted registry
  - Keeps the newest 5 commit-SHA image tags per repository by default
  - Deletes older SHA tags and runs Docker registry garbage collection weekly
- **Power Management**:
  - Installs and configures powertop with auto-tune
  - Configures LTR ignore for better Intel power states
  - Sets up cron jobs to apply settings on reboot
