# AOS-CX Trust-Anchor (CA) Certificates

English · **[Deutsch](README_de.md)**

An Ansible playbook that manages **Trust-Anchor (TA) profiles** on one or more
Aruba **AOS-CX** switches over the REST API. A TA profile is a CA certificate the
switch is told to trust (for example so it accepts server certificates issued by
your internal PKI).

You describe the CA certificates you *want* in [`certs.yml`](certs.yml); the
playbook makes each switch match that list – create what is missing, replace what
differs (after confirmation), and optionally remove profiles that are no longer
listed.

The playbook is idempotent – a second run with an unchanged `certs.yml` reports
`IDENTICAL` for every profile and changes nothing.

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Files](#files)
- [`certs.yml` format](#certsyml-format)
- [How the playbook works](#how-the-playbook-works)
- [Variables](#variables)
- [Safety / destructive actions](#safety--destructive-actions)
- [Limitations](#limitations)

---

## What it does

Per switch:

1. Log in to the REST API (session cookie).
2. Read the current state of every TA profile named in `certs.yml`.
3. Decide an action per profile: `CREATE` (missing), `IDENTICAL` (unchanged) or
   `UPDATE` (present but the certificate differs).
4. Create the missing profiles.
5. For `UPDATE`: ask for confirmation, then delete + re-create the profile
   (AOS-CX cannot reliably overwrite a TA certificate in place).
6. Find *orphaned* profiles (on the switch but not in `certs.yml`), list them and
   – after a separate confirmation – delete them.
7. Log out – also after an error (exception: declining the overwrite prompt,
   see [Limitations](#limitations)).

---

## Quick start

**Requirements**

- Python virtualenv with `ansible-core`.
- HTTPS (TCP/443) reachability from the Ansible controller to each switch.
  All REST calls run on the controller (`delegate_to: localhost`).
- The CA certificate(s) you want to deploy, in PEM format.

**Inventory** – reuse the shared [`../switch_hosts.yml`](../switch_hosts.yml).
The host names in it are what you reference from `certs.yml` → `target_hosts`.

**Run**

```bash
# from this folder (aos-cx/certs/)
ansible-playbook -i ../switch_hosts.yml play_ca.yml

# non-interactive (CI): skip every confirmation prompt
ansible-playbook -i ../switch_hosts.yml play_ca.yml -e overwrite_certs=true

# verify the switch TLS certificate during the REST calls
ansible-playbook -i ../switch_hosts.yml play_ca.yml -e validate_certs=true
```

---

## Files

| File | Purpose |
|---|---|
| [`play_ca.yml`](play_ca.yml) | The playbook – 9 numbered steps: login, query, init, diff, summary, confirm, create/replace, orphan handling, logout. |
| [`certs.yml`](certs.yml) | The target state: the CA certificates and which switches should trust them. **This is the file you edit.** The shipped certificates are throw-away self-signed examples. |

---

## `certs.yml` format

```yaml
ta_profiles:
  - name: "example_root_ca"        # profile name on the switch (no spaces)
    target_hosts:                  # inventory host names, or ["all"]
      - "all"
    cert_data: |-                  # PEM, block scalar, no leading spaces
      -----BEGIN CERTIFICATE-----
      MIID...
      -----END CERTIFICATE-----
```

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | TA profile name on the switch. Used as the REST API path – keep it short, no spaces. |
| `target_hosts` | list | yes | Inventory host names this profile applies to, or `["all"]` for every host in the inventory. |
| `cert_data` | string (PEM) | yes | The CA certificate, as a `|-` block scalar. No indentation before `-----BEGIN CERTIFICATE-----`. |

---

## How the playbook works

| # | Step | HTTP |
|---|---|---|
| 1 | Log in to the REST API | `POST /login` |
| 2 | Query each profile from `certs.yml` | `GET /system/pki_ta_profiles/<name>` (200 / 404) |
| 3 | Initialise the status list | – |
| 4 | Diff: `create` / `identical` / `update` per profile | – |
| 5 | Print the status summary | – |
| 6 | Confirm overwrite of differing profiles (`update`) | – (`pause`, skipped by `overwrite_certs`) |
| 7a / 7b / 7c | Create new · delete differing · re-create differing | `POST` / `DELETE` / `POST` |
| 8a–8g | Collect managed names, list orphaned profiles, confirm, delete | `GET` / `DELETE` |
| 9 | Log out (`always`) | `POST /logout` |

Confirmation prompts accept `yes` / `y` and the German `ja` / `j` (case
insensitive); anything else aborts that host cleanly (`meta: end_host`) without
marking the run as failed. Declining the overwrite prompt (step 6) stops the host
before step 7a, so missing profiles are not created in that run either.

---

## Variables

| Variable | Default | Description |
|---|---|---|
| `overwrite_certs` | `false` | `true` skips **all** interactive confirmations (differing certificates *and* orphan deletion). Use for CI/CD. Evaluated with `\| bool`, so `-e overwrite_certs=true` works on ansible-core ≥ 2.19. |
| `validate_certs` | `false` | `true` verifies the switch's TLS certificate on every REST call. Set `true` in production and provide a trusted CA. |

```bash
ansible-playbook -i ../switch_hosts.yml play_ca.yml \
  -e overwrite_certs=true -e validate_certs=true
```

---

## Safety / destructive actions

Two operations can remove data from the switch and are each guarded by a
confirmation prompt (bypassed only by `overwrite_certs=true`):

- **Replacing a differing certificate** (step 7b/7c) – the old TA profile is
  deleted and re-created. Between the two calls the switch briefly does not trust
  that CA.
- **Deleting orphaned profiles** (step 8g) – any TA profile on the switch that is
  not in `certs.yml`. Review the list printed in step 8d before confirming.

Creating missing profiles (step 7a) is not destructive and runs without asking.

---

## Limitations

- Only TA profiles (`pki_ta_profiles`) are managed – no leaf/server certificates,
  no key material, no CRL configuration.
- The REST API path is pinned to `v10.04`. Older AOS-CX firmware may need a
  different version in the `rest_base` variable.
- `certs.yml` holds certificates only (public data). Never put private keys in
  this repo; if you templatise it further, keep secrets in Ansible Vault.
- The login passes user name and password as URL parameters (not URL-encoded –
  characters such as `&`, `#` or `+` in the password can break the login).
  Step 1 runs with `no_log: true`, so the credentials never appear in the log; a
  failed login is therefore reported without details.
- Declining the overwrite prompt ends the host via `meta: end_host`, which skips
  the `always` section – the REST session is then not logged out and only
  expires via the switch's session timeout.
