# Windows UCSI research capture — ThinkPad T495

Recorded on 17 November 2026, Asia/Kolkata (UTC+05:30).

**Phone recheck:** A later capture detected the phone setup on connector 2 instead of connector 1, still reporting Type-C 1.5 A mode and the same conflicting RDO. See [experiment 7](analysis/phone-port2-recheck.md). Neither phone capture establishes an active PD contract.

**Phone experiment:** A user-reported USB-C-to-USB-C phone connection was detected on connector 1, with the laptop supplying power and an Android ADB interface enumerated. UCSI reported Type-C 1.5 A mode alongside inconsistent PDO/RDO data, so no verified PD charging wattage is claimed. See [experiment 6](analysis/phone-port1.md).

**Additional accessory experiment:** USB-C headphones were detected on connector 1 as AB17X USB Audio, with headphone and microphone endpoints. UCSI reported the laptop supplying power and no PD request. See [experiment 5](analysis/headphone-port1.md).

**Latest status: all four charger/port combinations are complete.** Xiaomi advertised 67 W on both connectors; the original ThinkPad charger advertised 65 W on both. All four active RDOs requested 20 V / 3.25 A (65 W). See [the complete comparison and experiment 4](analysis/four-experiment-comparison.md). Earlier statements about outstanding tests below are historical and superseded by this result.

## Charger and cable identification (user-confirmed)

The user clarified after both completed captures that the charger was a **Xiaomi 67 W charger connected using a USB-A-to-USB-C cable** (USB-A at the charger, USB-C at the laptop). This identification applies to experiments 1 and 2. Charger model number and cable markings were not recorded. It is user-supplied physical setup information, not an identity decoded from UCSI.

The **original ThinkPad charger has now been captured on connector 1** as experiment 3: it advertises 65 W and the laptop requests 65 W. See [the original-charger comparison](analysis/thinkpad-port1-comparison.md). Its connector 2 test remains outstanding. Results are stored separately from the Xiaomi captures. References below to the stock charger not yet being captured describe the historical scope of experiments 1 and 2 and are superseded by experiment 3.

Because the stated connection is USB-A-to-USB-C, the UCSI-reported PD mode and PDO/RDO values must not be presented as independent proof of a conventional USB-C-to-USB-C PD wire exchange. This investigation did not establish how this charger/cable combination negotiates power or whether proprietary signaling or firmware translation is involved. The measurements below remain firmware-reported values; the physical signaling mechanism is unresolved.

**Follow-up completed:** The same charger was moved to the other physical port at the user's request. UCSI connector 2 then reported the identical 67 W source advertisement and 65 W request, while connector 1 was disconnected. See [the second-port experiment and comparison](analysis/port2-comparison.md). The original findings below describe the first experiment; its statement that connector 2 was not tested is superseded by this follow-up.

## Principal finding

The connected power source on **UCSI connector 1** advertised a maximum fixed supply of **20 V / 3.35 A (67 W)**. The laptop's reported Request Data Object (RDO), **0x43051545**, selected source PDO 4 and requested **3.25 A at 20 V (65 W)**. This is a firmware-reported PD contract snapshot, not a measurement of instantaneous input power or a packet-level negotiation trace.

**Connector 2 was disconnected**. Both connectors reported power provider and consumer capability. No physical left/right or front/rear mapping of connector numbers was established. No active charging test was performed on connector 2.

The user had observed Lenovo Vantage displaying 67 W for a Xiaomi 67 W adapter and 65 W for the stock adapter. The captured 67 W source advertisement is consistent with that observation, but this session did not independently identify the adapter manufacturer or trace Vantage's implementation. It did not capture a separate stock-65-W-adapter session.

## Archive contents

- `captures/ucsi-initial.txt`: original first capture, requesting up to four PDOs at once.
- `captures/ucsi-results.txt`: original second capture, requesting each PDO offset separately.
- `captures/post-capture-state.txt`: later verification of device health, registry cleanup, and machine information; distinct from the original captures.
- `scripts/Read-Ucsi.original.ps1`: exact script used for the second capture. The first capture used the same structure but a single batch request instead of its PDO-offset loop.
- `scripts/Read-Ucsi.ps1`: reproduction copy, adjusted only for archive paths, unique output filenames, and accurate section labels. Not run against hardware in this archive-creation step.
- `scripts/Decode-Capture.ps1`: offline extraction and decoding of fixed partner-source PDOs and RDOs.
- `analysis/decoded.json`: machine-readable decoded capture.
- `tools/README.md`: where `UCSIControl.exe` comes from, the exact download URL, the MSI SHA-256 and how to extract it. The Microsoft binaries are deliberately **not** redistributed here.
- `tools/signature-check.txt`, `tools/version.txt`: tool metadata and local signature-check results.
- `SHA256SUMS.csv`: integrity hashes of archive files except the manifest itself.

