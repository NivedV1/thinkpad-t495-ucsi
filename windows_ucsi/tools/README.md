# UCSIControl provenance

`UCSIControl.exe` is Microsoft's UCSI test tool, shipped inside the MUTT
(Microsoft USB Test Tool) package. **It is not redistributed in this
repository.** The captures in `../captures/` were made with it; this page
records exactly which package it came from so the captures can be reproduced.

## Where to get it

| Item | Location |
|---|---|
| UCSIControl usage and examples | https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/ucsi#ucsicontrolexe |
| MUTT package overview | https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/mutt-software-package |
| Download page (package 3.0.2) | https://www.microsoft.com/en-us/download/details.aspx?id=51604 |
| Exact file used for these captures | https://download.microsoft.com/download/3856f445-db3d-4e15-ac03-622bfd453e12/MUTTPackage-3_0_2.msi |

SHA-256 of the downloaded MSI:

```text
7741618EEB97572B3A83965799738B2934B5D474782BA2670CCD07C678C022DE
```

## Extract it without installing anything

The installer was never run and no MUTT driver was installed. The MSI was opened
as an archive with 7-Zip and the single member `x64_ucsicontrol` was copied out:

```text
7z x MUTTPackage-3_0_2.msi x64_ucsicontrol
copy x64_ucsicontrol UCSIControl.exe
```

An administrative extraction (`msiexec /a MUTTPackage-3_0_2.msi`) produces the
same file without installing the package either.

Put the result at `tools/UCSIControl.exe`. `scripts/Read-Ucsi.ps1` resolves the
tool relative to its own directory as `..\tools\UCSIControl.exe`.

## Signature status observed here

Recorded in [`signature-check.txt`](signature-check.txt):

- **MSI**: Authenticode `UnknownError` — "a certificate chain processed, but
  terminated in a root certificate which is not trusted by the trust provider".
  Reported signer `CN=Microsoft Windows, O=Microsoft Corporation`.
- **Extracted `UCSIControl.exe`**: `NotSigned`.

The file came from Microsoft's own HTTPS download URL and the MSI hash above is
the one that was downloaded. That is provenance, not cryptographic publisher
validation, and it is recorded here rather than presented as one.

## Tool metadata

Recorded in [`version.txt`](version.txt):

```text
FileVersion      10.0.26572.1000
ProductVersion   10.0.26572.1000
CompanyName      Microsoft Corporation
OriginalFilename UcsiControl.exe
```

## Interface used

`UCSIControl.exe Send <HighDWORD> <LowDWORD>` issues one UCSI command through
the UCM-UCSI ACPI client and prints the command, the returned CCI and the
MESSAGE_IN bytes. Only `GET_*` commands were sent in these captures.

The tool prints the CCI **`DataLength`**, which is the field that makes this
firmware's truncated PDO response visible:

```text
NumberOfPdos: 3        <- four PDOs requested
DataLength: 4          <- four bytes returned, i.e. one PDO
```

Without that length field the extra bytes in the response buffer look like
data. They are leftovers from the previous command.

## Enabling the command channel

The tool needs the device's diagnostic interface, which is off by default:

```text
HKLM\SYSTEM\CurrentControlSet\Enum\ACPI\USBC000\0\Device Parameters
    TestInterfaceEnabled   DWORD = 1
```

then restart the device:

```text
pnputil /restart-device ACPI\USBC000\0
```

`scripts/Read-Ucsi.ps1` sets the value, restarts the device, captures, deletes
the value again (it did not exist before) and restarts once more. An interrupted
run can leave the value behind — check it before trusting a later capture, and
remove it when finished.
