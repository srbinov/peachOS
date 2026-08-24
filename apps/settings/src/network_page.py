import os

import gi

gi.require_version('NM', '1.0')

from gi.repository import GLib, Gtk, NM

from widgets import load_sized_image, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

DEVICE_TYPE_ICON = {
    NM.DeviceType.ETHERNET: 'network-wired-symbolic',
    NM.DeviceType.WIFI: 'network-wireless-symbolic',
    NM.DeviceType.MODEM: 'network-cellular-symbolic',
    NM.DeviceType.BRIDGE: 'network-workgroup-symbolic',
    NM.DeviceType.TUN: 'network-vpn-symbolic',
    NM.DeviceType.LOOPBACK: 'network-workgroup-symbolic',
}

CONNECTED_STATES = {NM.DeviceState.ACTIVATED}


class ServiceRow(Gtk.Box):
    def __init__(self, title: str, icon_name: str, subtitle: str, connected: bool, icon_file: str = None,
                 on_click=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        if icon_file and os.path.isfile(icon_file):
            icon = load_sized_image(icon_file, 28)
            self.append(icon)
        else:
            icon_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, css_classes=['sidebar-icon', 'accent-blue'])
            icon_box.set_size_request(28, 28)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(15)
            icon_box.append(icon)
            self.append(icon_box)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=title, xalign=0))
        status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dot = Gtk.Box(
            width_request=8, height_request=8, valign=Gtk.Align.CENTER,
            css_classes=['connected-dot' if connected else 'disconnected-dot'],
        )
        status_line.append(dot)
        status_line.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['dim-label', 'caption']))
        text_box.append(status_line)
        self.append(text_box)

        self.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))

        if on_click:
            self.set_cursor_from_name('pointer')
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a: on_click())
            self.add_controller(click)


class NetworkPage(Gtk.Box):
    def __init__(self, on_open_wifi=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_open_wifi = on_open_wifi
        self._client = None
        self._build_ui()
        NM.Client.new_async(None, self._on_client_ready)

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'network.svg'), 'network-workgroup-symbolic',
            'Network', 'Manage the network interfaces and services connected to this computer.',
        ))

        self._devices_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._devices_list)

        self._firewall_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._firewall_list)

        self._status_label = Gtk.Label(
            label='Loading network services…', wrap=True,
            css_classes=['dim-label'], valign=Gtk.Align.CENTER, vexpand=True,
        )
        self.append(self._status_label)

    def _on_client_ready(self, source, result):
        try:
            self._client = NM.Client.new_finish(result)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not connect to NetworkManager: {e.message}')
            self._status_label.set_visible(True)
            return

        self._client.connect('notify::state', lambda *_: self._refresh())
        for device in self._client.get_devices():
            device.connect('state-changed', lambda *_a: self._refresh())

        self._refresh()

    def _refresh(self):
        while (child := self._devices_list.get_first_child()) is not None:
            self._devices_list.remove(child)

        devices = [
            d for d in self._client.get_devices()
            if d.get_device_type() not in (NM.DeviceType.LOOPBACK, NM.DeviceType.GENERIC)
        ]

        self._devices_list.set_visible(bool(devices))
        self._status_label.set_visible(not devices)
        if not devices:
            self._status_label.set_label('No network interfaces detected.')
        else:
            for device in devices:
                dtype = device.get_device_type()
                icon_name = DEVICE_TYPE_ICON.get(dtype, 'network-wired-symbolic')
                # Was hardcoded to wifi.svg for every device regardless of type, which made
                # a plain ethernet connection (all this VM has -- confirmed via `nmcli device
                # status`, no real WiFi hardware here) *look* like a WiFi row. That's a real,
                # separate bug from -- but the direct cause of -- "clicking it doesn't go
                # anywhere": the row was never actually a WIFI-typed device, so the
                # WIFI-only on_click below was correctly leaving it non-clickable the whole
                # time; it just looked clickable because of this wrong icon.
                icon_file = os.path.join(ICON_DIR, 'wifi.svg' if dtype == NM.DeviceType.WIFI else 'network.svg')
                title = device.get_iface() or device.get_type_description() or 'Network'
                active_conn = device.get_active_connection()
                if active_conn:
                    title = active_conn.get_id() or title
                connected = device.get_state() in CONNECTED_STATES
                subtitle = 'Connected' if connected else 'Not Connected'
                on_click = self._on_open_wifi if dtype == NM.DeviceType.WIFI else None
                self._devices_list.append(ServiceRow(
                    title, icon_name, subtitle, connected, icon_file=icon_file, on_click=on_click))

        while (child := self._firewall_list.get_first_child()) is not None:
            self._firewall_list.remove(child)
        firewall_active = self._read_firewall_status()
        self._firewall_list.append(ServiceRow(
            'Firewall', 'security-high-symbolic',
            'Active' if firewall_active else 'Inactive', firewall_active,
            icon_file=os.path.join(ICON_DIR, 'firewall.svg'),
        ))

    def _read_firewall_status(self) -> bool:
        try:
            with open('/etc/ufw/ufw.conf') as f:
                for line in f:
                    if line.strip().startswith('ENABLED='):
                        return line.strip().split('=', 1)[1].strip().lower() == 'yes'
        except OSError:
            pass
        return False
