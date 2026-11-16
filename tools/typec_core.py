"""Read the USB Type-C / USB PD state of this machine.

Sysfs only. The privileged per-offset walk lives in ucsi_walk.py and is
optional; nothing here writes to the UCSI mailbox.

Layout this targets: Linux 6.19 typec class (drivers/usb/typec/{class,pd}.c).
Missing files are reported as missing, never guessed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

TYPEC = "/sys/class/typec"
DMI = "/sys/class/dmi/id"
UCSI_DEVICE = "USBC000:00"
UCSI_DRIVER = "/sys/bus/platform/drivers/ucsi_acpi"
USB_DEVICES = "/sys/bus/usb/devices"

# attributes a PDO object can carry, per drivers/usb/typec/pd.c
PDO_ATTRS = (
    "voltage",
    "maximum_current",
    "operational_current",
    "peak_current",
    "maximum_voltage",
    "minimum_voltage",
    "maximum_power",
    "operational_power",
    "pps_power_limited",
    "dual_role_power",
    "dual_role_data",
    "unconstrained_power",
    "usb_communication_capable",
    "usb_suspend_supported",
    "higher_capability",
    "fast_role_swap_current",
    "unchunked_extended_messages_supported",
)

_UNIT = {"mV": 1, "V": 1000, "mA": 1, "A": 1000, "mW": 1, "W": 1000}
_VALUE = re.compile(r"^\s*(-?\d+)\s*(mV|mA|mW|V|A|W)\s*$")


def read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(path: str) -> Optional[int]:
    value = read(path)
    try:
        return int(value, 0) if value is not None else None
    except ValueError:
        return None


def exists(path: str) -> bool:
    return os.path.exists(path)


def to_milli(value: Optional[str]) -> Optional[int]:
    """'5000mV' -> 5000, '3.25A' -> 3250, '15W' -> 15000."""
    if not value:
        return None
    match = _VALUE.match(value)
    if not match:
        try:
            return int(value)
        except ValueError:
            return None
    return int(match.group(1)) * _UNIT[match.group(2)]


def volts(mv: Optional[int]) -> Optional[float]:
    return None if mv is None else mv / 1000.0


def amps(ma: Optional[int]) -> Optional[float]:
    return None if ma is None else ma / 1000.0


def watts(mw: Optional[int]) -> Optional[float]:
    return None if mw is None else mw / 1000.0


# --------------------------------------------------------------------------
# PDO decoding (used for the debugfs walk; sysfs already carries the numbers)


def decode_pdo(raw: int) -> dict:
    """Decode one 32-bit PDO the way include/linux/usb/pd.h does."""
    kind = (raw >> 30) & 0x3
    out: dict = {"raw": raw}

    if kind == 0:  # fixed supply
        out.update(
            kind="fixed_supply",
            voltage_mv=((raw >> 10) & 0x3FF) * 50,
            maximum_current_ma=(raw & 0x3FF) * 10,
            dual_role_power=(raw >> 29) & 1,
            dual_role_data=(raw >> 28) & 1,
            unconstrained_power=(raw >> 27) & 1,
            usb_communication_capable=(raw >> 26) & 1,
            usb_suspend_supported=(raw >> 25) & 1,
        )
    elif kind == 1:  # battery
        out.update(
            kind="battery",
            maximum_voltage_mv=((raw >> 10) & 0x3FF) * 50,
            maximum_power_mw=(raw & 0x3FF) * 250,
        )
    elif kind == 2:  # variable supply
        out.update(
            kind="variable_supply",
            maximum_voltage_mv=((raw >> 10) & 0x3FF) * 50,
            maximum_current_ma=(raw & 0x3FF) * 10,
        )
    else:  # APDO
        if (raw >> 28) & 0x3 == 0:  # PPS
            out.update(
                kind="pps",
                maximum_voltage_mv=((raw >> 17) & 0xFF) * 100,
                minimum_voltage_mv=((raw >> 8) & 0xFF) * 100,
                maximum_current_ma=(raw & 0x7F) * 50,
                pps_power_limited=(raw >> 27) & 1,
            )
        else:
            out.update(kind="apdo", unknown=True)

    mw = None
    if out.get("maximum_power_mw") is not None:
        mw = out["maximum_power_mw"]
    elif out.get("voltage_mv") is not None and out.get("maximum_current_ma") is not None:
        mw = out["voltage_mv"] * out["maximum_current_ma"] // 1000
    elif out.get("maximum_voltage_mv") is not None and out.get("maximum_current_ma") is not None:
        mw = out["maximum_voltage_mv"] * out["maximum_current_ma"] // 1000
    out["maximum_power_mw"] = mw
    return out


def decode_rdo(raw: int) -> dict:
    """Decode a fixed-supply Request Data Object."""
    operating = (raw >> 10) & 0x3FF
    maximum = raw & 0x3FF
    return {
        "raw": raw,
        "position": (raw >> 28) & 0x7,
        "give_back": bool((raw >> 27) & 1),
        "capability_mismatch": bool((raw >> 26) & 1),
        "usb_communication_capable": bool((raw >> 25) & 1),
        "usb_suspend_supported": not ((raw >> 24) & 1),
        "operating_current_ma": operating * 10,
        "maximum_current_ma": maximum * 10,
    }


# --------------------------------------------------------------------------
# sysfs model


@dataclass
class Pdo:
    position: int
    kind: str
    attrs: dict = field(default_factory=dict)
    source: str = "sysfs"  # or "walk"
    raw: Optional[int] = None

    @property
    def voltage_mv(self) -> Optional[int]:
        for key in ("voltage", "maximum_voltage"):
            if self.attrs.get(key) is not None:
                return self.attrs[key]
        if self.raw is not None:
            return decode_pdo(self.raw).get("voltage_mv") or decode_pdo(self.raw).get(
                "maximum_voltage_mv"
            )
        return None

    @property
    def minimum_voltage_mv(self) -> Optional[int]:
        if self.attrs.get("minimum_voltage") is not None:
            return self.attrs["minimum_voltage"]
        return decode_pdo(self.raw).get("minimum_voltage_mv") if self.raw is not None else None

    @property
    def current_ma(self) -> Optional[int]:
        for key in ("maximum_current", "operational_current"):
            if self.attrs.get(key) is not None:
                return self.attrs[key]
        if self.raw is not None:
            return decode_pdo(self.raw).get("maximum_current_ma")
        return None

    @property
    def power_mw(self) -> Optional[int]:
        if self.attrs.get("maximum_power") is not None:
            return self.attrs["maximum_power"]
        if self.raw is not None:
            return decode_pdo(self.raw).get("maximum_power_mw")
        if self.voltage_mv is not None and self.current_ma is not None:
            return self.voltage_mv * self.current_ma // 1000
        return None

    def label(self) -> str:
        parts = []
        lo = self.minimum_voltage_mv
        hi = self.voltage_mv
        if lo is not None and hi is not None and lo != hi:
            parts.append(f"{volts(lo):.2f}-{volts(hi):.2f} V")
        elif hi is not None:
            parts.append(f"{volts(hi):.2f} V")
        if self.current_ma is not None:
            parts.append(f"{amps(self.current_ma):.2f} A")
        if self.power_mw:
            parts.append(f"{watts(self.power_mw):.1f} W")
        return " · ".join(parts) if parts else "undecoded"


def read_caps(pd_dir: str, role: str) -> list[Pdo]:
    base = os.path.join(pd_dir, f"{role}-capabilities")
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return []
    out = []
    for entry in entries:
        path = os.path.join(base, entry)
        if not os.path.isdir(path) or entry in ("power", "uevent"):
            continue
        position, _, kind = entry.partition(":")
        attrs = {}
        for name in PDO_ATTRS:
            raw = read(os.path.join(path, name))
            if raw is None:
                continue
            parsed = to_milli(raw)
            attrs[name] = parsed if parsed is not None else raw
        try:
            pos = int(position)
        except ValueError:
            pos = 0
        out.append(Pdo(position=pos, kind=kind or "unknown", attrs=attrs))
    return out


@dataclass
class Partner:
    name: str
    pd_supported: str
    pd_revision: str
    alt_modes: int
    source: list[Pdo] = field(default_factory=list)
    sink: list[Pdo] = field(default_factory=list)


@dataclass
class Port:
    name: str
    number: int
    power_role: str
    data_role: str
    opmode: str
    typec_revision: str
    pd_revision: str
    partner: Optional[Partner] = None
    cable: Optional[str] = None
    local_source: list[Pdo] = field(default_factory=list)
    sink_caps: list[Pdo] = field(default_factory=list)
    walk_source: Optional[list[Pdo]] = None
    walk_local: Optional[list[Pdo]] = None
    rdo: Optional[dict] = None

    @property
    def label(self) -> str:
        return f"{self.name} — connector {self.number}"

    @property
    def attached(self) -> bool:
        return self.partner is not None


def _read_partner(port_name: str, number: int) -> Optional[Partner]:
    base = os.path.join(TYPEC, f"{port_name}-partner")
    if not os.path.isdir(base):
        return None
    revision = read(os.path.join(base, "usb_power_delivery", "revision")) or "—"
    alt = read(os.path.join(base, "number_of_alternate_modes"))
    return Partner(
        name=f"{port_name}-partner",
        pd_supported=read(os.path.join(base, "supports_usb_power_delivery")) or "—",
        pd_revision=revision,
        alt_modes=int(alt) if alt and alt.isdigit() else 0,
        source=read_caps(os.path.join(base, "usb_power_delivery"), "source"),
        sink=read_caps(os.path.join(base, "usb_power_delivery"), "sink"),
    )


def _read_port(name: str, number: int) -> Port:
    base = os.path.join(TYPEC, name)
    pd_dir = os.path.join(base, "usb_power_delivery")
    cable_dir = os.path.join(TYPEC, f"{name}-cable")
    cable = None
    if os.path.isdir(cable_dir):
        cable = read(os.path.join(cable_dir, "type")) or "present"
    return Port(
        name=name,
        number=number,
        power_role=read(os.path.join(base, "power_role")) or "—",
        data_role=read(os.path.join(base, "data_role")) or "—",
        opmode=read(os.path.join(base, "power_operation_mode")) or "—",
        typec_revision=read(os.path.join(base, "usb_typec_revision")) or "—",
        pd_revision=read(os.path.join(pd_dir, "revision")) or "—",
        partner=_read_partner(name, number),
        cable=cable,
        local_source=read_caps(pd_dir, "source"),
        sink_caps=read_caps(pd_dir, "sink"),
    )


def read_ports() -> list[Port]:
    ports = []
    try:
        entries = os.listdir(TYPEC)
    except OSError:
        return ports
    numbers = sorted(
        (int(m.group(1)), name)
        for name in entries
        if (m := re.fullmatch(r"port(\d+)", name))
    )
    for index, (_, name) in enumerate(numbers, start=1):
        ports.append(_read_port(name, index))
    return ports


def read_usb_devices() -> list[dict]:
    out = []
    try:
        entries = os.listdir(USB_DEVICES)
    except OSError:
        return out
    for name in sorted(entries):
        base = os.path.join(USB_DEVICES, name)
        vendor = read(os.path.join(base, "idVendor"))
        if not vendor:
            continue  # interface or root hub without a driver bound
        out.append(
            {
                "name": name,
                "id": f"{vendor}:{read(os.path.join(base, 'idProduct')) or '????'}",
                "product": read(os.path.join(base, "product")) or "",
                "manufacturer": read(os.path.join(base, "manufacturer")) or "",
                "speed": read(os.path.join(base, "speed")) or "",
            }
        )
    return out


@dataclass
class Machine:
    vendor: str
    model: str
    family: str
    bios: str
    kernel: str
    ucsi_present: bool
    driver_bound: bool
    ports: list[Port]
    usb_devices: list[dict]
    taint: Optional[int]


def probe() -> Machine:
    return Machine(
        vendor=read(os.path.join(DMI, "sys_vendor")) or "—",
        model=read(os.path.join(DMI, "product_name")) or "—",
        family=read(os.path.join(DMI, "product_family")) or "—",
        bios=read(os.path.join(DMI, "bios_version")) or "—",
        kernel=os.uname().release,
        ucsi_present=exists(f"/sys/bus/platform/devices/{UCSI_DEVICE}"),
        driver_bound=exists(f"/sys/bus/platform/devices/{UCSI_DEVICE}/driver"),
        ports=read_ports(),
        usb_devices=read_usb_devices(),
        taint=read_int("/proc/sys/kernel/tainted"),
    )


# --------------------------------------------------------------------------
# optional privileged walk


def walk_helper_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ucsi_walk.py")


def run_walk(timeout: float = 30.0) -> tuple[bool, object]:
    """Run the per-offset walk. Returns (ok, data-or-message).

    Direct call when already root, pkexec otherwise.
    """
    import subprocess

    helper = walk_helper_path()
    if not os.path.exists(helper):
        return False, f"helper not found: {helper}"
    cmd = [helper] if os.geteuid() == 0 else ["pkexec", helper]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, detail[-1] if detail else f"exit {proc.returncode}"
    try:
        return True, json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return False, f"unreadable walk output: {exc}"


def apply_walk(ports: list[Port], data: dict) -> None:
    """Merge ucsi_walk.py output into the port model, in place."""
    for entry in data.get("connectors", []):
        number = entry.get("connector")
        port = next((p for p in ports if p.number == number), None)
        if port is None:
            continue
        if entry.get("rdo") is not None:
            port.rdo = entry["rdo"]
        if entry.get("partner_pdos"):
            port.walk_source = [
                Pdo(
                    position=i + 1,
                    kind=decode_pdo(v).get("kind", "unknown"),
                    source="walk",
                    raw=v,
                )
                for i, v in enumerate(entry["partner_pdos"])
            ]
        if entry.get("local_pdos"):
            port.walk_local = [
                Pdo(
                    position=i + 1,
                    kind=decode_pdo(v).get("kind", "unknown"),
                    source="walk",
                    raw=v,
                )
                for i, v in enumerate(entry["local_pdos"])
            ]


# --------------------------------------------------------------------------
# text rendering, used by --text and by the GUI self-test


def _pdo_lines(pdos: list[Pdo], in_use: Optional[int] = None) -> list[str]:
    lines = []
    for pdo in pdos:
        mark = "  ← in use" if in_use and pdo.position == in_use else ""
        lines.append(f"    {pdo.position}  {pdo.label()}{mark}")
    return lines


def describe(machine: Machine) -> str:
    lines = [
        f"{machine.vendor} {machine.family} ({machine.model}) · BIOS {machine.bios}",
        f"kernel {machine.kernel} · ucsi_acpi {'bound' if machine.driver_bound else 'not bound'}"
        f" · {len(machine.ports)} port(s)",
    ]
    if not machine.ports:
        lines += [
            "",
            "no Type-C ports registered.",
            "  ACPI device  USBC000:00 present" if machine.ucsi_present else "  ACPI device  missing",
            "  driver       ucsi_acpi not bound",
            "",
            "This is the VERSION 0x0000 defect: ucsi_register() returns -ENODEV silently.",
            "Check: sudo ./scripts/10-dump-ucsi.sh",
            "Bind:  sudo ./scripts/15-build-quirk.sh   (no firmware write)",
        ]
        return "\n".join(lines)

    for port in machine.ports:
        in_use = port.rdo["position"] if port.rdo else None
        lines += [
            "",
            f"{port.label}   {port.power_role} · PD {port.pd_revision} · {port.opmode}",
        ]
        if port.partner:
            lines.append(
                f"  partner      PD {port.partner.pd_supported}"
                f" · revision {port.partner.pd_revision}"
                f" · {port.partner.alt_modes} alt mode(s)"
            )
        else:
            lines.append("  partner      none")
        lines.append(f"  cable        {port.cable or 'none (no e-marker object)'}")
        if port.rdo:
            rdo = port.rdo
            obj = next(
                (c for c in (port.walk_source or []) if c.position == rdo["position"]),
                None,
            )
            current = rdo["operating_current_ma"] / 1000
            piece = f"positions {rdo['position']} · {current:.2f} A"
            if obj and obj.voltage_mv:
                voltage = obj.voltage_mv / 1000
                piece = f"position {rdo['position']} · {voltage:.2f} V / {current:.2f} A" \
                        f" = {voltage * current:.1f} W"
            lines.append(
                f"  negotiated   RDO 0x{rdo['raw']:08X} · {piece}"
                + (" · capability mismatch" if rdo["capability_mismatch"] else "")
            )
        if port.partner and port.partner.source:
            lines.append(f"  source PDOs (sysfs, {len(port.partner.source)})")
            lines += _pdo_lines(port.partner.source, in_use)
        if port.walk_source:
            lines.append(f"  source PDOs (firmware walk, {len(port.walk_source)})")
            lines += _pdo_lines(port.walk_source, in_use)
            if port.partner and len(port.walk_source) > len(port.partner.source):
                lines.append(
                    f"  ! sysfs exposes {len(port.partner.source)} of "
                    f"{len(port.walk_source)} — short GET_PDOS reply"
                )
        if not port.partner and not port.walk_source:
            lines.append("  nothing attached")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    machine = probe()
    as_json = "--json" in argv
    if as_json:
        payload = {
            "machine": {
                "vendor": machine.vendor,
                "model": machine.model,
                "family": machine.family,
                "bios": machine.bios,
                "kernel": machine.kernel,
                "ucsi_present": machine.ucsi_present,
                "driver_bound": machine.driver_bound,
                "taint": machine.taint,
            },
            "ports": [
                {
                    "name": p.name,
                    "number": p.number,
                    "power_role": p.power_role,
                    "data_role": p.data_role,
                    "opmode": p.opmode,
                    "typec_revision": p.typec_revision,
                    "pd_revision": p.pd_revision,
                    "cable": p.cable,
                    "partner": None
                    if not p.partner
                    else {
                        "pd_supported": p.partner.pd_supported,
                        "pd_revision": p.partner.pd_revision,
                        "alt_modes": p.partner.alt_modes,
                        "source_capabilities": [
                            {"position": c.position, "kind": c.kind, "label": c.label()}
                            for c in p.partner.source
                        ],
                    },
                }
                for p in machine.ports
            ],
            "usb_devices": machine.usb_devices,
        }
        print(json.dumps(payload, indent=2))
        return 0
    if "--walk" in argv:
        ok, data = run_walk()
        if ok:
            apply_walk(machine.ports, data)
        else:
            print(f"walk failed: {data}")
    print(describe(machine))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(os.sys.argv[1:]))
