# Tests and how to reproduce each one

Everything below was run on a ThinkPad T495 `20NK••••••`, BIOS `R12ET64W (1.34)`,
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

## T6 — USB-A charger produces a fabricated PD contract

Plug a Xiaomi 67 W Charging Combo (Type-A, MDY-12-EJ) with its own A-to-C cable.

```bash
sudo ./scripts/30-snapshot.sh /tmp/t6
sudo ./scripts/50-charge-rate.sh 360 /tmp/t6-rate
```

Expected (and what happened here):

```text
power_operation_mode          usb_power_delivery
partner supports_usb_power_delivery = yes
partner PD object revision    2.0
partner source PDOs           5000 mV / 3000 mA
cable object                  none            <- no e-marker is read
psy usb_type                  "C [PD] PD_PPS"
```

and from the energy counter:

```text
energy slope   17.07 W      (over 357 s, 72 samples)
```

PD cannot exist on an A-to-C cable, and 5 V x 3 A cannot deliver 17 W, so the
reported contract does not describe the power path. Capture:
[`data/logs/3-xiaomi-a-to-c`](../data/logs/3-xiaomi-a-to-c),
[`data/measurements`](../data/measurements).

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

## T8 — PDOs, alt modes, identity, stale state

```bash
sudo ./scripts/30-snapshot.sh /tmp/t8          # with a device attached
sudo ./scripts/30-snapshot.sh /tmp/t8-idle     # after unplugging
diff -u /tmp/t8-idle/summary.txt /tmp/t8/summary.txt | head -40
```

Check for:

- `source-capabilities` of `0 mV / 0 mA` or `1050 mV / 2560 mA`
- partner `usb_power_delivery_revision` = `0.0` while the PD object says `2.0`
  (kernel-side only: the attribute is filled at UCSI >= 2.1)
- empty `id_header`, `product`, `product_type`, `number_of_alternate_modes = 0`
- no `cable` directory
- PSY `current_now` above the last source PDO's current, or `voltage_now = 0`
  while the PDO has a voltage — both come from the EC's RDO
- alt modes `0x17ef` / `0x01ff` with `vdo=0x00000001`
- after unplugging, `power_operation_mode` / `power_role` still showing the old
  value on the idle connector

## T9 — DisplayPort alt mode

With a USB-C to HDMI/DP adapter attached, look for a new DRM connector:

```bash
ls /sys/class/drm/
sudo dmesg | grep -iE 'dp alt|displayport|typec'
```

UCSI exposes no `0xff01` SVID, so DP alt mode cannot be registered through this
path. If you have a machine where it works, that is worth an issue.

## T10 — check whether a different BIOS fixed it

Before running anything that writes, `scripts/00-prereq.sh` and
`scripts/10-dump-ucsi.sh` are enough: if `typec` entries already exist or
`VERSION` is non-zero, Lenovo has changed the firmware. Please report the BIOS
version with the output.
