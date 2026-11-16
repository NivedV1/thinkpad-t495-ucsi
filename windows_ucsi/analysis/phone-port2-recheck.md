# Experiment 7 — phone recheck on connector 2

Capture: 17 November 2026, 00:36:25–00:36:54, Asia/Kolkata (UTC+05:30), according to the Windows transcript clock.

The user requested another check of whether the phone was connected using PD. Ran the same archived capture helper through elevated PowerShell (PID 20728); the test interface was enabled temporarily and restored afterward. Phone and cable identity are carried forward from the preceding user context, not independently identified in this recheck. No phone-side commands were run.

## Fresh result

| Field | Connector 1 | Connector 2 |
|---|---|---|
| ConnectStatus | 0 | 1 |
| PowerOperationMode | 0 | 4 (Type-C 1.5 A) |
| PowerDirection | 1; inactive | 1 (laptop supplying power) |
| USB partner flag | 0 | 1 |
| Partner type | 1; inactive | 2 (UFP/device) |
| RDO | 0x00000000 | 0x1304B12C |

The active connection moved from UCSI connector 1 in experiment 6 to connector 2 in this capture. The same mode and RDO discrepancy persists: status reports Type-C 1.5 A mode (4), not PD mode (3), while the nonzero RDO mechanically decodes as selecting PDO 1 with 3 A current fields. The local source PDO on connector 2 is still malformed (`00 55 00 15` / `0x15005500`). No trustworthy selected voltage or PD charging wattage can be established.

Partner sink PDO offset 0 was empty; offset 1 returned `2c d1 02 00` (mechanically 9 V / 3 A), and offset 2 returned `e1 c0 03 00` (12 V / 2.25 A). Later offsets were empty. These incomplete sink capabilities are not evidence that the laptop is delivering those voltages or power levels. No partner source PDOs were returned. The active phone's current mode/RDO findings match experiment 6 despite the connector change.

**Conclusion:** The fresh UCSI status does not report an active PD-mode connection. It reports laptop-to-device power in Type-C 1.5 A mode. The contradictory RDO prevents a reliable PD-contract interpretation; it does not prove the phone lacks PD support. No instantaneous electrical measurements were taken.

## Evidence and cleanup

- Raw capture: `captures/ucsi-20261117-003625-791.txt`.
- Decoder output: `analysis/decoded-phone-port2.json`; current and wattage remain undetermined because this decoder handles partner-source profiles, not the laptop-source case.
- Post-capture verification: `captures/post-phone-recheck-state.txt`.
- Transcript completed with cleanup restart exit code 0. Device status afterward: OK. `TestInterfaceEnabled` absent.
- Archive hashes were refreshed without modifying earlier captures.

The mode mappings and limitations documented in [experiment 6](phone-port1.md) apply here.
