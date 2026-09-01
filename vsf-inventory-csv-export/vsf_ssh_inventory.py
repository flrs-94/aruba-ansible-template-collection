#!/usr/bin/env python3
"""Query the VSF member information of an Aruba switch over SSH (AOS-CX or AOS-S).

EN: Called once per host by the playbook play_vsf_info.yml (delegate_to: localhost).
    It always prints exactly one JSON object to stdout, never an exception:
    {"platform", "hostname", "ip", "members", "primary_image", "secondary_image",
     "active_boot_image", "vsf_health", "error"}
    - "ip" is the resolved IP address (relevant when --host is a DNS name).
    - each entry in "members" also carries the VSF link info
      (vsf_link1_port/-status, vsf_link2_port/-status).
    - "vsf_health" is the derived overall stack state: healthy / degraded / offline.

DE: Wird vom Playbook play_vsf_info.yml einmal pro Host aufgerufen (delegate_to: localhost).
    Gibt immer genau ein JSON-Objekt auf stdout aus, nie eine Exception (Struktur s. o.).
    - "ip" ist die aufgeloeste IP-Adresse (wichtig, wenn --host ein DNS-Name ist).
    - jeder Eintrag in "members" enthaelt zusaetzlich die VSF-Link-Infos.
    - "vsf_health" ist der abgeleitete Gesamtzustand des Stacks: healthy / degraded / offline.
"""
import argparse
import json
import re
import socket
import sys
import time

import paramiko

# EN: CLI prompt / pagination / ANSI escape sequences of the Aruba shells.
# DE: CLI-Prompt / Pagination / ANSI-Escape-Sequenzen der Aruba-Shells.
PROMPT_RE = re.compile(r"[\r\n][\w.\-]+[#>]\s*$")
MORE_RE = re.compile(r"-- MORE --")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def strip_ansi(text):
    return ANSI_RE.sub("", text)


def read_until_prompt(chan, max_wait=10.0):
    """EN: Read from the channel until a CLI prompt is seen; auto-answer pagination.
    DE: Liest vom Kanal, bis ein CLI-Prompt erkannt wird; beantwortet Pagination automatisch.
    """
    buf = b""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if chan.recv_ready():
            buf += chan.recv(65535)
            deadline = time.time() + max_wait
            # EN: Strip cursor control codes first, otherwise the prompt's line end is never matched.
            # DE: Cursor-Steuercodes zuerst entfernen, sonst wird das Zeilenende des Prompts nie erkannt.
            text = strip_ansi(buf.decode(errors="replace"))
            if MORE_RE.search(text):
                chan.send(" ")
                continue
            if PROMPT_RE.search(text):
                break
        else:
            time.sleep(0.2)
    return strip_ansi(buf.decode(errors="replace"))


def run_command(chan, command, max_wait=10.0):
    chan.send(command + "\r")
    time.sleep(0.3)
    return read_until_prompt(chan, max_wait=max_wait)


def detect_platform(version_text):
    """EN: Derive the platform from 'show version' - both OSes share the command name 'show vsf'.
    DE: Leitet die Plattform aus 'show version' ab - beide OS nutzen denselben Befehl 'show vsf'.
    """
    if "ArubaOS-CX" in version_text:
        return "AOS-CX"
    if "Image stamp" in version_text or "Boot ROM Version" in version_text:
        return "AOS-S"
    return "unknown"


def normalize_mac(value):
    """EN: Normalise a MAC address to the colon format aa:bb:cc:dd:ee:ff.
        AOS-S reports the Aruba format 'aabbcc-ddeeff', AOS-CX already 'aa:bb:cc:dd:ee:ff'.
        Unknown formats (length != 12 hex chars) are returned unchanged.
    DE: Vereinheitlicht eine MAC-Adresse auf das Doppelpunkt-Format aa:bb:cc:dd:ee:ff.
        AOS-S liefert das Aruba-Format 'aabbcc-ddeeff', AOS-CX bereits 'aa:bb:cc:dd:ee:ff'.
        Unbekannte Formate (Laenge != 12 Hexzeichen) bleiben unveraendert.
    """
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(hex_only) != 12:
        return value
    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2)).lower()


