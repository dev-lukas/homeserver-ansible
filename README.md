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

## Features

- **SSH Key Management**: Automatically deploys SSH keys to all hosts
- **Power Management**: 
  - Installs and configures powertop with auto-tune
  - Configures LTR ignore for better Intel power states
  - Sets up cron jobs to apply settings on reboot
