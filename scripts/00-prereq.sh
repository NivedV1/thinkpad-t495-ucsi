#!/bin/bash
# 00-prereq.sh - report whether this machine is in scope, and what is missing.
# Read-only. Run as your normal user; sudo is used only for reads that need it.
set -u

say() { printf '%s\n' "$*"; }
hdr() { printf '\n=== %s ===\n' "$*"; }

hdr "machine"
for f in sys_vendor product_name product_version bios_version bios_date board_name; do
	v=$(cat "/sys/class/dmi/id/$f" 2>/dev/null)
	[ -n "$v" ] && printf '%-18s %s\n' "$f" "$v"
done
printf '%-18s %s\n' kernel "$(uname -r)"

hdr "UCSI ACPI device"
found=0
for d in /sys/bus/acpi/devices/USBC000:*; do
	[ -d "$d" ] || continue
	found=1
	say "  $d"
	printf '    modalias  %s\n' "$(cat "$d/modalias" 2>/dev/null)"
	printf '    status    %s\n' "$(cat "$d/status" 2>/dev/null)"
	printf '    driver    %s\n' "$(readlink -f "$d/driver" 2>/dev/null | sed 's#.*/##')"
	[ -d "$d/firmware_node" ] && printf '    fwnode    %s\n' "$(readlink -f "$d/firmware_node" | sed 's#.*/##')"
done
[ "$found" = 1 ] || say "  none - firmware does not expose USBC000 at all"

hdr "typec class"
if [ -d /sys/class/typec ]; then
	n=$(ls -1 /sys/class/typec 2>/dev/null | wc -l)
	say "  entries: $n"
	ls -1 /sys/class/typec 2>/dev/null | sed 's/^/    /'
	[ "$n" = 0 ] && say "  empty: ucsi_acpi refused to bind (expected if VERSION is 0)"
else
	say "  /sys/class/typec missing (typec module not loaded?)"
fi

hdr "probe result in dmesg"
if dmesg 2>/dev/null | grep -q .; then
	dmesg | grep -iE 'ucsi|typec' | tail -20 | sed 's/^/  /'
else
	sudo -n dmesg 2>/dev/null | grep -iE 'ucsi|typec' | tail -20 | sed 's/^/  /' \
		|| say "  cannot read dmesg (try: sudo dmesg | grep -i ucsi)"
fi

hdr "kernel config"
for opt in CONFIG_UCSI_ACPI CONFIG_TYPEC CONFIG_TYPEC_UCSI; do
	v=$(grep -E "^$opt=" "/boot/config-$(uname -r)" 2>/dev/null | cut -d= -f2)
	printf '  %-22s %s\n' "$opt" "${v:-not found}"
done

hdr "write access needed for the diagnostic"
for p in /sys/bus/platform/drivers/ucsi_acpi/bind /dev/mem; do
	if [ -e "$p" ]; then
		if [ -w "$p" ]; then say "  $p writable"; else say "  $p needs root"; fi
	fi
done
if [ -e /dev/mem ]; then
	if sudo -n dd if=/dev/mem bs=4096 skip=$((0xBD6B2000 / 4096)) count=1 2>&1 \
		| grep -q '1+0 records in'; then
		say "  /dev/mem can read the UCSI range (module not needed)"
	else
		say "  /dev/mem refuses the UCSI range (CONFIG_STRICT_DEVMEM) - module needed"
	fi
fi

hdr "lockdown"
printf '  %s\n' "$(cat /sys/kernel/security/lockdown 2>/dev/null || echo 'not exposed')"

hdr "build tools for the module"
for t in make gcc; do
	printf '  %-10s %s\n' "$t" "$(command -v "$t" || echo 'MISSING')"
done
[ -d "/lib/modules/$(uname -r)/build" ] \
	&& say "  kernel headers present" \
	|| say "  kernel headers MISSING (/lib/modules/$(uname -r)/build)"

say ""
say "Next: sudo ./scripts/10-dump-ucsi.sh"
