# Captures

Each directory holds a 1 Hz `state.log` (from `scripts/40-watch.sh`) and a
filtered `kernel-events.txt` covering the same window.

| Directory | Attachment | Window |
|---|---|---|
| `1-audio-hotplug` | Avocent AB17X USB audio, unplug/replug | 150 s |
| `2-charger-nonpd` | non-PD charger; an unrelated audio adapter was on the other connector | 240 s |
| `3-xiaomi-a-to-c` | Xiaomi 67 W Type-A charger, A-to-C cable | 300 s |
| `4-phone-c-to-c` | Mi 11X, C-to-C | 200 s |

`state.log` format (fields appear in this order, one line per second):

```
HH:MM:SS ac=<0|1> bat=<status>/<power_now> port0[dr=<data_role> pr=<power_role> om=<opmode> part=<yes|no> cable=<yes|none> spd=<partner supports_pd> pd=<partner pd rev> idh=<id_header> prod=<product>] port1[...]
```

`-` means the attribute did not exist (no partner). Empty after `idh=` means the
file existed but was empty.

The four logs in this directory were captured before the `spd=` field was added
to the script; for those, use `pd=` for the partner revision and the files in
`../snapshots/` for the partner's `supports_usb_power_delivery` value.

Device serial numbers were replaced with `<redacted>` in `kernel-events.txt`.
Timestamps in `kernel-events.txt` are seconds since boot, not wall clock.
