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

## The same adapter, two attaches, opposite answers

The strongest version of this needs no exotic charger. The machine's own Lenovo
65 W adapter (label `20 V / 3.25 A`, MFG 6/2015) on `port1`
(`data/snapshots/lenovo-65w-typec.txt`):

| | Attach A | Attach B |
|---|---|---|
| when | 23:20–23:28 | from 23:28:24 |
| what changed | — | connector flipped over in the port |
| `power_operation_mode` | `usb_power_delivery` | `usb_power_delivery` |
| partner `supports_usb_power_delivery` | `no` | **`yes`** |
| partner PD object | **absent** | rev 2.0, source PDO 5 V / 3 A |
| PSY `current_now` | 2.68 A | 3.25 A |
| PSY `voltage_now` | 0 V | 0 V |
| battery | Charging, 17.11–17.27 W | Charging, 17.37 W at 11.63 V |

Flipping the connector does not change what the adapter can do. It only forces a
detach and a fresh attach — and a fresh attach is where the snapshot is taken.
Nine minutes of one orientation produced `no` with no PD object; the other
orientation produced `yes` with a PD object.

Attach B also catches the orphan window. At 23:28:25 the PD device existed under
`port1-partner/` but the partner's `usb_power_delivery` link did not; it appeared
one second later. `ucsi_register_partner_pdos()` registers `con->partner_pd`
first and only links it to the partner after both `GET_PDOS` calls succeed:

```c
con->partner_pd = typec_partner_usb_power_delivery_register(con->partner, &desc);
...
cap = ucsi_get_pd_caps(con, TYPEC_SOURCE, true);
if (IS_ERR(cap))
        return PTR_ERR(cap);
...
return typec_partner_set_usb_power_delivery(con->partner, con->partner_pd);
```

The task is queued with one retry, but the retry is a no-op:

```c
if (con->partner_pd)
        return 0;
```

So if the first `GET_PDOS` fails with `-EBUSY`, the object stays registered but
never linked, and the retry cannot fix it. No message is logged for any error
other than `-EBUSY`/`-ETIMEDOUT`, which are simply retried once and dropped.
That is where an unlinked PD object can come from. It is not what happened on
attach A — there `partnerpd_dirs=0`, so the registration was never reached at
all — but it is the other way to lose the PD object.

## What this explains

- The phone result: on two of three attaches the partner object said `no PD`
  and the port said `default`; on the third the partner said `yes PD` and the
  port said `usb_power_delivery`. On three samples, that is consistent with a
  race, not with a property of either connector.
- Why `supports_usb_power_delivery = no` can coexist with
  `power_operation_mode = usb_power_delivery` — with or without a PD object.
- Why a replug can change the answer without moving the cable, and why flipping
  the connector can do the same on the machine's own 65 W adapter.
- Why "no PD object" and "PD object with a 5 V / 3 A PDO" are both observed for
  a 20 V / 3.25 A adapter: the object's presence is decided by whether the
  registration task ran while the EC was reporting `PD`.

## What it does not explain

- The source capability itself. A 65 W adapter rated 20 V / 3.25 A is reported
  with exactly one PDO, `5 V / 3 A`, on both attaches — the Type-C default, not
  the contract. The A-to-C charger produces the same table even though it has no
  CC conductor. Whatever produces that list is not reading the adapter.
- Power conservation. `5 V x 3 A` is 15 W; the battery alone takes 17.37 W at
  11.63 V. The reported contract cannot be the one in force.
- The invalid source PDOs (`0 mV / 0 mA`, `1050 mV / 2560 mA`).
- The RDO-derived PSY values: `current_now` 3.25 A against a 3 A maximum, and
  `voltage_now` 0 V against a 5 V PDO.
- The swapped connector numbering relative to ACPI `_PLD`.

Those stand on their own. The registration-time race removes the "is it the
charger?" question; it does not make the data usable.

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
