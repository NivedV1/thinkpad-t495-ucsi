# Attachment test matrix

All rows: T495 20NKS29V00, BIOS 1.34, kernel 6.19.10-300.fc44.x86_64, VERSION
patched to 0x0110 in RAM (one boot only). "UCSI says" is verbatim from
`/sys/class/typec/`.

| # | Attachment | Cable | USB enumeration | UCSI attach | data_role | power_role | power_operation_mode | Partner PD | Reality |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Avocent AB17X USB audio (0624:3d3f) | C-to-A? (data only) | yes, `usb 2-4` | yes | host | source | `default` | no | correct |
| 2 | Non-PD charger ("charger #1") | C-to-C | none (no data) | **no** | - | - | - | - | AC=1, battery charging, zero UCSI events |
| 3 | Xiaomi 67 W Combo (Type-A), MDY-12-EJ | A-to-C | none (A port, no data) | yes | device | **sink** | **`usb_power_delivery`** | **yes, PD 2.0, first PDO 5 V / 3 A** | 17.07 W measured; Windows reads four PDOs and 20 V requested |
| 4 | Mi 11X (18d1:4ee2 / 18d1:4e11) | C-to-C | yes, `usb 2-4` | yes | host | source | `default` | no | correct, but no source PD |
| 5 | Mi 11X, same cable | C-to-C | yes, `usb 2-1` | yes | host | source | **`usb_power_delivery`** | **yes, PD 2.0, 5 V / 1.5 A** | same device, opposite verdict at the time |
| 6 | Mi 11X, back to first connector | C-to-C | yes, `usb 2-4` | yes | host | source | `default` | no | opposite again |
| 7 | Lenovo 65 W adapter (20 V / 3.25 A, MFG 6/2015), orientation A | captive C | none | yes | device | **sink** | **`usb_power_delivery`** | **no, no PD object for 8 min** | 17.11-17.27 W measured |
| 8 | same adapter, connector flipped over | captive C | none | yes | device | **sink** | **`usb_power_delivery`** | **yes, PD 2.0, first PDO 5 V / 3 A** | 17.37 W measured at 11.63 V |

Rows 7-8 are the machine's own charger, the same part, on the same `port1`,
with only the connector flipped. One attach never linked a PD object at all;
the other linked one 2 s after the partner appeared.

The single `5 V / 3 A` entry in every `usb_power_delivery` object is not the
adapter's full list. This firmware returns one PDO per `GET_PDOS` request, and
Linux asks only once; Windows walks offsets 0-3 and reads 5 V, 9 V, 15 V and
20 V from the same adapters. See `../README.md` §2-§3 and
`snapshots/lenovo-65w-typec.txt`.

Rows 4-6 were three separate attaches with fresh enumeration each time
(`usb 2-4: new high-speed USB device number N`), so the difference is not a
stale cached value.

They were read as connector-dependent at the time. They are not stable: a later
replug of the charger on one connector flipped `supports_usb_power_delivery`
from `no` to `yes` on the same `port1`, so rows 4-6 are better read as a
registration-time race. See `snapshots/xiaomi-charger-typec.txt`.

## Port capabilities as reported

```
port0 source-capabilities/1:fixed_supply:    0 mV /    0 mA      (0x15000000)
port1 source-capabilities/1:fixed_supply: 1050 mV / 2560 mA    (0x15005500, not a PD voltage)
port0 sink-capabilities/1:fixed_supply:   5000 mV /  100 mA
port1 sink-capabilities/1:fixed_supply:   5000 mV /  100 mA
```

The invalid local source PDOs are not a Linux artefact: Windows returns the same
two DWORDs on connectors 1 and 2. They are a separate firmware defect from the
`GET_PDOS` truncation.

`usb_power_delivery_revision` on the port is always `2.0`. On the partner it
reads `0.0` even when the partner's PD object reports `2.0`; that is kernel-side
(`desc.pd_revision` is only filled at UCSI >= 2.1), not a firmware fault.

The PSY is derived from the truncated PDO list and the RDO. With `num_pdos = 1`,
`voltage_now` indexes `src_pdos[3]` and reads 0 V, `voltage_max` reads
`src_pdos[0]` = 5 V, and `current_max` reads 3 A, while `current_now` comes
straight from the RDO and reads 3.25 A. The RDO itself is correct: position 4,
20 V, 3.25 A = 65 W.

## Alternate modes (identical on all four port entries)

```
svid=0x17ef mode=1 vdo=0x00000001 active=yes
svid=0x01ff mode=1 vdo=0x00000001 active=yes
```

DisplayPort's SVID is `0xff01`; it never appears, so DP alt mode cannot
register regardless of the VERSION patch.

## Never observed, in any run

- partner `id_header`, `product`, `product_type` (always empty)
- `number_of_alternate_modes` != 0
- any `portN-cable` object (no e-marker is ever read; `vconn_source = no`)
- `ucsi-source-psy-*` `voltage_now` != 0