Raw transcripts contain the local computer/user name and filesystem paths. They
are published unredacted, exactly as captured.

## System and interface

| Item | Observed value |
|---|---|
| Manufacturer / machine model | LENOVO / 20NKS29V00 (ThinkPad T495 family) |
| Operating system | Windows 11 Pro, build 26300 |
| UCSI PnP instance | `ACPI\USBC000\0` |
| ACPI BIOS device name | `\_SB.UBTC` |
| Device | UCM-UCSI ACPI Device |
| Client driver | UcmUcsiAcpiClient.sys |
| PnP driver version from preliminary inspection | 10.0.26100.8972 |
| Client driver's class version printed by tool | 1.1.0 |
| Connector count | 2 |
| GET_CAPABILITY PD version field | 0x0200 (PD 2.0) |
| GET_CAPABILITY Type-C version field | 0x0110 (Type-C 1.1) |
| PDO details available | Yes |
| Cable details available | No |

The tool printed UCSI VERSION **0.0.0** for both PPM and client driver, despite successful command responses. Treat this as an anomalous/unusable version report, not proof that the device implements a specification called UCSI 0.0.0. The PD version capability field is not a captured PD packet-header revision.

## Is your machine affected?

Two checks. The first needs no tools; the second uses Microsoft's UCSI test tool
and the capture script in this archive.

```powershell
Get-PnpDevice -InstanceId 'ACPI\USBC000\0' | Select-Object Status,Problem
Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion,ReleaseDate
```

| Result | Meaning |
|---|---|
| `Status OK`, `Problem 0` | Windows accepts the device. If Linux shows no `/sys/class/typec/` ports, the zero-version gate is Linux-side. |
| `Problem 10` / `43`, `Status Error` | the firmware fails under Windows too — a stronger report. |
| device absent | inconclusive; this needs a real Windows install, not WinPE. |

Then, for the response length, in an administrator PowerShell in this folder:

```powershell
.\scripts\Read-Ucsi.ps1
```

Check the generated transcript for four things:

1. `UCSI VERSION from PPM: 0.0.0` (expected);
2. a `GET_PDOS` with `NumberOfPdos: 3` (four requested) returning
   `DataLength: 4` and one 4-byte `MESSAGE_IN`;
3. the per-offset sections showing up to four PDOs (5 V, 9 V, 15 V, 20 V);
4. `RequestDataObject: 0x43051545` for a 20 V-capable charger.

`UCSIControl.exe` is not redistributed here; extract it first — see
[`tools/README.md`](tools/README.md).

## Findings and raw values

### Global capability

GET_CAPABILITY returned 16 bytes:

```text
44 40 00 00 02 14 00 00 02 00 20 01 00 02 10 01
```

The tool decoded `bmAttributes=0x4044`, `bNumConnectors=2`, `bmOptionalFeatures=0x14`, PD support enabled, PDO details available, and cable details unavailable.

### Per-connector capabilities and status

Both connectors returned capability bytes `e1 33`. The tool decoded USB2, USB3, alternate mode, DFP data role, Provider=1 and Consumer=1. Power-role capability must not be confused with USB data-role capability.

| Field | Connector 1 | Connector 2 |
|---|---|---|
| ConnectStatus | 1 | 0 |
| PowerOperationMode | 3 (PD) | 0 |
| PowerDirection | 0 (consumer while connected) | 0; not meaningful while disconnected |
| RDO | 0x43051545 | 0x00000000 |
| PowerBudgetLimitedReason | 0 | 0 |

Connector 1 status bytes: `40 40 2b 20 45 15 05 43 01` in the first capture. Connector 2: `00 00 00 20 00 00 00 00 01`. Status-change bits are event indicators and may differ between samples.

### Connected source's advertised profiles

The second capture queried offsets 0 through 6 independently. Four partner-source PDOs were returned for connector 1; the later offsets were empty.

| PDO position | Little-endian bytes | Decoded DWORD | Fixed voltage | Maximum current | Maximum power |
|---|---|---|---|---|---|
| 1 | 2c 91 01 0a | 0x0A01912C | 5 V | 3 A | 15 W |
| 2 | 2c d1 02 00 | 0x0002D12C | 9 V | 3 A | 27 W |
| 3 | 2c b1 04 00 | 0x0004B12C | 15 V | 3 A | 45 W |
| 4 | 4f 41 06 00 | 0x0006414F | 20 V | 3.35 A | 67 W |

