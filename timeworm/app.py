"""TimeWorm - frisst deine Stunden 🐛

Main application entry point.
"""
import sys
import math
import calendar
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk, Gio

from .db import init_db
from .repository import ProjectRepository, TimeEntryRepository


MONTH_NAMES = [
    '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]


def _color_dot(hex_color, size=12):
    """Create a small colored circle widget."""
    area = Gtk.DrawingArea()
    area.set_size_request(size, size)
    area.set_valign(Gtk.Align.CENTER)

    rgba = Gdk.RGBA()
    rgba.parse(hex_color)

    def draw(_widget, cr, width, height, _data):
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 2 * math.pi)
        cr.fill()

    area.set_draw_func(draw, None)
    return area


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
        self.set_default_size(700, 600)
        self.app = self.get_application()

        now = datetime.now()
        self.current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        self._setup_actions()

        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(box)

        # Header bar
        header = Adw.HeaderBar()
        box.append(header)

        btn_add = Gtk.Button(icon_name="list-add-symbolic")
        btn_add.set_tooltip_text("Neues Projekt")
        btn_add.connect("clicked", self.on_add_project)
        header.pack_start(btn_add)

        # View switcher in header
        self.view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Export menu button
        menu = Gio.Menu()
        menu.append("Excel (.xlsx)", "win.export-excel")
        menu.append("CSV (.csv)", "win.export-csv")
        menu.append("PDF Rechnung (.pdf)", "win.export-pdf")
        btn_export = Gtk.MenuButton(icon_name="document-save-symbolic")
        btn_export.set_tooltip_text("Exportieren")
        btn_export.set_menu_model(menu)
        header.pack_end(btn_export)

        # Content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        box.append(content)

        # Timer section
        content.append(self._build_timer_section())

        # Month selector
        content.append(self._build_month_selector())

        # View stack
        self.view_stack.set_vexpand(True)
        content.append(self.view_stack)

        # --- Entries page ---
        entries_sw = Gtk.ScrolledWindow(vexpand=True)
        self.entries_list = Gtk.ListBox()
        self.entries_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.entries_list.add_css_class("boxed-list")
        entries_sw.set_child(self.entries_list)
        page = self.view_stack.add_titled(entries_sw, "entries", "Einträge")
        page.set_icon_name("view-list-symbolic")

        # --- Stats page ---
        stats_sw = Gtk.ScrolledWindow(vexpand=True)
        self.stats_list = Gtk.ListBox()
        self.stats_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.stats_list.add_css_class("boxed-list")
        stats_sw.set_child(self.stats_list)
        page = self.view_stack.add_titled(stats_sw, "stats", "Statistik")
        page.set_icon_name("document-properties-symbolic")

        self.view_stack.connect("notify::visible-child",
                                lambda *_: self._refresh_visible())

        self._refresh_entries()
        self._refresh_stats()
        self._check_running()

    def _setup_actions(self):
        for name, callback in [("export-excel", self._on_export_excel),
                                ("export-csv", self._on_export_csv),
                                ("export-pdf", self._on_export_pdf)]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _build_timer_section(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        self.project_dropdown = Gtk.DropDown()
        self._refresh_projects()
        box.append(self.project_dropdown)

        self.timer_label = Gtk.Label(label="00:00:00")
        self.timer_label.add_css_class("title-1")
        box.append(self.timer_label)

        self.btn_toggle = Gtk.Button(label="▶ Start")
        self.btn_toggle.add_css_class("suggested-action")
        self.btn_toggle.connect("clicked", self.on_toggle_timer)
        box.append(self.btn_toggle)

        return box

    def _build_month_selector(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)

        btn_prev = Gtk.Button(icon_name="go-previous-symbolic")
        btn_prev.connect("clicked", lambda _: self._change_month(-1))
        box.append(btn_prev)

        self.month_label = Gtk.Label()
        self.month_label.add_css_class("title-4")
        self._update_month_label()
        box.append(self.month_label)

        btn_next = Gtk.Button(icon_name="go-next-symbolic")
        btn_next.connect("clicked", lambda _: self._change_month(1))
        box.append(btn_next)

        return box

    def _update_month_label(self):
        self.month_label.set_text(
            f"{MONTH_NAMES[self.current_month.month]} {self.current_month.year}"
        )

    def _change_month(self, delta):
        m = self.current_month.month + delta
        y = self.current_month.year
        if m < 1:
            m = 12
            y -= 1
        elif m > 12:
            m = 1
            y += 1
        self.current_month = self.current_month.replace(year=y, month=m)
        self._update_month_label()
        self._refresh_entries()
        self._refresh_stats()

    def _get_month_range(self):
        """Return (start_iso, end_iso) for the current month."""
        start = self.current_month.isoformat()
        _, last_day = calendar.monthrange(
            self.current_month.year, self.current_month.month
        )
        end = self.current_month.replace(
            day=last_day, hour=23, minute=59, second=59
        ).isoformat()
        return start, end

    def _refresh_projects(self):
        projects = ProjectRepository.get_all()
        model = Gtk.StringList()
        self._projects = projects
        for p in projects:
            model.append(f"{p['name']} ({p['hourly_rate']:.0f}€/h)")
        self.project_dropdown.set_model(model)

    def _refresh_visible(self):
        if self.view_stack.get_visible_child_name() == "stats":
            self._refresh_stats()

    def _clear_listbox(self, listbox):
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

    def _refresh_entries(self):
        self._clear_listbox(self.entries_list)
        start, end = self._get_month_range()
        entries = TimeEntryRepository.get_entries(start_date=start, end_date=end)

        for e in entries:
            start_dt = datetime.fromisoformat(e['start_time'])
            end_dt = datetime.fromisoformat(e['end_time'])
            hours = (end_dt - start_dt).total_seconds() / 3600
            amount = hours * e['hourly_rate']

            row = Adw.ActionRow()
            row.set_title(e['project_name'])
            subtitle = (
                f"{start_dt.strftime('%d.%m.%Y %H:%M')} – "
                f"{end_dt.strftime('%H:%M')} · "
                f"{hours:.1f}h · {amount:.2f}€"
            )
            if e['note']:
                subtitle += f" · {e['note']}"
            row.set_subtitle(subtitle)

            row.add_prefix(_color_dot(e.get('color', '#3584e4')))

            btn_edit = Gtk.Button(icon_name="document-edit-symbolic")
            btn_edit.set_valign(Gtk.Align.CENTER)
            btn_edit.add_css_class("flat")
            btn_edit.set_tooltip_text("Bearbeiten")
            btn_edit.connect("clicked", self._on_edit_entry, e)
            row.add_suffix(btn_edit)

            btn_del = Gtk.Button(icon_name="user-trash-symbolic")
            btn_del.set_valign(Gtk.Align.CENTER)
            btn_del.add_css_class("flat")
            btn_del.set_tooltip_text("Löschen")
            btn_del.connect("clicked", self._on_delete_entry, e)
            row.add_suffix(btn_del)

            self.entries_list.append(row)

    def _refresh_stats(self):
        self._clear_listbox(self.stats_list)
        start, end = self._get_month_range()
        summary = TimeEntryRepository.get_summary(start, end)

        if not summary:
            row = Adw.ActionRow()
            row.set_title("Keine Einträge")
            row.set_subtitle(
                f"{MONTH_NAMES[self.current_month.month]} "
                f"{self.current_month.year}"
            )
            self.stats_list.append(row)
            return

        max_hours = max((s['total_hours'] or 0) for s in summary)
        total_hours = 0.0
        total_amount = 0.0

        for s in summary:
            hours = s['total_hours'] or 0
            amount = hours * s['hourly_rate']
            total_hours += hours
            total_amount += amount

            row = Adw.ActionRow()
            row.set_title(s['name'])
            row.set_subtitle(
                f"{hours:.1f}h · {s['entry_count']} Einträge · {amount:.2f}€"
            )
            row.add_prefix(_color_dot(s.get('color', '#3584e4')))

            if max_hours > 0:
                bar = Gtk.ProgressBar()
                bar.set_fraction(hours / max_hours)
                bar.set_valign(Gtk.Align.CENTER)
                bar.set_size_request(120, -1)
                row.add_suffix(bar)

            self.stats_list.append(row)

        # Totals
        total_row = Adw.ActionRow()
        total_row.set_title(f"Gesamt: {total_hours:.1f}h")
        total_row.set_subtitle(f"{total_amount:.2f}€")
        self.stats_list.append(total_row)

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
            self._refresh_stats()
        else:
            if not self._projects:
                return
            idx = self.project_dropdown.get_selected()
            project = self._projects[idx]
            eid = TimeEntryRepository.start(project['id'])
            self.app.running_entry = {
                'id': eid,
                'start_time': datetime.now().isoformat()
            }
            self.btn_toggle.set_label("⏹ Stop")
            self.btn_toggle.remove_css_class("suggested-action")
            self.btn_toggle.add_css_class("destructive-action")
            self._start_timer_tick()

    def _start_timer_tick(self):
        def tick():
            if not self.app.running_entry:
                return False
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
        box.append(name_entry)

        rate_entry = Gtk.Entry(placeholder_text="Stundensatz (€)")
        box.append(rate_entry)

        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        color_box.append(Gtk.Label(label="Farbe:"))
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        default_rgba = Gdk.RGBA()
        default_rgba.parse('#3584e4')
        color_btn.set_rgba(default_rgba)
        color_box.append(color_btn)
        box.append(color_box)

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
                rgba = color_btn.get_rgba()
                color = (
                    f"#{int(rgba.red * 255):02x}"
                    f"{int(rgba.green * 255):02x}"
                    f"{int(rgba.blue * 255):02x}"
                )
                if name:
                    ProjectRepository.create(name, rate, color)
                    self._refresh_projects()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_edit_entry(self, btn, entry):
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Eintrag bearbeiten")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        start_dt = datetime.fromisoformat(entry['start_time'])
        end_dt = datetime.fromisoformat(entry['end_time'])

        box.append(Gtk.Label(
            label="Start (DD.MM.YYYY HH:MM):", halign=Gtk.Align.START
        ))
        start_entry = Gtk.Entry(text=start_dt.strftime('%d.%m.%Y %H:%M'))
        box.append(start_entry)

        box.append(Gtk.Label(
            label="Ende (DD.MM.YYYY HH:MM):", halign=Gtk.Align.START
        ))
        end_entry = Gtk.Entry(text=end_dt.strftime('%d.%m.%Y %H:%M'))
        box.append(end_entry)

        box.append(Gtk.Label(label="Notiz:", halign=Gtk.Align.START))
        note_entry = Gtk.Entry(text=entry.get('note', ''))
        box.append(note_entry)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("save", "Speichern")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "save":
                try:
                    new_start = datetime.strptime(
                        start_entry.get_text().strip(), '%d.%m.%Y %H:%M'
                    ).isoformat()
                    new_end = datetime.strptime(
                        end_entry.get_text().strip(), '%d.%m.%Y %H:%M'
                    ).isoformat()
                except ValueError:
                    return
                TimeEntryRepository.update(
                    entry['id'],
                    start_time=new_start,
                    end_time=new_end,
                    note=note_entry.get_text().strip()
                )
                self._refresh_entries()
                self._refresh_stats()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_delete_entry(self, btn, entry):
        dialog = Adw.MessageDialog(transient_for=self)
        dialog.set_heading("Eintrag löschen?")

        start_dt = datetime.fromisoformat(entry['start_time'])
        dialog.set_body(
            f"{entry['project_name']} – "
            f"{start_dt.strftime('%d.%m.%Y %H:%M')}"
        )

        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("delete", "Löschen")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response):
            if response == "delete":
                TimeEntryRepository.delete(entry['id'])
                self._refresh_entries()
                self._refresh_stats()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_export_excel(self, action, param):
        dialog = Gtk.FileDialog()
        month_str = (
            f"{self.current_month.year}-{self.current_month.month:02d}"
        )
        dialog.set_initial_name(f"timeworm_{month_str}.xlsx")

        def on_save(d, result):
            try:
                file = d.save_finish(result)
                if file:
                    from .export.exporter import export_excel
                    start, end = self._get_month_range()
                    export_excel(file.get_path(), start, end)
            except Exception:
                pass

        dialog.save(self, None, on_save)

    def _on_export_csv(self, action, param):
        dialog = Gtk.FileDialog()
        month_str = (
            f"{self.current_month.year}-{self.current_month.month:02d}"
        )
        dialog.set_initial_name(f"timeworm_{month_str}.csv")

        def on_save(d, result):
            try:
                file = d.save_finish(result)
                if file:
                    from .export.exporter import export_csv
                    start, end = self._get_month_range()
                    export_csv(file.get_path(), start, end)
            except Exception:
                pass

        dialog.save(self, None, on_save)

    def _on_export_pdf(self, action, param):
        dialog = Gtk.FileDialog()
        month_str = (
            f"{self.current_month.year}-{self.current_month.month:02d}"
        )
        dialog.set_initial_name(f"timeworm_{month_str}.pdf")

        def on_save(d, result):
            try:
                file = d.save_finish(result)
                if file:
                    from .export.exporter import export_pdf
                    start, end = self._get_month_range()
                    export_pdf(file.get_path(), start, end)
            except Exception:
                pass

        dialog.save(self, None, on_save)


def main():
    app = TimeWormApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
