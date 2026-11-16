# Complete charger/port comparison and experiment 4

All four combinations were captured on 17 November 2026. Connector numbers are UCSI identifiers; chassis front/rear positions were not documented.

| Experiment | User-identified charger | Active connector | Advertised maximum fixed profile | Requested profile | RDO |
|---|---|---|---|---|---|
| 1 | Xiaomi 67 W, USB-A-to-USB-C | 1 | 20 V / 3.35 A = 67 W | 20 V / 3.25 A = 65 W | 0x43051545 |
| 2 | Same Xiaomi setup | 2 | 20 V / 3.35 A = 67 W | 20 V / 3.25 A = 65 W | 0x43051545 |
| 3 | Original ThinkPad charger | 1 | 20 V / 3.25 A = 65 W | 20 V / 3.25 A = 65 W | 0x43051545 |
| 4 | Original ThinkPad charger | 2 | 20 V / 3.25 A = 65 W | 20 V / 3.25 A = 65 W | 0x43051545 |

Each charger returned the same partner-source PDO DWORDs on both ports. Both chargers also offered 5 V / 3 A, 9 V / 3 A and 15 V / 3 A. The highest advertised fixed-profile current differs: 3.35 A for Xiaomi, 3.25 A for ThinkPad. This corroborates the differing 67 W and 65 W Vantage displays reported and shown by the user. Vantage's precise software data path remains untraced.

## Experiment 4 procedure and result

The user reported moving the original charger to the next port. Ran the archived `scripts/Read-Ucsi.ps1` using elevated PowerShell (PID 10524). The transcript clock records 00:25:26–00:26:03, Asia/Kolkata (UTC+05:30). The helper temporarily enabled the diagnostic interface, restarted UCSI, queried both connectors and individual PDO offsets, then restored the registry state and restarted UCSI again.

Connector 1 reported disconnected (RDO 0). Connector 2 reported connected with RDO **0x43051545**, selecting source PDO 4 at **20 V / 3.25 A**, or **65 W requested**. Operating and maximum operating current fields were both 3.25 A.

| Connector 2 source PDO | Raw bytes, little endian | DWORD | Fixed supply |
|---|---|---|---|
| 1 | 2c 91 11 0a | 0x0A11912C | 5 V / 3 A |
| 2 | 2c d1 12 00 | 0x0012D12C | 9 V / 3 A |
| 3 | 2c b1 14 00 | 0x0014B12C | 15 V / 3 A |
| 4 | 45 41 16 00 | 0x00164145 | 20 V / 3.25 A |

## Evidence

- Raw capture: `captures/ucsi-20261117-002526-430.txt`.
- Raw capture SHA-256: `F5C923B423792F40CD4F07CC5AD22A438AA653133FEF1675357A9DCA27384B50`.
- Offline decoding: `analysis/decoded-thinkpad-port2.json`.
- Verification: `captures/post-thinkpad-port2-state.txt`.
- Transcript completed with cleanup restart exit code 0.
- Post-capture UCSI status: OK. `TestInterfaceEnabled` absent.

Original captures were preserved. The experiment index and archive SHA-256 manifest include the new experiment.

## Interpretation limits

These are sequential firmware-reported snapshots, not measured instantaneous wattage or a PD packet trace. They demonstrate matching 65 W requests on both connectors for the tested setups, not the absolute maximum possible hardware input or output capability. Charger identities are user-supplied; exact model numbers and the original charger's cable construction were not independently inspected. The Xiaomi A-to-C physical signaling mechanism remains unresolved. The previously documented local-PDO and version-report anomalies remain limitations; no new inference about them is made here.

This report supersedes historical statements in the earlier reports that the original charger or its second-port test remained outstanding.
