import sys
import signal
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from .db import init_db
from .ui.dockbar import Dockbar, get_dockbar_css
from .ui.time_tracking import TimeTrackingView
from .ui.reports import ReportsView
from .ui.settings import SettingsView


class TimeWormWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("TimeWorm")
        self.set_default_size(1100, 700)

        # Outer vertical box: headerbar + content
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(outer)

        # Header bar with window controls + app icon
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        header.set_show_start_title_buttons(True)

        # App icon + title in header
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_halign(Gtk.Align.CENTER)
        app_icon = Gtk.Image.new_from_icon_name("de.tbe.timeworm")
        app_icon.set_pixel_size(24)
        title_box.append(app_icon)
        title_label = Gtk.Label(label="TimeWorm")
        title_label.add_css_class("title-4")
        title_box.append(title_label)
        header.set_title_widget(title_box)

        outer.append(header)

        # Toast overlay wrapping main content
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_vexpand(True)
        outer.append(self._toast_overlay)

        # Main horizontal layout: dockbar | content
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._toast_overlay.set_child(main_box)

        # Dockbar (left sidebar)
        self._dockbar = Dockbar(on_switch=self._on_module_switch)
        main_box.append(self._dockbar)

        # Separator between dockbar and content
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(sep)

        # Content stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)
        main_box.append(self._stack)

        # Build module views
        self._time_view = TimeTrackingView()
        self._stack.add_named(self._time_view, "time-tracking")

        self._reports_view = ReportsView(get_window_fn=lambda: self)
        self._stack.add_named(self._reports_view, "reports")

        self._settings_view = SettingsView()
        self._stack.add_named(self._settings_view, "settings")

        # Start on time tracking
        self._stack.set_visible_child_name("time-tracking")

    def _on_module_switch(self, module_name):
        if not hasattr(self, '_stack'):
            return
        self._stack.set_visible_child_name(module_name)
        # Refresh the target view
        child = self._stack.get_visible_child()
        if hasattr(child, 'refresh'):
            child.refresh()


class TimeWormApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="de.tbe.timeworm")

    def do_activate(self):
        init_db()
        self._load_css()
        # Set app name + icon for desktop integration (dock, taskbar, window title)
        GLib.set_application_name("TimeWorm")
        Gtk.Window.set_default_icon_name("de.tbe.timeworm")
        win = TimeWormWindow(application=self)
        win.set_icon_name("de.tbe.timeworm")
        win.present()

    def _load_css(self):
        css = get_dockbar_css()
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = TimeWormApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
