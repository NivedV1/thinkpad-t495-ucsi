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

Why this matters: the charger is rated `5 V / 3 A` (15 W) on 5 V, and that is
before system draw. Delivering 17.07 W into the battery therefore requires
VBUS above 5 V, which the charger only enables through its vendor cable
identification. UCSI simultaneously reports a `5 V / 3 A` PD contract on the
same connector, which cannot describe that power path. No Linux interface on
this machine exposes input voltage or current (`AC/online` only), so the exact
VBUS voltage was not measurable without an inline meter.
