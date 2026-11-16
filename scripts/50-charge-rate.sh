#!/bin/bash
# 50-charge-rate.sh [seconds] [outdir] - measure the true charge rate from the
# battery energy counter, because power_now is noisy on these machines.
#
# This does not read the Type-C port at all; it tells you how much power is
# actually reaching the battery, which is the number to compare against the
# PDO that UCSI reports.
set -u

SECS=${1:-360}
OUT=${2:-/tmp/charge-rate-$(date +%H%M)}
mkdir -p "$OUT"
: > "$OUT/samples.log"

echo "sampling ${SECS}s into $OUT/samples.log"
echo "keep the machine idle and the charger connected"
for _ in $(seq 1 "$SECS"); do
	printf '%s %s %s %s %s %s\n' \
		"$(date +%s)" \
		"$(cat /sys/class/power_supply/BAT0/energy_now 2>/dev/null)" \
		"$(cat /sys/class/power_supply/BAT0/power_now 2>/dev/null)" \
		"$(cat /sys/class/power_supply/BAT0/voltage_now 2>/dev/null)" \
		"$(cat /sys/class/power_supply/BAT0/status 2>/dev/null)" \
		"$(cat /sys/class/power_supply/AC/online 2>/dev/null)" \
		>> "$OUT/samples.log"
	sleep 1
done

awk '
NR==1 { t0=$1 }
{ n++; t[n]=$1-t0; e[n]=$2; p[n]=$3; v[n]=$4; s[n]=$5; a[n]=$6 }
END {
  if (n < 10) { print "not enough samples"; exit }
  st=0; se=0; stt=0; ste=0
  for (i=1;i<=n;i++) { st+=t[i]; se+=e[i]; stt+=t[i]*t[i]; ste+=t[i]*e[i] }
  den=n*stt-st*st
  if (den == 0) { print "degenerate timestamps"; exit }
  slope=(n*ste-st*se)/den
  printf "samples        %d over %.0f s (%.1f min)\n", n, t[n], t[n]/60
  printf "energy         %.3f Wh -> %.3f Wh  (delta %.3f Wh)\n", e[1]/1e6, e[n]/1e6, (e[n]-e[1])/1e6
  printf "energy slope   %.2f W\n", slope*3600/1e6
  sp=0; np=0; pmin=1e18; pmax=0
  for (i=1;i<=n;i++) if (p[i]!="") { sp+=p[i]; np++; if (p[i]<pmin) pmin=p[i]; if (p[i]>pmax) pmax=p[i] }
  if (np) printf "power_now      mean %.2f W  min %.2f  max %.2f\n", sp/np/1e6, pmin/1e6, pmax/1e6
  else    printf "power_now      not exposed\n"
  printf "batt voltage   %.2f V -> %.2f V\n", v[1]/1e6, v[n]/1e6
  printf "status/ac      %s / %s\n", s[n], a[n]
  if (slope <= 0) print "NOTE: energy is not rising - charger not charging the battery?"
}' "$OUT/samples.log" | tee "$OUT/fit.txt"