def parse_vsf_members(vsf_detail_text):
    """EN: Split 'show vsf detail' into member blocks; the field names match on AOS-CX/AOS-S.
    DE: Zerlegt 'show vsf detail' in Mitgliederbloecke; die Feldnamen sind auf AOS-CX/AOS-S gleich.
    """
    blocks = re.split(r"(?=Member ID\s*:)", vsf_detail_text)
    members = []
    # EN: AOS-CX has no numeric priority but the roles primary/secondary:
    #       primary   = member whose Status is "Conductor"
    #       secondary = member ID from the stack header line "Secondary : <id>" (also in 'show vsf')
    #     AOS-S instead reports a real number ("Priority : 128"); the replacement below is skipped
    #     there because member["priority"] is then not "N/A".
    # DE: AOS-CX kennt keine numerische Priority, sondern die Rollen primary/secondary:
    #       primary   = Member mit Status "Conductor"
    #       secondary = Member-ID aus der Stack-Kopfzeile "Secondary : <id>" (auch in 'show vsf')
    #     AOS-S liefert dagegen eine echte Zahl ("Priority : 128"); die Ersetzung unten greift
    #     dort nicht, weil member["priority"] dann nicht "N/A" ist.
    cx_secondary_match = re.search(r"(?im)^[ \t]*Secondary[ \t]*:[ \t]*(\d+)", vsf_detail_text)
    cx_secondary_id = cx_secondary_match.group(1) if cx_secondary_match else None
    # EN: '[ \t]*' (not '\s*') after the colon - '\s*' would eat the next line on empty values.
    # DE: '[ \t]*' (nicht '\s*') nach dem Doppelpunkt - '\s*' frisst bei leeren Werten die Folgezeile.
    fields = {
        "mac_address": r"MAC Address[ \t]*:[ \t]*(.*)",
        "type": r"\bType[ \t]*:[ \t]*(.*)",
        "model": r"Model[ \t]*:[ \t]*(.*)",
        "status": r"Status[ \t]*:[ \t]*(.*)",
        "priority": r"Priority[ \t]*:[ \t]*(.*)",
        "rom_version": r"ROM Version[ \t]*:[ \t]*(.*)",
        "serial_number": r"Serial Number[ \t]*:[ \t]*(.*)",
        "uptime": r"Uptime[ \t]*:[ \t]*(.*)",
    }
    for block in blocks:
        id_match = re.search(r"Member ID\s*:\s*(\S+)", block)
        if not id_match:
            continue
        member = {"member_id": id_match.group(1)}
        for key, pattern in fields.items():
            match = re.search(pattern, block)
            member[key] = match.group(1).strip() if match and match.group(1).strip() else "N/A"
        # EN: Unify the MAC format across platforms (AOS-S: aabbcc-ddeeff -> aa:bb:...).
        # DE: MAC-Format plattformuebergreifend vereinheitlichen (AOS-S: aabbcc-ddeeff -> aa:bb:...).
        if member["mac_address"] != "N/A":
            member["mac_address"] = normalize_mac(member["mac_address"])
        # EN: AOS-CX - write the VSF role into the priority column instead of a missing number.
        # DE: AOS-CX - statt fehlender Zahl die VSF-Rolle in die Priority-Spalte schreiben.
        if member["priority"] == "N/A":
            if member["status"].strip().lower() == "conductor":
                member["priority"] = "primary"
            elif cx_secondary_id is not None and member["member_id"] == cx_secondary_id:
                member["priority"] = "secondary"
        members.append(member)
    return members


def _empty_links():
    return {"link1_port": "N/A", "link1_status": "N/A", "link2_port": "N/A", "link2_status": "N/A"}


