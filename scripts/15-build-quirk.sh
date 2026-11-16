#!/bin/bash
# 15-build-quirk.sh - build ucsi_acpi with the DMI quirk and load it.
#
# Unlike 20-enable-ucsi.sh this does NOT write to the UCSI register block. It
# replaces the driver instead, so the firmware is only read.
#
# The patch substitutes UCSI 1.1 when VERSION reads 0x0000, gated on this
# machine's DMI (LENOVO / ThinkPad T495). That is the change proposed upstream
# for the zero-version defect; see patches/.
#
# Undo: sudo rmmod ucsi_acpi && sudo modprobe ucsi_acpi
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
WORK=${WORK:-/tmp/t495-quirk}
KREL=$(uname -r)
KVER=${KREL%%-*}
KBUILD=/lib/modules/$KREL/build
PATCH=$(ls "$HERE"/patches/0001-*.patch 2>/dev/null | head -1)

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }
[ -d "$KBUILD" ] || { echo "no $KBUILD - install kernel-devel for $KREL"; exit 1; }
[ -n "$PATCH" ] || { echo "patch not found under $HERE/patches"; exit 1; }

echo "== kernel $KREL (base $KVER) =="
echo "== work dir $WORK =="
mkdir -p "$WORK"
cd "$WORK"

if [ ! -s ucsi_acpi.c ] || [ ! -s ucsi.h ]; then
	echo "== fetching ucsi_acpi.c and ucsi.h for v$KVER =="
	BASE="https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/drivers/usb/typec/ucsi"
	curl -fsSL -o ucsi_acpi.c "$BASE/ucsi_acpi.c?h=v$KVER"
	curl -fsSL -o ucsi.h      "$BASE/ucsi.h?h=v$KVER"
fi

if grep -q ucsi_t495_ops ucsi_acpi.c; then
	echo "== patch already applied =="
else
	echo "== applying $(basename "$PATCH") =="
	# labels are a/drivers/usb/typec/ucsi/<file>, stripped to <file>
	patch -p5 --no-backup-if-mismatch < "$PATCH"
fi

printf 'obj-m := ucsi_acpi.o\n' > Makefile

echo "== building =="
make -s -C "$KBUILD" M="$WORK" modules

echo "== swapping the module =="
rmmod ucsi_acpi 2>/dev/null || true
insmod "$WORK/ucsi_acpi.ko"

sleep 4

echo
echo "== dmesg =="
dmesg | grep -iE 'ucsi|typec' | tail -8 | sed 's/^/   /'

echo
echo "== typec =="
ls -1 /sys/class/typec 2>/dev/null | sed 's/^/   /'
[ -d /sys/class/typec/port0 ] || {
	echo "no ports appeared - the quirk did not match or the EC refused"
	exit 1
}

echo
echo "== partner source capabilities (what sysfs exposes) =="
CAPS=/sys/class/typec/port0-partner/usb_power_delivery/source-capabilities
for _ in $(seq 12); do
	[ -n "$(ls -A "$CAPS" 2>/dev/null)" ] && break
	sleep 1
done
if [ -d "$CAPS" ]; then
	for d in "$CAPS"/*/; do
		[ -d "$d" ] || continue
		case "$(basename "$d")" in power) continue ;; esac
		printf '   %s  %s  %s\n' "$(basename "$d")" \
			"$(cat "$d/voltage" 2>/dev/null)" "$(cat "$d/maximum_current" 2>/dev/null)"
	done
	[ -n "$(ls -A "$CAPS")" ] || echo "   (nothing yet - the PD object lags attach)"
else
	echo "   (no partner PD object)"
fi
printf '   power_operation_mode: %s\n' \
	"$(cat /sys/class/typec/port0/power_operation_mode 2>/dev/null)"

cat <<'EOF'

Next: sudo ./scripts/25-walk-pdos.sh    # every PDO, offset by offset
Restore stock: sudo rmmod ucsi_acpi && sudo modprobe ucsi_acpi
EOF
