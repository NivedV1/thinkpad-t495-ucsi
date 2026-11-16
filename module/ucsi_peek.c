// SPDX-License-Identifier: GPL-2.0
/*
 * ucsi_peek - inspect (and optionally patch) the UCSI ACPI register block
 *             on machines whose firmware reports VERSION 0x0000.
 *
 * Default behaviour is READ-ONLY: map the region, log a hex dump, print
 * VERSION and CCI, write nothing.
 *
 * With patch=1 it writes patch_ver (default 0x0100) into the VERSION field so
 * that ucsi_acpi's probe no longer returns -ENODEV.  The write lands in RAM:
 * it is lost on reboot (and possibly on resume, when firmware rewrites it).
 *
 * This is a diagnostic, not a fix.  The register block is also driven by the
 * embedded controller.  Read-only mode has been harmless here; the write has
 * been used for one boot at a time only.  Do not leave it in place.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/init.h>
#include <linux/types.h>
#include <linux/slab.h>

#define UCSI_VERSION	0x00
#define UCSI_CCI	0x04

#define DUMP_MAX	0x1000
#define DUMP_DEFAULT	0x30

static unsigned long addr = 0xBD6B2000UL;
module_param(addr, ulong, 0444);
MODULE_PARM_DESC(addr, "Physical address of the UCSI register block");

static unsigned int len = DUMP_DEFAULT;
module_param(len, uint, 0444);
MODULE_PARM_DESC(len, "Bytes to map and dump (0x20..0x1000)");

static bool patch;
module_param(patch, bool, 0444);
MODULE_PARM_DESC(patch, "1 = write patch_ver into the VERSION field");

static unsigned int patch_ver = 0x0100;
module_param(patch_ver, uint, 0444);
MODULE_PARM_DESC(patch_ver, "VERSION to write when patch=1 (0x0100, 0x0110, ...)");

static void *base;
static bool patched;

static void dump_bytes(const char *tag, const u8 *b, unsigned int n)
{
	unsigned int i, j;

	for (i = 0; i < n; i += 16) {
		char line[3 * 16 + 1];
		int pos = 0;

		line[0] = '\0';
		for (j = 0; j < 16 && i + j < n; j++)
			pos += scnprintf(line + pos, sizeof(line) - pos,
					 "%02x ", b[i + j]);
		pr_info("ucsi_peek: %s +%02x: %s\n", tag, i, line);
	}
}

static int __init ucsi_peek_init(void)
{
	u8 *buf;
	u16 ver;
	u32 cci;

	if (len < 0x20 || len > DUMP_MAX) {
		pr_err("ucsi_peek: bad len %#x (want 0x20..0x%x)\n",
		       len, DUMP_MAX);
		return -EINVAL;
	}
	if (addr & 0x3) {
		pr_err("ucsi_peek: address %#lx is not 4-byte aligned\n", addr);
		return -EINVAL;
	}

	base = ioremap_cache(addr, len);
	if (!base) {
		pr_err("ucsi_peek: cannot map %#lx+%#x\n", addr, len);
		return -ENOMEM;
	}

	buf = kmalloc(len, GFP_KERNEL);
	if (!buf) {
		iounmap(base);
		return -ENOMEM;
	}
	memcpy_fromio(buf, base, len);

	ver = readw(base + UCSI_VERSION);
	cci = readl(base + UCSI_CCI);

	pr_info("ucsi_peek: mapped %#lx+%#x\n", addr, len);
	pr_info("ucsi_peek: VERSION=0x%04x CCI=0x%08x\n", ver, cci);
	dump_bytes("raw", buf, len);
	kfree(buf);

	if (!patch) {
		pr_info("ucsi_peek: read-only mode, nothing written\n");
		return 0;
	}

	if (ver != 0)
		pr_warn("ucsi_peek: VERSION already 0x%04x, overwriting\n", ver);

	if (patch_ver > 0xffff) {
		pr_err("ucsi_peek: patch_ver %#x does not fit in 16 bits\n",
		       patch_ver);
		iounmap(base);
		base = NULL;
		return -EINVAL;
	}

	writew((u16)patch_ver, base + UCSI_VERSION);
	ver = readw(base + UCSI_VERSION);
	pr_info("ucsi_peek: wrote VERSION -> 0x%04x (readback)\n", ver);
	patched = true;

	if (ver != (u16)patch_ver) {
		pr_err("ucsi_peek: write did not stick, region is read-only\n");
		iounmap(base);
		base = NULL;
		return -EIO;
	}

	return 0;
}

static void __exit ucsi_peek_exit(void)
{
	if (base) {
		if (patched)
			pr_info("ucsi_peek: unloading, VERSION left at 0x%04x\n",
				readw(base + UCSI_VERSION));
		iounmap(base);
	}
}

module_init(ucsi_peek_init);
module_exit(ucsi_peek_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Inspect/patch the UCSI ACPI register block (diagnostic)");
MODULE_AUTHOR("Nived Chandran");
