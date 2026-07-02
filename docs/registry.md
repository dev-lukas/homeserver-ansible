# Container registry (LXC 106)

`registry.lukas-roth.dev` is served by the always-on `registry_lxc` container
(VMID 106, 192.168.178.14). It replaced the registry that used to live inside
the on-demand CI runner VM, so image pulls (production VPS, CI integration
jobs) no longer depend on the CI VM being awake.

## Architecture

- **Distribution v3** as a plain systemd service (`registry.service`) — no
  Docker in this LXC. A single idle Go binary keeps the host's package
  C-states intact; the unit is sandboxed (non-root, `ProtectSystem=strict`,
  empty capability set, syscall filter, 384M memory cap).
- **Auth + TLS terminate in the registry itself** (bcrypt htpasswd from
  `vault_reverse_proxy_auth_basic_users.registry`, self-signed cert for the
  proxy hop). The reverse proxy forwards the client's Authorization header,
  so nginx basic auth and registry auth share the same credentials.
- **Network**: pve firewall allows :5000 only from the reverse proxy (.4).
  All clients use `https://registry.lukas-roth.dev` (TLS via wildcard cert,
  GeoIP DE, basic auth).
- **Data**: ZFS dataset `mediapool/registry` (recordsize=1M), bind-mounted to
  `/var/lib/registry`, owned by host uid 101000 (container uid 1000).

## Operations

- **Retention/GC**: weekly cron (Sun 05:30) inside the LXC keeps `latest` +
  the newest 5 SHA tags per repo, then runs `registry garbage-collect`.
  Logs: `/var/log/registry-retention.log`.
- **Credentials**: password shared with CI (`REGISTRY_PASSWORD` secret) and
  the VPS (`vault_firephenix_registry_password`). The local retention script
  reads `/etc/registry/retention-credentials`
  (from `vault_registry_retention_credentials`).
- **Health check**: `curl https://registry.lukas-roth.dev/v2/` → 401
  (anonymous) means up + auth enforced.
- **Version bumps**: `registry_lxc_version` + `registry_lxc_binary_sha256`
  in `roles/registry_lxc/defaults/main.yml`, then
  `ansible-playbook playbooks/proxmox.yml --tags registry`.
