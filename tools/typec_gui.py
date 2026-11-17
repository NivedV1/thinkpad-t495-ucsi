#!/usr/bin/env python3
"""USB-C / PD viewer for this machine.

Shows what the kernel knows about each Type-C connector and what the firmware
actually reported, and keeps the two apart:

  * sysfs  - /sys/class/typec, what Linux exposes to everything else
  * firmware - the per-offset GET_PDOS walk, only on demand, root-only

The walk is opt-in because it shares the UCSI mailbox with ucsi_acpi.
"""

from __future__ import annotations

import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import typec_core as core  # noqa: E402

APP_ID = "io.github.nivedv1.TypeCPD"
SELFTEST = bool(os.environ.get("TYPEC_PD_SELFTEST"))


def copy_to_clipboard(text: str) -> None:
    display = Gdk.Display.get_default()
    if display is not None:
        display.get_clipboard().set(text)


class Window(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(620, 780)

        self.walk: dict | None = None
        self.walk_error: str | None = None
        self.walk_at: str | None = None
        self.walking = False
        self.signature: tuple | None = None
        self.machine: core.Machine | None = None
        self.groups: list[Adw.PreferencesGroup] = []

        header = Gtk.HeaderBar()
        self.walk_button = Gtk.Button(label="Full data")
        self.walk_button.set_tooltip_text(
            "Read every PDO through the UCSI mailbox (asks for authorisation)"
        )
        self.walk_button.connect("clicked", self.on_walk)
        header.pack_end(self.walk_button)

        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh now")
        self.refresh_button.connect("clicked", lambda *_: self.refresh(force=True))
        header.pack_end(self.refresh_button)

        self.page = Adw.PreferencesPage()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.page)

        self.toast = Adw.ToastOverlay()
        self.toast.set_child(toolbar)
        self.set_content(self.toast)

        self.refresh(force=True)
        GLib.timeout_add_seconds(1, self.refresh)

        if SELFTEST:
            GLib.timeout_add(600, self._selftest_done)

    # -- data ------------------------------------------------------------

    def collect(self) -> tuple[core.Machine, tuple]:
        machine = core.probe()
        if self.walk:
            core.apply_walk(machine.ports, self.walk)
        signature = (
            machine.driver_bound,
            machine.ucsi_present,
            len(machine.ports),
            tuple(
                (
                    p.name,
                    p.power_role,
                    p.opmode,
                    p.partner.pd_supported if p.partner else None,
                    p.partner.pd_revision if p.partner else None,
                    tuple((c.position, c.label()) for c in p.partner.source) if p.partner else (),
                    tuple((c.position, c.label()) for c in (p.walk_source or ())),
                    p.rdo["raw"] if p.rdo else None,
                )
                for p in machine.ports
            ),
            self.walk_error,
            len(machine.usb_devices),
        )
        return machine, signature

    def refresh(self, force: bool = False) -> bool:
        machine, signature = self.collect()
        self.machine = machine
        if force or signature != self.signature:
            self.signature = signature
            self.rebuild(machine)
        return True

    # -- widgets ---------------------------------------------------------

    def kv(self, key: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=key)
        row.add_css_class("property")
        label = Gtk.Label(label=value)
        label.add_css_class("dim-label")
        label.set_xalign(1.0)
        label.set_selectable(True)
        row.add_suffix(label)
        return row

    def command_row(self, title: str, command: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=command)
        row.add_css_class("property")
        button = Gtk.Button(icon_name="edit-copy-symbolic")
        button.add_css_class("flat")
        button.set_tooltip_text("Copy")
        button.connect("clicked", lambda *_: copy_to_clipboard(command))
        row.add_suffix(button)
        return row

    def pdo_row(self, pdo: core.Pdo, in_use: bool) -> Adw.ActionRow:
        row = Adw.ActionRow(title=pdo.label())
        row.set_subtitle(pdo.kind.replace("_", " "))
        if in_use:
            mark = Gtk.Image.new_from_icon_name("object-select-symbolic")
            mark.set_tooltip_text("selected by the Request Data Object")
            row.add_suffix(mark)
        return row

    def add_group(self, group: Adw.PreferencesGroup) -> None:
        self.groups.append(group)
        self.page.add(group)

    def rebuild(self, machine: core.Machine) -> None:
        for group in self.groups:
            self.page.remove(group)
        self.groups.clear()

        self.set_title(f"USB-C / PD — {machine.model}")

        status = Adw.PreferencesGroup(title="This machine")
        status.add(self.kv("Model", f"{machine.vendor} {machine.family} ({machine.model})"))
        status.add(self.kv("BIOS", machine.bios))
        status.add(self.kv("Kernel", machine.kernel))
        device = "present" if machine.ucsi_present else "missing"
        device += " · driver bound" if machine.driver_bound else " · driver not bound"
        status.add(self.kv("UCSI device", device))
        status.add(self.kv("Type-C ports", str(len(machine.ports))))
        self.add_group(status)

        if not machine.ports:
            self.add_group(self.defect_group(machine))
        else:
            for port in machine.ports:
                self.add_port(port)
            self.add_group(self.firmware_group(machine))

        if machine.usb_devices:
            usb = Adw.PreferencesGroup(
                title="USB devices",
                description="The kernel does not expose which Type-C connector a device arrived on here.",
            )
            for device in machine.usb_devices:
                title = device["product"] or "(no product string)"
                subtitle = f"{device['id']} · {device['name']}"
                if device["manufacturer"]:
                    subtitle += f" · {device['manufacturer']}"
                if device["speed"]:
                    subtitle += f" · {device['speed']} Mb/s"
                usb.add(Adw.ActionRow(title=title, subtitle=subtitle))
            self.add_group(usb)

        if self.walk_error:
            error = Adw.PreferencesGroup(title="Full data unavailable")
            error.add(Adw.ActionRow(title="Could not read the mailbox", subtitle=self.walk_error))
            error.add(
                self.command_row(
                    "Run it in a terminal instead",
                    f"sudo {core.walk_helper_path()} --pretty",
                )
            )
            self.add_group(error)

    def defect_group(self, machine: core.Machine) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="No Type-C ports registered",
            description="The ACPI device is there; the driver gave up without saying why.",
        )
        row = Adw.ActionRow(
            title="VERSION 0x0000",
            subtitle="ucsi_register() returns -ENODEV on version zero, before logging anything.",
        )
        row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        group.add(row)
        group.add(self.command_row("Check the register", "sudo ./scripts/10-dump-ucsi.sh"))
        group.add(
            self.command_row(
                "Bind with the kernel quirk", "sudo ./scripts/15-build-quirk.sh"
            )
        )
        return group

    def add_port(self, port: core.Port) -> None:
        description = f"{port.power_role} · PD {port.pd_revision} · {port.opmode}"
        group = Adw.PreferencesGroup(title=port.label, description=description)
        group.add(self.kv("Data role", port.data_role))
        group.add(self.kv("Type-C revision", port.typec_revision))
        if port.partner:
            group.add(
                self.kv(
                    "Partner",
                    f"PD {port.partner.pd_supported} · revision {port.partner.pd_revision}"
                    f" · {port.partner.alt_modes} alt mode(s)",
                )
            )
        else:
            group.add(self.kv("Partner", "nothing attached"))
        group.add(self.kv("Cable", port.cable or "none (no e-marker object)"))

        in_use = port.rdo["position"] if port.rdo else None
        if port.rdo:
            obj = next(
                (c for c in (port.walk_source or []) if c.position == in_use), None
            )
            current = port.rdo["operating_current_ma"] / 1000
            text = f"position {in_use} · {current:.2f} A"
            if obj and obj.voltage_mv:
                voltage = obj.voltage_mv / 1000
                text = f"position {in_use} · {voltage:.2f} V / {current:.2f} A = {voltage * current:.1f} W"
            if port.rdo["capability_mismatch"]:
                text += " · mismatch"
            group.add(self.kv("Negotiated", text))

        if not port.partner and not port.walk_source:
            group.add(Adw.ActionRow(title="Nothing attached", subtitle="connect a device or charger"))

        self.add_group(group)

        if port.partner and port.partner.source:
            caps = Adw.PreferencesGroup(
                title=f"Source PDOs · sysfs · {len(port.partner.source)}"
            )
            for pdo in port.partner.source:
                caps.add(self.pdo_row(pdo, pdo.position == in_use))
            self.add_group(caps)

        if port.walk_source:
            walked = Adw.PreferencesGroup(
                title=f"Source PDOs · firmware · {len(port.walk_source)}",
                description="Read one offset at a time through the UCSI mailbox.",
            )
            for pdo in port.walk_source:
                walked.add(self.pdo_row(pdo, pdo.position == in_use))
            if port.partner and len(port.walk_source) > len(port.partner.source):
                warn = Adw.ActionRow(
                    title="Short GET_PDOS reply",
                    subtitle=f"sysfs has {len(port.partner.source)} of "
                    f"{len(port.walk_source)}: the EC returns one PDO per batch request.",
                )
                warn.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
                walked.add(warn)
            self.add_group(walked)

        if port.local_source:
            local = Adw.PreferencesGroup(
                title="Local source PDOs",
                description="What this machine advertises when it sources power.",
            )
            for pdo in port.local_source:
                local.add(self.pdo_row(pdo, False))
            self.add_group(local)

    def firmware_group(self, machine: core.Machine) -> Adw.PreferencesGroup:
        """The in-page way into the privileged read; the header button is easy to miss."""
        group = Adw.PreferencesGroup(
            title="Firmware data",
            description="sysfs stops at the first PDO here. The full list and the "
            "negotiated contract come from the firmware, one object at a time.",
        )

        if self.walking:
            row = Adw.ActionRow(
                title="Reading the mailbox…",
                subtitle="Authorise the request with your fingerprint or password.",
            )
            spinner = Gtk.Spinner()
            spinner.start()
            row.add_suffix(spinner)
            group.add(row)
            return group

        if self.walk:
            count = sum(len(p.walk_source or ()) for p in machine.ports)
            subtitle = f"{count} source PDOs"
            if self.walk_at:
                subtitle += f" · read at {self.walk_at}"
            row = Adw.ActionRow(title="Firmware view loaded", subtitle=subtitle)
            row.add_prefix(Gtk.Image.new_from_icon_name("object-select-symbolic"))
            again = Gtk.Button(label="Re-read")
            again.add_css_class("flat")
            again.connect("clicked", self.on_walk)
            row.add_suffix(again)
            group.add(row)
            return group

        row = Adw.ActionRow(
            title="Read the full PDO list",
            subtitle="One GET_PDOS per offset through the UCSI mailbox. "
            "Asks for authorisation; read-only.",
        )
        row.add_prefix(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        row.set_activatable(True)
        row.connect("activated", self.on_walk)
        button = Gtk.Button(label="Read")
        button.add_css_class("suggested-action")
        button.connect("clicked", self.on_walk)
        row.add_suffix(button)
        group.add(row)
        return group

    # -- actions ---------------------------------------------------------

    def on_walk(self, _button) -> None:
        if self.walking:
            return
        self.walking = True
        self.walk_button.set_sensitive(False)
        self.walk_button.set_label("Reading…")
        self.refresh(force=True)

        import threading

        def worker():
            ok, data = core.run_walk()
            GLib.idle_add(self.walk_done, ok, data)

        threading.Thread(target=worker, daemon=True).start()

    def walk_done(self, ok: bool, data) -> bool:
        self.walking = False
        self.walk_button.set_sensitive(True)
        self.walk_button.set_label("Full data")
        if ok:
            self.walk = data
            self.walk_error = None
            self.walk_at = time.strftime("%H:%M")
            self.toast.add_toast(Adw.Toast(title="Read the full PDO list"))
        else:
            self.walk = None
            self.walk_error = str(data)
            self.walk_at = None
            self.toast.add_toast(Adw.Toast(title="Full data failed"))
        self.refresh(force=True)
        return False

    def _selftest_done(self) -> bool:
        if self.machine:
            print(core.describe(self.machine))
        self.get_application().quit()
        return False


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = Window(application=self)
        window.present()


def main() -> int:
    app = Application()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
