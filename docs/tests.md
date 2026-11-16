# Tests and how to reproduce each one

Everything below was run on a ThinkPad T495 `20NKS29V00`, BIOS `R12ET64W (1.34)`,
Fedora 44, kernel `6.19.10-300.fc44.x86_64`, Secure Boot off, lockdown `none`.
Times in `data/logs/*/state.log` are local wall clock (IST, UTC+5:30); kernel
timestamps are seconds since boot.

## T0 — baseline before the patch

```bash
ls /sys/class/typec/                       # empty
cat /sys/bus/platform/devices/USBC000:00/modalias
sudo sh -c 'echo USBC000:00 > /sys/bus/platform/drivers/ucsi_acpi/bind'
```

Expected: empty typec class, `acpi:USBC000:PNP0CA0:`, bind fails with
`No such device`, and nothing UCSI-related in dmesg.

## T1 — read the register block

```bash
sudo ./scripts/10-dump-ucsi.sh
```

Expected on an affected machine:

```text
ucsi_peek: VERSION=0x0000 CCI=0x08000002
```

This is the decisive, no-side-effect result. If VERSION is non-zero and the
driver binds on its own, your machine is not affected by this defect.

## T2 — kprobe the probe path

```bash
sudo modprobe ucsi_acpi
sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null
cd /sys/kernel/debug/tracing

echo 'r:read_ver ucsi_acpi_read_version $retval' >> kprobe_events
echo 'p:reg ucsi_register version=%di' >> kprobe_events
echo 'r:probe_ret ucsi_acpi_probe $retval' >> kprobe_events
echo 1 > events/kprobes/enable
echo USBC000:00 > /sys/bus/platform/drivers/ucsi_acpi/bind   # fails, as expected
grep -E 'read_ver|reg:|probe_ret' trace
```

Expected:

```text
   read_ver: (ucsi_acpi_read_version+0x0/...) arg1=0
   reg:      (ucsi_register+0x0/...) version=0
   probe_ret:(ucsi_acpi_probe+0x0/...) arg1=-19
```

The exact offsets depend on your kernel; the three values (`0`, `0`, `-19`)
are the point. A symbol-resolution trace of the same path on this machine is in
`report/thinkpad-t495-ucsi-report.md`.

## T3 — patch and bind

```bash
sudo ./scripts/20-enable-ucsi.sh
```

Expected:

```text
ucsi_peek: wrote VERSION -> 0x0100 (readback)
ucsi_acpi USBC000:00: Registered UCSI interface with version 1.0.0
typec port1: bound usb2-port4 (ops connector_ops)
typec port1: bound usb3-port4 (ops connector_ops)
```

`0x0100` and `0x0110` gave identical results.

## T3b — bind without writing firmware

The same binding, done by replacing the driver instead of the register. This is
the change proposed upstream ([`patches/`](../patches)), and it is the only
route that touches no firmware-owned memory.

```bash
sudo ./scripts/15-build-quirk.sh
```

It fetches `ucsi_acpi.c` and `ucsi.h` for `$(uname -r)`, applies the DMI quirk,
builds out-of-tree, unloads the stock module and inserts the rebuilt one.

Expected:

```text
ucsi_acpi USBC000:00: UCSI version is zero, assuming 1.1
typec port1: bound usb1-port4 (ops connector_ops)
typec port1: bound usb3-port4 (ops connector_ops)

== typec ==
   port0
   port0-partner
   port1

== partner source capabilities (what sysfs exposes) ==
   1:fixed_supply  5000mV  3000mA
   power_operation_mode: usb_power_delivery
```

`UCSI_VERSION_1_0` and `1_1` behave identically here; 1.1 is kept because
`GET_CAPABILITY` advertises `bcdUsbTypeCVersion 0x0110`.

With the 65 W adapter on connector 1, the full capture is
[`data/snapshots/lenovo-65w-kernel-quirk.txt`](../data/snapshots/lenovo-65w-kernel-quirk.txt):
the quirk makes the ports and the RDO visible, and sysfs still reports one
source PDO (5 V / 3 A) against the four the firmware has.

Undo:

```bash
sudo rmmod ucsi_acpi && sudo modprobe ucsi_acpi
```

## T4 — plain device, correct case

Plug a USB audio adapter or a USB 2.0 stick into one connector.

```bash
sudo ./scripts/40-watch.sh /tmp/t4 120
```

Expected: partner appears and disappears, `data_role` = `[host]`,
`power_role` = `[source]`, `power_operation_mode` = `default`, everything
within about a second. This shows the interface works for non-PD devices.
Capture: [`data/logs/1-audio-hotplug`](../data/logs/1-audio-hotplug).

## T5 — non-PD charger is invisible to UCSI

Plug a charger with no PD support.

```bash
sudo ./scripts/40-watch.sh /tmp/t5 120
```

