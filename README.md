# Aruba Ansible Template Collection

Wiederverwendbare, anonymisierte Ansible-Vorlagen für Aruba-Switches
(**AOS-CX** und **AOS-S**):

- VLANs eines AOS-CX-Switches aus einer zentralen Soll-Liste verwalten
  (REST-API + SSH)
- CA-Zertifikate als Trust-Anchor-(TA-)Profile auf AOS-CX-Switches einspielen
  und erneuern (REST-API)
- Beispielkonfiguration für AOS-S-Switches: LACP-Trunks + VLANs (SSH/CLI)
- SSH-basierte VSF-/Stacking-Inventur aller Switches mit CSV-Export

Alle mitgelieferten Adressen, Zugangsdaten und Namen sind Platzhalter
([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): `192.0.2.x` /
`198.51.100.x`, `*.example.com`, `example-user` / `YOUR_PASSWORD`,
`YOUR_*_CERTIFICATE_BASE64`).

## Module

| Ordner | Zweck | Zugriff | Doku |
|---|---|---|---|
| [`aos-cx/vlan/`](aos-cx/vlan/) | AOS-CX: VLANs aus einer Soll-Liste anlegen/aktualisieren/löschen + validieren | REST-API (HTTPS) + SSH | [EN](aos-cx/vlan/README.md) · [DE](aos-cx/vlan/README_de.md) |
| [`aos-cx/certificates/`](aos-cx/certificates/) | AOS-CX: TA-Profile (Root-/Intermediate-CA) abgleichen, anlegen, ersetzen, verwaiste löschen | REST-API (HTTPS) | [EN](aos-cx/certificates/README.md) · [DE](aos-cx/certificates/README_de.md) |
| [`aos-s/`](aos-s/) | AOS-S: Beispiel für LACP-Trunks + VLANs, Auslesen, `write memory` | SSH/CLI | [EN](aos-s/README.md) · [DE](aos-s/README_de.md) |
| [`vsf-inventory-csv-export/`](vsf-inventory-csv-export/) | VSF-/Stacking-Zustand aller Switches als CSV exportieren (AOS-CX + AOS-S, Plattform-Autoerkennung) | SSH/CLI | [EN](vsf-inventory-csv-export/README.md) · [DE](vsf-inventory-csv-export/README_de.md) |
| [`devcontainer/`](devcontainer/) | `requirements.yml` für die Collections + Dev-Container-Setup | – | – |

```
aruba-ansible-template-collection/
├── aos-cx/
│   ├── ansible.cfg
│   ├── switch_hosts.yml            # Beispiel-Inventory: Switch-IP, Zugangsdaten, Verbindungstyp
│   ├── vlan/
│   │   ├── switch_attributes.yml   # Playbook: VLANs anlegen/aktualisieren/löschen + validieren
│   │   ├── vlans.yml               # Soll-Zustand aller VLANs (generisches Beispiel)
│   │   ├── extra                   # Tasks 3-8 als eigenständiges Snippet (Referenz)
│   │   ├── README.md               # Doku (englisch)
│   │   └── README_de.md            # Doku (deutsch)
│   └── certificates/
│       ├── play_ca.yml             # Playbook: TA-Zertifikate (Root-/Intermediate-CA) einspielen
│       ├── certs.yml               # Zertifikatsdaten + Zielzuordnung (Platzhalter)
│       ├── certs.sample.json       # Beispiel-Request-Body der REST-API (Referenz)
│       ├── README.md               # Doku (englisch)
│       └── README_de.md            # Doku (deutsch)
├── aos-s/
│   ├── ansible.cfg
│   ├── switch_hosts.yml            # Beispiel-Inventory (AOS-S)
│   ├── switch_attributes.yml       # Playbook: LACP-Trunks + VLANs (Beispiel)
│   ├── README.md                   # Doku (englisch)
│   └── README_de.md                # Doku (deutsch)
├── devcontainer/
│   ├── requirements.yml            # Ansible Collections (arubanetworks.aoscx / .aos_switch)
│   └── .devcontainer/              # Dev-Container (Codespaces / Docker / Podman)
└── vsf-inventory-csv-export/
    ├── play_vsf_info.yml           # Playbook: VSF-Inventur je Host -> CSV
    ├── vsf_ssh_inventory.py        # SSH-Hilfsskript (Plattformerkennung, Parser)
    ├── inventory.example.yml       # Inventory-Vorlage (-> inventory.yml, git-ignored)
    └── exports/                    # erzeugte CSV-Dateien (git-ignored)
```

## Voraussetzungen

- Python-Virtualenv mit `ansible-core` (für die VSF-Inventur zusätzlich `paramiko`)
- Ansible Collections installiert:
  `ansible-galaxy collection install -r devcontainer/requirements.yml`