def parse_vsf_links(vsf_link_detail_text):
    """EN: Determine the *physical port* and the status of both VSF links per member.

        Return value: {member_id: {"link1_port","link1_status","link2_port","link2_status"}}.

        Source is 'show vsf link detail' - command and output format are usable on both
        AOS-CX and AOS-S (verified against real, stacked devices):

            VSF Member: 1  Link 1              <- AOS-CX header ("Link 1")
            VSF Member: 1     Link: 1          <- AOS-S header  ("Link: 1")
            Port     State ...
            -------  --------------------
            1/1/26   up ...                    <- AOS-CX: port 1/1/26, status up
            1/26     Up: Connected to port ... <- AOS-S:  port 1/26,   status Up

        -> port   = first token of the data row (e.g. 1/1/26 or 1/26); multiple ports
                    (LAG) are joined with a comma.
        -> status = first word of the State column (up/down/error or "Up"/"Down").
        Unconfigured / non-stacked links yield no port value -> "N/A".
        On a differing firmware format, only the regexes in this function need adjusting.

    DE: Ermittelt je VSF-Member den *physischen Port* und den Status der beiden VSF-Links.
        Quelle ist 'show vsf link detail' - Befehl und Ausgabeformat sind auf AOS-CX und
        AOS-S nutzbar (an realen, gestackten Geraeten verifiziert; Format siehe oben).
        -> Port   = erstes Token der Datenzeile (mehrere Ports -> per Komma verbunden).
        -> Status = erstes Wort der State-Spalte.
        Nicht konfigurierte / nicht gestackte Links -> "N/A".
        Bei abweichendem Firmware-Format sind nur die Regexe dieser Funktion anzupassen.
    """
    result = {}
    # EN: Strip CR - the SSH output arrives with \r\n. / DE: CR entfernen - SSH-Ausgabe kommt mit \r\n.
    text = (vsf_link_detail_text or "").replace("\r", "")
    # EN: re.split with two groups -> [pre, id, link_no, block, id, link_no, block, ...]
    # DE: re.split mit zwei Gruppen -> [pre, id, link_no, block, id, link_no, block, ...]
    parts = re.split(r"(?im)^[ \t]*VSF Member:[ \t]*(\d+)[ \t]+Link:?[ \t]*(\d+).*$", text)
    for i in range(1, len(parts) - 2, 3):
        member_id, link_no, block = parts[i], parts[i + 1], parts[i + 2]
        if link_no not in ("1", "2"):
            continue
        links = result.setdefault(member_id, _empty_links())
        ports = []
        status = "N/A"
        for row in re.finditer(r"(?m)^[ \t]*(\d+/\d+(?:/\d+)?)[ \t]+(\S+)", block):
            ports.append(row.group(1))
            if status == "N/A":
                status = row.group(2).rstrip(":")
        if ports:
            links[f"link{link_no}_port"] = ",".join(ports)
            links[f"link{link_no}_status"] = status
    return result


def parse_boot_images(platform, images_text="", flash_text="", version_text=""):
    """EN: Read the primary/secondary image version and the active boot image.
        AOS-CX: 'show images' lists the versions under the sections "... Primary Image" /
        "... Secondary Image"; the running image is in "Active Image : primary|secondary"
        (fallback: "Default Image : ...").
        AOS-S: 'show flash' gives one line "Primary Image : <size> <date> <version>"; the
        booted image is "Boot Image : Primary|Secondary" in 'show version'
        (fallback: "Default Boot : ..." from 'show flash').
    DE: Liest die Primary-/Secondary-Image-Version und das aktive Boot-Image aus (Quellen s. o.).
    """
    info = {"primary_image": "N/A", "secondary_image": "N/A", "active_boot_image": "N/A"}
    if platform == "AOS-CX":
        for key, anchor in (("primary_image", "Primary Image"), ("secondary_image", "Secondary Image")):
            match = re.search(anchor + r"[\s\S]{0,200}?Version[ \t]*:[ \t]*(\S+)", images_text, re.I)
            if match:
                info[key] = match.group(1).strip()
        active = re.search(r"(?im)^[ \t]*Active Image[ \t]*:[ \t]*(\S+)", images_text) \
            or re.search(r"(?im)^[ \t]*Default Image[ \t]*:[ \t]*(\S+)", images_text)
        if active:
            info["active_boot_image"] = active.group(1).strip()
    elif platform == "AOS-S":
        for key, anchor in (("primary_image", "Primary Image"), ("secondary_image", "Secondary Image")):
            match = re.search(anchor + r"[ \t]*:[ \t]*\d+[ \t]+\S+[ \t]+(\S+)", flash_text, re.I)
            if match:
                info[key] = match.group(1).strip()
        active = re.search(r"(?im)^[ \t]*Boot Image[ \t]*:[ \t]*(\S+)", version_text) \
            or re.search(r"(?im)^[ \t]*Default Boot[ \t]*:[ \t]*(\S+)", flash_text)
        if active:
            info["active_boot_image"] = active.group(1).strip()
    return info


