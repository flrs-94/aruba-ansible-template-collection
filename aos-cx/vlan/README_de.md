# AOS-CX-VLAN-Verwaltung

**[English](README.md)** · Deutsch

Ein Ansible-Playbook, das die VLANs eines oder mehrerer Aruba-**AOS-CX**-Switches
aus einer einzigen Source of Truth verwaltet. Der gewünschte Zustand steht in
[`vlans.yml`](vlans.yml); das Playbook gleicht den Switch auf diese Liste ab und
validiert das Ergebnis anschließend auf dem Gerät.

Das Playbook ist idempotent – ein erneuter Lauf ändert nichts mehr, sobald der
Switch im Soll-Zustand ist.

---

## Inhalt

- [Was es tut](#was-es-tut)
- [Schnellstart](#schnellstart)
- [Dateien](#dateien)
- [Format von `vlans.yml`](#format-von-vlansyml)
- [Ablauf des Playbooks](#ablauf-des-playbooks)
- [Variablen](#variablen)
- [REST vs. SSH](#rest-vs-ssh)
- [Sicheres Löschen von VLANs](#sicheres-löschen-von-vlans)
- [Einschränkungen](#einschränkungen)

---

## Was es tut

1. Legt jedes in `vlans.yml` gelistete VLAN an bzw. aktualisiert es (id, name,
   `voice`, `ip_igmp_snooping`).
2. Aktiviert `dhcpv4-snooping` auf den VLANs, die es anfordern.
3. Löscht optional VLANs, die auf dem Switch existieren, aber **nicht** in
   `vlans.yml` stehen (standardmäßig aus – siehe
   [Sicheres Löschen](#sicheres-löschen-von-vlans)).
4. Validiert jedes VLAN gegen den Switch (Name-Abgleich + DHCPv4-Snooping) und
   gibt eine kompakte Zusammenfassung der Fehler aus.

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core` und der Bibliothek
  [`pyaoscx`](https://pypi.org/project/pyaoscx/) (für die REST-Verbindung).
- Ansible-Collection `arubanetworks.aoscx`
  (`ansible-galaxy collection install -r ../../devcontainer/requirements.yml`).
- HTTPS (TCP/443) **und** SSH (TCP/22) vom Ansible-Controller zu jedem Switch.
  SSH wird nur für die DHCPv4-Snooping-Schritte benötigt.

**Inventory** – die gemeinsame [`../switch_hosts.yml`](../switch_hosts.yml)
weiterverwenden oder ein eigenes anlegen:

```yaml
all:
  hosts:
    aoscx_1:
      ansible_host: 192.0.2.11
  vars:
    ansible_user: admin
    ansible_password: CHANGEME          # besser Ansible Vault oder -e zur Laufzeit
    ansible_network_os: arubanetworks.aoscx.aoscx
    ansible_connection: arubanetworks.aoscx.aoscx
    ansible_aoscx_validate_certs: false
    ansible_aoscx_use_proxy: false
```

**Aufruf**

```bash
# aus diesem Ordner (aos-cx/vlan/)
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml

# zusätzlich VLANs löschen, die nicht mehr in vlans.yml stehen
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml -e vlan_cleanup=true
```

---

## Dateien

| Datei | Zweck |
|---|---|
| [`switch_attributes.yml`](switch_attributes.yml) | Das Playbook – 8 nummerierte Tasks: Anlegen/Aktualisieren, DHCPv4-Snooping, Facts, Löschen, erneute Facts, Running-Config, Validierung, Zusammenfassung. |
| [`vlans.yml`](vlans.yml) | Der Soll-Zustand: die komplette Liste der VLANs und ihrer Attribute. **Das ist die Datei, die im Alltag gepflegt wird.** Die mitgelieferte Liste ist ein generisches Beispiel. |
| [`extra`](extra) | Referenz-Kopie der Tasks 3–8 als eigenständiges Snippet (Facts, Cleanup, Validierung). Für den Playbook-Lauf nicht nötig – aufgehoben zur Wiederverwendung in anderen Playbooks. |

---

## Format von `vlans.yml`

Ein Listeneintrag je VLAN:

```yaml
vlans:
  - { id: 100, name: "clients-wired" }
  - { id: 110, name: "clients-wireless", ip_igmp_snooping: true }
  - { id: 120, name: "voice", voice: true, dhcpv4_snooping: true, ip_igmp_snooping: true }
```

| Schlüssel | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `id` | int (1–4094) | ja | VLAN-ID |
| `name` | string | ja | VLAN-Name auf dem Switch |
| `voice` | bool | nein | als Voice-VLAN markieren (IP-Telefone) |
| `ip_igmp_snooping` | bool | nein | IGMP-Snooping aktivieren (IPv4-Multicast) |
| `dhcpv4_snooping` | bool | nein | DHCPv4-Snooping aktivieren (per CLI, siehe unten) |

Nicht gesetzte optionale Schlüssel bleiben auf dem Switch-Standardwert.

---

## Ablauf des Playbooks

| # | Task | Modul | Verbindung |
|---|---|---|---|
| 1 | VLANs anlegen / aktualisieren | `aoscx_vlan` | REST |
| 2 | DHCPv4-Snooping aktivieren (`when: dhcpv4_snooping`) | `aoscx_config` | SSH |
| 3 | Konfigurierte VLAN-IDs abrufen | `aoscx_facts` | REST |
| 4 | Nicht in `vlans.yml` gelistete VLANs löschen (`when: vlan_cleanup`) | `aoscx_vlan` | REST |
| 5 | Facts erneut abrufen (Stand kann sich in 4 geändert haben) | `aoscx_facts` | REST |
| 6 | `show running-config` abrufen | `aoscx_command` | SSH |
| 7 | Name + DHCPv4-Snooping je VLAN validieren | `assert` | – |
| 8 | Zusammenfassung fehlgeschlagener VLANs ausgeben | `debug` | – |

Task 7 nutzt `ignore_errors: true`, damit ein einzelnes fehlerhaftes VLAN den
Loop nicht abbricht; alle VLANs werden geprüft und Task 8 listet die
fehlgeschlagenen IDs auf.

---

## Variablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `vlan_cleanup` | `false` | `true` aktiviert Task 4, der VLANs löscht, die auf dem Switch, aber nicht in `vlans.yml` stehen (VLAN 1 bleibt immer erhalten). |

```bash
ansible-playbook -i ../switch_hosts.yml switch_attributes.yml -e vlan_cleanup=true
```

---

## REST vs. SSH

Die Collection `arubanetworks.aoscx` bietet zwei Verbindungswege:

- **REST** (`pyaoscx`) – hier der Standard. `aoscx_vlan` und `aoscx_facts`
  funktionieren nur über REST.
- **SSH** (`network_cli`) – nötig für Module, die rohe CLI senden
  (`aoscx_config`, `aoscx_command`).

`dhcpv4-snooping` wird vom REST-Modul `aoscx_vlan` **nicht** abgebildet, daher
schalten die Tasks 2 und 6 die Verbindung per task-lokalen `vars` auf SSH um.
Ohne diese Umschaltung schlagen die Tasks mit *"Method not found"* fehl.

---

## Sicheres Löschen von VLANs

Task 4 ist eine destruktive Operation und daher doppelt abgesichert:

1. Er läuft nur mit `-e vlan_cleanup=true` (Standard `false`).
2. VLAN 1 (das Default-VLAN) ist immer ausgeschlossen.

Zuerst einmal ohne Flag laufen lassen, um zu sehen, was sich ändern *würde*, und
danach mit `-e vlan_cleanup=true` erneut ausführen, sobald die `vlans.yml`-Liste
sicher vollständig ist.

---

## Einschränkungen

- Verwaltet werden nur die VLAN-Attribute `name`, `voice`, `ip_igmp_snooping`
  und `dhcpv4_snooping`. L3/SVI, ACLs, VRFs usw. sind nicht Teil des Templates.
- Die DHCPv4-Snooping-Validierung parst den Text von `show running-config`; eine
  geänderte AOS-CX-Ausgabe kann eine Anpassung des Regex in Task 7 erfordern.
- Das Playbook führt **kein** `write memory` aus – bei Bedarf einen abschließenden
  `aoscx_command`-Task (`copy running-config startup-config`) ergänzen, damit die
  Änderung einen Neustart übersteht.
