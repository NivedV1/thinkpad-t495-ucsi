# Experiment 3 — original ThinkPad charger, first port

Capture: 17 November 2026, 00:22:26–00:22:57, Asia/Kolkata (UTC+05:30), according to the Windows transcript clock.

## Setup and method

After identifying the previous charger as a Xiaomi 67 W USB-A-to-USB-C setup and stating that the original ThinkPad charger was next, the user reported connecting to the first port. This experiment is therefore labeled **original ThinkPad charger**, based on conversation context. Charger model, serial number and cable construction were not independently inspected. The prior Xiaomi A-to-C cable description is not applied to this charger.

Ran the archived `scripts/Read-Ucsi.ps1` through elevated PowerShell (PID 3948), querying both connectors and each local/partner PDO offset 0..6. The same temporary registry enablement, device restart and restoration procedure was used as in the previous experiments. UCSI verified connector 1 connected and connector 2 disconnected. No earlier capture was overwritten.

## Measured source capabilities

| PDO | Raw little-endian bytes | DWORD | Voltage | Maximum current | Power |
|---|---|---|---|---|---|
| 1 | 2c 91 11 0a | 0x0A11912C | 5 V | 3 A | 15 W |
| 2 | 2c d1 12 00 | 0x0012D12C | 9 V | 3 A | 27 W |
| 3 | 2c b1 14 00 | 0x0014B12C | 15 V | 3 A | 45 W |
| 4 | 45 41 16 00 | 0x00164145 | 20 V | 3.25 A | 65 W |

Connector 1 reported **RDO 0x43051545**, selecting PDO 4 with operating and maximum operating current both **3.25 A**. Requested power is therefore **20 V × 3.25 A = 65 W**. Connector 2 returned ConnectStatus=0 and RDO=0.

## Cross-experiment comparison

| Experiment | User-identified charger/setup | Active connector | Highest advertised fixed profile | Requested profile |
|---|---|---|---|---|
| 1 | Xiaomi 67 W, USB-A-to-USB-C | 1 | 20 V / 3.35 A = 67 W | 20 V / 3.25 A = 65 W |
| 2 | Same Xiaomi setup | 2 | 20 V / 3.35 A = 67 W | 20 V / 3.25 A = 65 W |
| 3 | Original ThinkPad charger | 1 | 20 V / 3.25 A = 65 W | 20 V / 3.25 A = 65 W |

All three active RDOs are identical. The source PDOs distinguish the original charger's 65 W capability from the Xiaomi's 67 W capability. This is consistent with the user's earlier Vantage observations, but does not establish Vantage's exact API or implementation. The raw source PDOs also differ in fields beyond voltage/current; this report does not decode those additional fields.

The local-source anomalies were unchanged: connector 1 returned `00 00 00 15` and connector 2 `00 55 00 15`. Both local sink lists remained `0a 90 01 36`, `32 90 01 99`, `0a 90 01 59`. Changing the charger did not resolve those anomalies, and they are still not used to infer laptop maximum output power.

## Saved evidence and cleanup

- Raw capture: `captures/ucsi-20261117-002226-762.txt`.
- SHA-256: `4478EF9FDDB7152D26D246A656738CA9452EF1C034EA5DF69364EFA1E59A054D`.
- Offline decoding: `analysis/decoded-thinkpad-port1.json`.
- Post-capture verification: `captures/post-thinkpad-port1-state.txt`.
- Transcript completed; cleanup restart exit code 0.
- Subsequent PnP status: OK. `TestInterfaceEnabled` absent.

These are sequential firmware snapshots, not packet captures or instantaneous electrical measurements. The original ThinkPad charger has not yet been tested on connector 2. Hardware identity is user-supplied and physical front/rear mapping remains unspecified.