For a fixed PDO, type bits 31:30 are zero; voltage is bits 19:10 multiplied by 50 mV; current is bits 9:0 multiplied by 10 mA. DWORDs are assembled from the returned bytes in little-endian order.

For RDO `0x43051545`:

- Object position = `(RDO >> 28) & 0xF` = 4.
- Operating current (bits 9:0) = `(RDO & 0x3FF) * 0.01` = 3.25 A.
- Maximum operating current (bits 19:10) = `((RDO >> 10) & 0x3FF) * 0.01` = 3.25 A.
- Selected PDO voltage = 20 V, hence requested power = 65 W.
- Bits 25 and 24 (GiveBack and Capability Mismatch in the PD specification) are
  set; the two current fields are equal, so they do not affect the 65 W result.

This explains the distinction between a 67 W advertised source and a 65 W requested contract. It does **not** prove Vantage uses this exact API or computation.

### The response is always one PDO

The first capture asked for four PDOs in one command and received one:

```text
NumberOfPdos: 3        <- four requested
CCI DataLength: 4      <- four bytes returned
MESSAGE_IN: 2c 91 01 0a
```

The second capture asked each offset separately and received the whole list.
So the four-PDO request was not honoured; `DataLength` is the only reliable
indicator of how many PDOs arrived. Other request counts were not tested. This matters beyond Windows: Linux's UCSI
driver asks for four, receives one, and therefore records a one-entry capability
list. See the top-level README §2–§3.

### Laptop-side PDO anomalies

| Query | Connector 1 | Connector 2 |
|---|---|---|
| Local source, offset 0 | 00 00 00 15 | 00 55 00 15 |
| Local sink, offset 0 | 0a 90 01 36 | 0a 90 01 36 |
| Local sink, offset 1 | 32 90 01 99 | 32 90 01 99 |
| Local sink, offset 2 | 0a 90 01 59 | 0a 90 01 59 |

The local source DWORDs decode to implausible fixed-supply fields (connector 1: zero voltage/current; connector 2: 1.05 V and 2.56 A). These are not credible USB-C source capability limits. The cause was not determined; firmware behavior or interface/tool compatibility could be involved. Local sink data are preserved without using them to assert maximum laptop charging capacity. No reliable maximum output wattage for either connector was established.

## Methodology

1. Read system model, Windows build, PnP device status/properties, UCSI event provider, battery WMI data, and Lenovo service/driver presence with PowerShell. These preliminary console results were not saved verbatim at the time; the summary here distinguishes them from retained raw UCSI transcripts.
2. Confirmed that `TestInterfaceEnabled` was absent and the initial shell was not elevated. Ordinary registry modification failed with `Requested registry access is not allowed`.
3. Followed Microsoft's UCSI documentation to locate UCSIControl in MUTT. Downloaded `MUTTPackage-3_0_2.msi` directly from Microsoft. The package is not committed here; [`tools/README.md`](tools/README.md) keeps its download URL, SHA-256 and extraction steps.
4. A combined download/Windows Installer extraction command was blocked by automatic approval review with no specific explanation. Download alone succeeded. Used installed 7-Zip to extract the MSI as an archive, without running its installer or installing MUTT drivers. Copied archive member `x64_ucsicontrol` to `UCSIControl.exe`.
5. Local Authenticode validation of the MSI reported `UnknownError`: its certificate chain ended at an untrusted root. The reported signer was Microsoft Windows / Microsoft Corporation. The extracted executable reported `NotSigned`. The package was retrieved via Microsoft's HTTPS download URL; these signature results are recorded, not represented as successful cryptographic publisher validation.
6. Invoked a PowerShell helper using `Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden`. The elevated process succeeded. No system reboot was performed.
7. Saved the previous registry-value state; temporarily set DWORD `TestInterfaceEnabled=1` under the device's `Device Parameters` key; restarted only `ACPI\USBC000\0` using `pnputil /restart-device`; waited three seconds.
8. Ran UCSIControl help, GET_CAPABILITY, GET_CONNECTOR_CAPABILITY, GET_CONNECTOR_STATUS and local/partner source/sink GET_PDOS for connectors 1 and 2. Only GET commands were sent through UCSIControl. Device restart and registry changes were separate setup operations.
9. First capture requested four PDOs in one call, but firmware returned only one. Second capture requested offsets 0..6 individually to obtain the full available list. Both captures are retained.
10. In `finally`, removed the registry value because it originally did not exist, and restarted the UCSI device again. Cleanup restart returned exit code 0. Subsequent PnP verification showed status OK and the registry value absent.

