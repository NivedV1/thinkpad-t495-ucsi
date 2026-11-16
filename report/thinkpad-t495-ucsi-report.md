# ThinkPad T495 (20NK) — firmware reports UCSI VERSION 0x0000 and returns one PDO per GET_PDOS request

**Machine:** 20NKS29V00 · BIOS `R12ET64W (1.34)`, 2024-02-23

**Subject:** The UCSI VERSION register reads `0x0000`, so Linux `ucsi_acpi` refuses to bind (`-ENODEV`) and no Type-C ports exist. The same firmware works under Windows, which accepts version 0.0.0 and completes every UCSI command. Once Linux is forced past the version check, a second defect appears: `GET_PDOS` ignores the requested PDO count and returns exactly one PDO, so Linux sees only the first entry of a four-entry source capability list. That single short read produces the 0 V / 5 V / 3.25 A values that make the port look impossible; it is not a negotiated contract. Two further defects are visible on both operating systems: the local source PDOs are invalid, and connector 1 keeps reporting the same change bits.

**Raw captures and reproduction scripts:** https://github.com/NivedV1/thinkpad-t495-ucsi

## Summary

The ACPI firmware exposes a UCSI device (`_HID USBC000` / `_CID PNP0CA0`) with a valid register block at `0xBD6B2000` and two Type-C connectors. The UCSI **VERSION register reads 0x0000**. `ucsi_register()` treats version 0 as unusable and returns `-ENODEV` before registering any connector, so `/sys/class/typec/` is empty and no UCSI functionality is available in Linux.

This is the same defect reported for ThinkPad T14 Gen 2a (AMD) on linux-usb in April 2026 and confirmed by the UCSI maintainer as a Lenovo firmware bug.

**Windows runs the same firmware.** On a Windows 11 install on this machine, `UcmUcsiAcpiClient.sys` binds to `ACPI\USBC000\0`, PnP reports status OK, and every UCSI command completes while both the PPM and the client driver print version `0.0.0`. The device is therefore alive; the zero version is a gate in Linux, not a dead interface.

Forcing the version in Linux (RAM-only test) reveals the second defect:

- **`GET_PDOS` always returns one PDO.** A request for four PDOs returns `CCI DataLength: 4` and one DWORD; offsets 0–3 read individually return the full four-entry list. Windows sees 5 V, 9 V, 15 V and 20 V; Linux sees only 5 V / 3 A.
- `ucsi_get_pdos()` treats that one-PDO reply as the whole list (`num_pdos = 1`) and never asks for offsets 1–3. `voltage_now`, `voltage_max` and `current_max` are then computed from the truncated list, which is why Linux reports `0 V`, `5000 mV` and `3000 mA` while `current_now` comes from the RDO and reads `3250 mA`.
- The **RDO is correct**: `0x43051545` selects object position 4 (20 V) at 3.25 A = 65 W, matching the attached adapter's own PDO 4. The battery draws ~17 W, well within that contract.
- Both ports report **invalid local source PDOs** — `0 mV / 0 mA` on connector 1 and `1050 mV / 2560 mA` on connector 2 — in Linux and Windows alike. This is a separate firmware defect.
- Connector 1 reports `ConnectChange` and `NegotiatedPowerLevelChange` (status-change bits `0x4040`) in every capture; connector 2 reports `0x0000`, on both operating systems.
- PD object creation is timing-dependent: the partner's `supports_usb_power_delivery` is sampled once at registration, and the PD object can link seconds later or, occasionally, never.
- Connector numbering is **inverted** relative to ACPI and the kernel's own port links.
- The connector-status response is 9 bytes; the orientation bit (bit 86) is never included, so orientation cannot be read on either OS.

USB data and 5 V charging work, because the EC handles those independently of UCSI.

## System information

| Item | Value |
|---|---|
| Model | Lenovo ThinkPad T495, `20NKS29V00` |
| BIOS | `R12ET64W (1.34)`, 2024-02-23 |
| CPU | AMD Ryzen 5 PRO 3500U (Picasso) |
| OS (Linux) | Fedora 44, kernel `6.19.10-300.fc44.x86_64` |
| OS (Windows) | Windows 11 Pro, build 26300 |
| Secure Boot / lockdown | disabled / `none` |
| Modules | `ucsi_acpi`, `typec_ucsi`, `typec` (loaded; no device bound by default) |

## 1. Firmware interface as declared (SSDT)

