# AOS-CX AAA / Port-Access Audit → CSV

English · **[Deutsch](README_de.md)**

An Ansible playbook that audits **which physical ports** of one or more Aruba
**AOS-CX** switches have **AAA / port-access authentication** (802.1X / `dot1x`,
`mac-auth`) configured – and which do not – plus the RADIUS server group per
method. It writes a single **CSV** report, one row per physical port.

The query is **REST-only**: one `GET /system/interfaces?depth=<n>` per switch
returns every port together with its nested port-access configuration, so the
number of ports or VSF stack members does **not** need to be known in advance –
the playbook iterates over whatever the switch returns.

The playbook is **read-only** – it logs in, runs one `GET` and a `POST /logout`,
and never changes the switch.

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Files](#files)
- [CSV columns](#csv-columns)
- [`AAA Port-Access` values](#aaa-port-access-values)
- [How the playbook works](#how-the-playbook-works)
- [Variables](#variables)
- [How detection works / tuning it to your firmware](#how-detection-works--tuning-it-to-your-firmware)
- [Privacy and publishing](#privacy-and-publishing)
- [Limitations](#limitations)

---

## What it does

Per switch:

1. Log in to the REST API (session cookie).
2. `GET /system/interfaces?depth=4&attributes=…` – every interface with its
   `port_access_auth_configurations` and `port_security` sub-objects.
3. Optionally dump that raw JSON next to the CSV (`dump_raw=true`).
4. For every **physical** port (name like `1/1/24`): `OTHER` if it is not an
   `access` port, otherwise `YES` when `port_access_auth_configurations` has a
   `dot1x` / `mac-auth` key, else `NO`. Also record each method's server group.
5. Print a per-host hint (how many ports without AAA).
6. Log out (always, even on error).

Then, once on `localhost`: aggregate all hosts' rows and write
`exports/aaa_port_access_<YYYYMMDD_hhmmss>.csv`, followed by a summary line per
host / stack and a grand total.

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core`.
- HTTPS (TCP/443) from the Ansible controller to each switch. All REST calls run
  on the controller (`delegate_to: localhost`).
- A switch login with permission to read `/system/interfaces`.

**Inventory** – use the local [`demohost.yml`](demohost.yml) or the shared
[`../switch_hosts.yml`](../switch_hosts.yml):

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: example-user
    ansible_password: YOUR_PASSWORD     # prefer Ansible Vault or -e at runtime
```

> The playbook only needs `ansible_host`, `ansible_user`, `ansible_password`.
> `ansible_connection` / `ansible_network_os` are not required (no collection
> module is used, only `ansible.builtin.uri`).

**Run**

```bash
# from this folder (aos-cx/aaa/)
ansible-playbook -i demohost.yml play_aaa.yml

# verify detection against your firmware: also keep the raw interfaces JSON
ansible-playbook -i demohost.yml play_aaa.yml -e dump_raw=true

# older firmware that does not serve the v10.13 schema (Server Group columns stay empty)
ansible-playbook -i demohost.yml play_aaa.yml -e rest_version=v10.09

# stricter TLS
ansible-playbook -i demohost.yml play_aaa.yml -e validate_certs=true
```

The report lands in `exports/aaa_port_access_<YYYYMMDD_hhmmss>.csv`. Everything
under `exports/` is git-ignored (except `.gitkeep`).

---

## Files

| File | Purpose |
|---|---|
| [`play_aaa.yml`](play_aaa.yml) | The playbook – play 1 (per switch): login, read ports, optional raw dump, build rows, logout. Play 2 (`localhost`): aggregate + write CSV + per-host summary. |
| [`demohost.yml`](demohost.yml) | Example inventory for a single switch. Point `-i` at this or at `../switch_hosts.yml`. |
| `exports/` | Target folder for the generated CSV (and the optional raw JSON dump). Git-ignored except `.gitkeep`. |

---

## CSV columns

Separator is `;` so the file opens cleanly in a German locale. Free-text fields
(`VLAN Mode`, `Description`, `Indicator Keys`) have any `;` replaced with `,`.

| Column | Meaning |
|---|---|
| `AAA Port-Access` | **First column** – `YES` / `NO` / `OTHER` / `ERROR` per port (see [below](#aaa-port-access-values)). `OTHER` = the port is not in `access` mode. Plain text; colour it in Excel/LibreOffice via conditional formatting. |
| `Label` | `<hostname>-<port>`, e.g. `switch-access-1-1/1/24` – unique key per port. |
| `Hostname` | Inventory host name. |
| `IP-Address` | Management IP / DNS name from `ansible_host`. |
| `Stack Member` | First segment of the port name (`1` for `1/1/24`) = VSF member / chassis. `N/A` on an error row. |
| `Port` | Port name as reported by the switch (`member/slot/port`). |
| `Admin` | Configured admin state of the port (`up` / `down`; `up` when the switch omits the attribute). |
| `VLAN Mode` | `access` / `native-untagged` / … if set, else empty. Context only. |
| `Description` | Port description if set. Context only. |
| `Detected Methods` | The configured port-access auth methods: the keys of `port_access_auth_configurations` (`dot1x`, `mac-auth`); `-` if none. `port_security` is **not** listed here. |
| `dot1x Server Group` | Server group assigned to the `dot1x` method on this port (`server_group_attr` inside the method object); empty (`-`) if none / not a `dot1x` port. |
| `mac-auth Server Group` | Same for the `mac-auth` method. |
| `Indicator Keys` | The raw evidence: `auth_cfg=[…] port_security.enable=… pac_type=dict|uri`. `port_security.enable` is shown for information only – it does **not** drive the first column. `pac_type=uri` means the query `depth` was too low – raise `ports_depth`. On an `ERROR` row this holds the error message. |

---

## `AAA Port-Access` values

| Value | Suggested colour | Criteria |
|---|---|---|
| `YES` | 🟩 green | Access port **and** `port_access_auth_configurations` has ≥ 1 method key (`dot1x` / `mac-auth`). |
| `NO` | 🟥 red | Access port **and** `port_access_auth_configurations` is `{}`. `port_security.enable` being `true` does **not** make it `YES`. |
| `OTHER` | ⬜ grey | The effective VLAN mode is **not** `access` (trunk / native-untagged / unset uplink). Port-access auth is not expected here, so the port is not counted as "missing AAA". Checked before YES/NO. |
| `ERROR` | ⬜ grey | The switch was unreachable or a REST call failed. One row per failed host; the message is in `Indicator Keys`. |

---

## How the playbook works

| # | Step | HTTP |
|---|---|---|
| 1 | Log in to the REST API | `POST /login` |
| 2 | Read all interfaces + port-access config | `GET /system/interfaces?depth=4&attributes=…` |
| 3 | Dump raw interfaces JSON (`when: dump_raw`) | – |
| 4 | Build one audit row per physical port | – |
| 5 | Per-host hint: ports without AAA | – |
| 4r / 5r | *(rescue)* emit one `ERROR` row + hint | – |
| 6 | Log out (`always`) | `POST /logout` |
| 7–9 | *(localhost)* timestamp, collect rows, write CSV | – |
| 10 / 11 | *(localhost)* summary per host / stack, then grand total | – |

Play 1 wraps steps 1–6 in a `block` / `rescue` / `always`: a failed switch still
produces exactly one CSV row (`ERROR`), and the API session is always closed –
AOS-CX has a hard session limit and a leaked session blocks later logins.

---

## Variables

| Variable | Default | Description |
|---|---|---|
| `rest_version` | `v10.13` | REST API schema version in the URL path. `v10.13` is the default because the per-method `radius_server_group` field (the two `Server Group` columns) only exists from that schema on. A switch only serves schemas up to its own firmware – if login/query 404s, lower it (`-e rest_version=v10.09`); the `Server Group` columns then stay empty. |
| `rest_port` | `443` | TCP port of the switch REST API. Override (per host or `-e rest_port=8443`) only if REST is published elsewhere. |
| `port_resource` | `interfaces` | REST resource listing the physical ports. `interfaces` on AOS-CX ≳ 10.09 (verified on 10.09); set `-e port_resource=ports` on very old firmware if the query 404s. |
| `validate_certs` | `false` | `true` verifies the switch TLS certificate on every REST call. Set `true` in production with a trusted CA. |
| `ports_depth` | `4` | `depth` of the collection query. On a collection GET, `3` is the minimum that expands `port_access_auth_configurations` from a URI stub into a keyed dict (`4` also inlines each method's sub-config). If the `Indicator Keys` column shows `pac_type=uri`, raise it. |
| `interface_attributes` | `name,admin,vlan_mode,applied_vlan_mode,description,port_access_auth_configurations,port_security` | Attribute filter for the query (smaller response + dump). `-e interface_attributes=''` fetches full objects if a firmware rejects the filter (HTTP 400). |
| `server_group_attr` | `radius_server_group` | Attribute read from each `port_access_auth_configurations.<method>` object for the `<method> Server Group` columns. Per the AOS-CX API reference this field exists from schema `v10.13` on; empty on a configured method = "inherits the system-level RADIUS server group". |
| `port_filter_regex` | `^\d+/\d+/\d+$` | Only ports whose name matches are audited. Default keeps physical ports and drops LAGs, VLAN/loopback interfaces and sub-interfaces. |
| `dump_raw` | `false` | `true` also writes `exports/aaa_port_access_raw_<host>.json` – the raw interfaces response, for verifying the key paths against your firmware. |

```bash
ansible-playbook -i demohost.yml play_aaa.yml \
  -e rest_version=v10.09 -e validate_certs=true -e dump_raw=true
```

---

## How detection works / tuning it to your firmware

For each physical interface the playbook reads (top-level attributes verified on
AOS-CX 10.09; `radius_server_group` per the v10.13 API reference):

| Attribute | Meaning |
|---|---|
| `vlan_mode` / `applied_vlan_mode` | The port's VLAN mode. If the effective value is not `access`, the port is reported `OTHER` and the check below is skipped. |
| `port_access_auth_configurations` | A dict keyed by configured port-access auth method – `dot1x`, `mac-auth`. `{}` = none. Each value is that method's config object; its `radius_server_group` (from schema `v10.13`) fills the `<method> Server Group` column. |
| `port_security.enable` | Boolean, MAC **port-security** – shown in `Indicator Keys` for information **only**. It does *not* affect the first column (a port with just port-security is `NO`). |

For an `access` port, `AAA Port-Access = YES` when
`port_access_auth_configurations` has a `dot1x` or `mac-auth` key, else `NO`.
`Detected Methods` lists the keys; `Indicator Keys` records the raw values so the
call is auditable.

> A method key present but the authenticator left *disabled* still counts as
> `YES` here – the audit answers *configured vs not*, matching the CLI
> `aaa authentication port-access …` stanza being present.

**To check it against your switches:** run once with `-e dump_raw=true`, open
`exports/aaa_port_access_raw_<host>.json`, and compare a port you *know* has
802.1X with one that does not. If your firmware exposes the state (or the server
group) under different keys, adjust `auth_methods` / `server_group_attr` in
**task 4** of the playbook.

---

## Privacy and publishing

- **The playbook only reads.** One `GET` and a `POST /logout`; it never writes
  to the switch and keeps no state.
- **No secrets in the repo.** Commit `demohost.yml` only with a placeholder
  password; pass the real one at runtime (`-e ansible_password=…`, `--ask-vault-pass`,
  Ansible Vault). Task 1 runs with `no_log: true`.
- **Generated reports are private.** Everything under `exports/` is git-ignored:
  a real CSV lists your port descriptions and topology; a raw dump contains the
  full port configuration. Share those deliberately, not via git.
- **All examples use documentation ranges** – [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)
  IPs (`192.0.2.0/24`), [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) names.

---

## Limitations

- **Detection keys verified on AOS-CX 10.09; server group per the v10.13 API
  reference.** Other releases may differ – validate the first run against a
  known-good port and, if needed, adjust `auth_methods` / `server_group_attr`
  in task 4 (see [tuning](#how-detection-works--tuning-it-to-your-firmware)).
- **The two `Server Group` columns need schema `v10.13`.** On the 10.09 sample
  the `radius_server_group` field is absent, so the columns are empty. Run
  against firmware that serves `v10.13` (the default `rest_version`); an empty
  value on a configured method then means the method inherits the system-level
  RADIUS server group.
- Reports **per-port configuration presence**, not runtime state – it does not
  tell you whether a client actually authenticated, nor whether global
  `aaa authentication port-access` / RADIUS servers are set up. A configured but
  *disabled* authenticator still shows as `YES`.
- Physical ports only (`port_filter_regex`); LAG-level port-access is not audited.
- One REST session per switch – hosts are processed in Ansible's normal fork
  parallelism; each `always` block closes its own session.
- `rest_version` / `port_resource` are single pinned values; very old firmware
  may need `rest_version` lowered or `port_resource=ports`.
