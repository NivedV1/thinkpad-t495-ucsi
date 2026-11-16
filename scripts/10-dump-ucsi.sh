#!/bin/bash
# 10-dump-ucsi.sh - build the module and read the UCSI register block, read-only.
# Nothing is written to the register block by this script.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
ADDR=${UCSI_ADDR:-0xBD6B2000}
LEN=${UCSI_LEN:-0x30}

[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo $0"; exit 1; }

echo "== building module =="
make -s -C "$HERE/module"

echo
echo "== loading read-only (addr=$ADDR len=$LEN) =="
if lsmod | grep -q '^ucsi_peek'; then
	echo "ucsi_peek already loaded; unloading first"
	rmmod ucsi_peek
fi
insmod "$HERE/module/ucsi_peek.ko" addr="$ADDR" len="$LEN"

echo
echo "== dmesg =="
dmesg | grep ucsi_peek | tail -20

echo
echo "If VERSION is 0x0000, the firmware is in scope for this bug."
echo "Leave the module loaded, or remove it with: sudo rmmod ucsi_peek"