- `\_SB.UBTC`: `_HID "USBC000"`, `_CID "PNP0CA0"`, `_UID 0`, `_DDN "USB Type C"`
- `_CRS`: `Memory32Fixed 0xBD6B2000`, length `0x1000`
- `OperationRegion (USBC, SystemMemory, 0xBD6B2000, 0x30)` — standard UCSI layout (`VER`, `CCI`, `CTL`, `MGI`, `MGO`)
- Connectors: `CR01` `_ADR 0x05`, `CR02` `_ADR 0x08`, both `_UPC {0xFF, 0x09, 0x00, 0x00}`
- `_DSM` for UCSI UUID `6f8398c2-7ca4-11e4-ad36-631042b5008f`: function 0 → `0x0F`, function 1 → `ECWR()`, function 2 → `ECRD()`
- `ECWR`/`ECRD` use the ThinkPad `UBSY` mutex and the EC mailbox (`EC0`, registers `0x50`–`0x74`)

The interface is present and the `_DSM` works. Only the VERSION field is zero.

## 2. VERSION 0x0000 blocks binding in Linux

```text
$ cat /sys/bus/platform/devices/USBC000:00/modalias
acpi:USBC000:PNP0CA0:
$ ls /sys/class/typec/
(empty)
```

No UCSI message appears in dmesg — probe fails silently. A forced bind fails:

```text
$ sudo sh -c 'echo USBC000:00 > /sys/bus/platform/drivers/ucsi_acpi/bind'
sh: line 1: echo: write error: No such device
```

kprobes on the probe path:

```text
ucsi_probe:     (ucsi_acpi_probe+0x4/0x210 [ucsi_acpi])
r_ver:          (ucsi_register+0x1d/0xa0 [typec_ucsi] <- ucsi_acpi_read_version) arg1=0
r_reg:          (ucsi_acpi_probe+0x163/0x210 [ucsi_acpi] <- ucsi_register) arg1=-19
ucsi_probe_ret: (platform_probe+0x67/0x90 <- ucsi_acpi_probe) arg1=-19
```

`ucsi_acpi_read_version()` succeeds; the value read is `0x0000`. `ucsi_register()` takes its `version == 0` branch and returns `-ENODEV` before registering a connector. (Reading the region through `/dev/mem` returns 0 bytes under `CONFIG_STRICT_DEVMEM`, so a small out-of-tree module mapped it read-only for the dump.)

### 2.1 The same device works in Windows

Windows 11 on the same machine binds its UCSI client to `ACPI\USBC000\0` and reports:

```text
Status             OK
InstanceId         ACPI\USBC000\0
UCSI VERSION from PPM:                 0.0.0
UCSI VERSION from client driver:       0.0.0
Client driver:                         UcmUcsiAcpiClient.sys
```

Every `GET_CAPABILITY`, `GET_CONNECTOR_CAPABILITY`, `GET_CONNECTOR_STATUS` and `GET_PDOS` command returned `Command completed successfully`. Microsoft's UCSI test tool is the mechanism; it needs the device's diagnostic interface enabled temporarily (`TestInterfaceEnabled=1`), which was restored afterwards. Only `GET_*` commands were sent.

So the zero version does not prevent the platform's own UCSI client from operating. It is rejected only by Linux's `version == 0` check. A DMI quirk in `ucsi_acpi` would let the driver bind; that file already contains one per-model quirk (LG Gram, selecting an alternate ops table), though nothing that touches the version check. The defects in §3 and §6–§8 would remain.

## 3. GET_PDOS returns one PDO per request

Batch request on Windows, connector 1, partner source PDOs:

```text
UCSI_CONTROL:
  Command:          0x10 (GetPdos)
  ConnectorNumber:  1
  SourceOrSinkPdos: 1
  PdoOffset:        0x0
  NumberOfPdos:     3          <- four PDOs requested

UCSI_CCI:
  DataLength:       4          <- four bytes returned

UCSI MESSAGE_IN:
  2c 91 01 0a                  <- PDO 1 only
```

Reading each offset separately returns the full list:

| Offset | `DataLength` | DWORD | Fixed supply |
|---|---|---|---|
| 0 | 4 | `0x0A01912C` | 5 V / 3 A |
| 1 | 4 | `0x0002D12C` | 9 V / 3 A |
| 2 | 4 | `0x0004B12C` | 15 V / 3 A |
| 3 | 4 | `0x0006414F` | 20 V / 3.35 A (67 W Xiaomi) |
| 4 | 0 | — | no further PDOs |

The ThinkPad 65 W adapter returns the same four voltages with PDO 4 = `0x00164145` (20 V / 3.25 A), on both connectors. A request for one, three or four PDOs always returns exactly one; the requested count is ignored. `CCI DataLength` is the only reliable indicator of how many PDOs arrived.

