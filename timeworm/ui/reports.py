import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio
from datetime import datetime
from ..repository import TimeEntryRepository, ProjectRepository, CustomerRepository, SettingsRepository
from ..i18n import _
from ..formatting import format_currency, format_hours, format_decimal, format_date, format_rate

MONTH_NAMES = [
    "", _("Januar"), _("Februar"), _("März"), _("April"), _("Mai"), _("Juni"),
    _("Juli"), _("August"), _("September"), _("Oktober"), _("November"), _("Dezember")
]


def _format_amount(amount):
    return format_currency(amount)


def _format_hours(hours):
    if hours is None:
        return format_hours(0)
    return format_hours(hours)


class ReportsView(Gtk.Box):
    """Monthly reports with customer/project summary and export."""

    def __init__(self, get_window_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._get_window = get_window_fn
        self._ignore_filter_change = False
        now = datetime.now()
        self._current_year = now.year
        self._current_month = now.month
        self._build_ui()
        self._load_report()

    def _build_ui(self):
        # Month navigation
        month_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        month_bar.set_margin_start(8)
        month_bar.set_margin_end(8)
        month_bar.set_margin_top(8)
        month_bar.set_margin_bottom(4)
        month_bar.set_halign(Gtk.Align.CENTER)

        prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        prev_btn.set_has_frame(False)
        prev_btn.connect("clicked", self._on_prev_month)
        month_bar.append(prev_btn)

        self._month_label = Gtk.Label()
        self._month_label.add_css_class("title-4")
        self._month_label.set_size_request(160, -1)
        month_bar.append(self._month_label)

        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.set_has_frame(False)
        next_btn.connect("clicked", self._on_next_month)
        month_bar.append(next_btn)

        self.append(month_bar)

        # Customer filter
        filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_bar.set_margin_start(12)
        filter_bar.set_margin_end(12)
        filter_bar.set_margin_top(4)
        filter_bar.set_margin_bottom(4)
        filter_bar.append(Gtk.Label(label=_("Kunde:")))
        self._cust_filter = Gtk.DropDown()
        self._cust_filter_model = Gtk.StringList()
        self._cust_filter.set_model(self._cust_filter_model)
        self._cust_filter.connect("notify::selected", self._on_cust_filter_changed)
        self._cust_filter_ids = []
        filter_bar.append(self._cust_filter)
        self.append(filter_bar)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Scrollable report content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._report_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._report_box.set_margin_start(12)
        self._report_box.set_margin_end(12)
        self._report_box.set_margin_top(8)
        self._report_box.set_margin_bottom(8)
        scroll.set_child(self._report_box)
        self.append(scroll)

        # Export buttons at bottom
        export_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        export_bar.set_margin_start(12)
        export_bar.set_margin_end(12)
        export_bar.set_margin_top(4)
        export_bar.set_margin_bottom(8)
        export_bar.set_halign(Gtk.Align.END)

        export_bar.append(Gtk.Label(label=_("Monate:")))
        self._months_spin = Gtk.SpinButton()
        self._months_spin.set_range(1, 3)
        self._months_spin.set_increments(1, 1)
        self._months_spin.set_value(1)
        self._months_spin.set_digits(0)
        self._months_spin.set_size_request(50, -1)
        export_bar.append(self._months_spin)

        for label, fmt in [(_("Excel exportieren"), "xlsx"), (_("CSV exportieren"), "csv"), (_("PDF exportieren"), "pdf")]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", self._on_export, fmt)
            export_bar.append(btn)

        self.append(export_bar)

    def _on_prev_month(self, _btn):
        self._current_month -= 1
        if self._current_month < 1:
            self._current_month = 12
            self._current_year -= 1
        self._load_report()

    def _on_next_month(self, _btn):
        self._current_month += 1
        if self._current_month > 12:
            self._current_month = 1
            self._current_year += 1
        self._load_report()

    def _get_date_range(self):
        y, m = self._current_year, self._current_month
        start = f"{y:04d}-{m:02d}-01T00:00:00"
        if m == 12:
            end = f"{y + 1:04d}-01-01T00:00:00"
        else:
            end = f"{y:04d}-{m + 1:02d}-01T00:00:00"
        return start, end

    def _update_cust_filter(self):
        self._ignore_filter_change = True
        customers = CustomerRepository.get_all()
        prev_idx = self._cust_filter.get_selected()
        self._cust_filter_ids = [None] + [c['id'] for c in customers]
        while self._cust_filter_model.get_n_items() > 0:
            self._cust_filter_model.remove(0)
        self._cust_filter_model.append(_("Alle Kunden"))
        for c in customers:
            self._cust_filter_model.append(c['name'])
        if prev_idx < len(self._cust_filter_ids):
            self._cust_filter.set_selected(prev_idx)
        self._ignore_filter_change = False

    def _on_cust_filter_changed(self, dropdown, _pspec):
        if not self._ignore_filter_change:
            self._load_report(update_filter=False)

    def _get_selected_customer_id(self):
        idx = self._cust_filter.get_selected()
        if idx < len(self._cust_filter_ids):
            return self._cust_filter_ids[idx]
        return None

    def _load_report(self, update_filter=True):
        if getattr(self, '_loading', False):
            return
        self._loading = True
        self._month_label.set_text(f"{MONTH_NAMES[self._current_month]} {self._current_year}")
        if update_filter:
            self._update_cust_filter()

        # Clear
        child = self._report_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._report_box.remove(child)
            child = nxt

        start, end = self._get_date_range()
        customer_id = self._get_selected_customer_id()
        customer_summary = TimeEntryRepository.get_summary_by_customer(start, end, customer_id=customer_id)
        project_summary = TimeEntryRepository.get_summary(start, end, customer_id=customer_id)

        if not customer_summary:
            lbl = Gtk.Label(label=_("Keine Einträge in diesem Monat"))
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(40)
            self._report_box.append(lbl)
            self._loading = False
            return

        grand_hours = 0
        grand_amount = 0

        # Group projects by customer
        projects_by_customer = {}
        for p in project_summary:
            cname = p['customer_name']
            projects_by_customer.setdefault(cname, []).append(p)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")

        currency_totals = {}  # {currency: {'hours': 0, 'amount': 0}}

        for cust in customer_summary:
            cname = cust['customer_name']
            chours = cust['total_hours'] or 0
            grand_hours += chours

            # Group customer amounts by currency
            cust_currency_amounts = {}
            for proj in projects_by_customer.get(cname, []):
                cur = proj.get('currency', '€')
                phours = proj['total_hours'] or 0
                rate = proj['hourly_rate'] or 0
                pamount = phours * rate
                cust_currency_amounts.setdefault(cur, 0)
                cust_currency_amounts[cur] += pamount
                currency_totals.setdefault(cur, {'hours': 0, 'amount': 0})
                currency_totals[cur]['hours'] += phours
                currency_totals[cur]['amount'] += pamount

            # Format customer subtitle with currency-aware amounts
            cust_amounts_str = "  ".join(format_currency(amt, cur) for cur, amt in cust_currency_amounts.items())
            camount_str = f"{_format_hours(chours)}   {cust_amounts_str}" if cust_currency_amounts else _format_hours(chours)

            # Customer header row
            cust_row = Adw.ActionRow(title=cname, subtitle=camount_str)
            cust_row.add_css_class("title-4")

            # Color indicator
            color_dot = Gtk.DrawingArea()
            color_dot.set_size_request(12, 12)
            color_dot.set_valign(Gtk.Align.CENTER)
            color_str = cust.get('color', '#3584e4')
            color_dot.set_draw_func(self._draw_dot, color_str)
            cust_row.add_prefix(color_dot)

            list_box.append(cust_row)

            # Project rows under this customer
            for proj in projects_by_customer.get(cname, []):
                phours = proj['total_hours'] or 0
                rate = proj['hourly_rate'] or 0
                cur = proj.get('currency', '€')
                pamount = phours * rate
                prow = Adw.ActionRow(
                    title=f"    {proj['project_name']}",
                    subtitle=f"    {_format_hours(phours)} × {format_rate(rate, cur)} = {format_currency(pamount, cur)}   ({proj['entry_count']} {_('Einträge')})"
                )
                list_box.append(prow)

                # Progress bar
                if grand_hours > 0:
                    bar = Gtk.ProgressBar()
                    bar.set_fraction(phours / max(grand_hours, 1))
                    bar.set_margin_start(24)
                    bar.set_margin_end(24)
                    bar.set_margin_top(2)
                    bar.set_margin_bottom(4)
                    bar_row = Gtk.ListBoxRow(selectable=False)
                    bar_row.set_child(bar)
                    list_box.append(bar_row)

        self._report_box.append(list_box)

        # Grand total - one line per currency
        total_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        total_box.set_margin_top(12)

        for cur, totals in currency_totals.items():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl_text = _("GESAMT") if len(currency_totals) == 1 else f"{_('GESAMT')} {cur}"
            total_lbl = Gtk.Label(label=lbl_text, xalign=0)
            total_lbl.add_css_class("title-3")
            total_lbl.set_hexpand(True)
            row.append(total_lbl)
            total_val = Gtk.Label(label=f"{_format_hours(totals['hours'])}   {format_currency(totals['amount'], cur)}")
            total_val.add_css_class("title-3")
            row.append(total_val)
            total_box.append(row)

        self._report_box.append(total_box)
        self._loading = False

    def _draw_dot(self, area, cr, width, height, color_str):
        rgba = Gdk.RGBA()
        rgba.parse(color_str)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 3.14159 * 2)
        cr.fill()

    def _get_export_date_range(self):
        """Return (start, end) spanning `_months_spin` months back from current month."""
        n_months = int(self._months_spin.get_value())
        y, m = self._current_year, self._current_month
        # start = first day of (current month - (n_months - 1))
        start_m = m - (n_months - 1)
        start_y = y
        while start_m < 1:
            start_m += 12
            start_y -= 1
        start = f"{start_y:04d}-{start_m:02d}-01T00:00:00"
        # end = first day of next month after current
        if m == 12:
            end = f"{y + 1:04d}-01-01T00:00:00"
        else:
            end = f"{y:04d}-{m + 1:02d}-01T00:00:00"
        return start, end

    def _on_export(self, _btn, fmt):
        import re
        start, end = self._get_export_date_range()
        customer_id = self._get_selected_customer_id()
        n_months = int(self._months_spin.get_value())

        dialog = Gtk.FileDialog()
        if n_months > 1:
            # start month to current month range
            start_y, start_m = int(start[:4]), int(start[5:7])
            month_str = f"{start_y}-{start_m:02d}_{self._current_year}-{self._current_month:02d}"
        else:
            month_str = f"{self._current_year}-{self._current_month:02d}"
        if customer_id is not None:
            idx = self._cust_filter.get_selected()
            raw_name = self._cust_filter_model.get_string(idx) or "kunde"
            safe_name = re.sub(r'[^\w\-]', '_', raw_name).strip('_').lower()
            base = f"{safe_name}-{month_str}"
        else:
            base = f"timeworm-{month_str}"
        if fmt == "xlsx":
            dialog.set_initial_name(f"{base}.xlsx")
        elif fmt == "csv":
            dialog.set_initial_name(f"{base}.csv")
        else:
            dialog.set_initial_name(f"{base}.pdf")

        # Restore last export folder
        last_folder = SettingsRepository.get("export_folder")
        if last_folder:
            dialog.set_initial_folder(Gio.File.new_for_path(last_folder))

        dialog.save(self.get_root(), None, self._on_export_file_chosen, fmt, start, end, customer_id)

    def _on_export_file_chosen(self, dialog, result, fmt, start, end, customer_id):
        try:
            gfile = dialog.save_finish(result)
            filepath = gfile.get_path()
        except Exception:
            return

        # Remember export folder
        import os
        SettingsRepository.set("export_folder", os.path.dirname(filepath))

        from ..export.exporter import export_csv, export_excel, export_pdf
        if fmt == "xlsx":
            export_excel(filepath, start, end, customer_id=customer_id)
        elif fmt == "csv":
            export_csv(filepath, start, end, customer_id=customer_id)
        else:
            export_pdf(filepath, start, end, customer_id=customer_id)

        toast = Adw.Toast(title=_("Export gespeichert: {}").format(filepath))
        window = self.get_root()
        if hasattr(window, '_toast_overlay'):
            window._toast_overlay.add_toast(toast)

    def refresh(self):
        self._load_report()
