# Aruba Ansible Template Collection

Wiederverwendbare, anonymisierte Ansible-Vorlagen für Aruba-Switches
(**AOS-CX** und **AOS-S**):

- VLANs eines AOS-CX-Switches aus einer zentralen Soll-Liste verwalten
  (REST-API + SSH)
- SSH-basierte VSF-/Stacking-Inventur aller Switches mit CSV-Export

Alle mitgelieferten Adressen, Zugangsdaten und Namen sind Platzhalter
([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737): `192.0.2.x`,
`*.example.net`, `admin` / `CHANGEME`).

## Module

| Ordner | Zweck | Zugriff | Doku |
|---|---|---|---|
| [`aos-cx/vlan/`](aos-cx/vlan/) | AOS-CX: VLANs aus einer Soll-Liste anlegen/aktualisieren/löschen + validieren | REST-API (HTTPS) + SSH | [EN](aos-cx/vlan/README.md) · [DE](aos-cx/vlan/README_de.md) |
| [`vsf-inventory-csv-export/`](vsf-inventory-csv-export/) | VSF-/Stacking-Zustand aller Switches als CSV exportieren (AOS-CX + AOS-S, Plattform-Autoerkennung) | SSH/CLI | [EN](vsf-inventory-csv-export/README.md) · [DE](vsf-inventory-csv-export/README_de.md) |
| [`devcontainer/`](devcontainer/) | `requirements.yml` für die Collections + Dev-Container-Setup | – | – |

```
aruba-ansible-template-collection/
├── aos-cx/
│   ├── ansible.cfg
│   ├── switch_hosts.yml            # Beispiel-Inventory: Switch-IP, Zugangsdaten, Verbindungstyp
│   └── vlan/
│       ├── switch_attributes.yml   # Playbook: VLANs anlegen/aktualisieren/löschen + validieren
│       ├── vlans.yml               # Soll-Zustand aller VLANs (generisches Beispiel)
│       ├── extra                   # Tasks 3-8 als eigenständiges Snippet (Referenz)
│       ├── README.md               # Doku (englisch)
│       └── README_de.md            # Doku (deutsch)
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
- `*_validate_certs: false` deaktiviert die TLS-Prüfung gegenüber dem Switch. In
  produktiven Umgebungen auf `true` stellen und eine vertrauenswürdige CA
  hinterlegen.
- `inventory.yml` und der Ordner `exports/` der VSF-Inventur sind per
  `.gitignore` ausgenommen – echte Inventardaten gehören nicht ins Repo.
