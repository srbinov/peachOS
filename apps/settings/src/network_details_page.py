import os
import subprocess

from gi.repository import GLib, Gtk

from widgets import DropdownRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

IPV4_METHODS = [
    ('Automatic (DHCP)', 'auto'),
    ('Manual', 'manual'),
    ('Link-Local Only', 'link-local'),
    ('Disabled', 'disabled'),
]


def _nmcli(args):
    try:
        return subprocess.run(['nmcli'] + args, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None


class NetworkDetailsPage(Gtk.Box):
    """Per-connection editor -- auto-connect, IPv4 method + DNS, and delete.
    Reached by clicking a row on the Network page. Reused across connections
    via load(uuid, name)."""

    def __init__(self, go_back, on_changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self._go_back = go_back
        self._on_changed = on_changed
        self._uuid = None
        self._syncing = False

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER,
                         margin_top=8, margin_bottom=8)
        icon = Gtk.Image.new_from_icon_name('network-wired-symbolic')
        icon.set_pixel_size(56)
        header.append(icon)
        self._title_label = Gtk.Label(label='Connection', css_classes=['title-2'])
        header.append(self._title_label)
        header.append(Gtk.Label(label='Edit how this network connection behaves.',
                                css_classes=['dim-label'], wrap=True, justify=Gtk.Justification.CENTER))
        self.append(header)

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._autoconnect_row = ToggleRow('Connect Automatically',
                                          'Join this network whenever it is in range.')
        self._autoconnect_row.switch.connect('state-set', self._on_autoconnect_toggled)
        card.append(self._autoconnect_row)
        self._metered_row = ToggleRow('Metered Connection',
                                      'Limit background data on this network.')
        self._metered_row.switch.connect('state-set', self._on_metered_toggled)
        card.append(self._metered_row)
        self.append(card)

        self.append(Gtk.Label(label='IPv4', xalign=0, css_classes=['heading'], margin_start=4))
        ipv4_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._method_row = DropdownRow('Method', IPV4_METHODS)
        self._method_row.dropdown.connect('notify::selected', lambda *_a: self._on_method_changed())
        ipv4_card.append(self._method_row)

        self._address_row = self._entry_row('Address / Prefix', 'e.g. 192.168.1.50/24')
        self._gateway_row = self._entry_row('Gateway', 'e.g. 192.168.1.1')
        self._dns_row = self._entry_row('DNS Servers', 'comma-separated, e.g. 1.1.1.1, 8.8.8.8')
        for row in (self._address_row, self._gateway_row, self._dns_row):
            ipv4_card.append(row)
        self.append(ipv4_card)

        apply_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END, spacing=8)
        self._apply_btn = Gtk.Button(label='Apply', css_classes=['suggested-action'])
        self._apply_btn.connect('clicked', self._on_apply)
        apply_row.append(self._apply_btn)
        self.append(apply_row)

        self._status = Gtk.Label(xalign=0, wrap=True, css_classes=['dim-label', 'caption'], visible=False)
        self.append(self._status)

        delete_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
        delete_btn = Gtk.Button(label='Delete Connection', css_classes=['destructive-action'])
        delete_btn.connect('clicked', self._on_delete)
        delete_row.append(delete_btn)
        self.append(delete_row)

    def _entry_row(self, label, placeholder):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.append(Gtk.Label(label=label, xalign=0))
        row.entry = Gtk.Entry(hexpand=True, placeholder_text=placeholder)
        row.append(row.entry)
        return row

    # ---- load --------------------------------------------------------

    def load(self, uuid, name):
        self._uuid = uuid
        self._syncing = True
        self._status.set_visible(False)
        self._title_label.set_label(name)

        fields = self._connection_fields(uuid)
        self._autoconnect_row.switch.set_active(fields.get('connection.autoconnect') == 'yes')
        self._metered_row.switch.set_active(fields.get('connection.metered') == 'yes')

        method = fields.get('ipv4.method', 'auto')
        self._method_row.set_selected_value(method if method in dict(IPV4_METHODS).values() else 'auto')
        self._address_row.entry.set_text(fields.get('ipv4.addresses', '') or '')
        self._gateway_row.entry.set_text(fields.get('ipv4.gateway', '') or '')
        dns = fields.get('ipv4.dns', '') or ''
        self._dns_row.entry.set_text(dns.replace(' ', '').replace(',', ', '))
        self._sync_method_rows()
        self._syncing = False

    def _connection_fields(self, uuid):
        result = _nmcli(['-t', '-f', 'all', 'connection', 'show', uuid])
        fields = {}
        if not result or result.returncode != 0:
            return fields
        for line in result.stdout.splitlines():
            if ':' in line:
                key, _, value = line.partition(':')
                fields[key] = value
        return fields

    def _sync_method_rows(self):
        manual = self._method_row.get_selected_value() == 'manual'
        auto = self._method_row.get_selected_value() == 'auto'
        self._address_row.set_visible(manual)
        self._gateway_row.set_visible(manual)
        self._dns_row.set_visible(manual or auto)

    # ---- handlers ---------------------------------------------------

    def _on_method_changed(self):
        if not self._syncing:
            self._sync_method_rows()

    def _on_autoconnect_toggled(self, _switch, state):
        if not self._syncing and self._uuid:
            _nmcli(['connection', 'modify', self._uuid, 'connection.autoconnect', 'yes' if state else 'no'])
            self._on_changed()
        return False

    def _on_metered_toggled(self, _switch, state):
        if not self._syncing and self._uuid:
            _nmcli(['connection', 'modify', self._uuid, 'connection.metered', 'yes' if state else 'no'])
        return False

    def _on_apply(self, _btn):
        if not self._uuid:
            return
        method = self._method_row.get_selected_value()
        args = ['connection', 'modify', self._uuid, 'ipv4.method', method]
        if method == 'manual':
            addr = self._address_row.entry.get_text().strip()
            if not addr:
                self._show_status('Enter an address (e.g. 192.168.1.50/24) for manual IPv4.')
                return
            args += ['ipv4.addresses', addr]
            gw = self._gateway_row.entry.get_text().strip()
            args += ['ipv4.gateway', gw]
        dns = self._dns_row.entry.get_text().strip()
        if method in ('manual', 'auto'):
            args += ['ipv4.dns', dns.replace(' ', '')]
            args += ['ipv4.ignore-auto-dns', 'yes' if dns else 'no']

        result = _nmcli(args)
        if not result or result.returncode != 0:
            self._show_status((result.stderr if result else 'nmcli failed').strip())
            return
        _nmcli(['connection', 'up', self._uuid])
        self._show_status('Applied.', error=False)
        self._on_changed()

    def _on_delete(self, _btn):
        if not self._uuid:
            return
        dialog = Gtk.AlertDialog()
        dialog.set_modal(True)
        dialog.set_message('Delete this connection?')
        dialog.set_detail('It will be removed from this computer.')
        dialog.set_buttons(['Cancel', 'Delete'])
        dialog.set_cancel_button(0)

        def done(dlg, res):
            try:
                if dlg.choose_finish(res) == 1:
                    _nmcli(['connection', 'delete', self._uuid])
                    self._on_changed()
                    self._go_back()
            except GLib.Error:
                pass

        root = self.get_root()
        dialog.choose(root if isinstance(root, Gtk.Window) else None, None, done)

    def _show_status(self, text, error=True):
        self._status.set_label(text)
        self._status.set_visible(True)
        self._status.remove_css_class('error')
        if error:
            self._status.add_css_class('error')
