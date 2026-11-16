# ThinkPad T495 (20NK) — firmware reports UCSI VERSION 0x0000; with that bypassed, the UCSI data itself is wrong

**Machine:** 20NKS29V00 · BIOS `R12ET64W (1.34)`, 2024-02-23

**Subject:** The UCSI VERSION register reads `0x0000`, so Linux `ucsi_acpi` refuses to bind (`-ENODEV`) and no Type-C ports exist. Forcing the version field to a valid value makes the interface bind, and the port/partner data it then exposes is internally inconsistent: the machine's own 65 W adapter is described by a 5 V/3 A PD contract while delivering over 17 W, the same adapter flips between "PD" and "no PD" depending on how it was attached, source PDOs are invalid, there is no identity or cable data, and connector numbering is swapped.

**Raw captures and reproduction scripts:** https://github.com/NivedV1/thinkpad-t495-ucsi

## Summary

The ACPI firmware exposes a UCSI device (`_HID USBC000` / `_CID PNP0CA0`) with a valid register block at `0xBD6B2000` and two Type-C connectors. The UCSI **VERSION register reads 0x0000**. `ucsi_register()` treats version 0 as unusable and returns `-ENODEV` before registering any connector, so `/sys/class/typec/` is empty and no UCSI functionality is available.

This alone is the same defect reported for ThinkPad T14 Gen 2a (AMD) on linux-usb in April 2026 and confirmed by the UCSI maintainer as a Lenovo firmware bug.

To determine whether the zero version was the only fault, the version field was patched in RAM for testing (volatile, one boot only). The interface then binds and exposes ports — but the values it reports are not usable:

- The machine's **own Lenovo 65 W adapter** (rated 20 V / 3.25 A) is reported with a single **PD 2.0 source capability of 5 V / 3 A**, while the battery is measured taking **17.37 W** at 11.63 V — more than a 5 V / 3 A source can supply. The same table appears for a Xiaomi 67 W USB-A charger, where PD is physically impossible, with 17.07 W measured.
- PD state is unstable: the partner's `supports_usb_power_delivery` is a snapshot taken at registration, while `power_operation_mode` is updated later. The same 65 W adapter read `no` with **no PD object at all** for eight minutes, then `yes` with a PD object after the connector was flipped over — same port, same adapter. On the Xiaomi charger a replug flipped `no` to `yes`, with the PD object appearing about 3 s after the partner.
- Each port advertises **invalid source PDOs** (0 mV/0 mA and 1050 mV/2560 mA).
- Partner identity and cable (e-marker) data are always empty, and the alternate-mode table can never produce DisplayPort.
- Connector numbering is **inverted** relative to ACPI and the kernel's own port links.
- Detached connectors keep stale `power_operation_mode` / `power_role` values.

USB data and 5 V charging work, because the EC handles those independently of UCSI.

## System information

| Item | Value |
|---|---|
| Model | Lenovo ThinkPad T495, `20NKS29V00` |
| BIOS | `R12ET64W (1.34)`, 2024-02-23 |
| CPU | AMD Ryzen 5 PRO 3500U (Picasso) |
| OS | Fedora 44, kernel `6.19.10-300.fc44.x86_64` |
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

## 2. VERSION 0x0000 blocks binding

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

## 3. With VERSION patched: the data is still wrong

**Method.** A test module mapped `0xBD6B2000` and wrote `0x0100` into `VER`, then `ucsi_acpi` was re-bound. The patch is RAM-only and disappears on reboot. `0x0100` and `0x0110` give identical results. The driver then binds normally:

```text
ucsi_acpi USBC000:00: Registered UCSI interface with version 1.0.0
```

`/sys/class/typec/port0`, `port1`, partner objects and PSYs all appear. Six attachments were tested.

| Attachment | Attach seen | Data role | Power role | UCSI says | Reality |
|---|---|---|---|---|---|
| Avocent USB audio | yes | host | source | `default` | correct |
| Charger #1 (non-PD) | **no** | — | — | nothing | AC=1, battery charging |
| Lenovo 65 W adapter (20 V/3.25 A), orientation A | yes | device | **sink** | **`usb_power_delivery`, no PD object** | 17.11–17.27 W measured |
| Lenovo 65 W adapter, connector flipped | yes | device | **sink** | **`usb_power_delivery`, PD 2.0, 5 V/3 A** | 17.37 W measured |
| Xiaomi 67 W, A→C | yes | device | **sink** | **`usb_power_delivery`, PD 2.0, 5 V/3 A** | PD impossible over A→C; 17.07 W measured |
| Mi 11X phone, C→C | yes | host | source | `default` on one connector, `usb_power_delivery` + PD 2.0 on the other | timing-dependent (§3.2) |

