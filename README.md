# ThinkPad T495 / T14 Gen 2a (AMD): UCSI reports VERSION `0x0000` and truncates `GET_PDOS` to one PDO

Windows-side captures and reproduction instructions are available in
[windows_ucsi](windows_ucsi/README.md), including both USB-C connectors with
Xiaomi and original ThinkPad chargers, USB audio, and phone connection tests.
The archive preserves raw firmware responses, decoding limitations, and hashes.

Diagnostic project for two Lenovo firmware defects that leave USB-C unusable
under Linux — a zero UCSI version and a truncated PDO response — plus the
evidence needed to report them and a request for other owners to confirm them on
their machines.

**Status:** confirmed on one ThinkPad T495 (`20NKS29V00`, BIOS `R12ET64W 1.34`,
Fedora 44, kernel `6.19.10`). The same VERSION defect is already confirmed by the
UCSI maintainer on a ThinkPad T14 Gen 2a (AMD). **Not yet confirmed on other
machines — that is why this repo exists.** No fixed BIOS is known; a Linux-side
workaround is plausible and described below.

- Support report: [`report/thinkpad-t495-ucsi-report.md`](report/thinkpad-t495-ucsi-report.md)
- Raw captures: [`data/`](data/) and [`windows_ucsi/`](windows_ucsi/README.md)
- If you own an affected ThinkPad, please run [the read-only check](#step-5--how-to-check-your-machine) and open an issue.

> **This project writes to firmware-owned memory when you ask it to.** The
> module is read-only by default. The write is RAM-only and disappears on
> reboot, but read [`docs/safety.md`](docs/safety.md) before using it.

---

## Intent

1. Show, with reproducible local evidence, that the UCSI interface on these
   ThinkPads cannot initialize in Linux because firmware reports
   `VERSION = 0x0000`.
2. Show that populating the version is **not sufficient**: the EC returns only
   one PDO for a multi-PDO `GET_PDOS` request, and Linux's reader treats that
   short reply as the whole capability list.
3. Give other owners a safe, read-only way to check their own machine — in
   Linux and, more revealingly, in Windows — so the defect can be confirmed
   across models and BIOS versions.
4. Ask Lenovo to populate the version field and fix the response lengths, and
   ask the kernel side to consider a quirk for both in the meantime.

## TL;DR findings

| # | Finding |
|---|---|
| 1 | The ACPI UCSI device is present and well-formed (`_HID USBC000`, `_CID PNP0CA0`, `_CRS` region `0xBD6B2000+0x1000`, `_DSM` via EC mailbox), but **VERSION reads `0x0000`**. `ucsi_register()` treats that as unusable and returns `-ENODEV`, so `/sys/class/typec/` is empty. Probe fails silently. |
| 2 | **Windows runs the same firmware.** `UcmUcsiAcpiClient` binds to `ACPI\USBC000\0`, PnP status is OK, and every UCSI command completes while the PPM and client driver both report version `0.0.0`. The zero version is a Linux-side gate, not a dead device. |
| 3 | **`GET_PDOS` returns exactly one PDO for a four-PDO request** (`NumberOfPdos: 3`, zero-based, `CCI DataLength: 4`). Reading offsets 0, 1, 2, 3 individually returns four real PDOs, so the list exists and only the batch read is short. (Only the four-PDO request was tested.) |
| 4 | Linux reads the batch once. In v6.19 `ucsi_get_pdos()` computes `num_pdos = ret / 4 = 1`, sees `1 < UCSI_MAX_PDOS`, returns immediately, and never asks for offsets 1–3. `src_pdos[1..3]` stay zero. |
| 5 | That one missing read produces every "impossible" number: `voltage_now = src_pdos[rdo_index-1] = src_pdos[3] = 0`, `voltage_max = src_pdos[num_pdos-1] = PDO 1 = 5 V`, `current_max = PDO 1 = 3 A`, `current_now = RDO = 3.25 A`. The "5 V / 3 A contract" was the truncated list, not a negotiation. |
| 6 | The RDO is correct: `0x43051545` selects position 4 (20 V) at 3.25 A = **65 W**, matching the attached adapter's own PDO 4 on both operating systems. |
| 7 | Both ports report **invalid local source PDOs** — connector 1 `0 mV / 0 mA`, connector 2 `1050 mV / 2560 mA` — in Linux and Windows alike. That one is a separate, driver-independent firmware defect. |
| 8 | Connector 1 reports `ConnectChange` and `NegotiatedPowerLevelChange` (status-change bits `0x4040`) in every capture; connector 2 reports `0x0000`. Identical on both operating systems. |
| 9 | PD presence is a registration-time snapshot: the partner's `supports_usb_power_delivery` is set once, the PD object usually links a few seconds later, and occasionally never links at all. |
| 10 | UCSI connector numbering is swapped relative to ACPI `_ADR` and the kernel's `usbN-portM` links. |

## Identify it step by step

The path from "Linux has no USB-C" to "the firmware returns one PDO", in the
order the evidence appeared. Each step lists what to run, what this machine
returned, and what it rules out. The detailed version is in
[What we found](#what-we-found).

### Step 1 — Linux: the Type-C driver never binds

```bash
$ ls /sys/class/typec/ | wc -l
0
$ cat /sys/bus/platform/devices/USBC000:00/modalias
acpi:USBC000:PNP0CA0:
$ sudo dmesg | grep -iE 'ucsi|typec'
(nothing)
```

The ACPI device exists, `_CRS` declares the register block, `_DSM` works — and
probe still fails without a message. kprobes on the probe path show where:

```text
ucsi_probe:     (ucsi_acpi_probe+0x4/0x210 [ucsi_acpi])
r_ver:          (ucsi_register+0x1d/0xa0 [typec_ucsi] <- ucsi_acpi_read_version) arg1=0
r_reg:          (ucsi_acpi_probe+0x163/0x210 [ucsi_acpi] <- ucsi_register) arg1=-19
ucsi_probe_ret: (platform_probe+0x67/0x90 <- ucsi_acpi_probe) arg1=-19
```

The version read succeeds and returns `0`. `ucsi_register()` then does:

```c
if (!ucsi->version)
        return -ENODEV;
```

`-19` is `-ENODEV`. Probe gives up silently, so the first symptom is not "wrong
data" but "no data": no ports, no PD, no alt modes. Charging and USB data keep
working because the EC handles them without the OS.

Raw before/after register dump: [`data/ucsi-register-block.txt`](data/ucsi-register-block.txt).

### Step 2 — Windows: the same firmware answers every command

Boot Windows on the same machine and look at the same ACPI device:

```powershell
Get-PnpDevice -InstanceId 'ACPI\USBC000\0' | Select-Object Status,Problem
```

```text
Status  OK   Problem  0
```

`UcmUcsiAcpiClient.sys` binds, Microsoft's UCSI test tool completes
`GET_CAPABILITY`, `GET_CONNECTOR_STATUS` and `GET_PDOS`, and both the PPM and
the client driver print version `0.0.0`. The transport, the EC mailbox and the
`_DSM` all work; only Linux's `version == 0` check rejects the interface.

Then read the PDO list. One batch request for four PDOs returns one:

```text
NumberOfPdos: 3   (zero-based: four requested)
PdoOffset:    0
CCI DataLength: 4
MESSAGE_IN:   2c 91 01 0a   -> 0x0A01912C   5 V / 3 A
```

The same request, one offset at a time, returns the whole list:

| Offset | `DataLength` | PDO | Decoded |
|---|---|---|---|
| 0 | 4 | `0x0A01912C` | 5 V / 3 A |
| 1 | 4 | `0x0002D12C` | 9 V / 3 A |
| 2 | 4 | `0x0004B12C` | 15 V / 3 A |
| 3 | 4 | `0x0006414F` | 20 V / 3.35 A (67 W Xiaomi) |
| 4 | 0 | — | end of list |

The Lenovo 65 W adapter gives the same four voltages with PDO 4 =
`0x00164145` (20 V / 3.25 A). So the four entries exist, each offset read is
individually correct, and only the multi-PDO read is short.

That separates two independent firmware defects: **VERSION is zero**, and
**`GET_PDOS` ignores the four-PDO request**. Windows exposes both; it just does
not reject the device over the first one. Full transcripts:
[`windows_ucsi/`](windows_ucsi/README.md).

### Step 3 — Why it happens

Four layers, in order:

| Layer | What happens | Evidence |
|---|---|---|
| Firmware | reports `VERSION = 0x0000` | register dump; Windows PPM `0.0.0` |
| Linux | `ucsi_register()` returns `-ENODEV` on version zero | kprobe `arg1=-19` |
| Firmware | returns one PDO for a four-PDO `GET_PDOS` | `CCI DataLength: 4` |
| Linux | reads the batch once and keeps one entry | `num_pdos = ret / 4 = 1` |

`ucsi_get_pdos()` in v6.19 returns as soon as the first read is short, so
offsets 1–3 are never requested and `src_pdos[1..3]` stay zero. Every
"impossible" sysfs value follows from that one missing read:

| Attribute | Source | Value |
|---|---|---|
| `voltage_now` | `src_pdos[rdo_index - 1]` = `src_pdos[3]` | 0 |
| `voltage_max` | `src_pdos[num_pdos - 1]` = PDO 1 | 5 V |
| `current_max` | PDO 1 | 3 A |
| `current_now` | RDO operating current | 3.25 A |

Nothing negotiated 5 V / 3 A. The real contract is in the RDO: `0x43051545`
selects position 4 (the 20 V PDO) at 3.25 A, which is 65 W, and the battery
draw agrees with 20 V input. The full derivation is in
[§3 and §4 below](#3-what-the-truncated-reply-does-to-linux).

### Step 4 — Who it affects

**Linux users on affected firmware.** The whole `typec` class is missing, with
no error message: no PD information, no cable e-marker, no partner identity, no
USB-C hotplug events, no DisplayPort over USB-C. This is a kernel-level check,
so the distribution and desktop do not matter.

**Windows users.** Windows does not reject the device, so it looks healthy in
Device Manager. But any UCSI consumer still receives one PDO per batch read, and the local
source PDOs are still invalid (`0 mV / 0 mA`, `1050 mV / 2560 mA`). The
difference is enforcement, not data.

**Anyone reading firmware data.** Tools and drivers that trust the reply length
will under-report the charger; tools that walk offsets (as Microsoft's does)
see four PDOs. That is why the same machine can produce two different answers.

**Confirmed scope.** One ThinkPad T495, MTM `20NKS29V00`, BIOS `R12ET64W`
(1.34), Fedora 44, kernel 6.19.10. The same VERSION defect was reported for a
T14 Gen 2a (AMD) on linux-usb, where the UCSI maintainer called it a firmware
bug. Sister models (T14s, X13, other AMD ThinkPads of that generation) are
plausible but unconfirmed. No fixed BIOS is known.

### Step 5 — How to check your machine

Read-only. Nothing is modified.

```bash
# 1. does the firmware expose a UCSI device, and did it bind?
ls /sys/class/typec/ 2>/dev/null | wc -l
for d in /sys/bus/acpi/devices/USBC000:*; do cat "$d/modalias"; readlink -f "$d/driver"; done
sudo dmesg | grep -iE 'ucsi|typec'

# 2. what does the firmware say the version is? (needs the module, read-only)
sudo ./scripts/10-dump-ucsi.sh
```

| Observation | Meaning |
|---|---|
| `modalias` is `acpi:USBC000:PNP0CA0:`, `typec` count is 0, dmesg silent | your firmware has the same defect |
| `VERSION=0x0000` in the module output | confirmed, same as this machine |
| a driver is bound and ports already exist | **not affected** — please still report your model/BIOS, it narrows the range |

If you also have Windows on the machine,
[the Windows check](windows_ucsi/README.md#is-your-machine-affected) is the
stronger test: it shows whether the platform's own UCSI client accepts the
firmware, and lets you read the full PDO list the EC actually returns.

If the driver binds on your machine (or after the RAM patch), the same
per-offset walk can be done in Linux without Windows:

```bash
sudo ./scripts/20-enable-ucsi.sh    # RAM-only version patch; see docs/safety.md
sudo ./scripts/25-walk-pdos.sh
```

## What we found

### 1. The version field is zero, so Linux refuses the device

```text
$ cat /sys/bus/platform/devices/USBC000:00/modalias
acpi:USBC000:PNP0CA0:
$ ls /sys/class/typec/
(empty)
```

kprobes on the probe path:

```text
ucsi_probe:     (ucsi_acpi_probe+0x4/0x210 [ucsi_acpi])
r_ver:          (ucsi_register+0x1d/0xa0 [typec_ucsi] <- ucsi_acpi_read_version) arg1=0
r_reg:          (ucsi_acpi_probe+0x163/0x210 [ucsi_acpi] <- ucsi_register) arg1=-19
ucsi_probe_ret: (platform_probe+0x67/0x90 <- ucsi_acpi_probe) arg1=-19
```

The read succeeds; the value is `0x0000`. Forcing a bind fails with `ENODEV`
(`echo USBC000:00 > .../bind` → "No such device"). `/dev/mem` refuses that range
under `CONFIG_STRICT_DEVMEM`, so the register block is read through a small
out-of-tree module — the same module in [`module/`](module/).

Raw register dump, before and after the test write: [`data/ucsi-register-block.txt`](data/ucsi-register-block.txt).

**Windows accepts the same device.** On this machine Windows 11 binds
`UcmUcsiAcpiClient.sys` to `ACPI\USBC000\0`, reports PnP status OK, and completes
every `GET_CAPABILITY`, `GET_CONNECTOR_STATUS` and `GET_PDOS` command sent through
Microsoft's UCSI test tool — while printing `UCSI VERSION from PPM: 0.0.0` and
`from client driver: 0.0.0`. The transport, the EC mailbox and the ACPI `_DSM`
all work. Only Linux's `version == 0` check rejects the interface, so a DMI quirk
in `ucsi_acpi` would let the driver bind here. The driver already carries one
per-model quirk (LG Gram, selecting an alternate ops table), but nothing that
touches the version check. What such a quirk would expose is the subject of §2
and §3.

### 2. `GET_PDOS` truncates a four-PDO request to one PDO

Windows, connector 1, partner source PDOs, batch request:

```text
UCSI_CONTROL:
  Command:       0x10 (GetPdos)
  ConnectorNumber: 1
  SourceOrSinkPdos: 1        (partner/source)
  PdoOffset:     0x0
  NumberOfPdos:  3           (four PDOs requested)

UCSI_CCI:
  DataLength: 4              (four bytes returned)

UCSI MESSAGE_IN:
  2c 91 01 0a                (one PDO: 5 V / 3 A)
```

The same request offset by offset returns the whole list:

| Offset | `DataLength` | PDO | Decoded |
|---|---|---|---|
| 0 | 4 | `0x0A01912C` | 5 V / 3 A |
| 1 | 4 | `0x0002D12C` | 9 V / 3 A |
| 2 | 4 | `0x0004B12C` | 15 V / 3 A |
| 3 | 4 | `0x0006414F` | 20 V / 3.35 A (67 W Xiaomi) |
| 4 | 0 | — | no more PDOs |

The ThinkPad 65 W adapter returns the same four voltages, with PDO 4 =
`0x00164145` (20 V / 3.25 A), on both connectors. The firmware does not honour
the four-PDO request: one comes back. Batch reads that have data to return all
ended with `DataLength: 4`; the only zero-length reply was the partner's
sink-PDO list, which genuinely is empty. Other request counts were not tested.
`CCI DataLength` — not the request — is the only honest indicator of how many
PDOs actually arrived.

### 3. What the truncated reply does to Linux

`drivers/usb/typec/ucsi/ucsi.c`, v6.19:

```c
ret = ucsi_read_pdos(con, role, is_partner, pdos, 0, UCSI_MAX_PDOS);
if (ret < 0)
        return ret;

num_pdos = ret / sizeof(u32); /* number of bytes to 32-bit PDOs */
if (num_pdos < UCSI_MAX_PDOS)
        return num_pdos;      /* ret = 4 -> num_pdos = 1 -> return 1 */

/* get the remaining PDOs, if any */
ret = ucsi_read_pdos(con, role, is_partner, pdos, UCSI_MAX_PDOS, ...);
```

With `DataLength: 4`, `num_pdos` is 1, the early return fires, and offsets 1–3
are never requested. `con->num_pdos = 1` and `con->src_pdos[1..3]` remain zero.
The request itself is not the difference: `ucsi_read_pdos()` encodes
`UCSI_GET_PDOS_NUM_PDOS(num_pdos - 1)`, so Linux sends `NumberOfPdos: 3` — the
same four-PDO command the Windows tool sent.
The first entry is correct — Linux reads exactly the same `0x0A11912C`
(ThinkPad) / `0x0A01912C` (Xiaomi) that Windows reports.

Every remaining "impossible" value follows from that single short read
(`drivers/usb/typec/ucsi/psy.c`):

```c
index = rdo_index(con->rdo);          /* 4 */
pdo = con->src_pdos[index - 1];       /* src_pdos[3] == 0 */
val->intval = pdo_fixed_voltage(pdo) * 1000;   /* 0 uV */

pdo = con->src_pdos[con->num_pdos - 1];        /* src_pdos[0] = 5 V */
val->intval = pdo_max_current(pdo) * 1000;     /* 3000 mA */

val->intval = rdo_op_current(con->rdo) * 1000; /* 3250 mA */
```

So `voltage_now = 0`, `voltage_max = 5000 mV`, `current_max = 3000 mA` and
`current_now = 3250 mA` all describe the same truncated list. None of them is a
fabricated negotiation.

> `usb_type` printing `C [PD] PD_PPS` is not evidence of PPS either: `psy.c`
> hard-codes `usb_types = C | PD | PD_PPS` for every UCSI connector, and only
> the bracketed element (`PD`) is read from the EC.

### 4. The real contract is 20 V, and the RDO is right

RDO `0x43051545` decodes as object position 4 and 3.25 A operating current
(and 3.25 A maximum operating current). Position 4 of the attached adapter is
20 V, so the request is **20 V / 3.25 A = 65 W**:

| Adapter | PDO 4 (20 V) | RDO | Requested |
|---|---|---|---|
| Lenovo 65 W (label 20 V / 3.25 A) | 3.25 A | `0x43051545` | 65 W |
| Xiaomi 67 W | 3.35 A | `0x43051545` | 65 W |

The same RDO appears on both connectors and on both operating systems, and
Lenovo Vantage independently displays 65 W for the stock adapter and 67 W for
the Xiaomi one, matching the advertised PDO 4 in each case.

The battery measurements are consistent with that input, not with 5 V / 3 A:

```text
Linux    battery 17.37 W at 11.634 V   (1.49 A into the pack)
Windows  battery 16.423 W at 11.875 V  (BatteryStatus WMI)
```

A 5 V / 3 A source (15 W) could not charge the pack at ~17 W and run the system
at the same time. A 20 V / 3.25 A contract (65 W) has ample headroom, so there
is no power-conservation paradox once the whole PDO list is visible.

The Xiaomi charger is connected through a **USB-A-to-USB-C** cable and still
returns four PDOs and the 20 V request. Whatever signaling the charger uses, the
EC sees and requests a 20 V profile over that path; the earlier claim that PD
was impossible on A-to-C was wrong.

### 5. Local source PDOs, identity and alt modes

| | Linux | Windows (same machine) |
|---|---|---|
| connector 1 local source | `0 mV / 0 mA` (`0x15000000`) | `0x15000000` |
| connector 2 local source | `1050 mV / 2560 mA` (`0x15005500`) | `0x15005500` |

Both operating systems return the same two DWORDs, so this is not a Linux
artefact: the EC's own source-capability list is invalid. A laptop port that
advertises 0 V / 0 A (or 1.05 V, which is not a PD voltage) cannot offer a
usable source contract to a phone or accessory, even though 5 V sourcing works.

Related, and unchanged by the PDO-length bug:

- partner `id_header`, `product` and `product_type` are always empty; no
  `portN-cable` object is ever created, so no e-marker is read;
- the alt-mode table contains only `0x17ef` and `0x01ff` with `vdo=1`;
  DisplayPort's SVID `0xff01` never appears. Whether DP alt mode works in
  Windows on this machine has not been tested;
- `usb_power_delivery_revision` on the partner reads `0.0` while its PD object
  reads `2.0`. That is kernel-side: `desc.pd_revision` is only filled at
  UCSI >= 2.1 and the test patch is 1.1. It is listed so nobody re-reports it.

### 6. Connector 1 keeps reporting the same change bits

The connector-status response is **9 bytes** (`CCI DataLength: 9`), not 8.
Bytes 0–1 are `ConnectorStatusChange`:

```text
connector 1:  40 40 2b 20 45 15 05 43 01   -> change bits 0x4040
connector 2:  00 00 00 20 00 00 00 00 01   -> change bits 0x0000
```

`0x4040` is `ConnectChange` and `NegotiatedPowerLevelChange`. Both were set in
every capture, across reads and attach/detach cycles, identically on Linux and
Windows. A consumer polling for changes therefore keeps seeing the same event
on connector 1.

Upstream already carries one workaround in this area: the LG Gram quirk in
`ucsi_acpi.c` clears `POWER_LEVEL_CHANGE | PDOS_CHANGE` from the status directly
after a partner `GET_PDOS`. This machine's pair is different
(`CONNECT_CHANGE | POWER_LEVEL_CHANGE`), and `CONNECT_CHANGE` is genuine signal,
so the LG approach cannot simply be reused — but it is a precedent for treating
post-`GET_PDOS` change bits as firmware noise.

Byte 8 is `BatteryChargingStatus` (`01`), not orientation. The orientation bit
is `UCSI_CONSTAT_ORIENTATION` = bit 86, i.e. byte 10, and the response stops at
byte 8 — so **orientation is not observable through this interface**, on either
operating system.

### 7. PD presence is a registration-time snapshot

`supports_usb_power_delivery` is `desc.usb_pd`, set once inside
`ucsi_register_partner()` from the EC's `PWR_OPMODE`. The port's
`power_operation_mode` is updated later by `ucsi_pwr_opmode_change()`. If the EC
answers `default` at registration and `PD` a moment later, the partner keeps
`no` while the port reports PD.

Recent attaches show the normal shape of this: in four consecutive warm-up
attaches of a PD charger (both connectors), `supports_usb_power_delivery` read
`yes` at the instant the partner appeared, the PD object was **absent at t0 and
present 8 s later in all four**, and the RDO was `0x43051545` every time. The PD
object is queued after partner registration (`ucsi_register_partner_pdos()`),
which is why it lags.

One attach did not recover: the machine's own 65 W adapter sat on `port1` in one
orientation for eight minutes with `power_operation_mode = usb_power_delivery`,
`supports_usb_power_delivery = no` and no PD object at all. Flipping the
connector and re-attaching produced `yes` and a PD object within 2 s. The
likely reason is that the PD link is only set after both `GET_PDOS` calls
succeed, and the retry task is a no-op when the first attempt fails:

```c
con->partner_pd = typec_partner_usb_power_delivery_register(con->partner, &desc);
...
if (con->partner_pd)
        return 0;          /* retry does nothing */
```

So an occasional permanently-unlinked PD object is a second-order defect on top
of the EC timing. It does not change the contract: whenever a PD object exists,
its source list is the truncated one from §3.

The earlier "stale state after detach" observation was narrower than first
reported: `power_operation_mode` can still read the old value for a second or
two after unplugging, but it returns to `default` once the EC settles. It is a
transition, not a permanent leak.

### 8. Connector numbering is swapped

`_SB.UBTC.CR02` (`_ADR 8`) carries the same `_PLD` bytes as root-hub port 4
(`71 0C 00 02`), and Linux correctly links `usb2-port4`/`usb3-port4` to UCSI
`port1` = `CR02`. Nevertheless, a device on `usb 2-4` creates its partner under
`port0` = `CR01`, and a device on `usb 2-1` creates it under `port1` = `CR02`.
Four attachments, same inversion every time. Details:
[`data/acpi/port-mapping.md`](data/acpi/port-mapping.md).

Cross-checked against Windows: Linux `port0` is UCSI connector 1 and `port1` is
connector 2 (the local source PDOs and change bits line up exactly), so the
mismatch is between the EC's connector numbers and the ACPI/xHCI wiring, not
between operating systems. Physical front/rear labelling was not established.

## Tests done

| Test | Result |
|---|---|
| Read UCSI register block before/after write | `VERSION 0x0000` → `0x0110`; `0x0100` and `0x0110` behave identically |
| kprobe probe path | version read returns 0; `ucsi_register` returns `-19` |
| Force bind without patch | `ENODEV` |
| Windows PnP with VERSION 0.0.0 | `UcmUcsiAcpiClient` bound, status OK, all commands succeed |
| Batch `GET_PDOS` on Windows | 4 PDOs requested, `DataLength: 4`, one PDO returned |
| Per-offset `GET_PDOS` on Windows | 4 partner PDOs; PDO 4 = 20 V (3.25 A ThinkPad, 3.35 A Xiaomi) |
| RDO on both OSes | `0x43051545` = position 4, 3.25 A = 65 W |
| Hotplug with non-PD charger | AC online, battery charges, **no** UCSI event, no partner |
| Hotplug with USB audio adapter | partner add/remove, `data_role` flips, ~1 s |
| Lenovo 65 W adapter, both connectors, both OSes | 4 PDOs, 20 V request; Linux sees only PDO 1 |
| 4 warm-up attaches of a PD charger | `spd=yes`, RDO `0x43051545`, PD object absent at t0 and present 8 s later, 4/4 |
| Same adapter, one attach for 8 minutes | `spd=no`, no PD object; flipped connector → `yes` within 2 s |
| Local source PDOs, both OSes | `0x15000000` and `0x15005500` on connectors 1 and 2 |
| Connector status change bits, both OSes | connector 1 `0x4040`, connector 2 `0x0000`, unchanged in every capture |
| `_PLD` matching for port numbering | CR02 == root-hub port 4; partner lands on the other port |

Reproduction steps for each row: [`docs/tests.md`](docs/tests.md).

## Reproduce it yourself

Requirements: kernel headers (`kernel-devel`), `make`, `gcc`, root, Secure Boot
either disabled or the module signed. Tested with Fedora 44 /
`6.19.10-300.fc44.x86_64`, lockdown `none`, Secure Boot off.

```bash
git clone https://github.com/NivedV1/thinkpad-t495-ucsi.git
cd thinkpad-t495-ucsi

sudo ./scripts/00-prereq.sh          # read-only: is this machine in scope?
sudo ./scripts/10-dump-ucsi.sh       # read-only: build module, dump registers

# only if you accept the risk described in docs/safety.md:
sudo ./scripts/20-enable-ucsi.sh     # patch VERSION in RAM + bind ucsi_acpi
sudo ./scripts/25-walk-pdos.sh       # PDOs offset by offset (same walk as Windows)
sudo ./scripts/30-snapshot.sh /tmp/typec-before
sudo ./scripts/40-watch.sh /tmp/typec-watch 180   # plug/unplug while it runs
sudo ./scripts/50-charge-rate.sh 360              # for chargers

sudo ./scripts/90-undo.sh            # unbind + unload; reboot clears the patch
```

The module is read-only unless you pass `patch=1`:

```text
ucsi_peek.addr=0xBD6B2000   # default, from _CRS
ucsi_peek.len=0x30          # bytes to dump
ucsi_peek.patch=0           # 0 = never write
ucsi_peek.patch_ver=0x0100  # value used only when patch=1
```

## How to help: please test on your machine

The single most useful thing you can do is confirm or refute this on hardware
that is not this laptop.

**If the machine has Windows** (strongest, ~5 minutes): run the two commands in
[`windows_ucsi/README.md`](windows_ucsi/README.md#is-your-machine-affected) and
report four things — PnP status of `ACPI\USBC000\0`, the UCSI version it prints,
the `GET_PDOS` `DataLength` for a multi-PDO request, and the per-offset PDO
list. That separates "version gate only" from "firmware is broken on the
platform's own interface".

**Linux (read-only, ~1 minute):**

```bash
git clone https://github.com/NivedV1/thinkpad-t495-ucsi.git
cd thinkpad-t495-ucsi
sudo ./scripts/00-prereq.sh 2>&1 | tee /tmp/prereq.txt
sudo ./scripts/10-dump-ucsi.sh 2>&1 | tee /tmp/dump.txt
```

Then [open an issue](https://github.com/NivedV1/thinkpad-t495-ucsi/issues/new/choose)
and paste the two files. The template asks for model, BIOS, kernel and the
`VERSION` line.

**Full (if you are willing to patch RAM for one boot):** run
`20-enable-ucsi.sh` and, with a known PD charger and a phone:

1. `30-snapshot.sh` once per attachment, both connectors;
2. `40-watch.sh` while plugging and unplugging;
3. `50-charge-rate.sh 360` for each charger;
4. `90-undo.sh`, then reboot.

**What would be most valuable**

| If you have | It answers |
|---|---|
| a Windows install on an affected machine | whether Windows accepts the zero version and what the full PDO list is |
| an affected ThinkPad with a **different BIOS** | whether Lenovo fixed either defect in a later release |
| a T14 Gen 2a / T14s / X13 / other AMD ThinkPad of the same generation | how wide the defect is |
| a USB-C inline power meter | the actual VBUS, confirming the 20 V profile the RDO selects |
| a USB-C to HDMI/DP adapter on Windows | whether DP alt mode works despite the missing `0xff01` |

Please do **not** open an issue with only "me too" — the model, BIOS, kernel,
`VERSION` value and whether the driver binds are the minimum to make it useful.

## What we still do not know

- **Whether the kernel should work around the PDO count.** Reading offsets until
  a short `DataLength` is exactly what Windows does, and it would restore the
  full list. Whether upstream would accept that as a quirk, and whether it
  should be gated on this DMI or on the zero version, is open.
- **Whether the invalid local source PDOs have an operational effect.** They
  would cap what the port can offer as a source. The EC may use different data
  internally; source-role tests with a phone did not establish a PD contract.
- **Whether DisplayPort over USB-C works in Windows.** Not tested; if it does,
  the alt-mode table is a Linux-visible defect only.
- **Which physical connector is which.** The UCSI numbering is cross-checked
  between OSes, but front/rear/left/right labelling was never recorded.
- **Whether a later BIOS fixes either defect.** This machine is on `R12ET64W
  (1.34)`, 2024-02-23.

## Data in this repo

| Path | Contents |
|---|---|
| `report/thinkpad-t495-ucsi-report.md` | the support report prepared for Lenovo (full + web-form version) |
| `windows_ucsi/` | Windows captures, decoded PDOs, reproduction scripts and provenance |
| `module/ucsi_peek.c` | the diagnostic module (read-only by default) |
| `scripts/` | prerequisite check, register dump, enable/undo, PDO walk, snapshot, 1 Hz watch, charge-rate fit |
| `data/ucsi-register-block.txt` | raw register dumps, three states |
| `data/acpi/ssdt1-UBTC-excerpt.dsl` | `_SB.UBTC`, `CR01`, `CR02`, `_DSM`, EC mailbox |
| `data/acpi/port-mapping.md` | `_PLD` byte matching behind the numbering swap |
| `data/device-matrix.md` | every attachment, verbatim sysfs values |
| `data/logs/` | 1 Hz state logs and filtered kernel events per test |
| `data/measurements/` | 72-sample battery trace and the least-squares fit |
| `data/snapshots/` | recorded sysfs state for the Lenovo 65 W adapter and both phone attaches |
| `docs/tests.md` | how to reproduce each test |
| `docs/pd-verdict.md` | why `supports_usb_power_delivery` and `power_operation_mode` can disagree |
| `docs/safety.md` | what the RAM write does and does not do |

Machine identity is published as captured: `20NKS29V00` is the model/type, and
no separate serial was collected. Device serial numbers were removed from
kernel logs. Wall-clock times are IST; kernel timestamps are seconds since boot.

## Upstream

linux-usb, April 2026, ThinkPad T14 Gen 2a (AMD), same modalias and same `-19`:

- <https://ratatoskr.run/linux-usb/2026/04/8893642/t>
- <https://ratatoskr.run/linux-usb/2026/04/8896578/t> (follow-up patch thread)

UCSI maintainer Heikki Krogerus:

> "Again with the missing version. Please contact Lenovo. This is a bug in their
> firmware. The version field must supply the actual ucsi version."

## License

GPL-2.0 (the module must be GPL to link against the kernel). Documentation and
captured data are released under the same terms; see [`LICENSE`](LICENSE).