def parse_hostname(system_text):
    """EN: Read the actual configured device name from 'show system' - 'Hostname' on AOS-CX,
        'System Name' on AOS-S. The 'Name' value in 'show vsf detail' is only the VSF domain
        name and does not necessarily match the configured hostname.
    DE: Liest den konfigurierten Geraetenamen aus 'show system' - 'Hostname' bei AOS-CX,
        'System Name' bei AOS-S. Der 'Name'-Wert in 'show vsf detail' ist nur der VSF-Domainname.
    """
    match = re.search(r"(?:Hostname|System Name)[ \t]*:[ \t]*(.*)", system_text)
    return match.group(1).strip() if match and match.group(1).strip() else None


# EN: Member Status values that count as "member present/active" (AOS-CX + AOS-S).
# DE: Member-Status-Werte, die als "Member vorhanden/aktiv" gelten (AOS-CX + AOS-S).
_PRESENT_STATES = {"conductor", "commander", "standby", "member", "secondary", "active"}

# EN: VSF link states that indicate a real fault (e.g. AOS-CX state "error" with status code
#     T = peer timed out). A plain "down" on an unused chain-end link is normal and is NOT a fault.
# DE: VSF-Link-Zustaende, die einen echten Fehler anzeigen (z. B. AOS-CX-State "error" bei
#     Status-Code T = Peer timed out). Ein reines "down" auf einem ungenutzten Kettenende zaehlt nicht.
_LINK_ERROR_RE = re.compile(r"err|fault|fail|loop|incompat|inconsist|mismatch", re.I)


def _has_link_error(members):
    for member in members:
        for key in ("vsf_link1_status", "vsf_link2_status"):
            value = str(member.get(key, "")).strip()
            if value and value != "N/A" and _LINK_ERROR_RE.search(value):
                return True
    return False


def derive_vsf_health(result):
    """EN: Derive the overall stack state from platform / error / members / VSF links.
        - "offline"  : switch unreachable, error reported, or no member active
        - "degraded" : at least one member active, but
                       * not all listed members present (e.g. a "Not Present" slot), OR
                       * at least one VSF link in a fault state (error / loop / timeout / incompat)
        - "healthy"  : all listed members active and no VSF link in a fault state
    DE: Leitet den Gesamtzustand des Stacks aus platform / error / members / VSF-Links ab.
        - "offline"  : Switch nicht erreichbar, Fehler gemeldet, oder kein Member aktiv
        - "degraded" : mind. ein Member aktiv, aber nicht alle Member vorhanden ODER
                       mind. ein VSF-Link im Fehlerzustand
        - "healthy"  : alle gelisteten Member aktiv und kein VSF-Link im Fehlerzustand
    """
    if result.get("platform") not in ("AOS-CX", "AOS-S") or result.get("error"):
        return "offline"
    members = result.get("members") or []
    if not members:
        return "offline"
    present = [m for m in members if str(m.get("status", "")).strip().lower() in _PRESENT_STATES]
    if not present:
        return "offline"
    if len(present) != len(members) or _has_link_error(members):
        return "degraded"
    return "healthy"