The Linux driver's single read returns the same first DWORD, byte for byte (`0x0A11912C` for the ThinkPad, `0x0A01912C` for the Xiaomi), so the transport and the first PDO are consistent across operating systems.

## 4. What the truncated reply does to Linux

`drivers/usb/typec/ucsi/ucsi.c`, v6.19:

```c
ret = ucsi_read_pdos(con, role, is_partner, pdos, 0, UCSI_MAX_PDOS);
if (ret < 0)
        return ret;

num_pdos = ret / sizeof(u32); /* 4 bytes -> 1 PDO */
if (num_pdos < UCSI_MAX_PDOS)
        return num_pdos;      /* returns 1; offsets 1..3 are never read */

ret = ucsi_read_pdos(con, role, is_partner, pdos, UCSI_MAX_PDOS, ...);
```

`con->num_pdos` becomes 1 and `con->src_pdos[1..3]` remain zero. The power supply then reports values derived from that one entry (`psy.c`):

```c
index = rdo_index(con->rdo);                    /* 4 */
pdo = con->src_pdos[index - 1];                 /* src_pdos[3] == 0 */
val->intval = pdo_fixed_voltage(pdo) * 1000;    /* voltage_now  = 0 uV */

pdo = con->src_pdos[con->num_pdos - 1];         /* src_pdos[0] = 5 V */
val->intval = pdo_max_current(pdo) * 1000;      /* current_max  = 3000 mA */

val->intval = rdo_op_current(con->rdo) * 1000;  /* current_now  = 3250 mA */
```

So the values that look self-contradictory are all one short read: `voltage_now = 0` against a 5 V entry, `voltage_max = 5 V` although the adapter offers 20 V, `current_max = 3 A` although the request is 3.25 A.

One related display is *not* a firmware claim: `usb_type` shows `C [PD] PD_PPS` because `psy.c` hard-codes `usb_types = C | PD | PD_PPS` for every UCSI connector. Only the bracketed element (`PD`) is read from the EC.

## 5. The real contract is 20 V, and the RDO is correct

RDO `0x43051545`:

| Field | Value |
|---|---|
| Object position (bits 31:28) | 4 |
| Operating current (bits 9:0) | 3.25 A |
| Maximum operating current (bits 19:10) | 3.25 A |
| Selected PDO 4 voltage | 20 V |
| Requested power | 65 W |

Both adapters produce this RDO on both connectors:

| Adapter | PDO 4 | RDO | Requested |
|---|---|---|---|
| Lenovo 65 W (label 20 V / 3.25 A, MFG 6/2015) | 20 V / 3.25 A | `0x43051545` | 65 W |
| Xiaomi 67 W, A-to-C | 20 V / 3.35 A | `0x43051545` | 65 W |

Lenovo Vantage independently displays 65 W for the stock adapter and 67 W for the Xiaomi one, matching the advertised PDO 4 in each case.

The battery measurements are consistent with the 20 V contract; a 5 V / 3 A source could not supply them:

```text
Linux    battery 17.37 W at 11.634 V   (1.49 A into the pack)
Windows  battery 16.423 W at 11.875 V  (BatteryStatus WMI)
```

A 5 V / 3 A source (15 W) could not charge the pack at ~17 W while running the system; a 20 V / 3.25 A contract (65 W) has ample headroom. There is no power-conservation paradox once the full PDO list is visible.

The Xiaomi charger is connected by a USB-A-to-USB-C cable and still returns four PDOs and the 20 V request. Its physical signaling is not characterised here, but the EC sees and selects a 20 V profile over that path.

## 6. Invalid local source PDOs

| Port | Linux | Windows |
|---|---|---|
| connector 1 local source | `0 mV / 0 mA` | `0x15000000` |
| connector 2 local source | `1050 mV / 2560 mA` | `0x15005500` |

Both operating systems return the same two DWORDs. The EC's own source-capability list is therefore invalid independently of the driver: `0x15000000` decodes as a fixed supply of 0 V / 0 A, and `0x15005500` as 1.05 V / 2.56 A, which is not a PD voltage. A port advertising these cannot offer a usable source contract, although 5 V sourcing works in practice.

## 7. Identity and alternate modes