### 3.1 The reported contract cannot be the one in force

**The machine's own adapter.** Lenovo 65 W part, label `20 V / 3.25 A`, MFG DATE 6/2015. On both attaches UCSI reports one source capability, `5 V / 3 A`, and a PSY whose numbers cannot all be true at once:

```text
partner source PDO      5000 mV / 3000 mA     <- Type-C default, not the adapter
PSY voltage_now            0 mV
PSY voltage_max         5000 mV
PSY current_now         3250 mA               <- above its own 3000 mA maximum
PSY usb_type            "C [PD] PD_PPS"       <- with one fixed 5 V supply
battery                17.37 W at 11.634 V  -> 1.49 A into the pack
```

`5 V × 3 A = 15 W`, and that is before system draw, so the input must exceed 17 W: VBUS is above 5 V. The adapter is supplying a real contract above 5 V that UCSI does not describe.

**The USB-A charger.** Xiaomi 67 W Charging Combo (Type-A), **MDY-12-EJ**: a USB-**A** port, rated `5 V⎓3 A` or `5–20 V⎓6.2–3.25 A` with the original cable. There is no CC conductor from an A port, so USB-PD cannot be negotiated at all, and no `portN-cable` object is ever created (`vconn_source = no`). UCSI reports the same `usb_power_delivery` / PD 2.0 / `5 V / 3 A` / `PD_PPS` combination. Independent measurement of the same session, from the battery energy counter (`energy_now`, least-squares slope):

```text
samples        72 over 357 s (6.0 min)
energy         22.390 Wh -> 24.090 Wh  (delta 1.700 Wh)
energy slope   17.07 W
power_now      mean 17.56 W  (min 17.50, max 17.61)
batt voltage   11.72 V -> 11.79 V      (rising = genuine charge)
status/ac      Charging / 1            (no dropouts, no renegotiation)
```

`5 V × 3 A = 15 W` is that brick's entire 5 V capability, before system draw, so the input must exceed 17 W: VBUS is above 5 V. The cable's vendor identification path is unlocking the high-voltage mode, exactly as Xiaomi documents — and UCSI reports neither that voltage nor a real contract.

The EC's own source PSY agrees it cannot see its input: `ucsi-source-psy-USBC000:00{1,2}/voltage_now = 0` while `voltage_max = 5 V`.

**Finding:** the reported contract does not describe the actual power path. `PD` and `PPS` are fabricated. The decisive point is not the A-to-C cable — it is that a genuine 65 W PD adapter produces the *same* one-entry `5 V / 3 A` list, on both orientations, while delivering more than 17 W. The list is not read from the attached supply.

### 3.2 PD state is a timing race, not a per-connector property

Mi 11X over the same C→C cable, re-attached three times:

| Run | Enumerated on | Partner created under | `power_operation_mode` | Partner PD |
|---|---|---|---|---|
| 1 | `usb 2-4` | `port0` | `default` | no, no PD object |
| 2 | `usb 2-1` | `port1` | `usb_power_delivery` | yes, `pd2` rev 2.0, 5 V / 1.5 A |
| 3 | `usb 2-4` | `port0` | `default` | no, no PD object |

Same phone, same cable, same laptop, freshly re-enumerated each time (verified
by `usb 2-4: new high-speed USB device number N`). At the time this looked like a
per-connector property.

It is not. In a later 1 Hz capture the Xiaomi charger was unplugged and replugged
on the **same** connector (`port1`, `_SB.UBTC.CR02` both times):

| Time | `power_operation_mode` | partner `supports_usb_power_delivery` | PD object |
|---|---|---|---|
| 22:05:00–22:06:46 | `usb_power_delivery` | `no` | rev 2.0, 5 V / 3 A |
| 22:06:47 (unplug) | `default` | partner gone | gone |
| 22:06:54 (replug) | `usb_power_delivery` | **`yes`** | not yet present |
| 22:06:57 onward | `usb_power_delivery` | `yes` | rev 2.0, 5 V / 3 A |

`supports_usb_power_delivery` is `desc.usb_pd`, set once inside
`ucsi_register_partner()` from the EC's `PWR_OPMODE`. The port's
`power_operation_mode` is set later by `ucsi_pwr_opmode_change()`, from a
subsequent connector-change notification. When the EC answers `default` at
registration and `PD` a few seconds later, the partner keeps `no` for the whole
attach while the port reports PD and a PD object exists. That is exactly the
state seen above and on two of the three phone attaches.

