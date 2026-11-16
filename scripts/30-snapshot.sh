#!/bin/bash
# 30-snapshot.sh <outdir> - dump the full Type-C / PD state to files.
# Safe: reads sysfs only.
set -u

OUT=${1:-/tmp/typec-snapshot}
mkdir -p "$OUT"

read_attr() { # read_attr <file> <label>
	if [ -f "$1" ]; then
		printf '%-40s %s\n' "$2" "$(tr '\n' ' ' < "$1" | sed 's/ *$//')"
	else
		printf '%-40s %s\n' "$2" "(absent)"
	fi
}

dump_pdos() { # dump_pdos <dir> <label>
	local d=$1 label=$2 q any=0
	local f
	if [ ! -d "$d" ]; then printf '%s: absent\n' "$label"; return; fi
	printf '%s:\n' "$label"
	for q in "$d"/*/; do
		[ -d "$q" ] || continue
		local qn=${q%/}
		case "${qn##*/}" in power) continue;; esac
		any=1
		printf '  %s\n' "${q#"$d"/}"
		for f in voltage maximum_current operational_current; do
			[ -f "$q$f" ] && printf '    %-22s %s\n' "$f" "$(cat "$q$f")"
		done
	done
	[ "$any" = 1 ] || printf '  (no PDO objects)\n'
}

{
	echo "# snapshot $(date -Is)"
	echo "# host: $(cat /sys/class/dmi/id/product_name 2>/dev/null) $(cat /sys/class/dmi/id/product_version 2>/dev/null)"
	echo "# bios: $(cat /sys/class/dmi/id/bios_version 2>/dev/null)"
	echo "# kernel: $(uname -r)"
	echo

	echo "## power supplies"
	for s in /sys/class/power_supply/*; do
		[ -d "$s" ] || continue
		echo "[${s##*/}]"
		for a in online status usb_type voltage_now voltage_max current_max power_now energy_now; do
			[ -f "$s/$a" ] && printf '  %-20s %s\n' "$a" "$(cat "$s/$a" 2>/dev/null)"
		done
	done
	echo

	echo "## usb tree"
	lsusb -t 2>/dev/null
	echo

	for p in /sys/class/typec/port*; do
		case "${p##*/}" in *-*) continue;; esac
		[ -d "$p" ] || continue
		echo "## ${p##*/}"
		read_attr "$p/data_role" data_role
		read_attr "$p/power_role" power_role
		read_attr "$p/power_operation_mode" power_operation_mode
		read_attr "$p/usb_typec_revision" usb_typec_revision
		read_attr "$p/usb_power_delivery_revision" usb_power_delivery_revision
		read_attr "$p/vconn_source" vconn_source
		read_attr "$p/supported_accessory_modes" supported_accessory_modes
		read_attr "$p/usb_capability" usb_capability
		[ -e "$p/firmware_node" ] && \
			read_attr "$p/firmware_node/path" acpi_path
		echo "  linked usb ports: $(ls -d "$p"/usb*-port* 2>/dev/null | sed 's#.*/##' | tr '\n' ' ')"
		echo "  partners: $(ls -d "$p"/*partner* 2>/dev/null | sed 's#.*/##' | tr '\n' ' ')"
		echo "  cables:   $(ls -d "$p"/*cable* 2>/dev/null | sed 's#.*/##' | tr '\n' ' ')"
		for m in "$p"/"${p##*/}".*; do
			[ -d "$m" ] || continue
			printf '  altmode %-10s svid=%s mode=%s vdo=%s active=%s\n' \
				"${m##*/}" "$(cat "$m/svid" 2>/dev/null)" \
				"$(cat "$m/mode" 2>/dev/null)" \
				"$(cat "$m/vdo" 2>/dev/null)" \
				"$(cat "$m/active" 2>/dev/null)"
		done
		dump_pdos "$p/usb_power_delivery/source-capabilities" \
			"  source PDOs"
		dump_pdos "$p/usb_power_delivery/sink-capabilities" \
			"  sink PDOs"
		echo
	done

	for p in /sys/class/typec/*partner*; do
		[ -d "$p" ] || continue
		echo "## ${p##*/}"
		for a in id_header product product_type number_of_alternate_modes \
			 accessory_mode supports_usb_power_delivery \
			 usb_power_delivery_revision; do
			read_attr "$p/$a" "$a"
		done
		read_attr "$p/usb_power_delivery/revision" pd_object_revision
		dump_pdos "$p/usb_power_delivery/source-capabilities" "  partner source PDOs"
		dump_pdos "$p/usb_power_delivery/sink-capabilities" "  partner sink PDOs"
		echo
	done

	echo "## ucsi register block"
	dmesg | grep ucsi_peek | tail -8
	echo
	echo "## recent kernel events"
	dmesg | grep -iE 'ucsi|typec|usb [0-9]+-[0-9]+:' | tail -40
} | tee "$OUT/summary.txt" >/dev/null

echo "wrote $OUT/summary.txt"