- Partner `id_header`, `product` and `product_type` are always empty; no `portN-cable` object is ever created, so no e-marker is read.
- The alternate-mode table contains only SVID `0x17ef` and `0x01ff`, mode 1, `vdo=0x00000001`. DisplayPort's SVID `0xff01` never appears, so DP alt mode cannot register. Whether DP works in Windows has not been tested.
- Partner `usb_power_delivery_revision` reads `0.0` while its PD object reads `2.0`. This is kernel-side: `desc.pd_revision` is only filled at UCSI >= 2.1, and the RAM-patched version is 1.1. It is listed so it is not re-reported.

## 8. Connector 1 keeps reporting the same change bits

The connector-status response is 9 bytes (`CCI DataLength: 9`):

```text
connector 1:  40 40 2b 20 45 15 05 43 01
connector 2:  00 00 00 20 00 00 00 00 01
```

Bytes 0–1 are `ConnectorStatusChange`. Connector 1 returned `0x4040`
(`ConnectChange` and `NegotiatedPowerLevelChange`) on every read, before and
after attach/detach, on both operating systems. Connector 2 returned `0x0000`.
The bits were never observed to clear.

Byte 8 is `BatteryChargingStatus` (`01`). The orientation field is
`UCSI_CONSTAT_ORIENTATION` = bit 86 (byte 10), which is not included in the
9-byte response. **Orientation is therefore unobservable through this
interface**, on either operating system.

## 9. PD presence is a registration-time snapshot

`supports_usb_power_delivery` is set once inside `ucsi_register_partner()` from
the EC's `PWR_OPMODE`; `power_operation_mode` is updated later by
`ucsi_pwr_opmode_change()`. If the EC answers `default` at registration and `PD`
a moment later, the partner keeps `no` for the life of the attach while the port
reports PD.

Four consecutive warm-up attaches of the charger (both connectors) showed the
normal case: `supports_usb_power_delivery = yes` at the instant the partner
appeared, no PD object at t0, the PD object present 8 s later, and RDO
`0x43051545` each time.

One attach did not recover. The 65 W adapter sat on `port1` in one orientation
for eight minutes with `power_operation_mode = usb_power_delivery`,
`supports_usb_power_delivery = no` and no PD object at all; flipping the
connector and re-attaching produced `yes` and a PD object within 2 s. The PD
link is only set after both `GET_PDOS` calls succeed, and the retry task is a
no-op once `con->partner_pd` exists:

```c
con->partner_pd = typec_partner_usb_power_delivery_register(con->partner, &desc);
...
if (con->partner_pd)
        return 0;      /* retry does nothing */
```

So a first failed capability read can leave an orphan PD object permanently.
This is a second-order timing defect; it does not change the contract, and
whenever a PD object exists its list is the truncated one described in §3.

`power_operation_mode` can also remain stale for a second or two after unplug,
but it does return to `default` once the EC settles. It is a transition, not a
permanent leak.

## 10. Connector numbering is inverted

ACPI declares `CR01` `_ADR 5` → UCSI `port0` (fwnode `device:30`) and `CR02`
`_ADR 8` → `port1` (fwnode `device:31`). That mapping is provable from `_PLD`
bytes: `CR02`'s `_PLD` (`71 0C 00 02`) is byte-identical to root-hub `PLD4`,
which `HS04`/`SS04` use, and those enumerate as `usb2-port4`/`usb3-port4`. The
kernel links `usb2-port4`/`usb3-port4` to `port1`, which is therefore correct.

In practice a device on `usb 2-4` creates its partner under **`port0`**, and a
device on `usb 2-1` creates its partner under **`port1`** — the opposite of the
ACPI/kernel wiring, reproducibly, four times (Avocent, Xiaomi charger, phone
twice). Userspace therefore cannot map `/sys/class/typec/portN` to a physical
connector.

Windows confirms the OS-independent part: Linux `port0` is UCSI connector 1 and
`port1` is connector 2 (local source PDOs and change bits match exactly), so the
inversion is between the EC's connector numbers and the ACPI/xHCI wiring, not
between operating systems. Physical front/rear labelling was not recorded.

## 11. Upstream reference

linux-usb, April 2026 — *"[BUG] ucsi_acpi: Fails to bind on USBC000 devices, version=0 in NVS blocks probe"*, ThinkPad T14 Gen 2a (AMD), same modalias, same `-19`:

- https://ratatoskr.run/linux-usb/2026/04/8893642/t
- https://ratatoskr.run/linux-usb/2026/04/8896578/t (follow-up patch thread)

UCSI maintainer Heikki Krogerus:

> "Again with the missing version. Please contact Lenovo. This is a bug in their
> firmware. The version field must supply the actual ucsi version."

