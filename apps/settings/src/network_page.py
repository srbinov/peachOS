import os
import subprocess

import gi

gi.require_version('NM', '1.0')

from gi.repository import Gio, GLib, Gtk, NM

from widgets import DropdownRow, load_sized_image, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

DEVICE_TYPE_ICON = {
    NM.DeviceType.ETHERNET: 'network-wired-symbolic',
    NM.DeviceType.WIFI: 'network-wireless-symbolic',
    NM.DeviceType.MODEM: 'network-cellular-symbolic',
    NM.DeviceType.BRIDGE: 'network-workgroup-symbolic',
    NM.DeviceType.TUN: 'network-vpn-symbolic',
}

CONNECTED_STATES = {NM.DeviceState.ACTIVATED}
VPN_TYPES = ('vpn', 'wireguard')

PROXY_SCHEMA = 'org.gnome.system.proxy'
PROXY_MODES = [('Off', 'none'), ('Manual', 'manual'), ('Automatic', 'auto')]


def _nmcli(args):
    try:
        return subprocess.run(['nmcli'] + args, capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.SubprocessError):
        return None


class ServiceRow(Gtk.Box):
    def __init__(self, title, icon_name, subtitle, connected, icon_file=None, on_click=None, trailing=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        if icon_file and os.path.isfile(icon_file):
            self.append(load_sized_image(icon_file, 28))
        else:
            icon_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                               css_classes=['sidebar-icon', 'accent-blue'])
            icon_box.set_size_request(28, 28)
            glyph = Gtk.Image.new_from_icon_name(icon_name)
            glyph.set_pixel_size(15)
            icon_box.append(glyph)
            self.append(icon_box)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=title, xalign=0))
        status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_line.append(Gtk.Box(width_request=8, height_request=8, valign=Gtk.Align.CENTER,
                                   css_classes=['connected-dot' if connected else 'disconnected-dot']))
        status_line.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['dim-label', 'caption']))
        text_box.append(status_line)
        self.append(text_box)

        if trailing is not None:
            self.append(trailing)
        if on_click:
            self.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))
            self.set_cursor_from_name('pointer')
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a: on_click())
            self.add_controller(click)


