# AOS-CX AAA- / Port-Access-Audit → CSV-Export

**[English](README.md)** · Deutsch

Ein Ansible-Playbook, das ermittelt, **auf welchen physischen Ports** eines oder
mehrerer Aruba-**AOS-CX**-Switches eine **AAA-/Port-Access-Authentifizierung**
(802.1X / `dot1x`, `mac-auth`) konfiguriert ist – und auf welchen nicht – plus
die RADIUS-Server-Group je Methode. Es schreibt einen einzelnen **CSV**-Bericht,
eine Zeile je physischem Port.

Die Abfrage läuft **ausschließlich über REST**: ein einziges
`GET /system/interfaces?depth=4&attributes=…` je Switch liefert jedes Interface
samt seiner Port-Access-Konfiguration. Die Anzahl der Ports oder VSF-Stack-Member
muss also **vorab nicht bekannt** sein – das Playbook iteriert über das, was der
Switch zurückgibt.

Das Playbook ist **rein lesend** – es meldet sich an, führt einen `GET` und ein
`POST /logout` aus und ändert nie etwas am Switch.

---

## Inhalt

- [Was es tut](#was-es-tut)
- [Schnellstart](#schnellstart)
- [Dateien](#dateien)
- [CSV-Spalten](#csv-spalten)
- [`AAA Port-Access`-Werte](#aaa-port-access-werte)
- [Ablauf des Playbooks](#ablauf-des-playbooks)
- [Variablen](#variablen)
- [Wie die Erkennung funktioniert / an die eigene Firmware anpassen](#wie-die-erkennung-funktioniert--an-die-eigene-firmware-anpassen)
- [Datenschutz und Veröffentlichung](#datenschutz-und-veröffentlichung)
- [Einschränkungen](#einschränkungen)

---

## Was es tut

Pro Switch:

1. An der REST-API anmelden (Session-Cookie).
2. `GET /system/interfaces?depth=4&attributes=…` – jedes Interface mit seinen
   Unterobjekten `port_access_auth_configurations` und `port_security`.
3. Optional dieses Roh-JSON neben die CSV schreiben (`dump_raw=true`).
4. Für jeden **physischen** Port (Name wie `1/1/24`): `OTHER`, wenn kein
   `access`-Port, sonst `YES`, wenn `port_access_auth_configurations` einen
   `dot1x`- / `mac-auth`-Schlüssel hat, sonst `NO`. Dazu je Methode die
   zugeordnete Server-Group.
5. Hinweis je Host ausgeben (wie viele Ports ohne AAA).
6. Abmelden (immer, auch bei Fehler).

Danach, einmalig auf `localhost`: die Zeilen aller Hosts zusammenführen und
`exports/aaa_port_access_<JJJJMMTT_hhmmss>.csv` schreiben, gefolgt von einer
Zusammenfassungszeile je Host / Stack und einer Gesamtsumme.

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core`.
- HTTPS (TCP/443) vom Ansible-Controller zu jedem Switch. Alle REST-Aufrufe
  laufen auf dem Controller (`delegate_to: localhost`).
- Ein Switch-Login mit Leserecht auf `/system/interfaces`.

**Inventory** – die lokale [`demohost.yml`](demohost.yml) oder die gemeinsame
[`../switch_hosts.yml`](../switch_hosts.yml) verwenden:

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: example-user
    ansible_password: YOUR_PASSWORD     # besser Ansible Vault oder -e zur Laufzeit
```

> Das Playbook braucht nur `ansible_host`, `ansible_user`, `ansible_password`.
> `ansible_connection` / `ansible_network_os` sind nicht nötig (es wird kein
> Collection-Modul genutzt, nur `ansible.builtin.uri`).

**Aufruf**

```bash
# aus diesem Ordner (aos-cx/aaa/)
ansible-playbook -i demohost.yml play_aaa.yml

# Erkennung gegen die eigene Firmware prüfen: Roh-Interfaces-JSON mitschreiben
ansible-playbook -i demohost.yml play_aaa.yml -e dump_raw=true

# ältere Firmware ohne v10.13-Schema (Server-Group-Spalten bleiben leer)
ansible-playbook -i demohost.yml play_aaa.yml -e rest_version=v10.09

# strengeres TLS
ansible-playbook -i demohost.yml play_aaa.yml -e validate_certs=true
```

Der Bericht landet in `exports/aaa_port_access_<JJJJMMTT_hhmmss>.csv`. Alles
unter `exports/` ist per `.gitignore` ausgenommen (bis auf `.gitkeep`).

---

## Dateien

| Datei | Zweck |
|---|---|
| [`play_aaa.yml`](play_aaa.yml) | Das Playbook – Play 1 (je Switch): Login, Ports lesen, optionaler Rohdump, Zeilen bauen, Logout. Play 2 (`localhost`): zusammenführen + CSV schreiben + Zusammenfassung je Host. |
| [`demohost.yml`](demohost.yml) | Beispiel-Inventory für einen einzelnen Switch. `-i` hierauf oder auf `../switch_hosts.yml` zeigen lassen. |
| `exports/` | Zielordner für die erzeugte CSV (und den optionalen Roh-JSON-Dump). Per `.gitignore` ausgenommen, bis auf `.gitkeep`. |

---

## CSV-Spalten

Trennzeichen ist `;`, damit die Datei im deutschen Gebietsschema sauber öffnet.
In Freitextfeldern (`VLAN Mode`, `Description`, `Indicator Keys`) wird jedes `;`
durch `,` ersetzt.

| Spalte | Bedeutung |
|---|---|
| `AAA Port-Access` | **Erste Spalte** – `YES` / `NO` / `OTHER` / `ERROR` je Port (siehe [unten](#aaa-port-access-werte)). `OTHER` = Port ist nicht im `access`-Modus. Reiner Text; in Excel/LibreOffice per bedingter Formatierung einfärben. |
| `Label` | `<hostname>-<port>`, z. B. `switch-access-1-1/1/24` – eindeutiger Schlüssel je Port. |
| `Hostname` | Inventory-Hostname. |
| `IP-Address` | Management-IP / DNS-Name aus `ansible_host`. |
| `Stack Member` | Erstes Segment des Portnamens (`1` bei `1/1/24`) = VSF-Member / Chassis. `N/A` in einer Fehlerzeile. |
| `Port` | Portname wie vom Switch gemeldet (`member/slot/port`). |
| `Admin` | Konfigurierter Admin-Zustand des Ports (`up` / `down`; `up`, wenn der Switch das Attribut weglässt). |
| `VLAN Mode` | `access` / `native-untagged` / … falls gesetzt, sonst leer. Nur Kontext. |
| `Description` | Port-Beschreibung, falls gesetzt. Nur Kontext. |
| `Detected Methods` | Die konfigurierten Port-Access-Auth-Methoden: die Schlüssel von `port_access_auth_configurations` (`dot1x`, `mac-auth`); `-` falls keine. `port_security` steht hier **nicht**. |
| `dot1x Server Group` | Die dem `dot1x`-Verfahren auf diesem Port zugeordnete Server-Group (`server_group_attr` im Methoden-Objekt); leer (`-`), wenn keine / kein `dot1x`-Port. |
| `mac-auth Server Group` | Dasselbe für das `mac-auth`-Verfahren. |
| `Indicator Keys` | Der Rohnachweis: `auth_cfg=[…] port_security.enable=… pac_type=dict|uri`. `port_security.enable` steht nur zur Info und beeinflusst die erste Spalte **nicht**. `pac_type=uri` heißt, die Abfrage-`depth` war zu niedrig – `ports_depth` erhöhen. In einer `ERROR`-Zeile steht hier die Fehlermeldung. |

---

## `AAA Port-Access`-Werte

| Wert | Farbvorschlag | Kriterien |
|---|---|---|
| `YES` | 🟩 grün | Access-Port **und** `port_access_auth_configurations` hat ≥ 1 Methoden-Schlüssel (`dot1x` / `mac-auth`). |
| `NO` | 🟥 rot | Access-Port **und** `port_access_auth_configurations` ist `{}`. `port_security.enable = true` macht daraus **kein** `YES`. |
| `OTHER` | ⬜ grau | Der effektive VLAN-Modus ist **nicht** `access` (Trunk / native-untagged / nicht gesetzter Uplink). Port-Access-Auth wird hier nicht erwartet, der Port zählt daher nicht als „fehlende AAA". Wird vor YES/NO geprüft. |
| `ERROR` | ⬜ grau | Der Switch war nicht erreichbar oder ein REST-Aufruf schlug fehl. Eine Zeile je fehlgeschlagenem Host; die Meldung steht in `Indicator Keys`. |

---

## Ablauf des Playbooks

| # | Schritt | HTTP |
|---|---|---|
| 1 | An der REST-API anmelden | `POST /login` |
| 2 | Alle Interfaces + Port-Access-Konfig lesen | `GET /system/interfaces?depth=4&attributes=…` |
| 3 | Roh-JSON der Interfaces schreiben (`when: dump_raw`) | – |
| 4 | Eine Audit-Zeile je physischem Port bauen | – |
| 5 | Hinweis je Host: Ports ohne AAA | – |
| 4r / 5r | *(rescue)* eine `ERROR`-Zeile + Hinweis erzeugen | – |
| 6 | Abmelden (`always`) | `POST /logout` |
| 7–9 | *(localhost)* Zeitstempel, Zeilen sammeln, CSV schreiben | – |
| 10 / 11 | *(localhost)* Zusammenfassung je Host / Stack, dann Gesamtsumme | – |

Play 1 kapselt die Schritte 1–6 in `block` / `rescue` / `always`: ein
fehlgeschlagener Switch erzeugt trotzdem genau eine CSV-Zeile (`ERROR`), und die
API-Session wird immer geschlossen – AOS-CX hat ein hartes Session-Limit, eine
verwaiste Session blockiert spätere Logins.

---

## Variablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `rest_version` | `v10.13` | REST-API-Schemaversion im URL-Pfad. `v10.13` ist Standard, weil das Feld `radius_server_group` je Methode (die zwei `Server Group`-Spalten) erst ab diesem Schema existiert. Ein Switch liefert nur Schemata bis zu seiner Firmware – liefert Login/Abfrage 404, absenken (`-e rest_version=v10.09`); die `Server Group`-Spalten bleiben dann leer. |
| `rest_port` | `443` | TCP-Port der Switch-REST-API. Nur überschreiben (pro Host oder `-e rest_port=8443`), falls REST woanders liegt. |
| `port_resource` | `interfaces` | REST-Ressource mit den physischen Ports. `interfaces` auf AOS-CX ≳ 10.09 (auf 10.09 verifiziert); bei sehr alter Firmware `-e port_resource=ports`, falls die Abfrage 404 liefert. |
| `validate_certs` | `false` | `true` prüft bei jedem REST-Aufruf das TLS-Zertifikat des Switches. In Produktion auf `true` mit vertrauenswürdiger CA. |
| `ports_depth` | `4` | `depth` der Collection-Abfrage. Bei einem Collection-GET ist `3` das Minimum, das `port_access_auth_configurations` vom URI-Stub zu einem Schlüssel-Dict aufklappt (`4` fügt zusätzlich die Unterkonfig je Methode inline ein). Zeigt die Spalte `Indicator Keys` `pac_type=uri`, erhöhen. |
| `interface_attributes` | `name,admin,vlan_mode,applied_vlan_mode,description,port_access_auth_configurations,port_security` | Attribut-Filter der Abfrage (kleinere Antwort + Dump). `-e interface_attributes=''` holt die vollen Objekte, falls eine Firmware den Filter ablehnt (HTTP 400). |
| `server_group_attr` | `radius_server_group` | Attribut, das aus jedem `port_access_auth_configurations.<methode>`-Objekt für die Spalten `<Methode> Server Group` gelesen wird. Laut AOS-CX-API-Referenz existiert dieses Feld ab Schema `v10.13`; leer bei einer konfigurierten Methode = „erbt die System-RADIUS-Server-Group". |
| `port_filter_regex` | `^\d+/\d+/\d+$` | Nur Ports, deren Name passt, werden geprüft. Standard behält physische Ports, verwirft LAGs, VLAN-/Loopback-Interfaces und Sub-Interfaces. |
| `dump_raw` | `false` | `true` schreibt zusätzlich `exports/aaa_port_access_raw_<host>.json` – die rohe Interfaces-Antwort, zum Prüfen der Schlüsselpfade gegen die eigene Firmware. |

```bash
ansible-playbook -i demohost.yml play_aaa.yml \
  -e rest_version=v10.09 -e validate_certs=true -e dump_raw=true
```

---

## Wie die Erkennung funktioniert / an die eigene Firmware anpassen

Pro physischem Interface liest das Playbook (Top-Level-Attribute auf AOS-CX 10.09
verifiziert; `radius_server_group` laut v10.13-API-Referenz):

| Attribut | Bedeutung |
|---|---|
| `vlan_mode` / `applied_vlan_mode` | Der VLAN-Modus des Ports. Ist der effektive Wert nicht `access`, wird der Port als `OTHER` gemeldet und die folgende Prüfung entfällt. |
| `port_access_auth_configurations` | Ein Dict mit Schlüssel je konfigurierter Port-Access-Auth-Methode – `dot1x`, `mac-auth`. `{}` = keine. Jeder Wert ist das Konfig-Objekt der Methode; dessen `radius_server_group` (ab Schema `v10.13`) füllt die Spalte `<Methode> Server Group`. |
| `port_security.enable` | Bool, MAC-**Port-Security** – steht **nur** zur Info in `Indicator Keys`. Beeinflusst die erste Spalte *nicht* (ein Port mit nur Port-Security ist `NO`). |

Bei einem `access`-Port ist `AAA Port-Access = YES`, wenn
`port_access_auth_configurations` einen `dot1x`- oder `mac-auth`-Schlüssel hat,
sonst `NO`. `Detected Methods` listet die Schlüssel; `Indicator Keys` hält die
Rohwerte fest, sodass die Entscheidung nachvollziehbar ist.

> Ein vorhandener Methoden-Schlüssel bei *deaktiviertem* Authenticator zählt hier
> trotzdem als `YES` – das Audit beantwortet *konfiguriert vs. nicht*,
> entsprechend dem Vorhandensein der CLI-Strophe `aaa authentication
> port-access …`.

**Zum Prüfen gegen die eigenen Switches:** einmal mit `-e dump_raw=true` laufen
lassen, `exports/aaa_port_access_raw_<host>.json` öffnen und einen Port, von dem
man *weiß*, dass er 802.1X hat, mit einem ohne vergleichen. Exponiert die eigene
Firmware den Zustand (oder die Server-Group) unter anderen Schlüsseln,
`auth_methods` / `server_group_attr` in **Task 4** des Playbooks anpassen.

---

## Datenschutz und Veröffentlichung

- **Das Playbook liest nur.** Ein `GET` und ein `POST /logout`; es schreibt nie
  auf den Switch und hält keinen Zustand.
- **Keine Geheimnisse im Repo.** `demohost.yml` nur mit Platzhalter-Passwort
  committen; das echte zur Laufzeit übergeben (`-e ansible_password=…`,
  `--ask-vault-pass`, Ansible Vault). Task 1 läuft mit `no_log: true`.
- **Erzeugte Berichte sind privat.** Alles unter `exports/` ist per `.gitignore`
  ausgenommen: eine echte CSV listet Port-Beschreibungen und Topologie; ein
  Rohdump enthält die vollständige Port-Konfiguration. Solche Dateien bewusst
  teilen, nicht über git.
- **Alle Beispiele nutzen Dokumentationsbereiche** – [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)-
  IPs (`192.0.2.0/24`), [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)-Namen.

---

## Einschränkungen

- **Erkennungsschlüssel auf AOS-CX 10.09 verifiziert; Server-Group laut
  v10.13-API-Referenz.** Andere Releases können abweichen – den ersten Lauf gegen
  einen bekannt-guten Port validieren und bei Bedarf `auth_methods` /
  `server_group_attr` in Task 4 anpassen (siehe
  [Anpassen](#wie-die-erkennung-funktioniert--an-die-eigene-firmware-anpassen)).
- **Die zwei `Server Group`-Spalten brauchen Schema `v10.13`.** Im 10.09-Sample
  fehlt das Feld `radius_server_group`, die Spalten bleiben leer. Gegen eine
  Firmware laufen, die `v10.13` liefert (Default `rest_version`); ein leerer Wert
  bei einer konfigurierten Methode heißt dann, sie erbt die
  System-RADIUS-Server-Group.
- Meldet die **Präsenz der Port-Konfiguration**, nicht den Laufzeitzustand – es
  sagt nicht, ob sich ein Client tatsächlich authentifiziert hat, und auch
  nicht, ob global `aaa authentication port-access` / RADIUS-Server eingerichtet
  sind. Ein konfigurierter, aber *deaktivierter* Authenticator erscheint als `YES`.
- Nur physische Ports (`port_filter_regex`); Port-Access auf LAG-Ebene wird nicht
  geprüft.
- Eine REST-Session je Switch – die Hosts werden mit Ansibles normaler
  Fork-Parallelität abgearbeitet; jeder `always`-Block schließt seine eigene
  Session.
- `rest_version` / `port_resource` sind einzelne feste Werte; sehr alte Firmware
  braucht `rest_version` ggf. niedriger oder `port_resource=ports`.
