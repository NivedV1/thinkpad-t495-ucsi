# ThinkPad T495 / T14 Gen 2a (AMD): UCSI reports VERSION `0x0000`, and the data behind it is wrong

Diagnostic project for a Lenovo firmware defect that leaves USB-C unusable under
Linux, plus the evidence needed to report it and a request for other owners to
confirm it on their machines.

**Status:** confirmed on one ThinkPad T495 (`20NK••••••`, BIOS `R12ET64W 1.34`,
Fedora 44, kernel `6.19.10`). The same VERSION defect is already confirmed by the
UCSI maintainer on a ThinkPad T14 Gen 2a (AMD). **Not yet confirmed on other
machines — that is why this repo exists.** No fix is known.

- Support report: [`report/thinkpad-t495-ucsi-report.md`](report/thinkpad-t495-ucsi-report.md)
- Raw captures: [`data/`](data/)
- If you own an affected ThinkPad, please run [the two-command check](#is-your-machine-affected) and open an issue.

> **This project writes to firmware-owned memory when you ask it to.** The
> module is read-only by default. The write is RAM-only and disappears on
> reboot, but read [`docs/safety.md`](docs/safety.md) before using it.

---

## Intent

1. Show, with reproducible local evidence, that the UCSI interface on these
   ThinkPads cannot initialize in Linux because firmware reports
   `VERSION = 0x0000`.
2. Show that populating the version is **not sufficient**: the data the EC
   returns through UCSI is internally inconsistent and cannot be used to drive
   USB-C, power delivery or DisplayPort.
3. Give other owners a safe, read-only way to check their own machine, so the
   defect can be confirmed across models and BIOS versions rather than argued
   from a single laptop.
4. Ask Lenovo to fix the firmware, and ask the kernel side to consider whether a
   quirk is warranted in the meantime.

## TL;DR findings

| # | Finding |
|---|---|
| 1 | The ACPI UCSI device is present and well-formed (`_HID USBC000`, `_CID PNP0CA0`, `_CRS` region `0xBD6B2000+0x1000`, `_DSM` via EC mailbox), but **VERSION reads `0x0000`**. `ucsi_register()` treats that as unusable and returns `-ENODEV`, so `/sys/class/typec/` is empty. Probe fails silently. |
| 2 | Patching VERSION in RAM (test only) makes the driver bind and ports appear. **The data is still wrong.** |
| 3 | A Xiaomi 67 W **USB-A** charger — where PD is physically impossible — is reported as a **PD 2.0 contract of 5 V / 3 A**, while the battery is measured charging at **17.07 W**, more than a 5 V / 3 A source can deliver. |
| 4 | The same phone and cable get **opposite PD verdicts** on the two connectors, reproducibly: `default`/no-PD on one, `usb_power_delivery`/PD 2.0 on the other. |
| 5 | Ports advertise **invalid source PDOs** (`0 mV/0 mA` and `1050 mV/2560 mA`), never expose partner identity or cable e-marker data, and their alt-mode table cannot produce DisplayPort (`0xff01` is absent). |
| 6 | UCSI **connector numbering is swapped** relative to ACPI `_ADR` and to the kernel's own `usbN-portM` links — proved from `_PLD` bytes, not inferred. |

## Is your machine affected?

Read-only. Nothing is modified.

```bash
# 1. does the firmware expose a UCSI device, and did it bind?
ls /sys/class/typec/ 2>/dev/null | wc -l
for d in /sys/bus/acpi/devices/USBC000:*; do cat "$d/modalias"; readlink -f "$d/driver"; done
sudo dmesg | grep -iE 'ucsi|typec'

# 2. what does the firmware say the version is? (needs the module, read-only)
sudo ./scripts/10-dump-ucsi.sh
```

Interpretation:

| Observation | Meaning |
|---|---|
| `modalias` is `acpi:USBC000:PNP0CA0:`, `typec` count is 0, dmesg silent | your firmware has the same defect |
| `VERSION=0x0000` in the module output | confirmed, same as this machine |
| a driver is bound and ports already exist | **not affected** — please still report your model/BIOS, it narrows the range |

## What we found

### 1. The version field is zero, and probe dies silently

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

### 2. With VERSION patched, the interface binds but lies

With `0x0100` or `0x0110` written into VERSION, the driver registers the
interface and exposes `port0`, `port1`, partners and PSYs. Four attachments
were tested 1 Hz at a time:

| Attachment | UCSI attach | `power_operation_mode` | Partner PD | Reality |
|---|---|---|---|---|
| Avocent USB audio | yes | `default` | no | correct |
| Non-PD charger | **no** | — | — | AC goes online, battery charges, zero UCSI events |
| Xiaomi 67 W **A-to-C** | yes | **`usb_power_delivery`** | **yes, PD 2.0, 5 V/3 A** | PD impossible; 17.07 W measured |
| Mi 11X **C-to-C**, connector A | yes | `default` | no | correct, but no source PD |
| Mi 11X, connector B | yes | **`usb_power_delivery`** | **yes, PD 2.0, 5 V/1.5 A** | same device, opposite answer |
| Mi 11X, back to connector A | yes | `default` | no | verdict follows the connector |

### 3. The 17.07 W contradiction

A USB-A charger has no CC conductor, so it cannot negotiate PD. UCSI reports a
5 V / 3 A PD contract anyway. Meanwhile the battery energy counter, fitted over
six uninterrupted minutes:

```text
samples        72 over 357 s (6.0 min)
energy         22.390 Wh -> 24.090 Wh  (delta 1.700 Wh)
energy slope   17.07 W        <- independent of the noisy power_now
power_now      mean 17.56 W   (min 17.50, max 17.61)
batt voltage   11.72 V -> 11.79 V      (rising = genuine charge)
status/ac      Charging / 1            (no dropouts, no renegotiation)
```

5 V x 3 A is 15 W, and that is before system draw, so the input must exceed
17 W: VBUS is above 5 V. The charger's vendor cable unlocks that, and UCSI
reports neither the real voltage nor a real contract.

### 4. Port and partner data is not usable

```text
port0 source-capabilities/1:fixed_supply:    0 mV /    0 mA
port1 source-capabilities/1:fixed_supply: 1050 mV / 2560 mA   <- not a valid PD voltage
partner usb_power_delivery_revision: 0.0      while the PD object says 2.0
id_header / product / product_type:  always empty
portN-cable:                         never created (no e-marker is ever read)
altmodes:                            0x17ef and 0x01ff, vdo=1, identical on all four entries
```

DisplayPort's SVID is `0xff01`, which never appears, so DP alt mode cannot be
registered even with the version patched. Idle connectors also keep stale
`power_operation_mode` / `power_role` values after detach.

### 5. Connector numbering is swapped

`_SB.UBTC.CR02` (`_ADR 8`) carries the same `_PLD` bytes as root-hub port 4
(`71 0C 00 02`), and Linux correctly links `usb2-port4`/`usb3-port4` to UCSI
`port1` = `CR02`. Nevertheless, a device on `usb 2-4` creates its partner under
`port0` = `CR01`, and a device on `usb 2-1` creates it under `port1` = `CR02`.
Four attachments, same inversion every time. Details:
[`data/acpi/port-mapping.md`](data/acpi/port-mapping.md).

## Tests done

| Test | Result |
|---|---|
| Read UCSI register block before/after write | `VERSION 0x0000` → `0x0110`; `0x0100` and `0x0110` behave identically |
| kprobe probe path | version read returns 0; `ucsi_register` returns `-19` |
| Force bind without patch | `ENODEV` |
| Hotplug with non-PD charger | AC online, battery charges, **no** UCSI event, no partner |
| Hotplug with USB audio adapter | partner add/remove, `data_role` flips, ~1 s |
| Xiaomi 67 W A-to-C charger | fabricated PD 2.0 / 5 V 3 A; **17.07 W** measured over 6 min |
| Mi 11X C-to-C, both connectors, 3 attaches | opposite PD verdicts, deterministic per connector |
| PD object vs partner revision | object `2.0`, partner attribute `0.0` |
| Source/sink PDO readout | invalid source PDOs on both ports; sink PDOs 5 V/100 mA |
| Alt-mode enumeration | `0x17ef`, `0x01ff` only; no `0xff01` |
| Detach behaviour | stale opmode/role retained on the idle connector |
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

**Minimum (read-only, ~1 minute):**

```bash
git clone https://github.com/NivedV1/thinkpad-t495-ucsi.git
cd thinkpad-t495-ucsi
sudo ./scripts/00-prereq.sh 2>&1 | tee /tmp/prereq.txt
sudo ./scripts/10-dump-ucsi.sh 2>&1 | tee /tmp/dump.txt
```

Then [open an issue](https://github.com/NivedV1/thinkpad-t495-ucsi/issues/new/choose) and paste the two files. The
template asks for model, BIOS, kernel and the `VERSION` line.

**Full (if you are willing to patch RAM for one boot):** run
`20-enable-ucsi.sh` and, with a known PD charger and a phone:

1. `30-snapshot.sh` once per attachment, both connectors;
2. `40-watch.sh` while plugging and unplugging;
3. `50-charge-rate.sh 360` for each charger;
4. `90-undo.sh`, then reboot.

**What would be most valuable**

| If you have | It answers |
|---|---|
| an affected ThinkPad with a **different BIOS** | whether Lenovo fixed this in a later release |
| a T14 Gen 2a / T14s / X13 / other AMD ThinkPad of the same generation | how wide the defect is |
| a Windows install on the same machine | whether Windows sees PD/DP alt mode, i.e. whether the EC data is wrong only via UCSI |
| a USB-C inline power meter | whether the "PD" connector really negotiates a contract, and at what voltage |
| a USB-C to HDMI/DP adapter | whether DP alt mode works despite the missing `0xff01` |
| a **genuine PD** charger with a C-to-C cable | a real contract to compare the fabricated one against |

Please do **not** open an issue with only "me too" — the model, BIOS, kernel,
`VERSION` value and whether the driver binds are the minimum to make it useful.

## What we still do not know

- **Whether either connector genuinely negotiates PD.** The verdict differs per
  connector, and the port's own PDOs are invalid, so it could be arbitrary EC
  reporting. An inline USB-C meter would settle it.
- **The actual VBUS voltage** during the 17.07 W charge. No Linux interface
  exposes it: `AC` has only `online`, and the UCSI PSYs report either 0 or a
  value that does not match the port's own PDOs.
- **Whether DisplayPort over USB-C works in Windows** on this machine. If it
  does, the alt-mode table is a Linux-visible defect only.
- **Whether a kernel quirk is appropriate** for the version field alone, given
  that the data behind it is unusable. Upstream has no Lenovo quirk; the only
  zero-version workarounds are DMI quirks for one Acer and one LG Gram model.

## Data in this repo

| Path | Contents |
|---|---|
| `report/thinkpad-t495-ucsi-report.md` | the support report prepared for Lenovo (full + web-form version) |
| `module/ucsi_peek.c` | the diagnostic module (read-only by default) |
| `scripts/` | prerequisite check, register dump, enable/undo, snapshot, 1 Hz watch, charge-rate fit |
| `data/ucsi-register-block.txt` | raw register dumps, three states |
| `data/acpi/ssdt1-UBTC-excerpt.dsl` | `_SB.UBTC`, `CR01`, `CR02`, `_DSM`, EC mailbox |
| `data/acpi/port-mapping.md` | `_PLD` byte matching that proves the numbering swap |
| `data/device-matrix.md` | every attachment, verbatim sysfs values |
| `data/logs/` | 1 Hz state logs and filtered kernel events per test |
| `data/measurements/` | 72-sample battery trace and the least-squares fit |
| `data/snapshots/` | recorded sysfs state for the charger and both phone attaches |
| `docs/tests.md` | how to reproduce each test |
| `docs/safety.md` | what the RAM write does and does not do |

The machine serial is masked in this repository and device serial numbers were
removed from kernel logs. Wall-clock times are IST; kernel timestamps are
seconds since boot.

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
