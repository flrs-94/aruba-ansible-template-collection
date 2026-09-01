# VSF-Inventur → CSV-Export

**[English](README.md)** · Deutsch

Ein Ansible-Playbook plus ein kleines Python-Hilfsskript, die sich per **SSH** mit
Aruba-Switches verbinden (AOS-CX **und** AOS-S), deren **VSF-/Stacking**-Zustand
auslesen und einen kombinierten **CSV**-Bericht schreiben – eine Zeile je
Stack-Member, plus ein Stack-Gesamturteil in der ersten Spalte.

Die Plattform (AOS-CX vs. AOS-S) wird automatisch erkannt; das Inventory braucht
daher je Switch nur eine Adresse und Zugangsdaten.

---

## Inhalt

- [Schnellstart](#schnellstart)
- [Dateien](#dateien)
- [Beispielausgabe](#beispielausgabe)
- [CSV-Spalten](#csv-spalten)
- [`VSF-Status`-Werte](#vsf-status-werte)
- [Funktionsweise von `vsf_ssh_inventory.py`](#funktionsweise-von-vsf_ssh_inventorypy)
- [Designentscheidungen](#designentscheidungen)
- [Datenschutz und Veröffentlichung](#datenschutz-und-veröffentlichung)
- [Bekannte Grenzen](#bekannte-grenzen)
- [FAQ](#faq)

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core` **und** `paramiko`
- SSH-Erreichbarkeit (TCP/22) vom Controller zu jedem Switch
- Passwort-Authentifizierung (der Switch-Login)

**Ausführen**

```bash
cd vsf-inventory-csv-export
cp inventory.example.yml inventory.yml     # danach inventory.yml an die eigenen Switches anpassen
ansible-playbook -i inventory.yml play_vsf_info.yml --ask-pass
```

Der Bericht landet unter `exports/vsf_export_<JJJJMMTT_hhmmss>.csv`.
`inventory.yml` und alles unter `exports/` sind per `.gitignore` ausgenommen.

**Inventory-Format** (`ansible_host` darf eine IP oder ein auflösbarer Name sein;
siehe [`inventory.example.yml`](inventory.example.yml)):

```yaml
all:
  hosts:
    switch01:
      ansible_host: 192.0.2.11
    switch02:
      ansible_host: switch02.example.net
  vars:
    ansible_user: admin
    ansible_password: CHANGEME        # zur Laufzeit setzen: --ask-pass, -e oder Ansible Vault
```

---

## Dateien

| Datei | Zweck |
|---|---|
| [`play_vsf_info.yml`](play_vsf_info.yml) | Ansible-Playbook – ruft pro Host das Hilfsskript auf und schreibt die CSV. |
| [`vsf_ssh_inventory.py`](vsf_ssh_inventory.py) | Python-Hilfsskript – baut die SSH-Sitzung auf, erkennt die Plattform, parst `show vsf …` / `show images` / `show flash` und gibt ein JSON-Objekt aus. |
| [`inventory.example.yml`](inventory.example.yml) | Inventory-Vorlage – nach `inventory.yml` kopieren (per `.gitignore` ausgenommen) und anpassen. |
| `exports/` | Zielordner für die erzeugten CSV-Dateien (per `.gitignore` ausgenommen, bis auf `.gitkeep`). |

---

## Beispielausgabe

Bereinigtes Beispiel (Dokumentationsbereiche: [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)-
Adressen, [RFC 7042](https://www.rfc-editor.org/rfc/rfc7042#section-2.1.1)-MACs):

```
VSF-Status;Label;Hostname;IP-Address;Platform;Member ID;Status;MAC Address;Type;Model;Serial Number;Uptime;Priority;VSF Link 1 - Port;VSF Link 1 - Status;VSF Link 2 - Port;VSF Link 2 - Status;Primary Image;Secondary Image;Active Boot Image
healthy;switch-core-1;switch-core;192.0.2.11;AOS-CX;1;Conductor;00:00:5e:00:53:01;JL725A;6200F 24G Class4 PoE 4SFP+ 370W Switch;SN-EXAMPLE-0001;54 minutes;primary;1/1/26;up;1/1/25;up;ML.10.13.1180;ML.10.13.1050;primary
healthy;switch-core-3;switch-core;192.0.2.11;AOS-CX;3;Standby;00:00:5e:00:53:02;JL725A;6200F 24G Class4 PoE 4SFP+ 370W Switch;SN-EXAMPLE-0002;42 minutes;secondary;3/1/25;up;3/1/26;up;ML.10.13.1180;ML.10.13.1050;primary
healthy;switch-access-1;switch-access;192.0.2.12;AOS-S;1;Commander;00:00:5e:00:53:03;JL255A;Aruba JL255A 2930F-24G-PoE+-4SFP+ Switch;SN-EXAMPLE-0003;0d 4h 31m;128;1/26;Up;N/A;N/A;WC.16.11.0024;WC.16.11.0024;Primary
healthy;switch-access-2;switch-access;192.0.2.12;AOS-S;2;Standby;00:00:5e:00:53:04;JL256A;Aruba JL256A 2930F-48G-PoE+-4SFP+ Switch;SN-EXAMPLE-0004;0d 2h 36m;128;2/49;Up;N/A;N/A;WC.16.11.0024;WC.16.11.0024;Primary
offline;switch-edge-N/A;switch-edge;192.0.2.13;unreachable;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A
```

Trennzeichen ist `;`, damit die Datei in einem Excel/LibreOffice mit deutschem
Gebietsschema sauber öffnet. Echte Berichte enthalten Seriennummern, MACs und
Topologie – aus der Versionsverwaltung heraushalten (siehe
[Datenschutz und Veröffentlichung](#datenschutz-und-veröffentlichung)).

---

## CSV-Spalten

| Spalte | Bedeutung |
|---|---|
| `VSF-Status` | **Erste Spalte** – Stack-Gesamturteil: `healthy` / `degraded` / `offline` (siehe [unten](#vsf-status-werte)). Reiner Text; CSV kann keine Farben transportieren – daher z. B. in Excel per bedingter Formatierung einfärben (grün / gelb / rot). |
| `Label` | `<hostname>-<member_id>`, z. B. `switch-core-1` – eindeutiger Schlüssel je Stack-Member. |
| `Hostname` | Vom Switch selbst gemeldeter Name (Fallback: Inventory-Hostname). |
| `IP-Address` | Management-IP. Auch bei einem DNS-Inventory steht hier die aufgelöste IP (SSH-Peer-Adresse, DNS-Lookup als Fallback). |
| `Platform` | `AOS-CX`, `AOS-S` oder `unknown` / `unreachable` bei Fehlern. |
| `Member ID` | VSF-Mitglieds-ID. |
| `Status` | z. B. `Conductor` / `Commander` (aktiv), `Standby`, `Member` oder `Not Present`. |
| `MAC Address` | Auf beiden Plattformen als `aa:bb:cc:dd:ee:ff` normalisiert (das AOS-S-Format `aabbcc-ddeeff` wird umgesetzt). |
| `Type`, `Model`, `Serial Number`, `Uptime` | Gerätedetails aus `show vsf detail`; `N/A` falls nicht vorhanden (z. B. nicht bestückter Slot). |
| `Priority` | **AOS-S:** numerische VSF-Priority (z. B. `128`). **AOS-CX** (kennt keine numerische Priority): die VSF-Rolle – `primary` für den Conductor, `secondary` für den in der `show vsf`-Kopfzeile genannten Member, sonst `N/A`. |
| `VSF Link 1 - Port` / `- Status` | Physischer Port (z. B. `1/1/26` bzw. `1/26`) und Zustand (`up` / `down` / `error` …) von VSF-Link 1, aus `show vsf link detail`. `N/A` bei nicht gestacktem / nicht konfiguriertem Switch. |
| `VSF Link 2 - Port` / `- Status` | Dito für VSF-Link 2. |
| `Primary Image` / `Secondary Image` | Software-Version im Primary- bzw. Secondary-Flash (stack-weit, in jeder Zeile eines Stacks identisch). |
| `Active Boot Image` | Aktuell gebootetes Image (`primary` / `secondary` bzw. `Primary` / `Secondary` bei AOS-S). |

> `rom_version` ist weiterhin im JSON des Hilfsskripts enthalten, wird aber
> bewusst nicht in die CSV geschrieben.

---

## `VSF-Status`-Werte

| Wert | Farbvorschlag | Kriterien |
|---|---|---|
| `healthy` | 🟩 grün | Alle gelisteten Member sind aktiv **und** kein VSF-Link im Fehlerzustand. |
| `degraded` | 🟨 gelb | Mind. ein Member aktiv, aber **nicht alle** gelisteten Member vorhanden (z. B. `Not Present`-Slot) **oder** mind. ein VSF-Link im Fehlerzustand (`error`, Loop, Peer-Timeout, Inkompatibilität). Ein reines `down` auf einem ungenutzten Kettenende-Link zählt **nicht**. |
| `offline` | 🟥 rot | Switch nicht erreichbar, Fehler gemeldet, oder kein Member aktiv. |

---

## Funktionsweise von `vsf_ssh_inventory.py`

1. Baut eine **interaktive** SSH-Shell auf (kein reiner Exec-Kanal – AOS-S
   liefert `SSH command execution is not supported`).
2. Setzt eine sehr große PTY-Höhe (`height=1000`), damit die `-- MORE --`-
   Pagination der Switches praktisch nie greift; als Fallback wird sie zusätzlich
   erkannt und mit einem Leerzeichen beantwortet.
3. Entfernt ANSI-Cursor-Steuersequenzen **bevor** nach dem CLI-Prompt gesucht
   wird – ohne diesen Schritt hängt die Prompt-Erkennung, weil Aruba-Switches
   nach dem Prompt noch Cursor-Positionierungscodes senden.
4. Erkennt die Plattform aus `show version` (`ArubaOS-CX` vs.
   `Image stamp` / `Boot ROM Version`) und liest den konfigurierten Gerätenamen
   aus `show system`. Die IP-Spalte wird aus der SSH-Peer-Adresse / einem
   DNS-Lookup befüllt.
5. Führt `show vsf detail` aus und parst die Ausgabe in eine Member-Liste
   (`member_id`, `mac_address`, `type`, `model`, `status`, `serial_number`,
   `uptime`, `priority`). MAC-Adressen werden auf `aa:bb:cc:dd:ee:ff`
   normalisiert; bei AOS-CX tritt die VSF-Rolle (`primary` / `secondary`) in
   die `priority`-Spalte.
6. Ergänzt je Member den **physischen Port** und Zustand beider VSF-Links aus
   `show vsf link detail` – derselbe Befehl liefert auf AOS-CX (`1/1/26`) und
   AOS-S (`1/26`) ein vergleichbares `Port | State`-Tabellenformat. Nicht
   gestackte Switches → `N/A`.
7. Liest die Software-Images mit einem plattformspezifischen Befehl: AOS-CX über
   `show images`, AOS-S über `show flash` (+ `Boot Image` aus `show version`) →
   `primary_image`, `secondary_image`, `active_boot_image`.
8. Leitet den Gesamtzustand des Stacks ab (`vsf_health`, siehe
   [oben](#vsf-status-werte)).
9. Gibt in jedem Fall – auch bei Verbindungsfehlern – genau **ein JSON-Objekt**
   auf stdout aus, damit das Playbook das Ergebnis unabhängig vom Erfolg
   auswerten kann.

Bei abweichendem Firmware-Ausgabeformat sind nur die Regexe in der jeweiligen
`parse_*`-Funktion anzupassen.

---

## Designentscheidungen

### Warum SSH statt REST-API?

Die erste Umsetzung nutzte die REST-APIs von AOS-CX und AOS-S. Im praktischen
Betrieb scheiterte das an mehreren, teils plattformspezifischen Problemen:

- **AOS-CX REST-Sessionlimit** – jeder Login belegt eine Session; ohne sauberes
  Logout war das Limit schnell erreicht und weitere Logins wurden mit
  `401 – session limit reached` abgelehnt.
- **Kein einheitlicher REST-Login** – AOS-CX (`POST /rest/v10.09/login`) und
  AOS-S (`POST /rest/v4/login-sessions`) verwenden komplett unterschiedliche
  Login-Flows, Cookie-Namen und Fehlercodes; eine REST-basierte
  Plattformerkennung war dadurch fehleranfällig.
- **AOS-S REST lieferte keine Stacking-/VSF-Daten** in der getesteten
  Firmware – der naheliegende Endpunkt `/rest/v4/stacking/members` existierte
  nicht (`404`).
- **Ein Switch war über HTTPS/443 gar nicht erreichbar** (TLS-Handshake-Timeout),
  obwohl SSH auf allen Switches funktionierte.

Da SSH überall bestätigt war und keine Bindung an eine bestimmte API bestand,
wurde auf eine **SSH/CLI-basierte** Lösung umgestellt. Der entscheidende Fund
beim Testen gegen die realen Geräte: **beide Plattformen unterstützen denselben
Befehl `show vsf detail`** (Aruba hat die VSF-Terminologie auf ArubaOS-Switch
übertragen). Das ermöglicht einen einzigen, einheitlichen Parser statt zweier
getrennter REST-Implementierungen.

### Warum ein eigenes Skript statt `ansible.netcommon`?

`ansible.netcommon.network_cli` bringt bereits SSH-CLI-Module für Netzwerkgeräte
mit, aber:

- Der `network_os` (aoscx vs. arubaoss) muss **vorab** bekannt sein, um das
  passende Terminal-/Cliconf-Plugin zu wählen – genau das fehlt bei
  "unbekannten" Hosts.
- Ein Erkennungsversuch mit dem "falschen" `network_os` hinterließ die
  persistente `network_cli`-Verbindung in einem inkonsistenten Zustand, sodass
  der folgende Versuch mit dem "richtigen" `network_os` mit
  `cli prompt is not identified` fehlschlug (mit Live-Tests verifiziert).

Eine direkte `paramiko`-SSH-Verbindung (schon eine Projekt-Abhängigkeit) umgeht
das vollständig: Jeder Host bekommt eine frische, unabhängige Verbindung in
einem einzigen, kurzlebigen Python-Prozess ohne Zustand zwischen Hosts.

---

## Datenschutz und Veröffentlichung

Dieses Modul ist so ausgelegt, dass es sich als eigenständiges öffentliches
Repository veröffentlichen lässt.

- **Das Tool liest nur.** Es führt ausschließlich lesende `show`-Befehle aus,
  ändert nichts am Switch, hält keinen Zustand und gibt das geparste Ergebnis
  nur auf stdout an das Playbook zurück. Es „telefoniert nicht nach Hause".
- **Keine Geheimnisse im Repo.** `inventory.example.yml` wird committet, niemals
  `inventory.yml`. Das Switch-Passwort zur Laufzeit übergeben (`--ask-pass`),
  per `-e ansible_password=…` oder aus einer Ansible-Vault-Datei – es wird nicht
  gespeichert. Task 1.1 läuft mit `no_log: true`, das Passwort erscheint also
  nicht im Ansible-Log.
- **Erzeugte Berichte sind privat.** Alles unter `exports/` ist per `.gitignore`
  ausgenommen: eine echte CSV listet Seriennummern, MAC-Adressen,
  Firmware-Versionen und die Stack-Topologie. Solche Dateien bewusst teilen,
  nicht über git.
- **Alle Beispiele nutzen Dokumentationsbereiche** – [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)-
  IPs (`192.0.2.0/24`), [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)-Namen
  (`example.net`), [RFC 7042](https://www.rfc-editor.org/rfc/rfc7042#section-2.1.1)-
  MACs (`00:00:5e:00:53:xx`), Platzhalter-Seriennummern. Aruba-Artikelnummern
  (`JL725A`) und Firmware-Strings sind öffentliche Produktinformationen.
- **Aus einem größeren Repo herauslösen?** Mit einer frischen Historie starten
  (`git init` in einer Kopie) oder `git filter-repo` verwenden – die Historie
  des umgebenden Repos kann noch echte Adressen oder Berichte enthalten. Vor der
  Veröffentlichung eine `LICENSE` ergänzen.

---

## Bekannte Grenzen

- Nicht erreichbare Hosts (z. B. SSH-Timeout) und Switches ganz ohne
  VSF-Feature erzeugen trotzdem **eine** CSV-Zeile mit `VSF-Status = offline`
  (übrige Spalten `N/A`) sowie eine Debug-Meldung im Lauf.
- `vsf_health` bewertet nur Member-Präsenz und VSF-Link-Fehler. Ein einzelner,
  nicht gestackter Switch gilt als `healthy`, auch wenn ein VSF-Link `down`
  ist – nur echte Fehlerzustände (`error` / Loop / Timeout / Inkompatibilität)
  lösen `degraded` aus.
- Es wird nur Passwort-Authentifizierung unterstützt; SSH-Key-Auth ist nicht
  implementiert.

---

## FAQ

### Hostname bekannt, IP unbekannt?

`ansible_host` muss keine IP sein – jede per DNS / `/etc/hosts` auflösbare
Adresse funktioniert genauso (`switch02` in `inventory.example.yml`), da das
Skript sie unverändert an `paramiko.SSHClient().connect()` durchreicht und die
IP-Spalte separat auflöst. Ist der Switch-Name gar nicht auflösbar, wird vorher
ein zusätzlicher Schritt benötigt (z. B. DHCP-Leases, DNS oder eine bestehende
CMDB), der den Namen einer IP zuordnet.
