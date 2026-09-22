# AOS-S-Trunk- & VLAN-Beispiel

**[English](README.md)** · Deutsch

Ein Beispiel-Ansible-Playbook für klassische Aruba-**AOS-S**-Switches
(ArubaOS-Switch). Es konfiguriert per SSH/CLI zwei LACP-Trunks und zwei VLANs,
liest das Ergebnis aus und speichert die Konfiguration.

> Ports, VLAN-IDs und IP-Adresse im Playbook sind **Beispiele**. Vor dem Lauf an
> den eigenen Switch anpassen.

---

## Was es tut

| Schritt | Konfiguration / Befehl |
|---|---|
| LACP-Trunk `trk1` | Ports `9-10` |
| LACP-Trunk `trk2` | Ports `7-8` |
| VLAN 300 | Name `vlan300`, tagged auf `trk1`, `jumbo` |
| VLAN 200 | Name `vlan200`, untagged auf Ports `5-6`, tagged auf `trk1` und `trk2`, `voice`, IP `198.51.100.1/24` |
| Auslesen | `show trunks`, `show lacp`, `show vlan`, `show vlan 200`, `show vlan 300`, `show ip` |
| Speichern | `write memory` |

---

## Schnellstart

**Voraussetzungen**

- Python-Virtualenv mit `ansible-core`
- Ansible-Collections `arubanetworks.aos_switch` und `ansible.netcommon`
  (`ansible-galaxy collection install -r ../devcontainer/requirements.yml`)
- SSH (TCP/22) vom Ansible-Controller zum Switch

**Inventory** – [`switch_hosts.yml`](switch_hosts.yml) anpassen:

```yaml
all:
  hosts:
    switch1:
      ansible_host: 192.0.2.12
      ansible_user: example-user
      ansible_password: YOUR_PASSWORD   # besser Ansible Vault oder -e zur Laufzeit
      ansible_connection: local
      ansible_network_os: arubanetworks.aos_switch.arubaoss
```

**Aufruf**

```bash
# aus diesem Ordner (aos-s/), damit ansible.cfg greift
ansible-playbook -i switch_hosts.yml switch_attributes.yml
```

---

## Dateien

| Datei | Zweck |
|---|---|
| [`switch_attributes.yml`](switch_attributes.yml) | Das Playbook – Trunks, VLANs, Auslesen, `write memory`. |
| [`switch_hosts.yml`](switch_hosts.yml) | Beispiel-Inventory (Platzhalter für Adresse und Zugangsdaten). |
| [`ansible.cfg`](ansible.cfg) | Deaktiviert die SSH-Host-Key-Prüfung für diesen Ordner. |

---

## Verbindung

Das Inventory setzt `ansible_connection: local`, die Verbindungsart der
REST-basierten `arubaoss_*`-Module. Dieses Playbook nutzt ausschließlich die
CLI-Module `arubaoss_config` und `arubaoss_command` und überschreibt die
Verbindung daher für das ganze Play mit `ansible.netcommon.network_cli` (SSH).

---

## Hinweise

- Die `show`-Tasks laufen mit `no_log: true`; ihre Ausgabe erscheint im jeweils
  folgenden `debug`-Task.
- `write memory` wird immer als `changed` gemeldet.
- Die SSH-Host-Key-Prüfung ist deaktiviert (`ansible.cfg`,
  `StrictHostKeyChecking=no`). Produktiv aktivieren.
- Niemals echte Zugangsdaten committen – Ansible Vault nutzen oder das Passwort
  zur Laufzeit übergeben.
