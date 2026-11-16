#!/usr/bin/env python3
"""Read the full PD state through the UCSI debugfs mailbox.

Privileged helper for typec_pd.py, and usable on its own:

    sudo ./ucsi_walk.py            # JSON on stdout
    sudo ./ucsi_walk.py --pretty

Only GET_CONNECTOR_STATUS and GET_PDOS are sent. Read-only, but it does share
the mailbox with ucsi_acpi, so it runs one command at a time.

The debugfs file prints the 16-byte reply as two little-endian u64 fields,
high first (drivers/usb/typec/ucsi/debugfs.c), so the byte order is rebuilt
here rather than trusted from the printed layout.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typec_core import decode_rdo  # noqa: E402

ROOT = "/sys/kernel/debug/usb/ucsi"
GET_PDOS = 0x10
GET_CONNECTOR_STATUS = 0x12
MAX_OFFSET = 7


def device_dir() -> str:
    candidates = sorted(glob.glob(os.path.join(ROOT, "*")))
    for path in candidates:
        if os.path.exists(os.path.join(path, "command")):
            return path
    raise SystemExit(
        f"no UCSI debugfs device under {ROOT}\n"
        "ucsi_acpi must be bound and debugfs mounted:\n"
        "  sudo mount -t debugfs none /sys/kernel/debug"
    )


def send(directory: str, command: int) -> bytes:
    """Send one UCSI command, return the 16-byte reply."""
    cmd_path = os.path.join(directory, "command")
    rsp_path = os.path.join(directory, "response")
    last: Exception | None = None
    for attempt in range(3):
        try:
            with open(cmd_path, "w", encoding="ascii") as f:
                f.write(f"0x{command:016x}\n")
            with open(rsp_path, "r", encoding="ascii") as f:
                text = f.read().strip()
            break
        except OSError as exc:  # device busy or command rejected
            last = exc
            time.sleep(0.25 * (attempt + 1))
    else:
        raise RuntimeError(f"command 0x{command:x} failed: {last}")

    if text.startswith("0x"):
        text = text[2:]
    text = text.rjust(32, "0")
    high = int(text[:16], 16)
    low = int(text[16:], 16)
    return low.to_bytes(8, "little") + high.to_bytes(8, "little")


def connector_status(directory: str, connector: int) -> dict | None:
    reply = send(directory, GET_CONNECTOR_STATUS | (connector << 16))
    rdo = int.from_bytes(reply[4:8], "little")
    if rdo == 0:
        return None
    decoded = decode_rdo(rdo)
    decoded["connection_status_change"] = reply[0]
    decoded["power_operation_mode"] = reply[1]
    decoded["power_direction"] = reply[2]
    return decoded


def pdos(directory: str, connector: int, partner: bool, source: bool) -> list[int]:
    out = []
    for offset in range(MAX_OFFSET):
        command = GET_PDOS | (connector << 16) | (int(partner) << 23)
        command |= offset << 24
        command |= 1 << 34 if source else 0
        reply = send(directory, command)
        vdo = int.from_bytes(reply[0:4], "little")
        if not vdo:
            break
        out.append(vdo)
    return out


def connectors() -> list[int]:
    found = []
    for name in os.listdir("/sys/class/typec"):
        if name.startswith("port") and name[4:].isdigit():
            found.append(int(name[4:]) + 1)  # port0 is UCSI connector 1
    return sorted(found) or [1, 2]


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        print("run as root: sudo ./ucsi_walk.py", file=sys.stderr)
        return 1

    directory = device_dir()
    result: dict = {"device": os.path.basename(directory), "connectors": []}
    errors = []

    for connector in connectors():
        entry: dict = {"connector": connector}
        try:
            entry["rdo"] = connector_status(directory, connector)
        except RuntimeError as exc:
            entry["rdo"] = None
            errors.append(str(exc))
        try:
            # GET_PDOS with the Src flag set, partner bit selects the far end
            entry["partner_pdos"] = pdos(directory, connector, True, True)
            entry["local_pdos"] = pdos(directory, connector, False, True)
        except RuntimeError as exc:
            entry.setdefault("partner_pdos", [])
            entry.setdefault("local_pdos", [])
            errors.append(str(exc))
        result["connectors"].append(entry)

    if errors:
        result["errors"] = errors

    indent = 2 if "--pretty" in argv else None
    print(json.dumps(result, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
