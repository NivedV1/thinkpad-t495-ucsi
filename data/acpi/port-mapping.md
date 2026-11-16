# ACPI-level connector mapping (proved from _PLD, not inferred)

The T495 declares two Type-C connectors under `\_SB.UBTC`, and the xHCI root hub
(`\_SB.PCI0.GP17.XHC0.RHUB`) declares HS01-HS04 / SS01-SS04 with `_ADR` 1-8,
which the kernel enumerates as `usb2-port1..4` / `usb3-port1..4`.

Both sides carry a 16-byte `_PLD`. Matching them byte-for-byte:

| ACPI node | `_ADR` | `_PLD` bytes 8-11 | `_PLD` bytes 12-15 | Matches |
|---|---|---|---|---|
| `UBTC.CR01` | 0x05 | `69 0C 80 00` | `01 00 00 00` | `RHUB.PLD1` (offset 12 differs by 0x01) |
| `UBTC.CR02` | 0x08 | `71 0C 00 02` | `00 00 00 00` | `RHUB.PLD4` (identical) |
| `RHUB.HS04` / `SS04` | 0x04 / 0x08 | `71 0C 00 02` | `00 00 00 00` | `PLD4` -> CR02 |

So:

* `usb2-port4` / `usb3-port4` are **physically CR02** (`_ADR 8`).
* `usb2-port1` / `usb3-port1` are **physically CR01** (`_ADR 5`).
* Linux links `usb2-port4`/`usb3-port4` to UCSI `port1` = `CR02` — correct.

Observed against that:

| Device plugged into | Partner object created under | ACPI of that UCSI port | Correct? |
|---|---|---|---|
| `usb 2-4` (CR02) | `port0` | `CR01` | **no** |
| `usb 2-1` (CR01) | `port1` | `CR02` | **no** |

Four independent attachments (Avocent audio, Xiaomi charger, Mi 11X twice)
produced the same inversion, so UCSI connector numbering is swapped relative
to ACPI and to the kernel's own `usbN-portM` links. Userspace cannot map
`/sys/class/typec/portN` to a physical connector.
