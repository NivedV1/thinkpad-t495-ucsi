#!/bin/bash
# 90-undo.sh - unbind ucsi_acpi and unload the diagnostic module.
# The VERSION patch lives in RAM and is cleared for good by a reboot.
set -u

DEV=${UCSI_DEVICE:-USBC000:00}
BIND=/sys/bus/platform/drivers/ucsi_acpi

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }

if [ -d "/sys/bus/platform/devices/$DEV/driver" ]; then
	echo "$DEV" > "$BIND/unbind" 2>/dev/null && echo "unbound $DEV"
else
	echo "$DEV not bound"
fi

if lsmod | grep -q '^ucsi_peek'; then
	rmmod ucsi_peek && echo "unloaded ucsi_peek"
	dmesg | grep ucsi_peek | tail -3
else
	echo "ucsi_peek not loaded"
fi

echo
echo "typec entries now: $(ls /sys/class/typec 2>/dev/null | wc -l)"
echo "Reboot to restore the firmware's original VERSION value (0x0000)."