def main():
    """EN: Always prints exactly one JSON object to stdout (even on errors), never an exception.
    DE: Gibt immer genau ein JSON-Objekt auf stdout aus (auch bei Fehlern), nie eine Exception.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    # EN: --host may be a DNS name (see inventory.example.yml). For the "ip" column the address is
    #     resolved: first via DNS (also works for offline hosts), then - after a successful SSH
    #     connect - replaced with the peer IP actually used.
    # DE: --host kann ein DNS-Name sein (siehe inventory.example.yml). Fuer die "ip"-Spalte wird die
    #     Adresse aufgeloest: erst per DNS (auch fuer offline-Hosts), nach erfolgreichem SSH-Connect
    #     zusaetzlich mit der tatsaechlich verwendeten Peer-IP ueberschrieben.
    try:
        resolved_ip = socket.gethostbyname(args.host)
    except OSError:
        resolved_ip = args.host

    result = {
        "platform": "unreachable",
        "hostname": None,
        "ip": resolved_ip,
        "members": [],
        # EN: stack-wide boot/image info (same for every member of the switch).
        # DE: stack-weite Boot-/Image-Infos (fuer jeden Member desselben Switches gleich).
        "primary_image": "N/A",
        "secondary_image": "N/A",
        "active_boot_image": "N/A",
        # EN: overall stack state - set right at the end. / DE: Gesamtzustand - wird ganz am Ende gesetzt.
        "vsf_health": "offline",
        "error": None,
    }
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            args.host,
            username=args.user,
            password=args.password,
            look_for_keys=False,
            allow_agent=False,
            timeout=args.timeout,
        )
        try:
            result["ip"] = client.get_transport().getpeername()[0]
        except Exception:  # noqa: BLE001
            # EN: IP is optional - keep the DNS value as fallback.
            # DE: IP ist optional - DNS-Wert bleibt als Fallback.
            pass
        # EN: A large PTY height prevents "-- MORE --" pagination on long outputs.
        # DE: Grosse PTY-Hoehe verhindert "-- MORE --"-Pagination bei langen Ausgaben.
        chan = client.invoke_shell(term="vt100", width=220, height=1000)
        time.sleep(1.5)
        if chan.recv_ready():
            chan.recv(65535)
        # EN: Answers the AOS-S "Press any key to continue" splash screen if present.
        # DE: Beantwortet ggf. den "Press any key to continue"-Startbildschirm von AOS-S.
        chan.send("\r")
        time.sleep(1.0)
        if chan.recv_ready():
            chan.recv(65535)

        version_output = run_command(chan, "show version")
        result["platform"] = detect_platform(version_output)

        result["hostname"] = parse_hostname(run_command(chan, "show system"))

        detail_output = run_command(chan, "show vsf detail")
        if re.search(r"invalid input|unrecognized command|incomplete input", detail_output, re.I):
            result["error"] = "No VSF feature available on this switch"
        else:
            result["members"] = parse_vsf_members(detail_output)
            # EN: Physical VSF link ports/status per member from 'show vsf link detail'
            #     (same command for AOS-CX and AOS-S, see parse_vsf_links).
            # DE: Physische VSF-Link-Ports/-Status je Member aus 'show vsf link detail'
            #     (gleicher Befehl fuer AOS-CX und AOS-S, siehe parse_vsf_links).
            links_by_member = parse_vsf_links(run_command(chan, "show vsf link detail"))
            for member in result["members"]:
                link = links_by_member.get(member["member_id"], {})
                member["vsf_link1_port"] = link.get("link1_port", "N/A")
                member["vsf_link1_status"] = link.get("link1_status", "N/A")
                member["vsf_link2_port"] = link.get("link2_port", "N/A")
                member["vsf_link2_status"] = link.get("link2_status", "N/A")

        # EN: Determine primary/secondary/active boot image (platform-specific command).
        # DE: Primary-/Secondary-/aktives Boot-Image ermitteln (plattformspezifischer Befehl).
        if result["platform"] == "AOS-CX":
            result.update(parse_boot_images(
                "AOS-CX", images_text=run_command(chan, "show images"), version_text=version_output))
        elif result["platform"] == "AOS-S":
            result.update(parse_boot_images(
                "AOS-S", flash_text=run_command(chan, "show flash"), version_text=version_output))
    except Exception as exc:  # noqa: BLE001
        # EN: The result must always come back as JSON. / DE: Das Ergebnis soll immer als JSON zurueckkommen.
        result["error"] = str(exc)
    finally:
        client.close()

    # EN: Derive the overall state only here, once platform/error/members are final.
    # DE: Gesamtzustand erst hier ableiten, wenn platform/error/members final sind.
    result["vsf_health"] = derive_vsf_health(result)

    print(json.dumps(result))


if __name__ == "__main__":
    sys.exit(main())