Expected: `AC/online` goes 1, `BAT0/status` = `Charging`, and **no** new
partner, no opmode change and no UCSI connector-change event on that
connector. Capture: [`data/logs/2-charger-nonpd`](../data/logs/2-charger-nonpd)
(in that run an unrelated audio adapter was on the other connector, hence
`port0 ... partner=yes`).

## T6 — `GET_PDOS` returns one PDO for a four-PDO request

This is the decisive test for the second defect. Attach any PD source (the
machine's own 65 W adapter is ideal), bind the interface, and read a single
connector's partner source PDOs.

```bash
# Linux reads a batch of 4 internally; the snapshot shows what it kept:
sudo ./scripts/30-snapshot.sh /tmp/t6
grep -A4 'partner source PDOs' /tmp/t6/summary.txt
```

On this machine the batch read yields exactly one entry:

```text
  partner source PDOs:
  1:fixed_supply/
    voltage                5000mV
    maximum_current        3000mA
```

Windows, on the same machine, asks for four and receives `DataLength: 4`; then
asks offsets 0–3 individually and receives the whole list:

```text
offset 0 -> 2c 91 01 0a   5 V / 3 A
offset 1 -> 2c d1 02 00   9 V / 3 A
offset 2 -> 2c b1 04 00   15 V / 3 A
offset 3 -> 4f 41 06 00   20 V / 3.35 A
offset 4 -> DataLength: 0
```

The first PDO Linux reads matches Windows' PDO 1 byte for byte, so the transport
is fine and only the count is wrong. The ThinkPad 65 W adapter shows the same
shape with PDO 4 = `0x00164145` (20 V / 3.25 A).

`5 V × 3 A` is therefore the first of four advertised profiles, not the whole
list. It is not necessary to explain the 17 W battery draw with a hypothetical
voltage above 5 V: the RDO selects position 4 (20 V) at 3.25 A, which is 65 W.

Capture: [`data/logs/3-xiaomi-a-to-c`](../data/logs/3-xiaomi-a-to-c),
[`data/measurements`](../data/measurements),
[`windows_ucsi/captures/ucsi-results.txt`](../windows_ucsi/captures/ucsi-results.txt).

### Linux equivalent of the offset walk

The kernel's own `GET_PDOS` is a single four-PDO read, so sysfs only ever shows
one entry. The per-offset walk can still be done in Linux through UCSI debugfs,
which sends the same control value the Windows tool sent:

```bash
sudo ./scripts/20-enable-ucsi.sh          # bind the driver (RAM patch)
sudo ./scripts/25-walk-pdos.sh
```

Example output on this machine:

```text
conn 1 partner 1 offset 0  0x0A01912C   5000 mV  3000 mA (fixed)
conn 1 partner 1 offset 1  0x0002D12C   9000 mV  3000 mA (fixed)
conn 1 partner 1 offset 2  0x0004B12C  15000 mV  3000 mA (fixed)
conn 1 partner 1 offset 3  0x0006414F  20000 mV  3350 mA (fixed)
conn 1 partner 1 offset 4  no data (end of list)
```

The debugfs interface does not expose `CCI DataLength`; a zero reply marks the
end of the list. For a four-PDO request the kernel writes `0x700810010`, which
is exactly the `UCSI_CONTROL` value in the Windows capture — the requests are
identical, only the reply length differs.

## T7 — same phone, both connectors: PD state is not stable

Attach a phone over a C-to-C cable, then move it to the other connector, then
back.

```bash
sudo ./scripts/40-watch.sh /tmp/t7 200   # attach on connector A
# move the cable to connector B, then back to A, while the capture runs
```

Observed, three attaches, each with a fresh enumeration:

| Run | `usb 2-x` | UCSI port | opmode | partner PD |
|---|---|---|---|---|
| 1 | `2-4` | `port0` | `default` | no |
| 2 | `2-1` | `port1` | `usb_power_delivery` | yes, 2.0, 5 V/1.5 A |
| 3 | `2-4` | `port0` | `default` | no |

The verdict tracked the connector in this run, but it is timing-dependent, not a
connector property (see T7b). Capture:
[`data/logs/4-phone-c-to-c`](../data/logs/4-phone-c-to-c).

## T7b — replug the same charger on one connector

This is the test that shows the two PD values are sampled at different times.

```bash
sudo ./scripts/40-watch.sh /tmp/t7b 180
# start with the charger attached, unplug it, wait ~5 s, replug it
```

Observed on this machine (1 Hz, 180 s):

```text
22:05:00  port1 opmode=usb_power_delivery  partner supports_pd=no   PD object rev 2.0, 5 V/3 A
22:06:47  port1 opmode=default             partner gone
22:06:54  port1 opmode=usb_power_delivery  partner supports_pd=yes  PD object not yet present
22:06:57  port1 opmode=usb_power_delivery  partner supports_pd=yes  PD object rev 2.0, 5 V/3 A
```

Both attaches landed on the same `port1`. `supports_usb_power_delivery` is
captured once at partner registration; `power_operation_mode` follows a later
notification, so the two can disagree for the life of the attach. Capture:
[`data/snapshots/xiaomi-charger-typec.txt`](../data/snapshots/xiaomi-charger-typec.txt).

## T7c — flip the connector on the same adapter

The strongest version of T7b needs no exotic charger: use the machine's own
65 W adapter.

```bash
sudo ./scripts/40-watch.sh /tmp/t7c 300
# attach the adapter, leave it for a few minutes, then unplug it, turn the
# connector over, and plug it back in
```

Observed on this machine (Lenovo 65 W, 20 V / 3.25 A, same `port1` throughout):

```text
23:20:07-23:28:19  opmode=usb_power_delivery  supports_pd=no   no PD object at all
23:28:20           unplug; opmode stays usb_power_delivery (stale)
23:28:24  replug   opmode=usb_power_delivery  supports_pd=yes  PD object not yet linked
23:28:25           PD device directory exists but is not linked to the partner
23:28:26           PD object linked: rev 2.0, source PDO 5 V / 3 A
```

Check all four together, because any one alone is misleading:

```bash
cat /sys/class/typec/port1/power_operation_mode
cat /sys/class/typec/port1-partner/supports_usb_power_delivery
readlink -f /sys/class/typec/port1-partner/usb_power_delivery
cat /sys/class/typec/port1-partner/usb_power_delivery/source-capabilities/*/voltage
```

Then compare the reported PDO with the battery:

```bash
cat /sys/class/power_supply/BAT0/power_now      # 17369000 uW on this machine
cat /sys/class/power_supply/BAT0/voltage_now    # 11634000 uV
```

17.37 W into the pack at 11.63 V is 1.49 A. That is well inside a 20 V / 3.25 A
(65 W) contract, and impossible from the single `5 V / 3 A` entry Linux shows —
which is the point: the entry is truncated, not negotiated. Capture:
[`data/snapshots/lenovo-65w-typec.txt`](../data/snapshots/lenovo-65w-typec.txt).

## T8 — PDOs, alt modes, identity, stale state

```bash
sudo ./scripts/30-snapshot.sh /tmp/t8          # with a device attached
sudo ./scripts/30-snapshot.sh /tmp/t8-idle     # after unplugging
diff -u /tmp/t8-idle/summary.txt /tmp/t8/summary.txt | head -40
```

Check for:

- `source-capabilities` of `0 mV / 0 mA` or `1050 mV / 2560 mA`
- only one partner source PDO on a charger that advertises more — the batch
  read is truncated (`GET_PDOS` returns one PDO per call)
- `voltage_now = 0` while `current_now` is non-zero: `voltage_now` indexes
  `src_pdos[rdo_index - 1]`, beyond the single PDO the driver read, while
  `current_now` comes from the RDO
- partner `usb_power_delivery_revision` = `0.0` while the PD object says `2.0`
  (kernel-side only: the attribute is filled at UCSI >= 2.1)
- empty `id_header`, `product`, `product_type`, `number_of_alternate_modes = 0`
- no `cable` directory
- alt modes `0x17ef` / `0x01ff` with `vdo=0x00000001`
- right after unplugging, `power_operation_mode` may still show the old value
  for a second or two before returning to `default`

## T9 — DisplayPort alt mode

With a USB-C to HDMI/DP adapter attached, look for a new DRM connector:

```bash
ls /sys/class/drm/
sudo dmesg | grep -iE 'dp alt|displayport|typec'
```

UCSI exposes no `0xff01` SVID, so DP alt mode cannot be registered through this
path. DP was not tested on Windows, so whether the hardware can do it is still
open. If you have a machine where it works, that is worth an issue.

## T10 — check whether a different BIOS fixed it

Before running anything that writes, `scripts/00-prereq.sh` and
`scripts/10-dump-ucsi.sh` are enough: if `typec` entries already exist or
`VERSION` is non-zero, Lenovo has changed the firmware. Please report the BIOS
version with the output.

## T11 — Windows cross-check

The strongest independent test does not need the RAM patch. Boot Windows on the
same machine and follow [`windows_ucsi/README.md`](../windows_ucsi/README.md).
Report four things:

1. PnP status of `ACPI\USBC000\0` and whether `UcmUcsiAcpiClient` is bound;
2. the UCSI version the tool prints (expected `0.0.0`);
3. `CCI DataLength` for a multi-PDO `GET_PDOS` (expected `4` for a request of 3);
4. the per-offset PDO list (expected four entries, up to 20 V).

If Windows shows four PDOs while Linux shows one, the truncated reply is
confirmed on a second OS with Microsoft's own client stack.
