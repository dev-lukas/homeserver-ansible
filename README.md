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
3. Set up Proton Pass on the controller (next section)

## Secrets

Nothing secret is stored in this repository. Every credential is fetched at
run time from Proton Pass through [pass-cli](https://protonpass.github.io/pass-cli/)
and the `proton_pass` lookup (see `inventory/group_vars/proxmox/secrets.yml`
for the full list). The lookup is vendored in `plugins/lookup/` from
community.general main until a release ships the pass-cli 2.3 fix. SSH keys are
served by the Proton Pass SSH agent, so no private key touches the disk of
the controller or of Proxmox.

### Controller setup (once)

```bash
curl -fsSL https://proton.me/download/pass-cli/install.sh | bash   # installs ~/.local/bin/pass-cli
pass-cli login                                                     # web login, session persists
```

Then run the agent as a service, scoped to the `ssh-keys` vault:

```ini
# /etc/systemd/system/proton-pass-ssh-agent.service
[Unit]
Description=Proton Pass SSH agent
After=network-online.target

[Service]
ExecStart=%h/.local/bin/pass-cli ssh-agent start --vault-name ssh-keys --socket-path %h/.ssh/proton-pass-agent.sock
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now proton-pass-ssh-agent
echo 'export SSH_AUTH_SOCK="$HOME/.ssh/proton-pass-agent.sock"' >> ~/.bashrc   # for plain ssh
```

`ansible.cfg` points ssh at that socket and forwards the agent, so the
maintenance plays can ssh from Proxmox into guests without a key file. Every
playbook starts with `playbooks/tasks/secrets_preflight.yml`, which fails
early if the session or the agent socket is missing.

### Layout in Proton Pass

| Vault       | Item                       | Fields                                   |
|-------------|----------------------------|------------------------------------------|
| `ssh-keys`  | `ansible-deploy` (SSH Key) | `private_key`, `public_key`              |
| `homeserver`| `github-runner`            | `pat`                                    |
| `homeserver`| `hetzner-dns`              | `api_token`                              |
| `homeserver`| `maxmind`                  | `account_id`, `license_key`              |
| `homeserver`| `crowdsec`                 | `enroll_key`                             |
| `homeserver`| `reverse-proxy-basic-auth` | one hidden field per backend (htpasswd)  |
| `homeserver`| `registry-retention`       | `credentials`                            |
| `homeserver`| `immich`                   | `db_password`                            |
| `homeserver`| `adguard` (Login)          | `username`, `password`, `password_hash`  |
| `homeserver`| `sonarr`, `radarr`, `sonarr-anime`, `radarr-anime` | `api_key`      |
| `homeserver`| `protonvpn-wireguard`      | `private_key`, `addresses`               |
| `homeserver`| `ups`                      | `monitor_password`                       |
| `homeserver`| `proxmox` (Login)          | root password, used manually for `--ask-pass` |

Secrets go in as *hidden* custom fields whose names match the table. Adding a
secret means adding a field in Proton Pass and one lookup line in
`secrets.yml`.

### Bootstrapping a fresh Proxmox host

Before the deploy key is authorized, connect with the root password instead:

```bash
ansible-playbook playbooks/proxmox.yml --ask-pass --tags ssh
```

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
ansible-playbook playbooks/reverse_proxy_verify.yml
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
ansible-playbook playbooks/maintenance.yml
# Target a single component via tags, e.g.:
ansible-playbook playbooks/maintenance.yml --tags media_services
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
- **On-demand VMs** (both run with `onboot: 0` so the host can idle deep):
  - CI runner VM 108 is powered on/off by the GitHub-polling
    `ci_runner_autostart` watchdog
  - Dev VM 107 has a Home Assistant switch, backed by a Proxmox API token
    scoped to that one VM — see [docs/dev-vm-power.md](docs/dev-vm-power.md)
