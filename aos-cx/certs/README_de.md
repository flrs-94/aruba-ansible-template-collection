# AOS-CX Trust-Anchor-(CA-)Zertifikate

**[English](README.md)** · Deutsch

Ein Ansible-Playbook, das **Trust-Anchor-(TA-)Profile** auf einem oder mehreren
Aruba-**AOS-CX**-Switches über die REST-API verwaltet. Ein TA-Profil ist ein
CA-Zertifikat, dem der Switch vertrauen soll (z. B. damit er Server-Zertifikate
akzeptiert, die von der internen PKI ausgestellt wurden).

Der gewünschte Zustand steht in [`certs.yml`](certs.yml); das Playbook gleicht
jeden Switch darauf ab – fehlende Profile anlegen, abweichende ersetzen (nach
Bestätigung) und optional nicht mehr gelistete Profile entfernen.

Das Playbook ist idempotent – ein zweiter Lauf mit unveränderter `certs.yml`
meldet für jedes Profil `IDENTICAL` und ändert nichts.

---

## Inhalt

- [Was es tut](#was-es-tut)
- [Schnellstart](#schnellstart)
- [Dateien](#dateien)
- [Format von `certs.yml`](#format-von-certsyml)
- [Ablauf des Playbooks](#ablauf-des-playbooks)
- [Variablen](#variablen)
- [Sicherheit / destruktive Aktionen](#sicherheit--destruktive-aktionen)
- [Einschränkungen](#einschränkungen)

---

## Was es tut

Pro Switch:

1. An der REST-API anmelden (Session-Cookie).
2. Ist-Zustand jedes in `certs.yml` genannten TA-Profils lesen.
3. Aktion je Profil festlegen: `CREATE` (fehlt), `IDENTICAL` (unverändert) oder
   `UPDATE` (vorhanden, aber Zertifikat weicht ab).
4. Fehlende Profile anlegen.
5. Bei `UPDATE`: Bestätigung einholen, dann Profil löschen + neu anlegen
   (AOS-CX kann ein TA-Zertifikat nicht zuverlässig direkt überschreiben).
6. *Verwaiste* Profile finden (auf dem Switch, aber nicht in `certs.yml`),
   auflisten und – nach separater Bestätigung – löschen.
7. Abmelden – auch nach einem Fehler (Ausnahme: Ablehnen der Überschreib-Abfrage,
   siehe [Einschränkungen](#einschränkungen)).

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core`.
- HTTPS (TCP/443) vom Ansible-Controller zu jedem Switch. Alle REST-Aufrufe
  laufen auf dem Controller (`delegate_to: localhost`).
- Das/die auszurollende(n) CA-Zertifikat(e) im PEM-Format.

**Inventory** – die gemeinsame [`../switch_hosts.yml`](../switch_hosts.yml)
weiterverwenden. Die dortigen Hostnamen referenzierst du in `certs.yml` unter
`target_hosts`.

**Aufruf**

```bash
# aus diesem Ordner (aos-cx/certs/)
ansible-playbook -i ../switch_hosts.yml play_ca.yml

# nicht-interaktiv (CI): alle Bestätigungsabfragen überspringen
ansible-playbook -i ../switch_hosts.yml play_ca.yml -e overwrite_certs=true

# TLS-Zertifikat des Switches bei den REST-Aufrufen prüfen
ansible-playbook -i ../switch_hosts.yml play_ca.yml -e validate_certs=true
```

---

## Dateien

| Datei | Zweck |
|---|---|
| [`play_ca.yml`](play_ca.yml) | Das Playbook – 9 nummerierte Schritte: Login, Abfrage, Init, Abgleich, Zusammenfassung, Bestätigung, Anlegen/Ersetzen, Umgang mit verwaisten Profilen, Logout. |
| [`certs.yml`](certs.yml) | Der Soll-Zustand: die CA-Zertifikate und welche Switches ihnen vertrauen sollen. **Das ist die Datei, die du pflegst.** Die mitgelieferten Zertifikate sind Wegwerf-Selbstsignate. |

---

## Format von `certs.yml`

```yaml
ta_profiles:
  - name: "example_root_ca"        # Profilname auf dem Switch (keine Leerzeichen)
    target_hosts:                  # Inventory-Hostnamen, oder ["all"]
      - "all"
    cert_data: |-                  # PEM, Block-Skalar, keine führenden Leerzeichen
      -----BEGIN CERTIFICATE-----
      MIID...
      -----END CERTIFICATE-----
```

| Schlüssel | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `name` | string | ja | Name des TA-Profils auf dem Switch. Wird als REST-API-Pfad genutzt – kurz, keine Leerzeichen. |
| `target_hosts` | list | ja | Inventory-Hostnamen, für die das Profil gilt, oder `["all"]` für jeden Host im Inventory. |
| `cert_data` | string (PEM) | ja | Das CA-Zertifikat als `|-`-Block-Skalar. Keine Einrückung vor `-----BEGIN CERTIFICATE-----`. |

---

## Ablauf des Playbooks

| # | Schritt | HTTP |
|---|---|---|
| 1 | An der REST-API anmelden | `POST /login` |
| 2 | Jedes Profil aus `certs.yml` abfragen | `GET /system/pki_ta_profiles/<name>` (200 / 404) |
| 3 | Statusliste initialisieren | – |
| 4 | Abgleich: `create` / `identical` / `update` je Profil | – |
| 5 | Status-Zusammenfassung ausgeben | – |
| 6 | Überschreiben abweichender Profile bestätigen (`update`) | – (`pause`, via `overwrite_certs` übersprungen) |
| 7a / 7b / 7c | Neue anlegen · abweichende löschen · abweichende neu anlegen | `POST` / `DELETE` / `POST` |
| 8a–8g | Verwaltete Namen sammeln, verwaiste Profile auflisten, bestätigen, löschen | `GET` / `DELETE` |
| 9 | Abmelden (`always`) | `POST /logout` |

Die Bestätigungsabfragen akzeptieren `yes` / `y` und deutsch `ja` / `j`
(Groß-/Kleinschreibung egal); alles andere bricht diesen Host sauber ab
(`meta: end_host`), ohne den Lauf als fehlgeschlagen zu markieren. Wird die
Überschreib-Abfrage (Schritt 6) abgelehnt, endet der Host vor Schritt 7a – in
diesem Lauf werden also auch fehlende Profile nicht angelegt.

---

## Variablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `overwrite_certs` | `false` | `true` überspringt **alle** interaktiven Bestätigungen (abweichende Zertifikate *und* Löschen verwaister Profile). Für CI/CD. Wird mit `\| bool` ausgewertet, damit `-e overwrite_certs=true` auch unter ansible-core ≥ 2.19 funktioniert. |
| `validate_certs` | `false` | `true` prüft bei jedem REST-Aufruf das TLS-Zertifikat des Switches. In produktiven Umgebungen auf `true` und eine vertrauenswürdige CA hinterlegen. |

```bash
ansible-playbook -i ../switch_hosts.yml play_ca.yml \
  -e overwrite_certs=true -e validate_certs=true
```

---

## Sicherheit / destruktive Aktionen

Zwei Operationen können Daten vom Switch entfernen und sind je durch eine
Bestätigungsabfrage abgesichert (nur mit `overwrite_certs=true` übergangen):

- **Ersetzen eines abweichenden Zertifikats** (Schritt 7b/7c) – das alte
  TA-Profil wird gelöscht und neu angelegt. Zwischen den beiden Aufrufen
  vertraut der Switch dieser CA kurzzeitig nicht.
- **Löschen verwaister Profile** (Schritt 8g) – jedes TA-Profil auf dem Switch,
  das nicht in `certs.yml` steht. Die in Schritt 8d ausgegebene Liste vor der
  Bestätigung prüfen.

Das Anlegen fehlender Profile (Schritt 7a) ist nicht destruktiv und läuft ohne
Nachfrage.

---

## Einschränkungen

- Verwaltet werden nur TA-Profile (`pki_ta_profiles`) – keine
  Leaf-/Server-Zertifikate, kein Schlüsselmaterial, keine CRL-Konfiguration.
- Der REST-API-Pfad ist auf `v10.04` festgelegt. Ältere AOS-CX-Firmware braucht
  ggf. eine andere Version in der Variable `rest_base`.
- `certs.yml` enthält nur Zertifikate (öffentliche Daten). Niemals private
  Schlüssel in dieses Repo legen; bei weiterer Templatisierung Secrets in
  Ansible Vault halten.
- Der Login übergibt Benutzername und Passwort als URL-Parameter (ohne
  URL-Kodierung – Zeichen wie `&`, `#` oder `+` im Passwort können den Login
  stören). Schritt 1 läuft mit `no_log: true`, die Zugangsdaten erscheinen also
  nie im Log; ein fehlgeschlagener Login wird daher ohne Details gemeldet.
- Das Ablehnen der Überschreib-Abfrage beendet den Host per `meta: end_host`,
  was den `always`-Abschnitt überspringt – die REST-Session wird dann nicht
  abgemeldet und läuft erst über den Session-Timeout des Switches ab.
