# Why the two PD values can disagree

Two sysfs values look like they should always match, and on this machine they
often do not:

```text
/sys/class/typec/port1/power_operation_mode          usb_power_delivery
/sys/class/typec/port1-partner/supports_usb_power_delivery   no
```

Both describe the same attach. They are sampled at different moments, and the
EC can change its answer in between.

## Where each value comes from

Linux v6.19, `drivers/usb/typec/ucsi/ucsi.c`.

`supports_usb_power_delivery` is `desc.usb_pd`, set once when the partner object
is created, from the connector status at that instant:

```c
static int ucsi_register_partner(struct ucsi_connector *con)
{
        u8 pwr_opmode = UCSI_CONSTAT(con, PWR_OPMODE);
        ...
        desc.usb_pd = pwr_opmode == UCSI_CONSTAT_PWR_OPMODE_PD;
        ...
        partner = typec_register_partner(con->port, &desc);
```

`power_operation_mode` follows the connector-change path, which runs after the
partner has been registered:

```c
static void ucsi_pwr_opmode_change(struct ucsi_connector *con)
{
        switch (UCSI_CONSTAT(con, PWR_OPMODE)) {
        case UCSI_CONSTAT_PWR_OPMODE_PD:
                con->rdo = UCSI_CONSTAT(con, RDO);
                typec_set_pwr_opmode(con->port, TYPEC_PWR_MODE_PD);
                ...
```

In `ucsi_connector_change()`, the order is:

```c
if (UCSI_CONSTAT(con, CONNECTED)) {
        if (prev_state)
                return 0;
        ucsi_register_partner(con);      /* snapshot taken here */
        ucsi_pwr_opmode_change(con);     /* port value set here */
        ucsi_partner_change(con);
}
```

If the EC reports `default` at the moment `ucsi_register_partner()` runs, the
partner is created with `usb_pd = false` and `supports_usb_power_delivery`
reads `no` **for the rest of the attach**. A later notification can still set
`power_operation_mode = usb_power_delivery` and populate the PD object.

The attribute is not re-evaluated when the operation mode changes later.

## The replug that shows it

Xiaomi 67 W Type-A charger on its own A-to-C cable, same `port1` both times,
1 Hz capture (`data/snapshots/xiaomi-charger-typec.txt`):

| Time | `power_operation_mode` | partner `supports_usb_power_delivery` | PD object |
|---|---|---|---|
| 22:05:00–22:06:46 | `usb_power_delivery` | `no` | rev 2.0, 5 V / 3 A |
| 22:06:47 (unplug) | `default` | partner gone | gone |
| 22:06:54 (replug) | `usb_power_delivery` | **`yes`** | not yet present |
| 22:06:57 onward | `usb_power_delivery` | `yes` | rev 2.0, 5 V / 3 A |

The charger and cable did not change. The connector did not change. The value
flipped because the EC's answer arrived in a different order this time.

## What this explains

- The phone result: on two of three attaches the partner object said `no PD`
  and the port said `default`; on the third the partner said `yes PD` and the
  port said `usb_power_delivery`. On three samples, that is consistent with a
  race, not with a property of either connector.
- Why `supports_usb_power_delivery = no` can coexist with
  `power_operation_mode = usb_power_delivery` and a valid-looking PD object.
- Why a replug can change the answer without moving the cable.

## What it does not explain

- The A-to-C charger. It has no CC conductor, so it cannot negotiate PD at all.
  Yet every attach produced `power_operation_mode = usb_power_delivery` and a
  PD 2.0 object with a 5 V / 3 A PDO, while the battery charged at 17.07 W.
- The invalid source PDOs (`0 mV / 0 mA`, `1050 mV / 2560 mA`).
- The RDO-derived PSY values: `current_now` 3.25 A against a 3 A PDO, and
  `voltage_now` 0 V against a 5 V PDO.
- The swapped connector numbering relative to ACPI `_PLD`.

Those stand on their own.

## The `0.0` revision is not part of this

`port1-partner/usb_power_delivery_revision` reads `0.0` while
`port1-partner/usb_power_delivery/revision` reads `2.0`. That is not a firmware
contradiction:

```c
if (con->ucsi->version >= UCSI_VERSION_2_1) {
        u64 pd_revision = UCSI_CONCAP(con, PARTNER_PD_REVISION_V2_1);
        desc.pd_revision = UCSI_SPEC_REVISION_TO_BCD(pd_revision);
}
```

The patched version is 1.1, below 2.1, so `desc.pd_revision` is never filled and
the attribute stays at its zero-initialised value. The port's `2.0` comes from a
different field (`ucsi->cap.pd_version`). The repo deliberately does not list
this as a finding.

## How to check it yourself

```bash
# with the interface bound and a PD-capable charger attached
sudo ./scripts/40-watch.sh /tmp/pd 120
# unplug, wait ~5 s, replug, then:
cat /tmp/pd/state.log | sed -E 's/^[0-9:]+ //' | uniq -c
```

Look for a change in `spd=` (partner's `supports_usb_power_delivery`) and in
`opmode=` (the port's `power_operation_mode`) at different times. A value that
flips on a replug with the same cable and connector is the race.

```bash
grep -E ' port1\[' /tmp/pd/state.log | awk '{ ts=$1; $1=""; if ($0!=p) { print ts, substr($0,2); p=$0 } }'
```
