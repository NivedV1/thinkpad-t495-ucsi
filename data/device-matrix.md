# Attachment test matrix

All rows: T495 20NK••••••, BIOS 1.34, kernel 6.19.10-300.fc44.x86_64, VERSION
patched to 0x0110 in RAM (one boot only). "UCSI says" is verbatim from
`/sys/class/typec/`.

| # | Attachment | Cable | USB enumeration | UCSI attach | data_role | power_role | power_operation_mode | Partner PD | Reality |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Avocent AB17X USB audio (0624:3d3f) | C-to-A? (data only) | yes, `usb 2-4` | yes | host | source | `default` | no | correct |
| 2 | Non-PD charger ("charger #1") | C-to-C | none (no data) | **no** | - | - | - | - | AC=1, battery charging, zero UCSI events |
| 3 | Xiaomi 67 W Combo (Type-A), MDY-12-EJ | A-to-C | none (A port, no data) | yes | device | **sink** | **`usb_power_delivery`** | **yes, PD 2.0, 5 V / 3 A** | PD impossible over A-to-C; 17.07 W measured |
| 4 | Mi 11X (18d1:4ee2 / 18d1:4e11) | C-to-C | yes, `usb 2-4` | yes | host | source | `default` | no | correct, but no source PD |
| 5 | Mi 11X, same cable | C-to-C | yes, `usb 2-1` | yes | host | source | **`usb_power_delivery`** | **yes, PD 2.0, 5 V / 1.5 A** | same device, opposite verdict |
| 6 | Mi 11X, back to first connector | C-to-C | yes, `usb 2-4` | yes | host | source | `default` | no | verdict follows the connector |

Rows 4-6 were three separate attaches with fresh enumeration each time
(`usb 2-4: new high-speed USB device number N`), so the difference is not a
stale cached value.

## Port capabilities as reported

```
port0 source-capabilities/1:fixed_supply:    0 mV /    0 mA
port1 source-capabilities/1:fixed_supply: 1050 mV / 2560 mA    <- not a valid PD voltage
port0 sink-capabilities/1:fixed_supply:   5000 mV /  100 mA
port1 sink-capabilities/1:fixed_supply:   5000 mV /  100 mA
```

`usb_power_delivery_revision` on the port is always `2.0`. On the partner it
reads `0.0` even when the partner's PD object reports `2.0`.

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
