import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib


class Dockbar(Gtk.Box):
    """Vertical icon sidebar for module navigation."""

    def __init__(self, on_switch):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(52, -1)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.add_css_class("dockbar")

        self._buttons = {}
        self._on_switch = on_switch

        items = [
            ("time-tracking", "preferences-system-time-symbolic", "Zeiterfassung"),
            ("reports", "document-properties-symbolic", "Auswertungen"),
            ("settings", "preferences-system-symbolic", "Konfiguration"),
        ]

        for name, icon, tooltip in items:
            btn = Gtk.ToggleButton()
            btn.set_icon_name(icon)
            btn.set_tooltip_text(tooltip)
            btn.set_has_frame(False)
            btn.add_css_class("dockbar-button")
            btn.set_size_request(44, 44)
            btn.set_halign(Gtk.Align.CENTER)
            btn.connect("toggled", self._on_toggled, name)
            self._buttons[name] = btn
            self.append(btn)

        # Activate first button
        self._buttons["time-tracking"].set_active(True)

    def _on_toggled(self, button, name):
        if not button.get_active():
            # Prevent un-toggle: re-activate if it was the active one
            if all(not b.get_active() for b in self._buttons.values()):
                button.set_active(True)
            return

        # Deactivate all other buttons
        for bname, btn in self._buttons.items():
            if bname != name and btn.get_active():
                btn.handler_block_by_func(self._on_toggled)
                btn.set_active(False)
                btn.handler_unblock_by_func(self._on_toggled)

        self._on_switch(name)

    def set_active(self, name):
        btn = self._buttons.get(name)
        if btn and not btn.get_active():
            btn.set_active(True)


def get_dockbar_css():
    return """
    .dockbar {
        background-color: @headerbar_bg_color;
        border-right: 1px solid alpha(@borders, 0.3);
        padding: 4px;
    }
    .dockbar-button {
        border-radius: 8px;
        min-width: 40px;
        min-height: 40px;
        padding: 8px;
    }
    .dockbar-button:checked {
        background-color: alpha(@accent_color, 0.2);
        color: @accent_color;
    }
    """
