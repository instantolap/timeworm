"""TimeWorm - frisst deine Stunden 🐛

Main application entry point.
"""
import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from .db import init_db
from .repository import ProjectRepository, TimeEntryRepository


class TimeWormApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='de.tbe.timeworm')
        self.connect('activate', self.on_activate)
        self.running_entry = None
        self.timer_id = None

    def on_activate(self, app):
        init_db()
        self.win = TimeWormWindow(application=app)
        self.win.present()


class TimeWormWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("🐛 TimeWorm")
        self.set_default_size(700, 500)
        self.app = self.get_application()

        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(box)

        # Header bar
        header = Adw.HeaderBar()
        box.append(header)

        # Add project button
        btn_add = Gtk.Button(icon_name="list-add-symbolic")
        btn_add.connect("clicked", self.on_add_project)
        header.pack_start(btn_add)

        # Export button
        btn_export = Gtk.Button(icon_name="document-save-symbolic")
        btn_export.connect("clicked", self.on_export)
        header.pack_end(btn_export)

        # Content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        box.append(content)

        # Timer section
        self.timer_box = self._build_timer_section()
        content.append(self.timer_box)

        # Entries list
        sw = Gtk.ScrolledWindow(vexpand=True)
        self.entries_list = Gtk.ListBox()
        self.entries_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.entries_list.add_css_class("boxed-list")
        sw.set_child(self.entries_list)
        content.append(sw)

        self._refresh_entries()
        self._check_running()

    def _build_timer_section(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        # Project dropdown
        self.project_dropdown = Gtk.DropDown()
        self._refresh_projects()
        box.append(self.project_dropdown)

        # Timer label
        self.timer_label = Gtk.Label(label="00:00:00")
        self.timer_label.add_css_class("title-1")
        box.append(self.timer_label)

        # Start/Stop button
        self.btn_toggle = Gtk.Button(label="▶ Start")
        self.btn_toggle.add_css_class("suggested-action")
        self.btn_toggle.connect("clicked", self.on_toggle_timer)
        box.append(self.btn_toggle)

        return box

    def _refresh_projects(self):
        projects = ProjectRepository.get_all()
        model = Gtk.StringList()
        self._projects = projects
        for p in projects:
            model.append(f"{p['name']} ({p['hourly_rate']:.0f}€/h)")
        self.project_dropdown.set_model(model)

    def _refresh_entries(self):
        # Clear existing
        while True:
            row = self.entries_list.get_row_at_index(0)
            if row is None:
                break
            self.entries_list.remove(row)

        entries = TimeEntryRepository.get_entries()[:50]
        from datetime import datetime
        for e in entries:
            start = datetime.fromisoformat(e['start_time'])
            end = datetime.fromisoformat(e['end_time'])
            hours = (end - start).total_seconds() / 3600
            amount = hours * e['hourly_rate']

            row = Adw.ActionRow()
            row.set_title(e['project_name'])
            row.set_subtitle(
                f"{start.strftime('%d.%m.%Y %H:%M')} - {end.strftime('%H:%M')} · "
                f"{hours:.1f}h · {amount:.2f}€"
            )
            if e['note']:
                row.set_subtitle(row.get_subtitle() + f" · {e['note']}")
            self.entries_list.append(row)

    def _check_running(self):
        running = TimeEntryRepository.get_running()
        if running:
            self.app.running_entry = running
            self.btn_toggle.set_label("⏹ Stop")
            self.btn_toggle.remove_css_class("suggested-action")
            self.btn_toggle.add_css_class("destructive-action")
            self._start_timer_tick()

    def on_toggle_timer(self, btn):
        if self.app.running_entry:
            # Stop
            TimeEntryRepository.stop(self.app.running_entry['id'])
            self.app.running_entry = None
            self.btn_toggle.set_label("▶ Start")
            self.btn_toggle.remove_css_class("destructive-action")
            self.btn_toggle.add_css_class("suggested-action")
            self.timer_label.set_text("00:00:00")
            if self.app.timer_id:
                GLib.source_remove(self.app.timer_id)
                self.app.timer_id = None
            self._refresh_entries()
        else:
            # Start
            if not self._projects:
                return
            idx = self.project_dropdown.get_selected()
            project = self._projects[idx]
            eid = TimeEntryRepository.start(project['id'])
            self.app.running_entry = {'id': eid, 'start_time': __import__('datetime').datetime.now().isoformat()}
            self.btn_toggle.set_label("⏹ Stop")
            self.btn_toggle.remove_css_class("suggested-action")
            self.btn_toggle.add_css_class("destructive-action")
            self._start_timer_tick()

    def _start_timer_tick(self):
        def tick():
            if not self.app.running_entry:
                return False
            from datetime import datetime
            start = datetime.fromisoformat(self.app.running_entry['start_time'])
            delta = datetime.now() - start
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            mins, secs = divmod(rem, 60)
            self.timer_label.set_text(f"{hours:02d}:{mins:02d}:{secs:02d}")
            return True
        self.app.timer_id = GLib.timeout_add_seconds(1, tick)

    def on_add_project(self, btn):
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Neues Projekt")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_entry = Gtk.Entry(placeholder_text="Projektname")
        rate_entry = Gtk.Entry(placeholder_text="Stundensatz (€)")
        box.append(name_entry)
        box.append(rate_entry)
        dialog.set_extra_child(box)

        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("create", "Anlegen")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "create":
                name = name_entry.get_text().strip()
                try:
                    rate = float(rate_entry.get_text().strip().replace(',', '.'))
                except ValueError:
                    rate = 0.0
                if name:
                    ProjectRepository.create(name, rate)
                    self._refresh_projects()

        dialog.connect("response", on_response)
        dialog.present()

    def on_export(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name("timeworm_export.xlsx")
        
        def on_save(d, result):
            try:
                file = d.save_finish(result)
                if file:
                    from .export.exporter import export_excel
                    from datetime import datetime, timedelta
                    end = datetime.now().isoformat()
                    start = (datetime.now() - timedelta(days=30)).isoformat()
                    export_excel(file.get_path(), start, end)
            except Exception:
                pass

        dialog.save(self, None, on_save)


def main():
    app = TimeWormApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
