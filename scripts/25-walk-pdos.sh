#!/bin/bash
# 15-walk-pdos.sh - read PDOs one offset at a time through the UCSI debugfs
# interface, the same walk the Windows capture used. Read-only: only GET_PDOS
# is sent.
#
# Requires the driver to be bound, so run 20-enable-ucsi.sh first. The debugfs
# directory only exists while ucsi_acpi is registered.
set -eu

DEV=${UCSI_DEVICE:-USBC000:00}
DIR=/sys/kernel/debug/usb/ucsi/$DEV

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }

if [ ! -e "$DIR/command" ]; then
	mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi
if [ ! -e "$DIR/command" ]; then
	echo "no $DIR/command"
	echo "ucsi_acpi is not bound. Run ./scripts/20-enable-ucsi.sh first"
	echo "(the patch is RAM-only and disappears on reboot)."
	exit 1
fi

# UCSI_CONTROL for GET_PDOS, one PDO:
#   command 0x10, connector << 16, source << 34
#   partner << 23, offset << 24, (num_pdos - 1) << 32 = 0
get_one()
{
	local conn=$1 partner=$2 off=$3 cmd resp hex pdo

	cmd=$((0x10 | (conn << 16) | (partner << 23) | (off << 24) | (1 << 34)))
	if ! printf '0x%x\n' "$cmd" > "$DIR/command" 2>/dev/null; then
		echo "conn $conn partner $partner offset $off  command failed"
		return
	fi
	resp=$(cat "$DIR/response" 2>/dev/null) || {
		echo "conn $conn partner $partner offset $off  read failed"
		return
	}
	hex=${resp#0x}
	pdo=$((0x${hex: -8}))
	if [ "$pdo" -eq 0 ]; then
		printf 'conn %s partner %s offset %s  no data (end of list)\n' \
			"$conn" "$partner" "$off"
		return
	fi
	if [ $(((pdo >> 30) & 3)) -eq 0 ]; then
		printf 'conn %s partner %s offset %s  0x%08X  %5d mV %5d mA (fixed)\n' \
			"$conn" "$partner" "$off" "$pdo" \
			$((((pdo >> 10) & 0x3FF) * 50)) $(((pdo & 0x3FF) * 10))
	else
		printf 'conn %s partner %s offset %s  0x%08X  (non-fixed PDO)\n' \
			"$conn" "$partner" "$off" "$pdo"
	fi
}

echo "== partner source PDOs (the charger) =="
for conn in 1 2; do
	for off in 0 1 2 3; do
		get_one "$conn" 1 "$off"
	done
done

echo
echo "== local source PDOs (what the laptop advertises) =="
for conn in 1 2; do
	for off in 0 1 2 3; do
		get_one "$conn" 0 "$off"
	done
done

echo
echo "Each group of four is one connector. The debugfs interface does not"
echo "expose the CCI DataLength, so a zero reply is the end-of-list signal."
echo "Compare with windows_ucsi/README.md, which does the same walk."