class NetworkPage(Gtk.Box):
    def __init__(self, on_open_wifi=None, on_open_connection=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_open_wifi = on_open_wifi
        self._on_open_connection = on_open_connection
        self._client = None
        self._proxy_settings = Gio.Settings.new(PROXY_SCHEMA)
        self._proxy_syncing = False
        self._build_ui()
        NM.Client.new_async(None, self._on_client_ready)

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'network.svg'), 'network-workgroup-symbolic',
            'Network', 'Manage the network interfaces, VPNs, and proxy for this computer.',
        ))

        self._devices_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._devices_list)
        self._status_label = Gtk.Label(label='Loading network services…', wrap=True,
                                       css_classes=['dim-label'], valign=Gtk.Align.CENTER)
        self.append(self._status_label)

        # ---- VPN ----
        vpn_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vpn_header.append(Gtk.Label(label='VPN', xalign=0, hexpand=True, css_classes=['heading'], margin_start=4))
        add_vpn = Gtk.Button(icon_name='list-add-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)
        add_vpn.connect('clicked', self._on_add_vpn)
        vpn_header.append(add_vpn)
        self.append(vpn_header)
        self._vpn_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._vpn_list)
        self._vpn_empty = Gtk.Label(label='No VPNs configured.', xalign=0,
                                    css_classes=['dim-label', 'caption'], margin_start=4)
        self.append(self._vpn_empty)

        # ---- Proxy ----
        self.append(Gtk.Label(label='Network Proxy', xalign=0, css_classes=['heading'], margin_start=4))
        proxy_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._proxy_mode_row = DropdownRow('Proxy', PROXY_MODES)
        self._proxy_mode_row.dropdown.connect('notify::selected', lambda *_a: self._on_proxy_mode_changed())
        proxy_card.append(self._proxy_mode_row)

        self._proxy_auto_row = self._proxy_entry_row('Configuration URL', 'http://example.com/proxy.pac')
        proxy_card.append(self._proxy_auto_row)
        self._proxy_http_row = self._proxy_hostport_row('HTTP Proxy')
        self._proxy_https_row = self._proxy_hostport_row('HTTPS Proxy')
        self._proxy_socks_row = self._proxy_hostport_row('SOCKS Host')
        for row in (self._proxy_http_row, self._proxy_https_row, self._proxy_socks_row):
            proxy_card.append(row)
        self.append(proxy_card)

        # ---- Firewall ----
        self._firewall_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._firewall_list)

        self._load_proxy()
        for key in ('mode', 'autoconfig-url'):
            self._proxy_settings.connect(f'changed::{key}', lambda *_a: self._load_proxy())

    # ---- proxy rows ------------------------------------------------

    def _proxy_entry_row(self, label, placeholder):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.append(Gtk.Label(label=label, xalign=0))
        row.entry = Gtk.Entry(hexpand=True, placeholder_text=placeholder)
        row.entry.connect('changed', lambda *_a: self._save_proxy())
        row.append(row.entry)
        return row

    def _proxy_hostport_row(self, label):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, css_classes=['network-row'])
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.append(Gtk.Label(label=label, xalign=0, hexpand=True))
        row.host = Gtk.Entry(placeholder_text='host', width_chars=16)
        row.port = Gtk.SpinButton.new_with_range(0, 65535, 1)
        row.host.connect('changed', lambda *_a: self._save_proxy())
        row.port.connect('value-changed', lambda *_a: self._save_proxy())
        row.append(row.host)
        row.append(row.port)
        return row

    def _load_proxy(self):
        self._proxy_syncing = True
        mode = self._proxy_settings.get_string('mode')
        self._proxy_mode_row.set_selected_value(mode)
        self._proxy_auto_row.entry.set_text(self._proxy_settings.get_string('autoconfig-url'))
        for key, row in (('http', self._proxy_http_row), ('https', self._proxy_https_row),
                         ('socks', self._proxy_socks_row)):
            sub = Gio.Settings.new(f'{PROXY_SCHEMA}.{key}')
            row.host.set_text(sub.get_string('host'))
            row.port.set_value(sub.get_int('port'))
        self._update_proxy_visibility(mode)
        self._proxy_syncing = False

    def _update_proxy_visibility(self, mode):
        self._proxy_auto_row.set_visible(mode == 'auto')
        for row in (self._proxy_http_row, self._proxy_https_row, self._proxy_socks_row):
            row.set_visible(mode == 'manual')

    def _on_proxy_mode_changed(self):
        if self._proxy_syncing:
            return
        mode = self._proxy_mode_row.get_selected_value()
        self._proxy_settings.set_string('mode', mode)
        self._update_proxy_visibility(mode)

    def _save_proxy(self):
        if self._proxy_syncing:
            return
        self._proxy_settings.set_string('autoconfig-url', self._proxy_auto_row.entry.get_text().strip())
        for key, row in (('http', self._proxy_http_row), ('https', self._proxy_https_row),
                         ('socks', self._proxy_socks_row)):
            sub = Gio.Settings.new(f'{PROXY_SCHEMA}.{key}')
            sub.set_string('host', row.host.get_text().strip())
            sub.set_int('port', int(row.port.get_value()))

    # ---- NM ------------------------------------------------------

    def _on_client_ready(self, _source, result):
        try:
            self._client = NM.Client.new_finish(result)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not connect to NetworkManager: {e.message}')
            return
        self._client.connect('notify::state', lambda *_a: self._refresh())
        self._client.connect('connection-added', lambda *_a: self._refresh())
        self._client.connect('connection-removed', lambda *_a: self._refresh())
        for device in self._client.get_devices():
            device.connect('state-changed', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._refresh_devices()
        self._refresh_vpn()
        self._refresh_firewall()

    def _refresh_devices(self):
        while (child := self._devices_list.get_first_child()) is not None:
            self._devices_list.remove(child)

        devices = [d for d in self._client.get_devices()
                   if d.get_device_type() not in (NM.DeviceType.LOOPBACK, NM.DeviceType.GENERIC,
                                                  NM.DeviceType.TUN)]
        self._devices_list.set_visible(bool(devices))
        self._status_label.set_visible(not devices)
        if not devices:
            self._status_label.set_label('No network interfaces detected.')
            return

        for device in devices:
            dtype = device.get_device_type()
            icon_name = DEVICE_TYPE_ICON.get(dtype, 'network-wired-symbolic')
            icon_file = os.path.join(ICON_DIR, 'wifi.svg' if dtype == NM.DeviceType.WIFI else 'network.svg')
            title = device.get_iface() or device.get_type_description() or 'Network'
            active = device.get_active_connection()
            uuid = None
            if active and active.get_connection():
                title = active.get_id() or title
                uuid = active.get_connection().get_uuid()
            connected = device.get_state() in CONNECTED_STATES
            subtitle = 'Connected' if connected else 'Not Connected'

            on_click = None
            if dtype == NM.DeviceType.WIFI and self._on_open_wifi:
                on_click = self._on_open_wifi
            elif uuid and self._on_open_connection:
                on_click = lambda u=uuid, t=title: self._on_open_connection(u, t)

            self._devices_list.append(ServiceRow(title, icon_name, subtitle, connected,
                                                 icon_file=icon_file, on_click=on_click))

    def _refresh_vpn(self):
        while (child := self._vpn_list.get_first_child()) is not None:
            self._vpn_list.remove(child)

        vpns = [c for c in self._client.get_connections()
                if c.get_connection_type() in VPN_TYPES]
        self._vpn_list.set_visible(bool(vpns))
        self._vpn_empty.set_visible(not vpns)

        active_uuids = {a.get_uuid() for a in self._client.get_active_connections()}
        for conn in vpns:
            uuid = conn.get_uuid()
            name = conn.get_id()
            is_up = uuid in active_uuids
            switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=is_up)
            switch.connect('state-set', self._on_vpn_toggled, uuid)
            on_click = (lambda u=uuid, t=name: self._on_open_connection(u, t)) if self._on_open_connection else None
            self._vpn_list.append(ServiceRow(
                name, 'network-vpn-symbolic', 'Connected' if is_up else 'Not Connected',
                is_up, on_click=on_click, trailing=switch))

    def _on_vpn_toggled(self, _switch, state, uuid):
        _nmcli(['connection', 'up' if state else 'down', 'uuid', uuid])
        GLib.timeout_add(600, lambda: (self._refresh(), False)[1])
        return False

    def _on_add_vpn(self, _btn):
        dialog = Gtk.FileDialog(title='Import VPN Configuration')
        flt = Gtk.FileFilter(name='VPN configs (.ovpn, .conf, .ovpntls)')
        for pattern in ('*.ovpn', '*.conf', '*.ovpntls', '*.pcf'):
            flt.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_vpn_file_chosen)

    def _on_vpn_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path() if gfile else None
        if not path:
            return
        vpn_type = 'wireguard' if path.endswith('.conf') else 'openvpn'
        res = _nmcli(['connection', 'import', 'type', vpn_type, 'file', path])
        if not res or res.returncode != 0:
            self._status_label.set_label(
                f'Import failed: {(res.stderr if res else "nmcli not available").strip()}')
            self._status_label.set_visible(True)
        self._refresh()

    def _refresh_firewall(self):
        while (child := self._firewall_list.get_first_child()) is not None:
            self._firewall_list.remove(child)
        active = self._read_firewall_status()
        self._firewall_list.append(ServiceRow(
            'Firewall', 'security-high-symbolic', 'Active' if active else 'Inactive', active,
            icon_file=os.path.join(ICON_DIR, 'firewall.svg')))

    def _read_firewall_status(self):
        try:
            with open('/etc/ufw/ufw.conf') as f:
                for line in f:
                    if line.strip().startswith('ENABLED='):
                        return line.strip().split('=', 1)[1].strip().lower() == 'yes'
        except OSError:
            pass
        return False