The machine's own 65 W adapter shows the same race, with a wider gap. It sat on
`port1` in one orientation for eight minutes with `power_operation_mode =
usb_power_delivery`, `supports_usb_power_delivery = no` and **no PD object at
all**; flipping the connector and re-attaching produced `yes` and a PD object
within 2 s:

| Time | `power_operation_mode` | partner `supports_usb_power_delivery` | PD object |
|---|---|---|---|
| 23:20:07–23:28:19 | `usb_power_delivery` | `no` | **absent** |
| 23:28:20 (unplug) | `usb_power_delivery` (stale) | partner gone | gone |
| 23:28:24 (replug, flipped) | `usb_power_delivery` | **`yes`** | not yet linked |
| 23:28:25 | `usb_power_delivery` | `yes` | device exists, not linked to partner |
| 23:28:26 onward | `usb_power_delivery` | `yes` | rev 2.0, 5 V / 3 A |

The 23:28:25 sample is the orphan window described in `docs/pd-verdict.md`:
`ucsi_register_partner_pdos()` registers `con->partner_pd` before the `GET_PDOS`
calls, and only links it to the partner if both succeed.

**Finding:** the two PD values can disagree because they are sampled at different
times, and the PD object's very existence depends on the same timing. Nine
minutes of one orientation produced no PD object; the other orientation produced
one. The fabricated contract does not depend on this: on every attach where a PD
object exists, it claims `5 V / 3 A` while the battery draws more than 17 W.

Even on the attach that claimed PD, the port's own source PDO was `1050 mV / 2560 mA` — 1050 mV is not a valid PD voltage — so there was no coherent capability set from which a contract could have been made.

The practical asymmetry is in the power direction: when the machine is the source (phone attached), a `default`/no-PD verdict is harmless, because the phone only needs 5 V. When the machine is the sink (charger attached), the EC invents a PD contract and a PD object.

### 3.3 Invalid source PDOs

```text
port0 source-capabilities/1:fixed_supply:   0 mV /    0 mA
port1 source-capabilities/1:fixed_supply: 1050 mV / 2560 mA
port0/port1 sink-capabilities:           5000 mV /  100 mA
```

Neither port exposes a usable source capability set, and both sink sets are the trivial 100 mA default. The UCSI PSYs do not describe the port either: during the charger run `voltage_now` was 0 while the battery charged at 17 W, and with the phone attached and the port sourcing, the PSY still reported 5 V / 1.5 A while the port's own source PDO read 0 mV / 0 mA.

### 3.4 No identity, no cable, unusable alt modes

- Partner `id_header`, `product`, `product_type` are always empty; `number_of_alternate_modes = 0`; no `portN-cable` object is ever created. (Identity and cable details are PD VDMs, so with no real PD there is nothing to discover — this is consistent, not a separate bug.)
- `usb_power_delivery_revision` on the partner reads `0.0` while its PD object
  reads `2.0`. This one is **not** a firmware finding: `ucsi_register_partner()`
  only fills `desc.pd_revision` when `con->ucsi->version >= UCSI_VERSION_2_1`, and
  the patched version here is 1.1. It is listed so nobody re-reports it.
- The PSY values are derived from the EC's RDO. On the charger attach
  `current_now = rdo_op_current(rdo)` read 3.00 A, then 3.25 A after a replug,
  while the only PDO is 5 V / 3 A; `voltage_now` indexes the partner PDO with
  `rdo_index(rdo)` and read 0 V. The RDO does not describe a valid contract.
- All four connector alt-mode entries are `svid=17ef` and `svid=01ff`, `mode=1`, `vdo=0x00000001`, `active=yes`. DisplayPort's SVID is **`0xff01`**, so DP alt mode can never register from this table, regardless of the version patch.

### 3.5 Connector numbering is inverted

ACPI declares `CR01` `_ADR 5` → UCSI `port0` (fwnode `device:30`) and `CR02` `_ADR 8` → `port1` (fwnode `device:31`). That mapping is provable from `_PLD` bytes: `CR02`'s `_PLD` (`71 0C 00 02`) is byte-identical to root-hub `PLD4`, which `HS04`/`SS04` use, and those enumerate as `usb2-port4`/`usb3-port4`. The kernel links `usb2-port4`/`usb3-port4` to `port1`, which is therefore correct.

In practice a device on `usb 2-4` creates its partner under **`port0`**, and a device on `usb 2-1` creates its partner under **`port1`** — the opposite of the ACPI/kernel wiring, reproducibly, four times (Avocent, Xiaomi charger, phone twice). Userspace therefore cannot map `/sys/class/typec/portN` to a physical connector.

### 3.6 Stale state after detach

