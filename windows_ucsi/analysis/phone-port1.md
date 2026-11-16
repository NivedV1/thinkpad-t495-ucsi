# Experiment 6 — phone via USB-C-to-USB-C

Capture: 17 November 2026, 00:32:18–00:32:42, Asia/Kolkata (UTC+05:30), according to the transcript clock.

## Setup and method

The user reported connecting a phone through a C-to-C cable. Phone retail model and cable specifications were not independently identified. Ran the existing capture helper through elevated PowerShell (PID 4512), querying both connectors and individual PDO offsets. The session's restricted environment required approved elevated execution for the diagnostic capture and read-only PnP/CIM queries; the first sandboxed PnP query failed with CIM access unavailable. No phone commands, ADB session, file access, debugging authorization or USB-mode change was performed.

Windows enumerated **Android ADB Interface**, VID_18D1 / PID_4E11, status **OK**. This confirms an ADB USB interface is present, not that an ADB connection is authorized or that file transfer works. The saved broad PnP filter also matched an unrelated Microphone Array name and D: portable-device entry; these are not attributed to the phone.

## UCSI snapshot

| Field | Connector 1 | Connector 2 |
|---|---|---|
| ConnectStatus | 1 | 0 |
| PowerDirection | 1 (laptop supplies power) | 0; inactive |
| PowerOperationMode | 4 (Type-C 1.5 A) | 0 |
| Partner USB flag | 1 | 0 |
| Partner alternate-mode flag | 0 | 0 |
| ConnectorPartnerType | 2 (UFP/device) | 1; inactive |
| RequestDataObject | 0x1304B12C | 0x00000000 |
| PowerBudgetLimitedReason | 0 | 0 |

Mode 4 maps to Type-C 1.5 A; mode 3 is the PD mode observed in the charger experiments. Mapping source: [Linux upstream UCSI definitions](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/typec/ucsi/ucsi.h), consulted during this experiment. The USB-C current mode normally corresponds to a nominal 5 V supply, but this capture does not measure voltage or current, and no actual charging wattage is established.

## Inconsistent power data: do not infer a PD contract

Although status reports Type-C 1.5 A mode, the returned RDO is nonzero. Interpreted purely as a fixed-supply RDO, `0x1304B12C` selects PDO 1 with both current fields equal to 3 A. That is not consistent evidence of a current 1.5 A-mode PD contract. A valid selected local-source voltage cannot be recovered: local source PDO 1 remains the previously observed malformed `0x15000000` (zero voltage/current fields). The cause is unresolved; stale firmware data or interface behavior are possibilities, not demonstrated explanations.

The partner sink query returned:

| Offset | Result | Mechanical fixed-PDO interpretation |
|---|---|---|
| 0 | Empty MESSAGE_IN, DataLength=0 | Missing first sink PDO |
| 1 | 2c d1 02 00 / 0x0002D12C | 9 V / 3 A |
| 2 | e1 c0 03 00 / 0x0003C0E1 | 12 V / 2.25 A |
| 3–6 | Empty | No data |

Those sink profiles are incomplete and are **not proof that the laptop supplies 9 V, 12 V, 27 W or any PD fast-charging level**. No partner source PDOs were returned. The laptop's local source/sink values remained the same as earlier captures.

The defensible conclusion is that the laptop detects a USB device on connector 1, reports supplying it power, and reports Type-C 1.5 A mode. Exact delivered power, phone battery charge rate and a valid active PD contract were not established. Independent electrical/PD analysis would be needed to resolve the inconsistencies.

## Evidence and cleanup

- `captures/ucsi-20261117-003218-034.txt`: raw UCSI transcript.
- `captures/phone-device-state.txt`: PnP identification, including unrelated broad-filter matches noted above.
- `captures/post-phone-state.txt`: cleanup verification.
- `analysis/decoded-phone-port1.json`: existing offline decoder output. This decoder only matches partner-source PDOs; with the laptop acting as source it cannot calculate this experiment's power. Null current/power fields mean undetermined, not zero consumption. Consult this report and raw data for the mode and partner sink values.
- Transcript completed, cleanup restart exit code 0; post-capture UCSI status OK and `TestInterfaceEnabled` absent.

Earlier experiments remain intact. File integrity hashes are recorded in `SHA256SUMS.csv`.
