# AOS-CX TA Certificate Management

English · **[Deutsch](README_de.md)**

An Ansible playbook that deploys and renews CA certificates (root /
intermediate) as **Trust Anchor (TA) profiles** on Aruba **AOS-CX** switches via
the REST API. You describe the certificates you *want* in
[`certs.yml`](certs.yml); the playbook compares them with the switch, creates
missing profiles, replaces differing ones after confirmation and can remove
profiles that are no longer maintained.

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Files](#files)
- [`certs.yml` format](#certsyml-format)
- [How the playbook works](#how-the-playbook-works)
- [Variables](#variables)
- [Confirmations and non-interactive runs](#confirmations-and-non-interactive-runs)
- [Security notes](#security-notes)
- [Limitations](#limitations)

---

## What it does

1. Logs in to the AOS-CX REST API (`/rest/v10.04`).
2. Compares every TA profile from `certs.yml` that targets the current host
   with the switch: `create` (missing), `identical` or `update` (different).
3. Creates missing profiles without asking; overwrites differing profiles only
   after confirmation (`yes` / `no`, German `ja` / `j` is accepted as well).
4. Lists TA profiles on the switch that are **not** in `certs.yml` (orphans)
   and deletes them after a separate confirmation.
5. Logs out at the end – even if a task failed (exception: declining the
   overwrite prompt, see [Limitations](#limitations)).

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core` (only `ansible.builtin` modules are
  used – no extra collection needed for this playbook).
- HTTPS (TCP/443) reachability from the Ansible controller to each switch; the
  REST API must be enabled on the switch.

**Inventory** – reuse the shared [`../switch_hosts.yml`](../switch_hosts.yml) or
write your own. The playbook only needs `ansible_host`, `ansible_user` and
`ansible_password`:

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: example-user
    ansible_password: YOUR_PASSWORD     # prefer Ansible Vault or -e at runtime
```

**Certificates** – replace the placeholders in [`certs.yml`](certs.yml) with
your own CA certificates (PEM).

**Run**

```bash
# from this folder (aos-cx/certificates/)
ansible-playbook -i ../switch_hosts.yml play_ca.yml

# non-interactive (CI/CD) with TLS verification of the switch
ansible-playbook -i ../switch_hosts.yml play_ca.yml \
  -e overwrite_certs=true -e validate_certs=true
```

---

## Files

| File | Purpose |
|---|---|
| [`play_ca.yml`](play_ca.yml) | The playbook – login, compare, create/replace, orphan cleanup, logout. |
| [`certs.yml`](certs.yml) | The target state: TA profiles, their certificates and target hosts. **This is the file you edit.** The shipped entries are placeholders. |
| [`certs.sample.json`](certs.sample.json) | Example request body of the AOS-CX REST call `POST /rest/v10.04/system/pki_ta_profiles` (reference only, not used by the playbook). |

---

## `certs.yml` format

One list entry per TA profile:

```yaml
ta_profiles:
  - name: "example_root_ca"
    target_hosts:
      - "aoscx_1"          # inventory host names, or "all"
    cert_data: |-
      -----BEGIN CERTIFICATE-----
      YOUR_ROOT_CA_CERTIFICATE_BASE64
      -----END CERTIFICATE-----
```

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | TA profile name on the switch |
| `target_hosts` | list | yes | inventory host names, or `["all"]` for every host. Entries without `target_hosts` are ignored. |
| `cert_data` | string | yes | CA certificate in PEM format as a block scalar `\|-` – no extra leading whitespace before `-----BEGIN CERTIFICATE-----` |

---

## How the playbook works

| # | Task | Method / module |
|---|---|---|
| 1 | Log in, keep the session cookie | `POST /login` |
| 2 | Query each targeted TA profile (200 = found, 404 = missing) | `GET /system/pki_ta_profiles/<name>` |
| 3–4 | Build the status list: `create` / `identical` / `update` | `set_fact` |
| 5 | Show the status per profile | `debug` |
| 6–6c | Confirmation for `update`; on "no" the host ends without any change (missing profiles are not created either) | `pause`, `meta: end_host` |
| 7a | Create missing profiles | `POST /system/pki_ta_profiles` |
| 7b–7c | Replace differing profiles (delete, then re-create) | `DELETE` + `POST` |
| 8a–8g | Detect orphaned profiles and delete them after confirmation | `GET`, `pause`, `DELETE` |
| 9 | Log out (`always` section) | `POST /logout` |

AOS-CX does not reliably allow overwriting a TA certificate in place, so a
differing profile is deleted and re-created (7b/7c). All REST calls run on the
Ansible controller (`delegate_to: localhost`).

---

## Variables

| Variable | Default | Description |
|---|---|---|
| `overwrite_certs` | `false` | `true` skips **all** confirmation prompts (e.g. for CI/CD) – differing profiles are overwritten **and** orphaned profiles are deleted. |
| `validate_certs` | `false` | `true` verifies the switch's TLS certificate for every REST call. |

---

## Confirmations and non-interactive runs

- Differing certificates (task 6) and orphaned profiles (task 8e) each need an
  explicit `yes` / `y` / `ja` / `j`. Anything else leaves the switch unchanged.
- With `-e overwrite_certs=true` both prompts are skipped and treated as
  **confirmed**. Make sure `certs.yml` lists *every* TA profile a switch should
  keep – any other profile on that switch is deleted as an orphan.
- Run once interactively first to review the status summary (task 5) and the
  orphan list (task 8d).

---

## Security notes

- `certs.yml` must only contain **public** CA certificates – never a private
  key.
- The AOS-CX login passes user name and password as URL parameters. Task 1
  therefore runs with `no_log: true`, so the credentials do not appear in the
  Ansible log (a failed login is then reported without details).
- `validate_certs: false` disables TLS verification towards the switch. In
  production set it to `true` and trust the switch certificate's CA on the
  controller.
- Never commit real credentials – use Ansible Vault or pass the password at
  runtime.

---

## Limitations

- The REST API version is fixed to `v10.04` in the URLs; adjust it if your
  firmware requires a different version.
- Credentials are inserted into the login URL without URL encoding – passwords
  containing characters such as `&`, `#` or `+` may break the login.
- Profiles are compared by their certificate text only; other TA profile
  attributes are not managed.
- If you decline the overwrite prompt (task 6), `meta: end_host` ends the play
  for that host and skips the `always` section – the REST session is then not
  logged out and only expires via the switch's session timeout.