Idle connectors never reset: `port0` retained `power_role = source [sink]` and `port1` retained `power_operation_mode = usb_power_delivery` for minutes after detach, with no partner present.

## 4. Upstream reference

linux-usb, April 2026 — *"[BUG] ucsi_acpi: Fails to bind on USBC000 devices, version=0 in NVS blocks probe"*, ThinkPad T14 Gen 2a (AMD), same modalias, same `-19`:

- https://ratatoskr.run/linux-usb/2026/04/8893642/t
- https://ratatoskr.run/linux-usb/2026/04/8896578/t (follow-up patch thread)

UCSI maintainer Heikki Krogerus:

> "Again with the missing version. Please contact Lenovo. This is a bug in their firmware. The version field must supply the actual ucsi version."

Writing `0x0100` into the version field made the driver bind there too, and USB-C display hotplug was reported working. Current mainline has **no Lenovo quirk** for this; the only zero-version workarounds are DMI quirks for one Acer and one LG Gram model, so T495/T14 Gen 2a users have no automatic fix.

## 5. Request to Lenovo

1. Populate the UCSI VERSION field with the actual UCSI version (e.g. `0x0100`) in a BIOS update for machine type `20NK`, as the UCSI specification requires.
2. If that is addressed, please also review the values the EC returns through UCSI on this platform, which are wrong even with a valid version:
   - The supplied source capability set does not match the attached adapter. The machine's own 65 W (20 V / 3.25 A) adapter is reported with a single `5 V / 3 A` PDO while the battery draws 17.37 W. The same table is produced for a USB-A source where PD cannot exist.
   - `PWR_OPMODE` / PD presence is not stable between attaches of the same adapter, and `supports_usb_power_delivery` can disagree with `power_operation_mode`. The same 65 W adapter produced no PD object at all in one orientation and a PD object in the other.
   - Source PDOs are invalid (`0 mV/0 mA`, `1050 mV/2560 mA`).
   - Connector numbering is swapped relative to the ACPI `_ADR` values.
   - Alternate-mode table cannot yield DisplayPort (`0xff01` absent).
   - `PWR_OPMODE` and `POWER_ROLE` are not reset on detach.
3. If no fix is planned, please confirm so the limitation can be documented publicly.

**Impact:** no `/sys/class/typec/` entries by default; no PD voltage/current, cable e-marker, partner identity or alt-mode information; no UCSI-based USB-C hotplug events; no DisplayPort over USB-C in Linux. USB data and 5 V charging continue to work via the EC.

## Attachments

- `acpidump -o t495-acpi.dat` (SSDT with `\_SB.UBTC`, `CR01`, `CR02`; DSDT `XHC0` `RHUB` `_UPC`/`_PLD`)
- `dmesg` with and without the VERSION patch
- `lsusb -t`
- `cat /sys/bus/platform/devices/USBC000:00/modalias`
- `ls /sys/class/typec/`
- Raw UCSI register dump: `VER=0x0000`, `CCI=0x20000000` (ACK_COMPLETE)
- Battery energy-counter trace for the 17.07 W measurement
- Recorded sysfs state for the 65 W adapter, both orientations:
  `data/snapshots/lenovo-65w-typec.txt`

---

## Short version (support web form)

> ThinkPad T495, 20NKS29V00, BIOS R12ET64W (1.34). The firmware exposes a UCSI device (`_HID USBC000`) with a valid register block and two Type-C connectors, but the UCSI VERSION register reads 0x0000. Linux `ucsi_acpi` rejects version 0 with `-ENODEV`, so `/sys/class/typec/` is empty. A UCSI maintainer has confirmed this as a Lenovo firmware bug on ThinkPad T14 Gen 2a (AMD) and asks customers to contact Lenovo (linux-usb, April 2026).
>
> For testing only, I patched the version field in RAM (volatile, one boot). The interface then binds, but the data it returns is not usable: with the machine's own 65 W (20 V/3.25 A) adapter attached, UCSI reports a single PD 2.0 source capability of 5 V/3 A while the battery charges at a measured 17.37 W (more than 5 V/3 A can deliver), and the same adapter exposes no PD object at all in one connector orientation but does in the other; a USB-A charger that cannot do PD is reported as the same 5 V/3 A contract; source PDOs are invalid (0 mV/0 mA and 1050 mV/2560 mA); identity and cable data are always empty; the alt-mode table cannot produce DisplayPort; connector numbering is swapped; and opmode/role are not reset on detach.
>
> Please confirm whether a BIOS update can populate the UCSI VERSION field (e.g. 0x0100) and correct the UCSI data above, or whether this will not be fixed.