Writing `0x0100` into the version field made the driver bind there too, and USB-C display hotplug was reported working. Current mainline has **no Lenovo quirk and no zero-version workaround at all**; the only DMI quirk in `ucsi_acpi.c` is for one LG Gram model and only selects an alternate ops table. T495/T14 Gen 2a users therefore have no automatic fix.

## 12. Request to Lenovo

1. Populate the UCSI VERSION field with the actual UCSI version (e.g. `0x0100`) in a BIOS update for machine type `20NK`, as the UCSI specification requires.
2. Fix `GET_PDOS`: the command must return the number of PDOs requested in `NumberOfPdos` (or at least as many as the response buffer allows), not exactly one. On this firmware a four-PDO request returns `DataLength: 4`, while offsets 0–3 individually prove four PDOs exist.
3. Fix the invalid local source PDOs: connector 1 reports a fixed supply of `0 mV / 0 mA` (`0x15000000`), connector 2 reports `1050 mV / 2560 mA` (`0x15005500`). The same values are returned by Windows.
4. Review the connector-status change bits: connector 1 returned `0x4040` (`ConnectChange`, `NegotiatedPowerLevelChange`) on every read in these captures; connector 2 returned `0x0000`.
5. Review PD object creation: `PWR_OPMODE` can read `default` at partner registration and `PD` moments later, leaving the partner marked as non-PD; one attach never obtained a PD object at all.
6. Fix the connector numbering swap relative to the ACPI `_ADR` values, and add DisplayPort's SVID `0xff01` to the alternate-mode table if the hardware supports it.
7. If no fix is planned, please confirm so the limitation can be documented publicly.

**Impact:** no `/sys/class/typec/` entries by default in Linux; no PD voltage/current, source capability list, cable e-marker, partner identity or alt-mode information; no UCSI-based USB-C hotplug events; no DisplayPort over USB-C in Linux. USB data and 5 V charging continue to work via the EC. Windows is usable but reads the same invalid local PDOs and stuck change bits.

## Attachments

- `acpidump -o t495-acpi.dat` (SSDT with `\_SB.UBTC`, `CR01`, `CR02`; DSDT `XHC0` `RHUB` `_UPC`/`_PLD`)
- `dmesg` with and without the VERSION patch
- `lsusb -t`
- `cat /sys/bus/platform/devices/USBC000:00/modalias`
- `ls /sys/class/typec/`
- Raw UCSI register dump: `VER=0x0000`, `CCI=0x20000000` (ACK_COMPLETE)
- Windows UCSI transcripts: batch and per-offset `GET_PDOS`, both connectors, both chargers
- Battery energy-counter trace for the 17.07 W measurement
- Recorded sysfs state for the 65 W adapter, both orientations:
  `data/snapshots/lenovo-65w-typec.txt`

---

## Short version (support web form)

> ThinkPad T495, 20NKS29V00, BIOS R12ET64W (1.34). The firmware exposes a UCSI device (`_HID USBC000`) with a valid register block and two Type-C connectors, but the UCSI VERSION register reads 0x0000. Linux `ucsi_acpi` rejects version 0 with `-ENODEV`, so `/sys/class/typec/` is empty. A UCSI maintainer has confirmed this as a Lenovo firmware bug on ThinkPad T14 Gen 2a (AMD) and asks customers to contact Lenovo (linux-usb, April 2026).
>
> The same firmware runs under Windows: `UcmUcsiAcpiClient` binds, PnP status is OK, and every UCSI command succeeds while both the PPM and the client driver report version 0.0.0. So the zero version blocks Linux only.
>
> With the version field patched in RAM for testing, Linux binds but misreports the power data: `GET_PDOS` ignores the requested PDO count and returns exactly one PDO (`DataLength: 4`). Windows reads offsets 0–3 individually and gets four PDOs (5 V, 9 V, 15 V, 20 V); Linux reads once, sees only 5 V / 3 A, and computes 0 V / 3.25 A from the truncated list. The Request Data Object `0x43051545` is correct — position 4, 20 V at 3.25 A = 65 W — and the battery draws ~17 W, well within it.
>
> Two further defects appear on both operating systems: the local source PDOs are invalid (connector 1: 0 V / 0 A, connector 2: 1.05 V / 2.56 A), and connector 1 keeps returning `ConnectChange` / `NegotiatedPowerLevelChange` (status-change bits 0x4040).
>
> Please populate the UCSI VERSION field (e.g. 0x0100) and fix `GET_PDOS` to honour the requested PDO count, plus the local source PDOs and the stuck change bits. If this will not be fixed, please confirm.
