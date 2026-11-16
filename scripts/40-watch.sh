#!/bin/bash
# 40-watch.sh <outdir> [seconds] - 1 Hz capture of AC, battery, roles, partner, PD, cable.
# Safe: reads sysfs and follows dmesg only.
set -u

OUT=${1:-/tmp/typec-watch}
SECS=${2:-180}
mkdir -p "$OUT"
: > "$OUT/state.log"
: > "$OUT/kernel-events.log"

dmesg -w > "$OUT/kernel-events.log" 2>&1 &
DPID=$!
trap 'kill "$DPID" 2>/dev/null' EXIT

snapshot() {
	local ts=$1 line part cable pdrev idh prod
	line="$ts ac=$(cat /sys/class/power_supply/AC/online 2>/dev/null)"
	line="$line bat=$(cat /sys/class/power_supply/BAT0/status 2>/dev/null)/$(cat /sys/class/power_supply/BAT0/power_now 2>/dev/null)"
	for p in /sys/class/typec/port*; do
		case "${p##*/}" in *-*) continue;; esac
		[ -d "$p" ] || continue
		part=none; cable=none; pdrev=-; idh=-; prod=-
		local pp
		for pp in "$p"/*partner*; do [ -d "$pp" ] && part=$pp; done
		for pp in "$p"/*cable*; do [ -d "$pp" ] && cable=yes; done
		if [ "$part" != none ]; then
			pdrev=$(cat "$part/usb_power_delivery_revision" 2>/dev/null)
			idh=$(cat "$part/id_header" 2>/dev/null)
			prod=$(cat "$part/product" 2>/dev/null)
		fi
		line="$line ${p##*/}[dr=$(cat "$p/data_role" 2>/dev/null | tr -d '\n')"
		line="$line pr=$(cat "$p/power_role" 2>/dev/null | tr -d '\n')"
		line="$line om=$(cat "$p/power_operation_mode" 2>/dev/null)"
		line="$line part=$([ "$part" = none ] && echo no || echo yes) cable=$cable"
		line="$line pd=$pdrev idh=$idh prod=$prod]"
	done
	echo "$line" >> "$OUT/state.log"
}

echo "capturing ${SECS}s into $OUT (plug/unplug while this runs)"
for _ in $(seq 1 "$SECS"); do
	snapshot "$(date +%H:%M:%S)"
	sleep 1
done
kill "$DPID" 2>/dev/null
trap - EXIT
echo done > "$OUT/DONE"
echo "wrote $OUT/state.log and $OUT/kernel-events.log"
