# `tools/` — a small viewer for this machine

A GTK4 window that shows the Type-C connectors, what is attached to them, and
the power capabilities behind them. It exists because the two layers disagree
here, and the disagreement is the whole point:

| Layer | What it says |
|---|---|
| sysfs | one source PDO, 5 V / 3 A, for a 65 W adapter |
| firmware | four PDOs, 5 / 9 / 15 / 20 V, the last one in use |

The window shows both, labelled, and never merges them into one list.

## Run

```bash
python3 tools/typec_gui.py
```

Requires GTK 4 and PyGObject (`gtk4`, `python3-gobject`, `libadwaita` on
Fedora). No build step, no other dependencies.

`tools/install-desktop.sh` adds it to the application grid; the entry points at
this checkout, so run it again if the repository moves.

## What it reads

- `/sys/class/typec/` — ports, partners, cables, alt-mode counts, revisions.
- `/sys/class/usb_power_delivery/` — the capability objects, via the attributes
  `drivers/usb/typec/pd.c` exposes (`voltage`, `maximum_current`, …).
- `/sys/bus/usb/devices/` — attached USB devices. The kernel does not expose
  which connector they arrived on here, so the window does not claim one.

**Full data** is the only privileged path. It is offered both as a header
button and as a **Read the full PDO list** row at the bottom of the page; it
runs `ucsi_walk.py` through `pkexec` and reads `GET_PDOS` per offset plus
`GET_CONNECTOR_STATUS`, which is where the four PDOs and the negotiated
contract come from. It is opt-in for a reason: the driver owns that mailbox,
and the helper sends one command at a time. Decline the authorisation prompt
and the window keeps working from sysfs alone.

## No ports at all

If `/sys/class/typec/` is empty the window explains why instead of showing an
empty list: the ACPI device is present, `ucsi_acpi` is not bound, and
`VERSION` reads `0x0000`, which `ucsi_register()` rejects with `-ENODEV`
without logging anything. The fix commands are printed with a copy button.

## Files

| File | Role |
|---|---|
| `typec_core.py` | sysfs model, PDO/RDO decoders, optional walk driver. No GTK; `python3 typec_core.py [--json] [--walk]` prints the same data as text |
| `typec_gui.py` | the window, 1 Hz refresh, rebuilds only when something changed |
| `ucsi_walk.py` | root helper, JSON on stdout, `GET_PDOS` and `GET_CONNECTOR_STATUS` only |
| `install-desktop.sh` | writes the `.desktop` entry |
