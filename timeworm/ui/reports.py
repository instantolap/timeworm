import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk
from datetime import datetime
from ..repository import TimeEntryRepository, ProjectRepository

MONTH_NAMES = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]


def _format_amount(amount):
    return f"{amount:,.2f}\u2009€".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_hours(hours):
    if hours is None:
        return "0,0h"
    return f"{hours:,.1f}h".replace(".", ",")


class ReportsView(Gtk.Box):
    """Monthly reports with customer/project summary and export."""

    def __init__(self, get_window_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._get_window = get_window_fn
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

        for label, fmt in [("Excel", "xlsx"), ("CSV", "csv"), ("PDF", "pdf")]:
            btn = Gtk.Button(label=f"{label} exportieren")
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

    def _load_report(self):
        self._month_label.set_text(f"{MONTH_NAMES[self._current_month]} {self._current_year}")

        # Clear
        child = self._report_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._report_box.remove(child)
            child = nxt

        start, end = self._get_date_range()
        customer_summary = TimeEntryRepository.get_summary_by_customer(start, end)
        project_summary = TimeEntryRepository.get_summary(start, end)

        if not customer_summary:
            lbl = Gtk.Label(label="Keine Einträge in diesem Monat")
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(40)
            self._report_box.append(lbl)
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

        for cust in customer_summary:
            cname = cust['customer_name']
            chours = cust['total_hours'] or 0
            camount = cust['total_amount'] or 0
            grand_hours += chours
            grand_amount += camount

            # Customer header row
            cust_row = Adw.ActionRow(title=cname, subtitle=f"{_format_hours(chours)}   {_format_amount(camount)}")
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
                pamount = phours * rate
                prow = Adw.ActionRow(
                    title=f"    {proj['project_name']}",
                    subtitle=f"    {_format_hours(phours)} × {rate:,.2f}\u2009€/h = {_format_amount(pamount)}   ({proj['entry_count']} Einträge)"
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

        # Grand total
        total_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        total_box.set_margin_top(12)
        total_lbl = Gtk.Label(label="GESAMT", xalign=0)
        total_lbl.add_css_class("title-3")
        total_lbl.set_hexpand(True)
        total_box.append(total_lbl)
        total_val = Gtk.Label(label=f"{_format_hours(grand_hours)}   {_format_amount(grand_amount)}")
        total_val.add_css_class("title-3")
        total_box.append(total_val)
        self._report_box.append(total_box)

    def _draw_dot(self, area, cr, width, height, color_str):
        rgba = Gdk.RGBA()
        rgba.parse(color_str)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 3.14159 * 2)
        cr.fill()

    def _on_export(self, _btn, fmt):
        start, end = self._get_date_range()

        dialog = Gtk.FileDialog()
        month_str = f"{self._current_year}-{self._current_month:02d}"
        if fmt == "xlsx":
            dialog.set_initial_name(f"timeworm-{month_str}.xlsx")
        elif fmt == "csv":
            dialog.set_initial_name(f"timeworm-{month_str}.csv")
        else:
            dialog.set_initial_name(f"timeworm-{month_str}.pdf")

        dialog.save(self.get_root(), None, self._on_export_file_chosen, fmt, start, end)

    def _on_export_file_chosen(self, dialog, result, fmt, start, end):
        try:
            gfile = dialog.save_finish(result)
            filepath = gfile.get_path()
        except Exception:
            return

        from ..export.exporter import export_csv, export_excel, export_pdf
        if fmt == "xlsx":
            export_excel(filepath, start, end)
        elif fmt == "csv":
            export_csv(filepath, start, end)
        else:
            export_pdf(filepath, start, end)

        toast = Adw.Toast(title=f"Export gespeichert: {filepath}")
        window = self.get_root()
        if hasattr(window, '_toast_overlay'):
            window._toast_overlay.add_toast(toast)

    def refresh(self):
        self._load_report()
