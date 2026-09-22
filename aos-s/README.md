# AOS-S Trunk & VLAN Example

English · **[Deutsch](README_de.md)**

An example Ansible playbook for classic Aruba **AOS-S** (ArubaOS-Switch)
switches. It configures two LACP trunks and two VLANs over SSH/CLI, reads the
result back and saves the configuration.

> The ports, VLAN IDs and the IP address in the playbook are **examples**.
> Adapt them to your switch before running it.

---

## What it does

| Step | Configuration / command |
|---|---|
| LACP trunk `trk1` | ports `9-10` |
| LACP trunk `trk2` | ports `7-8` |
| VLAN 300 | name `vlan300`, tagged on `trk1`, `jumbo` |
| VLAN 200 | name `vlan200`, untagged on ports `5-6`, tagged on `trk1` and `trk2`, `voice`, IP `198.51.100.1/24` |
| Read back | `show trunks`, `show lacp`, `show vlan`, `show vlan 200`, `show vlan 300`, `show ip` |
| Save | `write memory` |

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core`
- Ansible collections `arubanetworks.aos_switch` and `ansible.netcommon`
  (`ansible-galaxy collection install -r ../devcontainer/requirements.yml`)
- SSH (TCP/22) reachability from the Ansible controller to the switch

**Inventory** – adapt [`switch_hosts.yml`](switch_hosts.yml):

```yaml
all:
  hosts:
    switch1:
      ansible_host: 192.0.2.12
      ansible_user: example-user
      ansible_password: YOUR_PASSWORD   # prefer Ansible Vault or -e at runtime
      ansible_connection: local
      ansible_network_os: arubanetworks.aos_switch.arubaoss
```

**Run**

```bash
# from this folder (aos-s/), so that ansible.cfg is picked up
ansible-playbook -i switch_hosts.yml switch_attributes.yml
```

---

## Files

| File | Purpose |
|---|---|
| [`switch_attributes.yml`](switch_attributes.yml) | The playbook – trunks, VLANs, read-back, `write memory`. |
| [`switch_hosts.yml`](switch_hosts.yml) | Example inventory (placeholder address and credentials). |
| [`ansible.cfg`](ansible.cfg) | Disables SSH host key checking for this folder. |

---

## Connection

The inventory sets `ansible_connection: local`, the connection method of the
REST-based `arubaoss_*` modules. This playbook only uses the CLI modules
`arubaoss_config` and `arubaoss_command`, so it overrides the connection for the
whole play with `ansible.netcommon.network_cli` (SSH).

---

## Notes

- The `show` tasks run with `no_log: true`; their output is printed by the
  following `debug` task.
- `write memory` is always reported as `changed`.
- SSH host key checking is disabled (`ansible.cfg`, `StrictHostKeyChecking=no`).
  Enable it in production environments.
- Never commit real credentials – use Ansible Vault or pass the password at
  runtime.
