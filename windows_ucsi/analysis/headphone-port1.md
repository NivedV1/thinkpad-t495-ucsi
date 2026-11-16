# Experiment 5 — USB-C headphones

Capture: 17 November 2026, 00:28:05–00:28:28, Asia/Kolkata (UTC+05:30), according to the transcript clock.

The user reported connecting headphones to a USB-C port. Ran the existing UCSI capture helper through elevated PowerShell (PID 12664), and inspected present Windows PnP audio devices and driver properties. The same temporary diagnostic-interface enablement and cleanup procedure was used. No audio playback, microphone recording, default-device change or volume change was performed.

## Windows recognition

| Item | Observed result |
|---|---|
| Audio device | AB17X USB Audio |
| USB IDs | VID_0624 / PID_3D3F, audio interface MI_00 |
| Playback endpoint | Headset Earphone (AB17X USB Audio) |
| Recording endpoint | Headset Microphone (AB17X USB Audio) |
| Device and endpoint status | OK |
| Driver provider | Microsoft |
| Driver service | usbaudio |
| Driver version | 10.0.26100.9457 |

This confirms enumeration as a digital USB audio device with playback and microphone endpoints. It does not establish audio quality, successful audible playback, microphone operation or whether these are Windows' default audio endpoints. Retail brand/model was not established from the generic device name.

## UCSI state

| Field | Connector 1 | Connector 2 |
|---|---|---|
| ConnectStatus | 1 | 0 |
| PowerDirection | 1 (laptop supplies power) | 0; inactive |
| USB partner flag | 1 | 0 |
| Alternate-mode partner flag | 0 | 0 |
| PowerOperationMode | 0 | 0 |
| RDO | 0x00000000 | 0x00000000 |
| PowerBudgetLimitedReason | 0 | 0 |

Connector 1's connection, USB partner flag and power direction are consistent with the newly attached USB audio accessory. Connector 2 was disconnected. The physical connector-to-audio-device association is inferred from this setup and the sole connected UCSI port; no USB topology mapping was independently performed.

Unlike the charger tests (PowerOperationMode=3 and a nonzero RDO), this capture reports **no negotiated PD request**. PowerOperationMode=0 is not interpreted as a precise USB current advertisement. Exact supply voltage, current allowance and actual consumption were not established. The digital USB audio enumeration provides evidence for USB audio operation rather than a passive analog-only accessory, but this was not an electrical signaling test.

## Saved evidence

- `captures/ucsi-20261117-002805-210.txt`: full raw UCSI transcript.
- `captures/headphone-device-state.txt`: Windows audio enumeration, driver properties and post-capture cleanup state.
- `analysis/decoded-headphone-port1.json`: offline decoding. The decoder focuses on partner-source PDOs and RDOs; consult the raw capture for power direction and audio-related context.
- Transcript ended with cleanup restart exit code 0. Subsequent UCSI PnP status was OK and `TestInterfaceEnabled` was absent.

The archive's SHA-256 manifest covers all new evidence. Earlier charger data were preserved. Previously documented firmware/tool anomalies still apply; no inference about maximum headphone power is drawn from local PDO data.
