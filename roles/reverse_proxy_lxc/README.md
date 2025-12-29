# Reverse Proxy LXC Role

This Ansible role deploys a highly secure reverse proxy on a Proxmox LXC container with the following features:

## Features

- **Debian 13 (Trixie)** LXC container on Proxmox VE
- **Nginx Mainline** with HTTP/2 support
- **GeoIP2 Blocking** - Restricts traffic to allowed countries (default: Germany only)
- **Let's Encrypt Wildcard SSL** via Hetzner DNS Challenge
- **CrowdSec Security Engine** with Nginx Bouncer
- **Unattended Upgrades** for automatic security patches
- **Comprehensive Hardening** (SSH, sysctl, fail2ban)

## Requirements

### Vault Variables (Required)

Add these to your vault file:

```yaml
# Hetzner DNS API Token (required for Let's Encrypt)
vault_hetzner_api_token: "your-hetzner-dns-api-token"

# MaxMind GeoIP (optional but recommended)
vault_maxmind_account_id: "your-account-id"
vault_maxmind_license_key: "your-license-key"

# CrowdSec Console (optional)
vault_crowdsec_enroll_key: "your-enrollment-key"
```

### External Requirements

1. **Hetzner DNS API Token**: Required for DNS-01 challenge for wildcard certificates
   - Get from: https://dns.hetzner.com/settings/api-token
   
2. **MaxMind Account**: Required for GeoIP database downloads
   - Register at: https://www.maxmind.com/en/geolite2/signup

3. **CrowdSec Console** (Optional): For centralized security monitoring
   - Register at: https://app.crowdsec.net/

## Role Variables

### Container Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `reverse_proxy_vmid` | `103` | Proxmox VMID |
| `reverse_proxy_hostname` | `reverse-proxy` | Container hostname |
| `reverse_proxy_ip` | `192.168.178.4` | Static IP address |
| `reverse_proxy_gateway` | `192.168.178.1` | Network gateway |
| `reverse_proxy_memory` | `512` | Memory in MB |
| `reverse_proxy_cores` | `2` | CPU cores |
| `reverse_proxy_disk_size` | `8` | Disk size in GB |

### Domain Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `reverse_proxy_domain` | `lukas-roth.dev` | Primary domain |
| `reverse_proxy_email` | `admin@lukas-roth.dev` | Let's Encrypt email |

### GeoIP Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `reverse_proxy_allowed_countries` | `["DE"]` | ISO country codes to allow |

### Backend Services

Configure services to proxy:

```yaml
reverse_proxy_backends:
  - name: "homeassistant"
    subdomain: "ha"
    backend_host: "192.168.178.3"
    backend_port: 8123
    websocket: true
  - name: "adguard"
    subdomain: "adguard"
    backend_host: "192.168.178.2"
    backend_port: 3000
    websocket: false
```

## Usage

Run the playbook:

```bash
# Deploy only the reverse proxy
ansible-playbook playbooks/proxmox.yml --tags reverse_proxy

# With verbose output
ansible-playbook playbooks/proxmox.yml --tags reverse_proxy -v
```

## Security Features

### Network Security

- Proxmox firewall enabled with DROP policy
- Only ports 80, 443, and 22 (internal only) allowed
- SSH restricted to internal subnet

### GeoIP Blocking

- All traffic from non-allowed countries returns 444 (silent drop)
- GeoIP database auto-updates weekly
- Applied globally before any server block processing

### CrowdSec

- Nginx collection installed for web attack detection
- SSH collection for brute force protection
- HTTP CVE collection for known vulnerabilities
- Nginx bouncer blocks malicious IPs in real-time
- Hub auto-updates daily

### SSL/TLS

- TLS 1.2 and 1.3 only
- Strong cipher suite
- OCSP stapling enabled
- DH parameters (2048-bit)
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)

### Container Hardening

- SSH key-only authentication
- fail2ban for SSH protection
- Restrictive sysctl settings
- Automatic security updates

## Maintenance

### Systemd Timers

| Timer | Schedule | Purpose |
|-------|----------|---------|
| `certbot-renewal.timer` | Twice daily | SSL certificate renewal |
| `geoip-update.timer` | Weekly | GeoIP database update |
| `crowdsec-update.timer` | Daily | CrowdSec hub update |
| `maintenance-check.timer` | Daily 6:00 | Status check |

### Useful Commands

Access the container:

```bash
pct enter 103
```

Check status:

```bash
/usr/local/bin/maintenance-status.sh
```

Check CrowdSec decisions:

```bash
cscli decisions list
```

Test Nginx configuration:

```bash
nginx -t
```

## Files Created

```
/etc/nginx/
├── nginx.conf              # Main configuration with GeoIP
├── snippets/
│   ├── geo-block.conf      # Geo-blocking rules
│   ├── ssl-params.conf     # SSL security settings
│   ├── proxy-params.conf   # Standard proxy headers
│   └── websocket-params.conf # WebSocket headers
├── sites-available/
│   └── default             # Default catch-all server
└── sites-enabled/
    └── *.conf              # Enabled backends

/etc/letsencrypt/
├── hetzner-credentials.ini # Hetzner API token
└── live/                   # SSL certificates

/etc/crowdsec/
├── config.yaml            # Main configuration
└── acquis.d/
    ├── nginx.yaml         # Nginx log acquisition
    └── sshd.yaml          # SSH log acquisition
```

## Troubleshooting

### Certificate Issues

```bash
# Check certificate status
certbot certificates

# Force renewal
/opt/certbot-hetzner/bin/certbot renew --force-renewal
```

### GeoIP Not Working

```bash
# Check if database exists
ls -la /var/lib/GeoIP/

# Test GeoIP lookup
mmdblookup --file /var/lib/GeoIP/GeoLite2-Country.mmdb --ip 8.8.8.8
```

### CrowdSec Issues

```bash
# Check service status
systemctl status crowdsec
systemctl status crowdsec-nginx-bouncer

# Check bouncer registration
cscli bouncers list

# View metrics
cscli metrics
```
