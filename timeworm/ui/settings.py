import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk
from ..repository import CustomerRepository, ProjectRepository
from ..i18n import _


class SettingsView(Gtk.Box):
    """Configuration view for managing customers and projects."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._build_ui()
        self._load_customers()

    def _build_ui(self):
        # Use a vertical split: customers on top, projects below
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self._stack)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(8)
        switcher.set_margin_bottom(4)
        self.append(switcher)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        self._stack.set_vexpand(True)
        self.append(self._stack)

        # --- Customer tab ---
        cust_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cust_page.set_margin_start(12)
        cust_page.set_margin_end(12)
        cust_page.set_margin_top(8)

        cust_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cust_toolbar.set_margin_bottom(8)
        cust_title = Gtk.Label(label=_("Kunden"))
        cust_title.add_css_class("title-3")
        cust_title.set_hexpand(True)
        cust_title.set_halign(Gtk.Align.START)
        cust_toolbar.append(cust_title)

        add_cust_btn = Gtk.Button(label=_("+ Neuer Kunde"))
        add_cust_btn.add_css_class("suggested-action")
        add_cust_btn.connect("clicked", self._on_add_customer)
        cust_toolbar.append(add_cust_btn)
        cust_page.append(cust_toolbar)

        cust_scroll = Gtk.ScrolledWindow()
        cust_scroll.set_vexpand(True)
        cust_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._customer_list = Gtk.ListBox()
        self._customer_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._customer_list.add_css_class("boxed-list")
        cust_scroll.set_child(self._customer_list)
        cust_page.append(cust_scroll)

        self._stack.add_titled(cust_page, "customers", "Kunden")

        # --- Project tab ---
        proj_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        proj_page.set_margin_start(12)
        proj_page.set_margin_end(12)
        proj_page.set_margin_top(8)

        proj_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        proj_toolbar.set_margin_bottom(8)

        # Customer filter dropdown
        proj_toolbar.append(Gtk.Label(label=_("Kunde:")))
        self._cust_filter = Gtk.DropDown()
        self._cust_filter_model = Gtk.StringList()
        self._cust_filter.set_model(self._cust_filter_model)
        self._cust_filter.connect("notify::selected", self._on_cust_filter_changed)
        self._cust_filter_ids = []
        proj_toolbar.append(self._cust_filter)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        proj_toolbar.append(spacer)

        add_proj_btn = Gtk.Button(label=_("+ Neues Projekt"))
        add_proj_btn.add_css_class("suggested-action")
        add_proj_btn.connect("clicked", self._on_add_project)
        proj_toolbar.append(add_proj_btn)
        proj_page.append(proj_toolbar)

        proj_scroll = Gtk.ScrolledWindow()
        proj_scroll.set_vexpand(True)
        proj_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._project_list = Gtk.ListBox()
        self._project_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._project_list.add_css_class("boxed-list")
        proj_scroll.set_child(self._project_list)
        proj_page.append(proj_scroll)

        self._stack.add_titled(proj_page, "projects", "Projekte")

    # --- Customer CRUD ---
    def _load_customers(self):
        customers = CustomerRepository.get_all(active_only=False)

        # Clear list
        child = self._customer_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._customer_list.remove(child)
            child = nxt

        for cust in customers:
            row = Adw.ActionRow(title=cust['name'])
            if not cust['active']:
                row.set_subtitle("(deaktiviert)")
                row.add_css_class("dim-label")

            # Color indicator
            color_dot = Gtk.DrawingArea()
            color_dot.set_size_request(16, 16)
            color_dot.set_valign(Gtk.Align.CENTER)
            color_dot.set_draw_func(self._draw_dot, cust.get('color', '#3584e4'))
            row.add_prefix(color_dot)

            # Edit button
            edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
            edit_btn.set_valign(Gtk.Align.CENTER)
            edit_btn.set_has_frame(False)
            edit_btn.connect("clicked", self._on_edit_customer, cust)
            row.add_suffix(edit_btn)

            # Toggle active button
            if cust['active']:
                del_btn = Gtk.Button(icon_name="user-trash-symbolic")
                del_btn.set_valign(Gtk.Align.CENTER)
                del_btn.set_has_frame(False)
                del_btn.add_css_class("error")
                del_btn.set_tooltip_text(_("Deaktivieren"))
                del_btn.connect("clicked", self._on_deactivate_customer, cust['id'])
                row.add_suffix(del_btn)
            else:
                act_btn = Gtk.Button(icon_name="view-reveal-symbolic")
                act_btn.set_valign(Gtk.Align.CENTER)
                act_btn.set_has_frame(False)
                act_btn.set_tooltip_text(_("Aktivieren"))
                act_btn.connect("clicked", self._on_activate_customer, cust['id'])
                row.add_suffix(act_btn)

            self._customer_list.append(row)

        # Update customer filter in projects tab
        self._update_cust_filter()

    def _draw_dot(self, area, cr, width, height, color_str):
        rgba = Gdk.RGBA()
        rgba.parse(color_str)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 3.14159 * 2)
        cr.fill()

    def _on_add_customer(self, _btn):
        dialog = Adw.AlertDialog(
            heading=_("Neuer Kunde"),
            body=_("Name und Farbe für den neuen Kunden:"),
        )
        dialog.add_response("cancel", _("Abbrechen"))
        dialog.add_response("create", _("Erstellen"))
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text(_("Kundenname"))
        box.append(name_entry)

        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        color_box.append(Gtk.Label(label=_("Farbe:")))
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        rgba.parse("#3584e4")
        color_btn.set_rgba(rgba)
        color_box.append(color_btn)
        box.append(color_box)

        dialog.set_extra_child(box)
        dialog.connect("response", self._on_create_customer, name_entry, color_btn)
        dialog.present(self.get_root())

    def _on_create_customer(self, dialog, response, name_entry, color_btn):
        if response == "create":
            name = name_entry.get_text().strip()
            if not name:
                return
            rgba = color_btn.get_rgba()
            color = f"#{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"
            CustomerRepository.create(name, color)
            self._load_customers()

    def _on_edit_customer(self, _btn, cust):
        dialog = Adw.AlertDialog(
            heading=_("Kunde bearbeiten"),
            body=f"Kunde: {cust['name']}",
        )
        dialog.add_response("cancel", _("Abbrechen"))
        dialog.add_response("save", _("Speichern"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_entry = Gtk.Entry()
        name_entry.set_text(cust['name'])
        box.append(name_entry)

        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        color_box.append(Gtk.Label(label=_("Farbe:")))
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        rgba.parse(cust.get('color', '#3584e4'))
        color_btn.set_rgba(rgba)
        color_box.append(color_btn)
        box.append(color_box)

        dialog.set_extra_child(box)
        dialog.connect("response", self._on_save_customer, cust['id'], name_entry, color_btn)
        dialog.present(self.get_root())

    def _on_save_customer(self, dialog, response, cust_id, name_entry, color_btn):
        if response == "save":
            name = name_entry.get_text().strip()
            if not name:
                return
            rgba = color_btn.get_rgba()
            color = f"#{int(rgba.red*255):02x}{int(rgba.green*255):02x}{int(rgba.blue*255):02x}"
            CustomerRepository.update(cust_id, name=name, color=color)
            self._load_customers()

    def _on_deactivate_customer(self, _btn, cust_id):
        CustomerRepository.delete(cust_id)
        self._load_customers()

    def _on_activate_customer(self, _btn, cust_id):
        CustomerRepository.update(cust_id, active=1)
        self._load_customers()

    # --- Project CRUD ---
    def _update_cust_filter(self):
        customers = CustomerRepository.get_all()
        self._cust_filter_ids = [c['id'] for c in customers]
        while self._cust_filter_model.get_n_items() > 0:
            self._cust_filter_model.remove(0)
        for c in customers:
            self._cust_filter_model.append(c['name'])
        if self._cust_filter_ids:
            self._cust_filter.set_selected(0)
            self._load_projects(self._cust_filter_ids[0])

    def _on_cust_filter_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if idx < len(self._cust_filter_ids):
            self._load_projects(self._cust_filter_ids[idx])

    def _load_projects(self, customer_id):
        projects = ProjectRepository.get_by_customer(customer_id, active_only=False)

        child = self._project_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._project_list.remove(child)
            child = nxt

        if not projects:
            lbl = Gtk.Label(label=_("Keine Projekte für diesen Kunden"))
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(20)
            row = Gtk.ListBoxRow(selectable=False)
            row.set_child(lbl)
            self._project_list.append(row)
            return

        for proj in projects:
            rate_str = f"{proj['hourly_rate']:,.2f}\u2009€/h".replace(",", "X").replace(".", ",").replace("X", ".")
            row = Adw.ActionRow(title=proj['name'], subtitle=rate_str)
            if not proj['active']:
                row.add_suffix(Gtk.Label(label=_("(deaktiviert)")))
                row.add_css_class("dim-label")

            edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
            edit_btn.set_valign(Gtk.Align.CENTER)
            edit_btn.set_has_frame(False)
            edit_btn.connect("clicked", self._on_edit_project, proj)
            row.add_suffix(edit_btn)

            if proj['active']:
                del_btn = Gtk.Button(icon_name="user-trash-symbolic")
                del_btn.set_valign(Gtk.Align.CENTER)
                del_btn.set_has_frame(False)
                del_btn.add_css_class("error")
                del_btn.set_tooltip_text(_("Deaktivieren"))
                del_btn.connect("clicked", self._on_deactivate_project, proj['id'])
                row.add_suffix(del_btn)
            else:
                act_btn = Gtk.Button(icon_name="view-reveal-symbolic")
                act_btn.set_valign(Gtk.Align.CENTER)
                act_btn.set_has_frame(False)
                act_btn.set_tooltip_text(_("Aktivieren"))
                act_btn.connect("clicked", self._on_activate_project, proj['id'])
                row.add_suffix(act_btn)

            self._project_list.append(row)

    def _on_add_project(self, _btn):
        if not self._cust_filter_ids:
            dialog = Adw.AlertDialog(heading=_("Kein Kunde"), body=_("Bitte erstelle zuerst einen Kunden."))
            dialog.add_response("ok", "OK")
            dialog.present(self.get_root())
            return

        idx = self._cust_filter.get_selected()
        customer_id = self._cust_filter_ids[idx]

        dialog = Adw.AlertDialog(
            heading=_("Neues Projekt"),
            body=_("Name und Stundensatz:"),
        )
        dialog.add_response("cancel", _("Abbrechen"))
        dialog.add_response("create", _("Erstellen"))
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text(_("Projektname"))
        box.append(name_entry)

        rate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rate_box.append(Gtk.Label(label=_("Stundensatz (€):")))
        rate_entry = Gtk.Entry()
        rate_entry.set_text("0.00")
        rate_entry.set_max_width_chars(8)
        rate_box.append(rate_entry)
        box.append(rate_box)

        quantum_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quantum_box.append(Gtk.Label(label=_("Quantisierung (h):")))
        quantum_entry = Gtk.Entry()
        quantum_entry.set_text("0.25")
        quantum_entry.set_max_width_chars(8)
        quantum_box.append(quantum_entry)
        box.append(quantum_box)

        dialog.set_extra_child(box)
        dialog.connect("response", self._on_create_project, customer_id, name_entry, rate_entry, quantum_entry)
        dialog.present(self.get_root())

    def _on_create_project(self, dialog, response, customer_id, name_entry, rate_entry, quantum_entry):
        if response == "create":
            name = name_entry.get_text().strip()
            if not name:
                return
            try:
                rate = float(rate_entry.get_text().strip().replace(",", "."))
            except ValueError:
                rate = 0.0
            try:
                quantum = float(quantum_entry.get_text().strip().replace(",", "."))
            except ValueError:
                quantum = 0.25
            pid = ProjectRepository.create(customer_id, name, rate)
            ProjectRepository.update(pid, time_quantum=quantum)
            self._load_projects(customer_id)

    def _on_edit_project(self, _btn, proj):
        dialog = Adw.AlertDialog(
            heading=_("Projekt bearbeiten"),
            body=f"Projekt: {proj['name']}",
        )
        dialog.add_response("cancel", _("Abbrechen"))
        dialog.add_response("save", _("Speichern"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_entry = Gtk.Entry()
        name_entry.set_text(proj['name'])
        box.append(name_entry)

        rate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rate_box.append(Gtk.Label(label=_("Stundensatz (€):")))
        rate_entry = Gtk.Entry()
        rate_entry.set_text(str(proj['hourly_rate']))
        rate_entry.set_max_width_chars(8)
        rate_box.append(rate_entry)
        box.append(rate_box)

        quantum_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quantum_box.append(Gtk.Label(label=_("Quantisierung (h):")))
        quantum_entry = Gtk.Entry()
        quantum_entry.set_text(str(proj.get('time_quantum', 0.25)))
        quantum_entry.set_max_width_chars(8)
        quantum_box.append(quantum_entry)
        box.append(quantum_box)

        dialog.set_extra_child(box)
        dialog.connect("response", self._on_save_project, proj, name_entry, rate_entry, quantum_entry)
        dialog.present(self.get_root())

    def _on_save_project(self, dialog, response, proj, name_entry, rate_entry, quantum_entry):
        if response == "save":
            name = name_entry.get_text().strip()
            if not name:
                return
            try:
                rate = float(rate_entry.get_text().strip().replace(",", "."))
            except ValueError:
                rate = proj['hourly_rate']
            try:
                quantum = float(quantum_entry.get_text().strip().replace(",", "."))
            except ValueError:
                quantum = proj.get('time_quantum', 0.25)
            ProjectRepository.update(proj['id'], name=name, hourly_rate=rate, time_quantum=quantum)
            idx = self._cust_filter.get_selected()
            if idx < len(self._cust_filter_ids):
                self._load_projects(self._cust_filter_ids[idx])

    def _on_deactivate_project(self, _btn, proj_id):
        ProjectRepository.delete(proj_id)
        idx = self._cust_filter.get_selected()
        if idx < len(self._cust_filter_ids):
            self._load_projects(self._cust_filter_ids[idx])

    def _on_activate_project(self, _btn, proj_id):
        ProjectRepository.update(proj_id, active=1)
        idx = self._cust_filter.get_selected()
        if idx < len(self._cust_filter_ids):
            self._load_projects(self._cust_filter_ids[idx])

    def refresh(self):
        self._load_customers()
