# Battery charge-rate measurement

`battery-samples.log` was written by `scripts/50-charge-rate.sh` while the
Xiaomi 67 W Type-A charger was connected through its own A-to-C cable.

Columns (space separated):

```
unix_time  energy_now[uWh]  power_now[uW]  voltage_now[uV]  status  AC_online
```

The battery exposes no `current_now` on this machine, and `power_now` is noisy
(8-29 W), so the rate is taken from the monotonic `energy_now` counter with a
least-squares fit over the whole window. `power_now` is reported only as a
cross-check.

Result of the full run:

```
samples        72 over 357 s (6.0 min)
energy         22.390 Wh -> 24.090 Wh  (delta 1.700 Wh)
energy slope   17.07 W
power_now      mean 17.56 W  (min 17.50, max 17.61)
batt voltage   11.72 V -> 11.79 V      (rising = genuine charge)
status/ac      Charging / 1            (no dropouts, no renegotiation)
```

An earlier 3-minute window of the same session gave 17.15 W over 176 s, so the
figure is stable.

Why this matters: the battery absorbs 17.07 W at ~11.7 V, while the adapter's
5 V rail is rated 3 A (15 W) and its own 5 V PDO is exactly `5 V / 3 A`. A
single 5 V / 3 A contract cannot charge the pack at 17 W and run the system, so
that entry is not the whole capability list. The full list, read offset by
offset on Windows, is 5 V, 9 V, 15 V and 20 V, and the RDO `0x43051545` selects
position 4 (20 V / 3.25 A = 65 W). The measurement is therefore consistent with
the 20 V profile and rules out the truncated 5 V entry as the contract in force.
Linux exposes no input voltage or current, so the 20 V figure rests on the
firmware-reported PDO/RDO pair and the matching Vantage display, not on a meter.