- Für das VLAN-Playbook zusätzlich die Bibliothek
  [`pyaoscx`](https://pypi.org/project/pyaoscx/) (REST-Verbindung)
- Netzwerkzugriff vom Ansible-Controller auf die Management-Adresse der Switches
  (HTTPS für die REST-Tasks, SSH für die CLI-Tasks und die VSF-Inventur)

---

## VLANs verwalten (AOS-CX)

```bash
ansible-playbook -i aos-cx/switch_hosts.yml aos-cx/vlan/switch_attributes.yml

# zusätzlich VLANs löschen, die nicht mehr in vlans.yml stehen
ansible-playbook -i aos-cx/switch_hosts.yml aos-cx/vlan/switch_attributes.yml \
  -e vlan_cleanup=true
```

Der Soll-Zustand wird in [`aos-cx/vlan/vlans.yml`](aos-cx/vlan/vlans.yml) gepflegt
(die mitgelieferte Liste ist ein generisches Beispiel). Das Playbook legt fehlende
VLANs an, korrigiert Namen, aktiviert DHCPv4-Snooping und validiert das Ergebnis
auf dem Switch; mit `-e vlan_cleanup=true` werden zusätzlich nicht mehr gelistete
VLANs entfernt (VLAN 1 bleibt immer erhalten).

Details, `vlans.yml`-Schema und Ablauf der 8 Tasks:
[`aos-cx/vlan/README.md`](aos-cx/vlan/README.md) (englisch) bzw.
[`README_de.md`](aos-cx/vlan/README_de.md) (deutsch).

---

## Zertifikate einspielen (AOS-CX)

```bash
# Platzhalter in aos-cx/certificates/certs.yml durch eigene CA-Zertifikate ersetzen
ansible-playbook -i aos-cx/switch_hosts.yml aos-cx/certificates/play_ca.yml

# nicht-interaktiv (z. B. CI/CD) mit TLS-Prüfung des Switches
ansible-playbook -i aos-cx/switch_hosts.yml aos-cx/certificates/play_ca.yml \
  -e overwrite_certs=true -e validate_certs=true
```

Die TA-Profile werden in [`aos-cx/certificates/certs.yml`](aos-cx/certificates/certs.yml)
gepflegt (`name`, `target_hosts`, `cert_data` im PEM-Format). Das Playbook meldet
sich an der REST-API an, legt fehlende Profile an, überschreibt abweichende nur
nach Bestätigung (`yes`/`no`, deutsch auch `ja`/`j`), bietet das Löschen nicht
mehr gepflegter Profile an und meldet sich am Ende ab – auch nach einem Fehler.

| Variable | Standard | Beschreibung |
|---|---|---|
| `overwrite_certs` | `false` | `true` überspringt alle Bestätigungsabfragen – überschreibt abweichende **und** löscht verwaiste Profile |
| `validate_certs` | `false` | `true` prüft das TLS-Zertifikat des Switches beim REST-Zugriff |

Details: [`aos-cx/certificates/README.md`](aos-cx/certificates/README.md)
(englisch) bzw. [`README_de.md`](aos-cx/certificates/README_de.md) (deutsch).

---

## AOS-S Switches

Für klassische AOS-S-Switches liegt unter [`aos-s/`](aos-s/) ein eigenes
Beispiel-Inventory samt Playbook (LACP-Trunks, VLANs, Auslesen, `write memory`)
vor. Ports, VLAN-IDs und IP-Adresse im Playbook sind Beispiele und vor dem Lauf
anzupassen.

```bash
cd aos-s
ansible-playbook -i switch_hosts.yml switch_attributes.yml
```

Details: [`aos-s/README.md`](aos-s/README.md) (englisch) bzw.
[`README_de.md`](aos-s/README_de.md) (deutsch).

---

## VSF-/Stacking-Inventur (CSV-Export)

SSH-basierte Inventur des VSF-Zustands aller Switches – erkennt AOS-CX und AOS-S
automatisch und schreibt eine kombinierte CSV mit einer Zeile je Stack-Member
und einem Ampel-Gesamturteil (`healthy` / `degraded` / `offline`).

```bash
cd vsf-inventory-csv-export
cp inventory.example.yml inventory.yml     # dann inventory.yml anpassen
ansible-playbook -i inventory.yml play_vsf_info.yml --ask-pass
```

Das Modul ist in sich geschlossen und enthält keine sensiblen Daten. Details,
CSV-Spalten und Designentscheidungen:
[`vsf-inventory-csv-export/README.md`](vsf-inventory-csv-export/README.md)
(englisch) bzw. [`README_de.md`](vsf-inventory-csv-export/README_de.md) (deutsch).

---

## Sicherheitshinweise

- Zugangsdaten (`ansible_password`) stehen in den Beispiel-Inventories als
  Platzhalter im Klartext. Für den produktiven Einsatz **Ansible Vault** nutzen
  oder das Passwort zur Laufzeit übergeben (`--ask-pass`, `-e`).
- `*_validate_certs: false` bzw. `validate_certs: false` deaktiviert die
  TLS-Prüfung gegenüber dem Switch. In produktiven Umgebungen auf `true` stellen
  und eine vertrauenswürdige CA hinterlegen.
- `aos-cx/certificates/certs.yml` enthält nur öffentliche CA-Zertifikate –
  niemals private Schlüssel committen.
- `inventory.yml` und der Ordner `exports/` der VSF-Inventur sind per
  `.gitignore` ausgenommen – echte Inventardaten gehören nicht ins Repo.
