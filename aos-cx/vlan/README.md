# AOS-CX VLAN Management

English · **[Deutsch](README_de.md)**

An Ansible playbook that manages the VLANs of one or more Aruba **AOS-CX**
switches from a single source of truth. You describe the VLANs you *want* in
[`vlans.yml`](vlans.yml); the playbook makes the switch match that list and then
validates the result on the device.

The playbook is idempotent – running it again changes nothing once the switch is
in the desired state.

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Files](#files)
- [`vlans.yml` format](#vlansyml-format)
- [How the playbook works](#how-the-playbook-works)
- [Variables](#variables)
- [REST vs. SSH](#rest-vs-ssh)
- [Safe deletion of VLANs](#safe-deletion-of-vlans)
- [Limitations](#limitations)

---

## What it does

1. Creates / updates every VLAN listed in `vlans.yml` (id, name, `voice`,
   `ip_igmp_snooping`).
2. Enables `dhcpv4-snooping` on the VLANs that ask for it.
3. Optionally deletes VLANs that exist on the switch but are **not** in
   `vlans.yml` (off by default – see [Safe deletion](#safe-deletion-of-vlans)).
4. Validates each VLAN against the switch (name match + DHCPv4 snooping) and
   prints a compact summary of any failures.

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core` and the [`pyaoscx`](https://pypi.org/project/pyaoscx/)
  library (needed by the REST connection).
- Ansible collection `arubanetworks.aoscx`
  (`ansible-galaxy collection install -r ../../devcontainer/requirements.yml`).
- HTTPS (TCP/443) **and** SSH (TCP/22) reachability from the Ansible controller
  to each switch. SSH is only used for the DHCPv4-snooping steps.

**Inventory** – reuse the shared [`../switch_hosts.yml`](../switch_hosts.yml) or
write your own:

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: admin
    ansible_password: CHANGEME          # prefer Ansible Vault or -e at runtime
    ansible_network_os: arubanetworks.aoscx.aoscx
    ansible_connection: arubanetworks.aoscx.aoscx
    ansible_aoscx_validate_certs: false
    ansible_aoscx_use_proxy: false
```

**Run**

```bash
# from this folder (aos-cx/vlan/)
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml

# also delete VLANs that are no longer in vlans.yml
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml -e vlan_cleanup=true
```

---

## Files

| File | Purpose |
|---|---|
| [`switch_attributes.yml`](switch_attributes.yml) | The playbook – 8 numbered tasks: create/update, DHCPv4 snooping, gather, delete, re-gather, running-config, validate, summary. |
| [`vlans.yml`](vlans.yml) | The target state: the full list of VLANs and their attributes. **This is the file you edit day to day.** The shipped list is a generic example. |
| [`extra`](extra) | Reference copy of tasks 3–8 as a standalone snippet (facts, cleanup, validation). Not needed to run the playbook – kept for reuse in other playbooks. |

---

## `vlans.yml` format

One list entry per VLAN:

```yaml
vlans:
  - { id: 100, name: "clients-wired" }
  - { id: 110, name: "clients-wireless", ip_igmp_snooping: true }
  - { id: 120, name: "voice", voice: true, dhcpv4_snooping: true, ip_igmp_snooping: true }
```

| Key | Type | Required | Meaning |
|---|---|---|---|
| `id` | int (1–4094) | yes | VLAN ID |
| `name` | string | yes | VLAN name on the switch |
| `voice` | bool | no | mark as voice VLAN (IP phones) |
| `ip_igmp_snooping` | bool | no | enable IGMP snooping (IPv4 multicast) |
| `dhcpv4_snooping` | bool | no | enable DHCPv4 snooping (applied via CLI, see below) |

Any optional key that is omitted is left at the switch default.

---

## How the playbook works

| # | Task | Module | Transport |
|---|---|---|---|
| 1 | Create / update VLANs | `aoscx_vlan` | REST |
| 2 | Enable DHCPv4 snooping (`when: dhcpv4_snooping`) | `aoscx_config` | SSH |
| 3 | Gather configured VLAN IDs | `aoscx_facts` | REST |
| 4 | Delete VLANs missing from `vlans.yml` (`when: vlan_cleanup`) | `aoscx_vlan` | REST |
| 5 | Re-gather facts (state may have changed in 4) | `aoscx_facts` | REST |
| 6 | Fetch `show running-config` | `aoscx_command` | SSH |
| 7 | Validate name + DHCPv4 snooping per VLAN | `assert` | – |
| 8 | Print summary of failed VLANs | `debug` | – |

Step 7 uses `ignore_errors: true` so a single failing VLAN does not abort the
loop; every VLAN is checked and step 8 lists the IDs that failed.

---

## Variables

| Variable | Default | Description |
|---|---|---|
| `vlan_cleanup` | `false` | `true` enables task 4, which deletes VLANs that are on the switch but not in `vlans.yml` (VLAN 1 is always kept). |

```bash
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml -e vlan_cleanup=true
```

---

## REST vs. SSH

The `arubanetworks.aoscx` collection offers two transports:

- **REST** (`pyaoscx`) – the default here. `aoscx_vlan` and `aoscx_facts` only
  work over REST.
- **SSH** (`network_cli`) – required for modules that send raw CLI
  (`aoscx_config`, `aoscx_command`).

`dhcpv4-snooping` is **not** exposed by the REST `aoscx_vlan` module, so tasks 2
and 6 switch the connection to SSH per task via task-local `vars`. Without that
override those tasks fail with *"Method not found"*.

---

## Safe deletion of VLANs

Task 4 is a destructive operation, so it is guarded twice:

1. It only runs with `-e vlan_cleanup=true` (default `false`).
2. VLAN 1 (the default VLAN) is always excluded.

Run once without the flag to see what *would* change, then re-run with
`-e vlan_cleanup=true` once you are confident the `vlans.yml` list is complete.

---

## Limitations

- Only the VLAN attributes `name`, `voice`, `ip_igmp_snooping` and
  `dhcpv4_snooping` are managed. L3/SVI, ACLs, VRFs etc. are out of scope.
- DHCPv4-snooping validation parses the text of `show running-config`; a change
  in AOS-CX output format could require adjusting the regex in task 7.
- The playbook does **not** run `write memory` – add a final `aoscx_command`
  task (`copy running-config startup-config`) if you want the change persisted
  across reboots.
