#!/bin/bash
# 20-enable-ucsi.sh - patch VERSION in RAM so ucsi_acpi binds, then rebind it.
#
# WRITES TO FIRMWARE-OWNED MEMORY. Read docs/safety.md first.
# The change disappears on reboot. Undo now with: sudo ./scripts/90-undo.sh
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
DEV=${UCSI_DEVICE:-USBC000:00}
VER=${UCSI_PATCH_VER:-0x0100}
BIND=/sys/bus/platform/drivers/ucsi_acpi

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }
[ "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" = "--yes" ] || {
	echo "This writes ${VER} into the UCSI VERSION register (RAM only)."
	echo "Continue? [y/N]"
	read -r a
	case "$a" in y|Y|yes|YES) ;; *) echo "aborted"; exit 1 ;; esac
}

echo "== building module =="
make -s -C "$HERE/module"

echo
echo "== clearing any previous patch =="
if lsmod | grep -q '^ucsi_peek'; then
	rmmod ucsi_peek
fi

echo
echo "== unbinding ucsi_acpi (if bound) =="
if [ -e "$BIND/$DEV" ] || [ -d "/sys/bus/platform/devices/$DEV/driver" ]; then
	echo "$DEV" > "$BIND/unbind" 2>/dev/null || true
	sleep 1
fi
echo "   typec entries now: $(ls /sys/class/typec 2>/dev/null | wc -l)"

echo
echo "== writing VERSION = $VER (RAM) =="
insmod "$HERE/module/ucsi_peek.ko" patch=1 patch_ver="$VER"
dmesg | grep ucsi_peek | tail -6

echo
echo "== binding ucsi_acpi =="
echo "$DEV" > "$BIND/bind"
sleep 2

echo
echo "== dmesg =="
dmesg | grep -iE 'ucsi_acpi|typec port' | tail -10

echo
echo "== typec entries =="
ls -1 /sys/class/typec 2>/dev/null | sed 's/^/   /'
[ -d /sys/class/typec/port0 ] || {
	echo "no ports appeared - VERSION patch did not take effect"
	exit 1
}

echo
echo "Now plug something in and run: sudo ./scripts/30-snapshot.sh /tmp/typec-$(date +%H%M)"
echo "Undo when finished:            sudo ./scripts/90-undo.sh"
