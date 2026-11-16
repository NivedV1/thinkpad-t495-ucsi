# Safety

## What the module does

`ucsi_peek` maps the physical memory region the firmware declares for UCSI
(`_SB.UBTC._CRS` → `0xBD6B2000`, length `0x1000`) and prints the first bytes.

- **Default: read-only.** `patch=0`. It reads `VERSION` (offset `0x00`) and `CCI`
  (`0x04`), dumps the region, and writes nothing.
- **Only when you pass `patch=1`** does it write 2 bytes into `VERSION`. Nothing
  else is ever written.

## What the write does and does not do

**Does**

- Change `VERSION` in DRAM-backed firmware memory for the current boot.
- Let `ucsi_acpi` bind, which registers Type-C ports with the kernel.
- Taint the kernel (out-of-tree module) and may leave `VERSION` non-zero until
  the next reboot or resume.

**Does not**

- Touch SPI flash, the BIOS image, the EC firmware, or any EFI variable. There
  is no persistent change; a reboot restores `0x0000` because the firmware
  writes that value again.
- Change USB data routing, charging, or the EC's own charging logic. Those are
  independent of UCSI and kept working throughout the original testing.
- Survive a module unload in the sense of "reverting" — unloading the module
  leaves `VERSION` as it is. `scripts/90-undo.sh` unbinds the driver and unloads
  the module; a reboot is what clears the value.

## Why it is not entirely risk-free

The region is also driven by the embedded controller. Turning `VERSION` from
invalid to valid makes the kernel start issuing UCSI commands (GET_CONNECTOR_STATUS,
GET_PDOS, GET_ALT_MODES, SET_NOTIFY_ENABLE, role-swap requests) that the firmware
was previously never asked for on this boot. On the machine used here that was
stable for hours and across many plug events, but the firmware was clearly not
validated for this path.

Stop and reboot if you see any of:

- `ucsi_acpi` errors repeating in dmesg, or a command timeout / "PPM not
  responding"
- the machine refusing to charge, or AC state flapping
- a hung USB controller, or repeated `usb 2-x: device not accepting address`
- any thermal or fan oddity that was not there before

A reboot always returns the machine to the state it boots in.

## Practical notes

- **Do not add it to `/etc/modules-load.d`.** Load it by hand for one session.
- **`/dev/mem` is not needed**; it refuses the RAM range under
  `CONFIG_STRICT_DEVMEM`, which is why a module is used at all.
- **Secure Boot:** an unsigned module will be rejected. Either disable Secure
  Boot for the test, or sign the module with your own MOK. Do not disable the
  kernel's module signature enforcement globally.
- **Lockdown:** with `lockdown=confidentiality` or `integrity`, module loading
  may be restricted; check `/sys/kernel/security/lockdown`.
- **Address:** the default `0xBD6B2000` comes from this machine's `_CRS`.
  Verify it before loading on a different model:

  ```bash
  sudo acpidump -o acpi.dat && acpixtract -a acpi.dat && iasl -d ssdt*.dat
  grep -A4 Memory32Fixed ssdt*.dsl | grep -i -B2 -A2 0x
  ```

  Then pass `addr=0x...` explicitly.

## Undo

```bash
sudo ./scripts/90-undo.sh
sudo reboot
```

Unbinding alone (`echo USBC000:00 > .../ucsi_acpi/unbind`) stops the kernel from
touching the interface; the module can stay loaded read-only.