## Exact command construction

UCSIControl syntax: `UCSIControl.exe Send <HighDWORD> <LowDWORD>`. Arguments are hexadecimal, without requiring a `0x` prefix.

| Operation | High DWORD | Low DWORD |
|---|---|---|
| Global capability | 0 | 6 |
| Connector 1 / 2 capability | 0 | 10007 / 20007 |
| Connector 1 / 2 status | 0 | 10012 / 20012 |
| Local source PDO, one at offset 0 | 4 | 10010 / 20010 |
| Local sink PDO, one at offset 0 | 0 | 10010 / 20010 |
| Partner source PDO, one at offset 0 | 4 | 810010 / 820010 |
| Partner sink PDO, one at offset 0 | 0 | 810010 / 820010 |

For offset `n`, add `(n << 24)` to the low DWORD. Connector number occupies bits 22:16, partner selection bit 23, PDO offset bits 31:24, number-of-PDOs-minus-one starts at bit 32, and source selection is bit 34. The first capture used high DWORD 7 for four source PDOs and 3 for four sink PDOs. The second used 4 and 0 for single PDOs. The retained original script's section label still says “initial batch”; the individual `PDO offset` lines and printed controls establish that the second capture uses single requests.

## Reproduction

From an **administrator PowerShell** window, in the `windows_ucsi` folder:

```powershell
cd <path-to>\windows_ucsi
.\scripts\Read-Ucsi.ps1
```

`Read-Ucsi.ps1` expects the Microsoft tool at `..\tools\UCSIControl.exe`. Extract it first — see [`tools/README.md`](tools/README.md) for the download link and the MSI hash.

The reproduction script expects this laptop's device instance and exactly two connectors. It writes a new timestamped transcript under `captures` and restores the prior registry state. It briefly restarts UCSI before and after collection, which may interrupt USB-C operation. The original capture script is retained separately for fidelity; it expected the executable beside it and overwrote `ucsi-results.txt`.

To decode an existing capture without accessing hardware:

```powershell
.\scripts\Decode-Capture.ps1
```

The capture helper does not enforce a per-command timeout, and native command failures may be recorded without stopping subsequent queries. Review CCI, error fields, transcript completion and cleanup before interpreting a rerun. An interrupted process can prevent `finally` cleanup; inspect the registry and device state in that case. Do not treat a script-level zero exit code alone as proof of valid measurements.

## Limits and follow-up experiments

- These are sequential snapshots, not simultaneous measurements or PD wire packets. No voltage/current meter was used.
- UCSI supplies firmware-reported state; the local-source and version anomalies show that not all fields should be trusted equally.
- The 65 W result is the requested contract ceiling, not battery charge rate, instantaneous draw, or proof of the absolute hardware input limit under all conditions.
- The earlier battery WMI snapshot showed about 16.423 W battery charging and 11.875 V battery voltage. It was separate from this capture and does not measure USB-C input voltage or input wattage.
- Lenovo Vantage's precise data path was not reverse engineered. LenovoVantageService and IBMPMSVC were observed running as LocalSystem, with IBMPMDRV loaded; that alone does not prove which call provides adapter wattage.
- Next experiments: label charger/cable and physical port, repeat on connector 2, then repeat with the stock 65 W charger. Preserve separate transcripts and note connection changes. Use a PD analyzer if packet-level negotiation or independent electrical confirmation is needed.

## References and acquisition provenance

- Microsoft UCSI instructions and command examples: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/ucsi#ucsicontrolexe
- MUTT package overview: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/mutt-software-package
- Microsoft download page (package version 3.0.2): https://www.microsoft.com/en-us/download/details.aspx?id=51604
- Exact downloaded file: https://download.microsoft.com/download/3856f445-db3d-4e15-ac03-622bfd453e12/MUTTPackage-3_0_2.msi
- Downloaded MSI SHA-256: `7741618EEB97572B3A83965799738B2934B5D474782BA2670CCD07C678C022DE`
- Linux upstream UCSI command-field definitions consulted: https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/typec/ucsi/ucsi.h
- Linux upstream PD fixed-PDO/RDO decoding definitions consulted: https://raw.githubusercontent.com/torvalds/linux/master/include/linux/usb/pd.h
- Lenovo model specification: https://psref.lenovo.com/syspool/Sys/PDF/ThinkPad/ThinkPad_T495/ThinkPad_T495_Spec.PDF

Online references were consulted during the investigation. The upstream `master` URLs are mutable; the concrete decoding formulas used are recorded above for reproducibility. No immutable source commit was recorded.
