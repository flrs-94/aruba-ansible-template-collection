# AOS-CX-TA-Zertifikatsverwaltung

**[English](README.md)** · Deutsch

Ein Ansible-Playbook, das CA-Zertifikate (Root / Intermediate) als
**Trust-Anchor-(TA-)Profile** per REST-API auf Aruba-**AOS-CX**-Switches
einspielt und erneuert. Die gewünschten Zertifikate stehen in
[`certs.yml`](certs.yml); das Playbook gleicht sie mit dem Switch ab, legt
fehlende Profile an, ersetzt abweichende nach Bestätigung und kann nicht mehr
gepflegte Profile entfernen.

---

## Inhalt

- [Was es tut](#was-es-tut)
- [Schnellstart](#schnellstart)
- [Dateien](#dateien)
- [Format von `certs.yml`](#format-von-certsyml)
- [Ablauf des Playbooks](#ablauf-des-playbooks)
- [Variablen](#variablen)
- [Bestätigungen und nicht-interaktive Läufe](#bestätigungen-und-nicht-interaktive-läufe)
- [Sicherheitshinweise](#sicherheitshinweise)
- [Einschränkungen](#einschränkungen)

---

## Was es tut

1. Meldet sich an der AOS-CX-REST-API an (`/rest/v10.04`).
2. Gleicht jedes TA-Profil aus `certs.yml`, das den aktuellen Host betrifft,
   mit dem Switch ab: `create` (fehlt), `identical` oder `update` (abweichend).
3. Legt fehlende Profile ohne Rückfrage an; überschreibt abweichende Profile
   nur nach Bestätigung (`yes` / `no`, deutsch auch `ja` / `j`).
4. Listet TA-Profile auf dem Switch, die **nicht** in `certs.yml` stehen
   (verwaist), und löscht sie nach einer separaten Bestätigung.
5. Meldet sich am Ende ab – auch wenn ein Task fehlgeschlagen ist (Ausnahme:
   Ablehnen der Überschreib-Abfrage, siehe [Einschränkungen](#einschränkungen)).

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core` (es werden nur `ansible.builtin`-Module
  genutzt – für dieses Playbook ist keine zusätzliche Collection nötig).
- HTTPS (TCP/443) vom Ansible-Controller zu jedem Switch; die REST-API muss auf
  dem Switch aktiviert sein.

**Inventory** – die gemeinsame [`../switch_hosts.yml`](../switch_hosts.yml)
weiterverwenden oder ein eigenes anlegen. Das Playbook benötigt nur
`ansible_host`, `ansible_user` und `ansible_password`:

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: example-user
    ansible_password: YOUR_PASSWORD     # besser Ansible Vault oder -e zur Laufzeit
```

**Zertifikate** – die Platzhalter in [`certs.yml`](certs.yml) durch die eigenen
CA-Zertifikate (PEM) ersetzen.

**Aufruf**

```bash
# aus diesem Ordner (aos-cx/certificates/)
ansible-playbook -i ../switch_hosts.yml play_ca.yml

# nicht-interaktiv (CI/CD) mit TLS-Prüfung des Switches
ansible-playbook -i ../switch_hosts.yml play_ca.yml \
  -e overwrite_certs=true -e validate_certs=true
```

---

## Dateien

| Datei | Zweck |
|---|---|
| [`play_ca.yml`](play_ca.yml) | Das Playbook – Login, Abgleich, Anlegen/Ersetzen, Bereinigung verwaister Profile, Logout. |
| [`certs.yml`](certs.yml) | Der Soll-Zustand: TA-Profile, ihre Zertifikate und Zielhosts. **Diese Datei wird gepflegt.** Die mitgelieferten Einträge sind Platzhalter. |
| [`certs.sample.json`](certs.sample.json) | Beispiel-Request-Body des AOS-CX-REST-Aufrufs `POST /rest/v10.04/system/pki_ta_profiles` (nur Referenz, wird vom Playbook nicht genutzt). |

---

## Format von `certs.yml`

Ein Listeneintrag je TA-Profil:

```yaml
ta_profiles:
  - name: "example_root_ca"
    target_hosts:
      - "aoscx_1"          # Inventory-Hostnamen oder "all"
    cert_data: |-
      -----BEGIN CERTIFICATE-----
      YOUR_ROOT_CA_CERTIFICATE_BASE64
      -----END CERTIFICATE-----
```

| Schlüssel | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `name` | string | ja | Name des TA-Profils auf dem Switch |
| `target_hosts` | Liste | ja | Inventory-Hostnamen oder `["all"]` für alle Hosts. Einträge ohne `target_hosts` werden ignoriert. |
| `cert_data` | string | ja | CA-Zertifikat im PEM-Format als Block-Skalar `\|-` – ohne zusätzliche führende Leerzeichen vor `-----BEGIN CERTIFICATE-----` |

---

## Ablauf des Playbooks

| # | Task | Methode / Modul |
|---|---|---|
| 1 | Login, Session-Cookie merken | `POST /login` |
| 2 | Jedes betroffene TA-Profil abfragen (200 = vorhanden, 404 = fehlt) | `GET /system/pki_ta_profiles/<name>` |
| 3–4 | Statusliste bilden: `create` / `identical` / `update` | `set_fact` |
| 5 | Status je Profil anzeigen | `debug` |
| 6–6c | Bestätigung bei `update`; bei „nein“ endet der Host ohne jede Änderung (auch fehlende Profile werden nicht angelegt) | `pause`, `meta: end_host` |
| 7a | Fehlende Profile anlegen | `POST /system/pki_ta_profiles` |
| 7b–7c | Abweichende Profile ersetzen (löschen, dann neu anlegen) | `DELETE` + `POST` |
| 8a–8g | Verwaiste Profile ermitteln und nach Bestätigung löschen | `GET`, `pause`, `DELETE` |
| 9 | Logout (`always`-Abschnitt) | `POST /logout` |

AOS-CX erlaubt das direkte Überschreiben eines TA-Zertifikats nicht zuverlässig,
daher wird ein abweichendes Profil gelöscht und neu angelegt (7b/7c). Alle
REST-Aufrufe laufen auf dem Ansible-Controller (`delegate_to: localhost`).

---

## Variablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `overwrite_certs` | `false` | `true` überspringt **alle** Bestätigungsabfragen (z. B. für CI/CD) – abweichende Profile werden überschrieben **und** verwaiste Profile gelöscht. |
| `validate_certs` | `false` | `true` prüft das TLS-Zertifikat des Switches bei jedem REST-Aufruf. |

---

## Bestätigungen und nicht-interaktive Läufe

- Abweichende Zertifikate (Task 6) und verwaiste Profile (Task 8e) erfordern
  jeweils ein explizites `yes` / `y` / `ja` / `j`. Jede andere Eingabe lässt den
  Switch unverändert.
- Mit `-e overwrite_certs=true` entfallen beide Abfragen und gelten als
  **bestätigt**. Sicherstellen, dass `certs.yml` *jedes* TA-Profil enthält, das
  auf einem Switch bleiben soll – jedes andere Profil dieses Switches wird als
  verwaist gelöscht.
- Zuerst einmal interaktiv laufen lassen und die Status-Zusammenfassung
  (Task 5) sowie die Liste verwaister Profile (Task 8d) prüfen.

---

## Sicherheitshinweise

- `certs.yml` darf nur **öffentliche** CA-Zertifikate enthalten – niemals einen
  privaten Schlüssel.
- Der AOS-CX-Login übergibt Benutzername und Passwort als URL-Parameter. Task 1
  läuft deshalb mit `no_log: true`, damit die Zugangsdaten nicht im Ansible-Log
  erscheinen (ein fehlgeschlagener Login wird dann ohne Details gemeldet).
- `validate_certs: false` deaktiviert die TLS-Prüfung gegenüber dem Switch.
  Produktiv auf `true` stellen und die CA des Switch-Zertifikats auf dem
  Controller hinterlegen.
- Niemals echte Zugangsdaten committen – Ansible Vault nutzen oder das Passwort
  zur Laufzeit übergeben.

---

## Einschränkungen

- Die REST-API-Version ist in den URLs fest auf `v10.04` gesetzt; bei Bedarf an
  die eigene Firmware anpassen.
- Die Zugangsdaten werden ohne URL-Kodierung in die Login-URL eingesetzt –
  Passwörter mit Zeichen wie `&`, `#` oder `+` können den Login stören.
- Profile werden nur anhand des Zertifikatstexts verglichen; weitere Attribute
  des TA-Profils werden nicht verwaltet.
- Wird die Überschreib-Abfrage (Task 6) abgelehnt, beendet `meta: end_host` das
  Play für diesen Host und überspringt den `always`-Abschnitt – die REST-Session
  wird dann nicht abgemeldet und läuft erst über den Session-Timeout des
  Switches ab.
