# VSF Inventory → CSV Export

English · **[Deutsch](README_de.md)**

An Ansible playbook plus a small Python helper that connect to Aruba switches
over **SSH** (AOS-CX **and** AOS-S), read their **VSF / stacking** state, and
write one combined **CSV** report – one row per stack member, plus a per-stack
health verdict in the first column.

The platform (AOS-CX vs. AOS-S) is auto-detected, so the inventory only needs an
address and login per switch.

---

## Contents

- [Quick start](#quick-start)
- [Files](#files)
- [Example output](#example-output)
- [CSV columns](#csv-columns)
- [`VSF-Status` values](#vsf-status-values)
- [How `vsf_ssh_inventory.py` works](#how-vsf_ssh_inventorypy-works)
- [Design notes](#design-notes)
- [Privacy and publishing](#privacy-and-publishing)
- [Limitations](#limitations)
- [FAQ](#faq)

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core` **and** `paramiko`
- SSH (TCP/22) reachability from the controller to every switch
- Password authentication (the switch login)

**Run**

```bash
cd vsf-inventory-csv-export
cp inventory.example.yml inventory.yml     # then edit inventory.yml for your switches
ansible-playbook -i inventory.yml play_vsf_info.yml --ask-pass
```

The report is written to `exports/vsf_export_<YYYYMMDD_HHMMSS>.csv`.
`inventory.yml` and everything under `exports/` are git-ignored.

**Inventory format** (`ansible_host` may be an IP or any resolvable name; see
[`inventory.example.yml`](inventory.example.yml)):

```yaml
all:
  hosts:
    switch01:
      ansible_host: 192.0.2.11
    switch02:
      ansible_host: switch02.example.net
  vars:
    ansible_user: admin
    ansible_password: CHANGEME        # override at runtime: --ask-pass, -e, or Ansible Vault
```

---

## Files

| File | Purpose |
|---|---|
| [`play_vsf_info.yml`](play_vsf_info.yml) | Ansible playbook – calls the helper once per host and writes the CSV. |
| [`vsf_ssh_inventory.py`](vsf_ssh_inventory.py) | Python helper – opens the SSH session, detects the platform, parses `show vsf …` / `show images` / `show flash`, and prints one JSON object. |
| [`inventory.example.yml`](inventory.example.yml) | Inventory template – copy to `inventory.yml` (git-ignored) and adjust. |
| `exports/` | Output folder for the generated CSV files (git-ignored except `.gitkeep`). |

---

## Example output

Sanitised sample (documentation ranges: [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)
addresses, [RFC 7042](https://www.rfc-editor.org/rfc/rfc7042#section-2.1.1) MACs):

```
VSF-Status;Label;Hostname;IP-Address;Platform;Member ID;Status;MAC Address;Type;Model;Serial Number;Uptime;Priority;VSF Link 1 - Port;VSF Link 1 - Status;VSF Link 2 - Port;VSF Link 2 - Status;Primary Image;Secondary Image;Active Boot Image
healthy;switch-core-1;switch-core;192.0.2.11;AOS-CX;1;Conductor;00:00:5e:00:53:01;JL725A;6200F 24G Class4 PoE 4SFP+ 370W Switch;SN-EXAMPLE-0001;54 minutes;primary;1/1/26;up;1/1/25;up;ML.10.13.1180;ML.10.13.1050;primary
healthy;switch-core-3;switch-core;192.0.2.11;AOS-CX;3;Standby;00:00:5e:00:53:02;JL725A;6200F 24G Class4 PoE 4SFP+ 370W Switch;SN-EXAMPLE-0002;42 minutes;secondary;3/1/25;up;3/1/26;up;ML.10.13.1180;ML.10.13.1050;primary
healthy;switch-access-1;switch-access;192.0.2.12;AOS-S;1;Commander;00:00:5e:00:53:03;JL255A;Aruba JL255A 2930F-24G-PoE+-4SFP+ Switch;SN-EXAMPLE-0003;0d 4h 31m;128;1/26;Up;N/A;N/A;WC.16.11.0024;WC.16.11.0024;Primary
healthy;switch-access-2;switch-access;192.0.2.12;AOS-S;2;Standby;00:00:5e:00:53:04;JL256A;Aruba JL256A 2930F-48G-PoE+-4SFP+ Switch;SN-EXAMPLE-0004;0d 2h 36m;128;2/49;Up;N/A;N/A;WC.16.11.0024;WC.16.11.0024;Primary
offline;switch-edge-N/A;switch-edge;192.0.2.13;unreachable;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A
```

The separator is `;` so the file opens cleanly in a German-locale Excel/LibreOffice.
Real reports contain your live serial numbers, MACs and topology – keep them out
of version control (see [Privacy and publishing](#privacy-and-publishing)).

---

## CSV columns

| Column | Meaning |
|---|---|
| `VSF-Status` | **First column** – overall stack verdict: `healthy` / `degraded` / `offline` (see [below](#vsf-status-values)). Plain text; CSV cannot carry colours, so tint it in Excel via conditional formatting (green / yellow / red). |
| `Label` | `<hostname>-<member_id>`, e.g. `switch-core-1` – a unique key per stack member. |
| `Hostname` | Name reported by the switch itself (falls back to the inventory host name). |
| `IP-Address` | Management IP. Even with a DNS-name inventory this is the resolved IP (SSH peer address, DNS lookup as fallback). |
| `Platform` | `AOS-CX`, `AOS-S`, or `unknown` / `unreachable` on failure. |
| `Member ID` | VSF member ID. |
| `Status` | e.g. `Conductor` / `Commander` (active), `Standby`, `Member`, or `Not Present`. |
| `MAC Address` | Normalised to `aa:bb:cc:dd:ee:ff` on both platforms (the AOS-S format `aabbcc-ddeeff` is converted). |
| `Type`, `Model`, `Serial Number`, `Uptime` | Device details from `show vsf detail`; `N/A` when absent (e.g. an unpopulated slot). |
| `Priority` | **AOS-S:** numeric VSF priority (e.g. `128`). **AOS-CX** (no numeric priority): the VSF role – `primary` for the Conductor, `secondary` for the member named in the `show vsf` stack header, otherwise `N/A`. |
| `VSF Link 1 - Port` / `- Status` | Physical port (e.g. `1/1/26` or `1/26`) and state (`up` / `down` / `error` …) of VSF link 1, from `show vsf link detail`. `N/A` on a non-stacked / unconfigured switch. |
| `VSF Link 2 - Port` / `- Status` | Same for VSF link 2. |
| `Primary Image` / `Secondary Image` | Software version in the primary / secondary flash (stack-wide, identical on every row of a stack). |
| `Active Boot Image` | Currently booted image (`primary` / `secondary`, or `Primary` / `Secondary` on AOS-S). |

> `rom_version` is still present in the helper's JSON output but is intentionally
> left out of the CSV.

---

## `VSF-Status` values

| Value | Suggested colour | Criteria |
|---|---|---|
| `healthy` | 🟩 green | All listed members are active **and** no VSF link is in a fault state. |
| `degraded` | 🟨 yellow | At least one member is active, but **not all** listed members are present (e.g. a `Not Present` slot) **or** at least one VSF link is in a fault state (`error`, loop, peer timeout, incompatibility). A plain `down` on an unused chain-end link does **not** count. |
| `offline` | 🟥 red | Switch unreachable, an error was reported, or no member is active. |

---

## How `vsf_ssh_inventory.py` works

1. Opens an **interactive** SSH shell (not a bare exec channel – AOS-S returns
   `SSH command execution is not supported`).
2. Sets a very large PTY height (`height=1000`) so the switches' `-- MORE --`
   pagination practically never triggers; as a fallback it is also detected and
   answered with a space.
3. Strips ANSI cursor-control sequences **before** searching for the CLI prompt –
   without this the prompt detection hangs, because Aruba switches emit
   cursor-positioning codes after the prompt.
4. Detects the platform from `show version` (`ArubaOS-CX` vs.
   `Image stamp` / `Boot ROM Version`) and reads the configured device name from
   `show system`. The IP column is filled from the SSH peer address / a DNS
   lookup.
5. Runs `show vsf detail` and parses it into a member list
   (`member_id`, `mac_address`, `type`, `model`, `status`, `serial_number`,
   `uptime`, `priority`). MAC addresses are normalised to `aa:bb:cc:dd:ee:ff`;
   on AOS-CX the VSF role (`primary` / `secondary`) is written into `priority`.
6. Adds the **physical port** and state of both VSF links per member from
   `show vsf link detail` – the same command yields a comparable `Port | State`
   table on AOS-CX (`1/1/26`) and AOS-S (`1/26`). Non-stacked switches → `N/A`.
7. Reads the software images with a platform-specific command: AOS-CX via
   `show images`, AOS-S via `show flash` (+ `Boot Image` from `show version`) →
   `primary_image`, `secondary_image`, `active_boot_image`.
8. Derives the overall stack state (`vsf_health`, see
   [above](#vsf-status-values)).
9. Always prints exactly **one JSON object** to stdout – even on connection
   errors – so the playbook can process the result regardless of success.

On a differing firmware output format, only the regexes in the corresponding
`parse_*` function need adjusting.

---

## Design notes

### Why SSH instead of the REST API?

The first implementation used the AOS-CX and AOS-S REST APIs. In practice it hit
several, partly platform-specific problems:

- **AOS-CX REST session limit** – every login consumes a session; without a
  clean logout the limit was reached quickly and further logins were rejected
  with `401 – session limit reached`.
- **No unified REST login** – AOS-CX (`POST /rest/v10.09/login`) and AOS-S
  (`POST /rest/v4/login-sessions`) use completely different login flows, cookie
  names and error codes, which made REST-based platform detection fragile.
- **AOS-S REST returned no stacking/VSF data** on the tested firmware – the
  obvious endpoint `/rest/v4/stacking/members` did not exist (`404`).
- **One switch was not reachable over HTTPS/443 at all** (TLS handshake
  timeout), although SSH worked on all switches.

Since SSH was confirmed to work everywhere and no specific API was required, the
tool switched to an **SSH/CLI-based** approach. The key finding when testing
against the real devices: **both platforms support the same command
`show vsf detail`** (Aruba extended the VSF terminology to ArubaOS-Switch). That
allows a single, unified parser instead of two separate REST implementations.

### Why a custom script instead of `ansible.netcommon`?

`ansible.netcommon.network_cli` already ships SSH-CLI modules for network
devices, but:

- The `network_os` (aoscx vs. arubaoss) must be known **up front** to pick the
  right terminal/cliconf plugin – exactly what is missing for "unknown" hosts.
- A detection attempt with the "wrong" `network_os` left the persistent
  `network_cli` connection in an inconsistent state, so the following attempt
  with the "right" `network_os` failed with `cli prompt is not identified`
  (verified with live tests).

A direct `paramiko` SSH connection (already a project dependency) avoids this
entirely: each host gets a fresh, independent connection in a single short-lived
Python process with no state shared between hosts.

---

## Privacy and publishing

This module is meant to be safe to publish as a standalone public repository.

- **The tool only reads.** It runs read-only `show` commands, changes nothing on
  the switch, keeps no state, and only prints the parsed result to stdout for the
  playbook. It does not phone home.
- **No secrets in the repo.** Commit `inventory.example.yml`, never
  `inventory.yml`. Supply the switch password at runtime (`--ask-pass`), via
  `-e ansible_password=…`, or from an Ansible Vault file – it is not stored.
  Task 1.1 runs with `no_log: true` so the password never reaches the Ansible log.
- **Generated reports are private.** Everything under `exports/` is git-ignored:
  a real CSV lists your live serial numbers, MAC addresses, firmware versions and
  stack topology. Share those files deliberately, not through git.
- **All examples use documentation ranges** – [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)
  IPs (`192.0.2.0/24`), [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)
  names (`example.net`), [RFC 7042](https://www.rfc-editor.org/rfc/rfc7042#section-2.1.1)
  MACs (`00:00:5e:00:53:xx`), placeholder serials. Aruba part numbers (`JL725A`)
  and firmware strings are public product information.
- **Splitting this out of a larger repo?** Start a fresh history
  (`git init` in a copy) or use `git filter-repo` – the surrounding repo's
  history may still contain real addresses or reports. Add a `LICENSE` before
  publishing.

---

## Limitations

- Unreachable hosts (e.g. SSH timeout) and switches without any VSF feature
  still produce **one** CSV row with `VSF-Status = offline` (the remaining
  columns are `N/A`), plus a debug message during the run.
- `vsf_health` only evaluates member presence and VSF link faults. A single,
  non-stacked switch counts as `healthy` even if a VSF link is `down` – only
  real fault states (`error` / loop / timeout / incompatibility) trigger
  `degraded`.
- Only password authentication is supported; SSH key auth is not implemented.

---

## FAQ

### Hostname known, IP unknown?

`ansible_host` need not be an IP – any address resolvable via DNS / `/etc/hosts`
works too (`switch02` in `inventory.example.yml`), because the script passes it
unchanged to `paramiko.SSHClient().connect()` and resolves the IP column
separately. If the switch name is not resolvable at all, an extra lookup step is
needed beforehand (e.g. DHCP leases, DNS, or an existing CMDB) to map the name
to an IP.
