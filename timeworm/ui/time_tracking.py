import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk, Gio
from datetime import datetime, timedelta
from ..repository import CustomerRepository, ProjectRepository, TimeEntryRepository, quantize_hours

MONTH_NAMES = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]
WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _format_duration(hours):
    if hours is None or hours < 0:
        return "0min"
    h = int(hours)
    m = int((hours - h) * 60)
    if h > 0:
        return f"{h}h {m:02d}min"
    return f"{m}min"


def _format_amount(hours, rate):
    if hours is None:
        return "0,00\u2009€"
    amount = hours * rate
    return f"{amount:,.2f}\u2009€".replace(",", "X").replace(".", ",").replace("X", ".")


def _parse_time(time_str):
    """Parse HH:MM to (hour, minute)."""
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1])


class TimeTrackingView(Gtk.Box):
    """Main time tracking view with day list and detail panel."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._timer_id = None
        self._selected_entry_id = None
        self._ignore_detail_changes = False
        self._build_ui()
        self._load_month()
        self._check_running_timer()

    def _build_ui(self):
        # Top toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)

        add_btn = Gtk.Button(label="+ Eintrag")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_entry)
        toolbar.append(add_btn)

        self._timer_btn = Gtk.Button(label="▶ Start")
        self._timer_btn.connect("clicked", self._on_timer_toggle)
        toolbar.append(self._timer_btn)

        self._timer_label = Gtk.Label(label="")
        self._timer_label.set_hexpand(True)
        self._timer_label.set_halign(Gtk.Align.START)
        self._timer_label.set_margin_start(8)
        self._timer_label.add_css_class("caption")
        toolbar.append(self._timer_label)

        self.append(toolbar)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Paned: left = day list, right = detail panel
        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_vexpand(True)
        self._paned.set_shrink_start_child(False)
        self._paned.set_shrink_end_child(False)
        self.append(self._paned)

        # LEFT SIDE: month nav + day list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left_box.set_size_request(380, -1)

        # Month navigation
        month_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        month_bar.set_margin_start(8)
        month_bar.set_margin_end(8)
        month_bar.set_margin_top(4)
        month_bar.set_margin_bottom(4)
        month_bar.set_halign(Gtk.Align.CENTER)

        prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        prev_btn.set_has_frame(False)
        prev_btn.connect("clicked", self._on_prev_month)
        month_bar.append(prev_btn)

        now = datetime.now()
        self._current_year = now.year
        self._current_month = now.month
        self._month_label = Gtk.Label()
        self._month_label.add_css_class("title-4")
        self._month_label.set_size_request(160, -1)
        month_bar.append(self._month_label)

        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.set_has_frame(False)
        next_btn.connect("clicked", self._on_next_month)
        month_bar.append(next_btn)

        left_box.append(month_bar)

        # Scrollable day list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._day_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(self._day_list_box)
        left_box.append(scroll)

        self._paned.set_start_child(left_box)

        # RIGHT SIDE: detail panel
        self._detail_panel = self._build_detail_panel()
        self._paned.set_end_child(self._detail_panel)
        self._paned.set_position(420)

    def _build_detail_panel(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_size_request(300, -1)

        # Placeholder when nothing selected
        self._placeholder = Gtk.Label(label="Eintrag auswählen")
        self._placeholder.set_vexpand(True)
        self._placeholder.add_css_class("dim-label")
        self._placeholder.add_css_class("title-3")
        outer.append(self._placeholder)

        # Detail form (hidden initially)
        self._detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._detail_box.set_margin_start(12)
        self._detail_box.set_margin_end(12)
        self._detail_box.set_margin_top(8)
        self._detail_box.set_margin_bottom(8)
        self._detail_box.set_visible(False)
        outer.append(self._detail_box)

        # Action buttons at top
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_bar.set_halign(Gtk.Align.END)

        save_btn = Gtk.Button(label="Speichern")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_detail)
        action_bar.append(save_btn)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", self._on_delete_detail)
        action_bar.append(del_btn)
        self._detail_box.append(action_bar)

        # Description
        self._detail_box.append(Gtk.Label(label="Beschreibung", xalign=0))
        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("Kurzbeschreibung...")
        self._detail_box.append(self._desc_entry)

        # Note
        self._detail_box.append(Gtk.Label(label="Notizen", xalign=0))
        self._note_view = Gtk.TextView()
        self._note_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self._note_view.set_size_request(-1, 80)
        note_frame = Gtk.Frame()
        note_frame.set_child(self._note_view)
        self._detail_box.append(note_frame)

        # Customer dropdown
        self._detail_box.append(Gtk.Label(label="Kunde", xalign=0))
        self._customer_dropdown = Gtk.DropDown()
        self._customer_model = Gtk.StringList()
        self._customer_dropdown.set_model(self._customer_model)
        self._customer_dropdown.connect("notify::selected", self._on_customer_changed)
        self._customer_ids = []
        self._detail_box.append(self._customer_dropdown)

        # Project dropdown
        self._detail_box.append(Gtk.Label(label="Projekt", xalign=0))
        self._project_dropdown = Gtk.DropDown()
        self._project_model = Gtk.StringList()
        self._project_dropdown.set_model(self._project_model)
        self._project_ids = []
        self._detail_box.append(self._project_dropdown)

        # Date
        self._detail_box.append(Gtk.Label(label="Datum", xalign=0))
        self._date_entry = Gtk.Entry()
        self._date_entry.set_placeholder_text("TT.MM.JJJJ")
        self._detail_box.append(self._date_entry)

        # Start / End in a row
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        start_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        start_box.append(Gtk.Label(label="Start", xalign=0))
        self._start_entry = Gtk.Entry()
        self._start_entry.set_placeholder_text("HH:MM")
        self._start_entry.set_max_width_chars(6)
        self._start_entry.connect("changed", self._on_time_changed)
        start_box.append(self._start_entry)
        start_box.set_hexpand(True)
        time_box.append(start_box)

        end_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        end_box.append(Gtk.Label(label="Ende", xalign=0))
        self._end_entry = Gtk.Entry()
        self._end_entry.set_placeholder_text("HH:MM")
        self._end_entry.set_max_width_chars(6)
        self._end_entry.connect("changed", self._on_time_changed)
        end_box.append(self._end_entry)
        end_box.set_hexpand(True)
        time_box.append(end_box)

        self._detail_box.append(time_box)

        # Duration + Amount (read-only)
        calc_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        calc_box.set_margin_top(8)

        dur_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        dur_box.append(Gtk.Label(label="Dauer", xalign=0))
        self._duration_label = Gtk.Label(label="—", xalign=0)
        self._duration_label.add_css_class("title-4")
        dur_box.append(self._duration_label)
        dur_box.set_hexpand(True)
        calc_box.append(dur_box)

        amt_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        amt_box.append(Gtk.Label(label="Betrag", xalign=0))
        self._amount_label = Gtk.Label(label="—", xalign=0)
        self._amount_label.add_css_class("title-4")
        amt_box.append(self._amount_label)
        amt_box.set_hexpand(True)
        calc_box.append(amt_box)

        self._detail_box.append(calc_box)

        return outer

    # --- Month navigation ---
    def _update_month_label(self):
        self._month_label.set_text(f"{MONTH_NAMES[self._current_month]} {self._current_year}")

    def _on_prev_month(self, _btn):
        self._current_month -= 1
        if self._current_month < 1:
            self._current_month = 12
            self._current_year -= 1
        self._load_month()

    def _on_next_month(self, _btn):
        self._current_month += 1
        if self._current_month > 12:
            self._current_month = 1
            self._current_year += 1
        self._load_month()

    def _load_month(self):
        self._update_month_label()
        y, m = self._current_year, self._current_month
        start = f"{y:04d}-{m:02d}-01T00:00:00"
        if m == 12:
            end = f"{y + 1:04d}-01-01T00:00:00"
        else:
            end = f"{y:04d}-{m + 1:02d}-01T00:00:00"

        grouped = TimeEntryRepository.get_entries_grouped_by_day(start, end)

        # Clear old
        child = self._day_list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._day_list_box.remove(child)
            child = next_child

        if not grouped:
            lbl = Gtk.Label(label="Keine Einträge in diesem Monat")
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(40)
            self._day_list_box.append(lbl)
            return

        today_str = datetime.now().strftime('%Y-%m-%d')

        for day_key in sorted(grouped.keys(), reverse=True):
            entries = grouped[day_key]
            self._add_day_expander(day_key, entries, expanded=(day_key == today_str))

    def _add_day_expander(self, day_key, entries, expanded=False):
        dt = datetime.fromisoformat(day_key)
        weekday = WEEKDAY_NAMES[dt.weekday()]
        date_str = dt.strftime('%d.%m.%Y')

        total_hours = 0
        total_amount = 0
        for e in entries:
            if e['end_time']:
                st = datetime.fromisoformat(e['start_time'])
                et = datetime.fromisoformat(e['end_time'])
                raw_h = (et - st).total_seconds() / 3600
                q = e.get('time_quantum', 0.25) or 0.25
                h = quantize_hours(raw_h, q)
                total_hours += h
                total_amount += h * (e['hourly_rate'] or 0)

        # Header label
        header_text = f"{weekday}, {date_str}"
        summary_text = _format_duration(total_hours) + "  " + _format_amount(total_hours, total_amount / total_hours if total_hours > 0 else 0)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.set_hexpand(True)
        header_box.add_css_class("day-header")
        day_lbl = Gtk.Label(label=header_text, xalign=0)
        day_lbl.set_hexpand(True)
        day_lbl.add_css_class("heading")
        header_box.append(day_lbl)

        amount_str = f"{total_amount:,.2f}\u2009€".replace(",", "X").replace(".", ",").replace("X", ".")
        sum_lbl = Gtk.Label(label=f"{_format_duration(total_hours)}   {amount_str}")
        sum_lbl.add_css_class("caption")
        header_box.append(sum_lbl)

        # Build expander with custom title
        expander = Gtk.Expander()
        expander.set_label_widget(header_box)
        expander.set_expanded(expanded)
        expander.set_margin_start(4)
        expander.set_margin_end(4)
        expander.set_margin_top(10)
        expander.set_margin_bottom(2)

        # Entry rows inside
        entries_box = Gtk.ListBox()
        entries_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        entries_box.add_css_class("boxed-list")
        entries_box.add_css_class("day-entries")
        entries_box.connect("row-selected", self._on_entry_selected)

        for entry in entries:
            row = self._create_entry_row(entry)
            entries_box.append(row)

        expander.set_child(entries_box)
        self._day_list_box.append(expander)

    def _create_entry_row(self, entry):
        row = Gtk.ListBoxRow()
        row._entry_id = entry['id']
        row._entry_data = entry

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(8)

        # Color bar
        color_bar = Gtk.DrawingArea()
        color_bar.set_size_request(4, 36)
        color_str = entry.get('color', '#3584e4')
        color_bar.set_draw_func(self._draw_color_bar, color_str)
        box.append(color_bar)

        # Info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        project_label = Gtk.Label(xalign=0)
        desc = entry.get('description', '') or ''
        if desc:
            project_label.set_text(f"{entry['project_name']} — {desc}")
        else:
            project_label.set_text(f"{entry['project_name']} ({entry['customer_name']})")
        info_box.append(project_label)

        if entry['end_time']:
            st = datetime.fromisoformat(entry['start_time'])
            et = datetime.fromisoformat(entry['end_time'])
            raw_hours = (et - st).total_seconds() / 3600
            q = entry.get('time_quantum', 0.25) or 0.25
            hours = quantize_hours(raw_hours, q)
            time_str = f"{st.strftime('%H:%M')} – {et.strftime('%H:%M')}"
            sub_lbl = Gtk.Label(label=time_str, xalign=0)
            sub_lbl.add_css_class("dim-label")
            sub_lbl.add_css_class("caption")
            info_box.append(sub_lbl)
        else:
            hours = 0
        box.append(info_box)

        # Duration (quantized)
        dur_lbl = Gtk.Label(label=_format_duration(hours))
        dur_lbl.add_css_class("caption")
        box.append(dur_lbl)

        row.set_child(box)

        # Context menu
        self._setup_context_menu(row, entry)

        return row

    def _draw_color_bar(self, area, cr, width, height, color_str):
        from gi.repository import Gdk as _Gdk
        rgba = _Gdk.RGBA()
        rgba.parse(color_str)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.rectangle(0, 0, width, height)
        cr.fill()

    def _setup_context_menu(self, row, entry):
        menu = Gio.Menu()
        menu.append("Bearbeiten", f"entry.edit-{entry['id']}")
        menu.append("Löschen", f"entry.delete-{entry['id']}")
        menu.append("Duplizieren", f"entry.duplicate-{entry['id']}")
        menu.append("Fortsetzen", f"entry.resume-{entry['id']}")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)

        # Right-click gesture
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_right_click, popover, row)
        row.add_controller(gesture)

        # Register actions
        group = Gio.SimpleActionGroup()
        action_edit = Gio.SimpleAction(name=f"edit-{entry['id']}")
        action_edit.connect("activate", lambda a, p: self._select_entry(entry))
        group.add_action(action_edit)

        action_delete = Gio.SimpleAction(name=f"delete-{entry['id']}")
        action_delete.connect("activate", lambda a, p: self._confirm_delete(entry['id']))
        group.add_action(action_delete)

        action_dup = Gio.SimpleAction(name=f"duplicate-{entry['id']}")
        action_dup.connect("activate", lambda a, p: self._duplicate_entry(entry['id']))
        group.add_action(action_dup)

        action_resume = Gio.SimpleAction(name=f"resume-{entry['id']}")
        action_resume.connect("activate", lambda a, p: self._resume_entry(entry))
        group.add_action(action_resume)

        row.insert_action_group("entry", group)

    def _on_right_click(self, gesture, n_press, x, y, popover, row):
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.popup()

    # --- Entry selection ---
    def _on_entry_selected(self, listbox, row):
        if row is None:
            return
        entry = row._entry_data
        self._select_entry(entry)

    def _select_entry(self, entry):
        self._selected_entry_id = entry['id']
        self._placeholder.set_visible(False)
        self._detail_box.set_visible(True)
        self._populate_detail(entry)

    def _populate_detail(self, entry):
        self._ignore_detail_changes = True

        self._desc_entry.set_text(entry.get('description', '') or '')
        buf = self._note_view.get_buffer()
        buf.set_text(entry.get('note', '') or '')

        # Populate customer dropdown
        customers = CustomerRepository.get_all()
        self._customer_ids = [c['id'] for c in customers]
        while self._customer_model.get_n_items() > 0:
            self._customer_model.remove(0)
        for c in customers:
            self._customer_model.append(c['name'])

        # Select current customer
        cust_id = entry.get('customer_id')
        if cust_id in self._customer_ids:
            self._customer_dropdown.set_selected(self._customer_ids.index(cust_id))

        # Populate project dropdown for this customer
        self._refresh_project_dropdown(cust_id, entry.get('project_id'))

        # Date + times
        st = datetime.fromisoformat(entry['start_time'])
        self._date_entry.set_text(st.strftime('%d.%m.%Y'))
        self._start_entry.set_text(st.strftime('%H:%M'))

        if entry['end_time']:
            et = datetime.fromisoformat(entry['end_time'])
            self._end_entry.set_text(et.strftime('%H:%M'))
        else:
            self._end_entry.set_text("")

        self._ignore_detail_changes = False
        self._update_calculated_fields()

    def _refresh_project_dropdown(self, customer_id, select_project_id=None):
        projects = ProjectRepository.get_by_customer(customer_id) if customer_id else ProjectRepository.get_all()
        self._project_ids = [p['id'] for p in projects]
        while self._project_model.get_n_items() > 0:
            self._project_model.remove(0)
        for p in projects:
            self._project_model.append(p['name'])
        if select_project_id and select_project_id in self._project_ids:
            self._project_dropdown.set_selected(self._project_ids.index(select_project_id))
        elif self._project_ids:
            self._project_dropdown.set_selected(0)

    def _on_customer_changed(self, dropdown, _pspec):
        if self._ignore_detail_changes:
            return
        idx = dropdown.get_selected()
        if idx < len(self._customer_ids):
            self._refresh_project_dropdown(self._customer_ids[idx])

    def _on_time_changed(self, _entry):
        if self._ignore_detail_changes:
            return
        self._update_calculated_fields()

    def _update_calculated_fields(self):
        try:
            sh, sm = _parse_time(self._start_entry.get_text())
            eh, em = _parse_time(self._end_entry.get_text())
            raw_hours = (eh * 60 + em - sh * 60 - sm) / 60
            if raw_hours < 0:
                raw_hours += 24

            # Get hourly rate and quantum from selected project
            proj_idx = self._project_dropdown.get_selected()
            rate = 0
            quantum = 0.25
            if proj_idx != Gtk.INVALID_LIST_POSITION and proj_idx < len(self._project_ids):
                proj = ProjectRepository.get_by_id(self._project_ids[proj_idx])
                if proj:
                    rate = proj['hourly_rate']
                    quantum = proj.get('time_quantum', 0.25) or 0.25
            hours = quantize_hours(raw_hours, quantum)
            self._duration_label.set_text(_format_duration(hours))
            self._amount_label.set_text(_format_amount(hours, rate))
        except (ValueError, IndexError):
            self._duration_label.set_text("—")
            self._amount_label.set_text("—")

    # --- Detail actions ---
    def _on_save_detail(self, _btn):
        if not self._selected_entry_id:
            return

        # Parse date
        date_text = self._date_entry.get_text().strip()
        try:
            day = datetime.strptime(date_text, '%d.%m.%Y')
        except ValueError:
            return

        start_text = self._start_entry.get_text().strip()
        end_text = self._end_entry.get_text().strip()
        try:
            sh, sm = _parse_time(start_text)
            eh, em = _parse_time(end_text)
        except (ValueError, IndexError):
            return

        start_dt = day.replace(hour=sh, minute=sm, second=0)
        end_dt = day.replace(hour=eh, minute=em, second=0)
        if end_dt < start_dt:
            end_dt += timedelta(days=1)

        proj_idx = self._project_dropdown.get_selected()
        if proj_idx == Gtk.INVALID_LIST_POSITION or proj_idx >= len(self._project_ids):
            return
        project_id = self._project_ids[proj_idx]

        buf = self._note_view.get_buffer()
        note = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        TimeEntryRepository.update(
            self._selected_entry_id,
            project_id=project_id,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            note=note,
            description=self._desc_entry.get_text().strip(),
        )
        self._load_month()

    def _on_delete_detail(self, _btn):
        if self._selected_entry_id:
            self._confirm_delete(self._selected_entry_id)

    def _confirm_delete(self, entry_id):
        dialog = Adw.AlertDialog(
            heading="Eintrag löschen?",
            body="Dieser Eintrag wird unwiderruflich gelöscht.",
        )
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("delete", "Löschen")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_confirmed, entry_id)
        dialog.present(self.get_root())

    def _on_delete_confirmed(self, dialog, response, entry_id):
        if response == "delete":
            TimeEntryRepository.delete(entry_id)
            if self._selected_entry_id == entry_id:
                self._selected_entry_id = None
                self._detail_box.set_visible(False)
                self._placeholder.set_visible(True)
            self._load_month()

    def _duplicate_entry(self, entry_id):
        TimeEntryRepository.duplicate(entry_id)
        self._load_month()

    def _resume_entry(self, entry):
        TimeEntryRepository.stop_running()
        TimeEntryRepository.start(entry['project_id'], entry.get('note', ''))
        self._check_running_timer()
        self._load_month()

    # --- Manual entry ---
    def _on_add_entry(self, _btn):
        projects = ProjectRepository.get_all()
        if not projects:
            dialog = Adw.AlertDialog(
                heading="Kein Projekt vorhanden",
                body="Bitte erstelle zuerst einen Kunden und ein Projekt unter Konfiguration.",
            )
            dialog.add_response("ok", "OK")
            dialog.present(self.get_root())
            return

        now = datetime.now()
        # Round to nearest 15 min
        minute = (now.minute // 15) * 15
        start = now.replace(minute=minute, second=0, microsecond=0)
        end = start + timedelta(hours=1)

        project = projects[0]
        entry_id = TimeEntryRepository.create_manual(
            project['id'],
            start.isoformat(),
            end.isoformat(),
            note='',
            description='',
        )
        self._load_month()

        # Select the new entry
        entry = {
            'id': entry_id,
            'project_id': project['id'],
            'project_name': project['name'],
            'customer_name': project['customer_name'],
            'customer_id': project['customer_id'],
            'hourly_rate': project['hourly_rate'],
            'color': project['color'],
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'note': '',
            'description': '',
        }
        self._select_entry(entry)

    # --- Timer ---
    def _on_timer_toggle(self, _btn):
        running = TimeEntryRepository.get_running()
        if running:
            TimeEntryRepository.stop(running['id'])
            self._stop_timer_ui()
            self._load_month()
        else:
            self._show_start_timer_dialog()

    def _show_start_timer_dialog(self):
        projects = ProjectRepository.get_all()
        if not projects:
            dialog = Adw.AlertDialog(
                heading="Kein Projekt vorhanden",
                body="Bitte erstelle zuerst einen Kunden und ein Projekt unter Konfiguration.",
            )
            dialog.add_response("ok", "OK")
            dialog.present(self.get_root())
            return

        dialog = Adw.AlertDialog(
            heading="Timer starten",
            body="Projekt für den Timer auswählen:",
        )
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("start", "Starten")
        dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)

        # Dialog content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Project selection dropdown
        dropdown = Gtk.DropDown()
        model = Gtk.StringList()
        p_ids = []
        for p in projects:
            model.append(f"{p['name']} ({p['customer_name']})")
            p_ids.append(p['id'])
        dropdown.set_model(model)
        content_box.append(dropdown)

        # Description entry
        desc_entry = Gtk.Entry()
        desc_entry.set_placeholder_text("Was arbeitest du?")
        content_box.append(desc_entry)

        dialog.set_extra_child(content_box)

        dialog.connect("response", self._on_start_timer_response, dropdown, p_ids, desc_entry)
        dialog.present(self.get_root())

    def _on_start_timer_response(self, dialog, response, dropdown, p_ids, desc_entry):
        if response == "start":
            idx = dropdown.get_selected()
            if idx < len(p_ids):
                TimeEntryRepository.stop_running()
                description = desc_entry.get_text().strip()
                TimeEntryRepository.start(p_ids[idx], description=description)
                self._check_running_timer()

    def _check_running_timer(self):
        running = TimeEntryRepository.get_running()
        if running:
            self._timer_btn.set_label("⏹ Stop")
            self._start_timer_ui(running)
        else:
            self._stop_timer_ui()

    def _start_timer_ui(self, running):
        self._timer_btn.set_label("⏹ Stop")
        self._running_entry = running
        self._update_timer_display()
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add_seconds(1, self._tick_timer)

    def _stop_timer_ui(self):
        self._timer_btn.set_label("▶ Start")
        self._timer_label.set_text("")
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _tick_timer(self):
        self._update_timer_display()
        return True  # Continue ticking

    def _update_timer_display(self):
        running = TimeEntryRepository.get_running()
        if not running:
            self._stop_timer_ui()
            return
        start = datetime.fromisoformat(running['start_time'])
        elapsed = datetime.now() - start
        total_secs = int(elapsed.total_seconds())
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        self._timer_label.set_text(f"{running['project_name']} ⏱ {h:02d}:{m:02d}:{s:02d}")

    def refresh(self):
        self._load_month()
        self._check_running_timer()
