# Experiment 2 — same charger, other USB-C port

Capture: 17 November 2026, 00:19:17–00:19:54, Asia/Kolkata (UTC+05:30), according to the Windows transcript clock.

**Setup clarification supplied afterward by the user:** Both experiments used a **Xiaomi 67 W charger with a USB-A-to-USB-C cable**, USB-A at the charger and USB-C at the laptop. This is user-confirmed setup metadata, not a charger/cable identity retrieved from UCSI. The original ThinkPad charger is the next planned experiment and is not represented in either existing capture. The physical signaling mechanism of this A-to-C setup was not established; UCSI's reported PD state alone does not verify a conventional C-to-C PD exchange.

## Procedure

The user reported moving the same charger to the other physical USB-C port. Ran the archived `scripts/Read-Ucsi.ps1` through an elevated PowerShell process (PID 20128). The script temporarily enabled the UCSI diagnostic interface, restarted the UCSI device, queried both connectors and PDO offsets 0..6, restored the original registry state, and restarted the device again. No charger model or cable identity was independently read. The physical port's chassis position was not recorded.

The capture verifies the move: connector 1 is now disconnected and connector 2 is connected. This was a separate experiment; no first-experiment captures were overwritten.

## Results

| Measurement | Experiment 1 | Experiment 2 |
|---|---|---|
| Active UCSI connector | 1 | 2 |
| Inactive connector | 2 | 1 |
| Source PDO 1 | 5 V / 3 A / 15 W | Identical |
| Source PDO 2 | 9 V / 3 A / 27 W | Identical |
| Source PDO 3 | 15 V / 3 A / 45 W | Identical |
| Source PDO 4 | 20 V / 3.35 A / 67 W | Identical |
| Active RDO | 0x43051545 | 0x43051545 |
| Selected source PDO | 4 | 4 |
| Requested operating current | 3.25 A | 3.25 A |
| Requested maximum operating current | 3.25 A | 3.25 A |
| Requested power at selected voltage | 20 V × 3.25 A = 65 W | Identical |

**Both USB-C connectors have now demonstrated a firmware-reported 65 W PD request with the user-reported same charger.** The source advertises 67 W on either connection. This is not an instantaneous power measurement or proof of each port's absolute maximum supported input power. No packet-level PD exchange was recorded.

## Evidence and verification

- Raw capture: `captures/ucsi-20261117-001917-772.txt`.
- Raw capture SHA-256: `BEE88EA3E2A66077CDD0A1F94DD01328E28D1BE90232B56F55D4783A077AFBC4`.
- Offline decoding: `analysis/decoded-port2-20261117-001917.json`.
- Decoder: `scripts/Decode-Capture.ps1`, run with the new capture and a separate output filename.
- Transcript contains `Cleanup restart exit code: 0` and its completion marker.
- Post-capture inspection: UCSI device status OK; `TestInterfaceEnabled` absent. Saved separately as `captures/post-port2-state.txt`.
- Four partner-source PDOs returned for connector 2; connector 1 has no partner-source PDOs in this capture.

The firmware/tool limitations described in the main report still apply, including the reported UCSI version 0.0.0 and unreliable local-source PDO values. The first report's statement that connector 2 had no active test is superseded by this experiment. Testing the stock 65 W charger remains outstanding.
