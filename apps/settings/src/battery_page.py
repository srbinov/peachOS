import os

from gi.repository import Gio, GLib, Gtk

from widgets import add_hover_highlight, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

UPOWER_SERVICE = 'org.freedesktop.UPower'
UPOWER_DEVICE_IFACE = 'org.freedesktop.UPower.Device'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'
PPD_SERVICE = 'net.hadess.PowerProfiles'
PPD_PATH = '/net/hadess/PowerProfiles'
PPD_IFACE = 'net.hadess.PowerProfiles'

# UPower Device.State enum
STATE_NAMES = {
    0: 'Unknown', 1: 'Charging', 2: 'Discharging',
    3: 'Empty', 4: 'Fully Charged', 5: 'Pending Charge', 6: 'Pending Discharge',
}


class InfoRow(Gtk.Box):
    def __init__(self, title: str, trailing: Gtk.Widget):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(12)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        add_hover_highlight(self)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.append(trailing)


class HistoryCard(Gtk.Box):
    def __init__(self, title: str):
        # Margins go on the *children*, not on this box itself -- margins on
        # the card widget just push it away from its siblings (that's what
        # produced the header text sitting flush in the corner before: the
        # card's own edges had zero internal padding for its content).
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=['wifi-card'])
        title_label = Gtk.Label(
            label=title, xalign=0, css_classes=['heading'],
            margin_start=14, margin_end=14, margin_top=12,
        )
        self.append(title_label)
        placeholder = Gtk.Label(
            label='Not enough history collected yet.',
            xalign=0.5, css_classes=['dim-label', 'caption'],
            halign=Gtk.Align.CENTER, margin_top=20, margin_bottom=28,
        )
        self.append(placeholder)


class BatteryPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._bus = None
        self._battery_path = None

        self._build_ui()
        self._connect_bus()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'energy.svg'), 'battery-full-symbolic',
            'Battery', 'Monitor battery health and manage power-saving settings.',
        ))

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon_path = os.path.join(ICON_DIR, 'energy.svg')
        icon = Gtk.Image.new_from_file(icon_path) if os.path.isfile(icon_path) \
            else Gtk.Image.new_from_icon_name('battery-full-symbolic')
        icon.set_pixel_size(28)
        header.append(icon)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title_box.append(Gtk.Label(label='Battery', xalign=0, css_classes=['title-2']))
        self._status_label = Gtk.Label(label='Checking battery…', xalign=0, css_classes=['dim-label'])
        title_box.append(self._status_label)
        header.append(title_box)
        self.append(header)

        settings_frame = Gtk.Box(css_classes=['wifi-card'])
        settings_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        settings_frame.append(settings_list)

        self._low_power_switch = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)
        self._low_power_switch.connect('state-set', self._on_low_power_toggled)
        settings_list.append(InfoRow('Low Power Mode', self._low_power_switch))
        settings_list.append(Gtk.Separator())

        self._health_label = Gtk.Label(label='—', css_classes=['dim-label'])
        settings_list.append(InfoRow('Battery Health', self._health_label))

        self.append(settings_frame)

        toggle_row = Gtk.Box(css_classes=['linked'], halign=Gtk.Align.FILL, homogeneous=True)
        btn_24h = Gtk.ToggleButton(label='Last 24 Hours', active=True, css_classes=['segmented-toggle'])
        btn_10d = Gtk.ToggleButton(label='Last 10 Days', group=btn_24h, css_classes=['segmented-toggle'])
        toggle_row.append(btn_24h)
        toggle_row.append(btn_10d)
        self.append(toggle_row)

        self.append(HistoryCard('Battery Level'))
        self.append(HistoryCard('Screen On Usage'))

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END, spacing=8)
        bottom_row.append(Gtk.Button(label='Options…'))
        bottom_row.append(Gtk.Button(icon_name='help-about-symbolic', css_classes=['circular']))
        self.append(bottom_row)

    # ---- D-Bus wiring -------------------------------------------------

    def _connect_bus(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not reach the system bus: {e.message}')
            return

        self._find_battery_device()
        self._refresh_power_profile()

        self._bus.signal_subscribe(
            UPOWER_SERVICE, PROPS_IFACE, 'PropertiesChanged', None, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh_battery(),
        )
        self._bus.signal_subscribe(
            PPD_SERVICE, PROPS_IFACE, 'PropertiesChanged', PPD_PATH, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh_power_profile(),
        )

    def _find_battery_device(self):
        try:
            result = self._bus.call_sync(
                UPOWER_SERVICE, '/org/freedesktop/UPower', 'org.freedesktop.UPower',
                'EnumerateDevices', None, GLib.VariantType.new('(ao)'),
                Gio.DBusCallFlags.NONE, 2000, None,
            )
            paths = result.unpack()[0]
        except GLib.Error as e:
            self._status_label.set_label(f'Could not reach UPower: {e.message}')
            return

        for path in paths:
            try:
                props = self._bus.call_sync(
                    UPOWER_SERVICE, path, PROPS_IFACE, 'GetAll',
                    GLib.Variant('(s)', (UPOWER_DEVICE_IFACE,)),
                    GLib.VariantType.new('(a{sv})'), Gio.DBusCallFlags.NONE, 2000, None,
                ).unpack()[0]
            except GLib.Error:
                continue
            if props.get('PowerSupply') and props.get('IsPresent') and props.get('Type') == 2:  # 2 = Battery
                self._battery_path = path
                break

        if not self._battery_path:
            self._status_label.set_label('No battery detected on this computer.')
            return

        self._refresh_battery()

    def _refresh_battery(self):
        if not self._battery_path:
            return
        try:
            props = self._bus.call_sync(
                UPOWER_SERVICE, self._battery_path, PROPS_IFACE, 'GetAll',
                GLib.Variant('(s)', (UPOWER_DEVICE_IFACE,)),
                GLib.VariantType.new('(a{sv})'), Gio.DBusCallFlags.NONE, 2000, None,
            ).unpack()[0]
        except GLib.Error as e:
            self._status_label.set_label(f'Could not read battery status: {e.message}')
            return

        percentage = round(props.get('Percentage', 0))
        state = STATE_NAMES.get(props.get('State', 0), 'Unknown')
        if state == 'Fully Charged':
            self._status_label.set_label('Fully Charged')
        else:
            self._status_label.set_label(f'{percentage}% – {state}')

        full = props.get('EnergyFull', 0)
        design = props.get('EnergyFullDesign', 0)
        if design:
            health_pct = round((full / design) * 100)
            self._health_label.set_label('Normal' if health_pct >= 80 else 'Service Recommended')
        else:
            self._health_label.set_label('Unknown')

    def _refresh_power_profile(self):
        try:
            active = self._bus.call_sync(
                PPD_SERVICE, PPD_PATH, PROPS_IFACE, 'Get',
                GLib.Variant('(ss)', (PPD_IFACE, 'ActiveProfile')),
                GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
            ).unpack()[0]
        except GLib.Error:
            self._low_power_switch.set_sensitive(False)
            return

        self._low_power_switch.set_sensitive(True)
        self._low_power_switch.set_active(active == 'power-saver')

    def _on_low_power_toggled(self, switch, state):
        target = 'power-saver' if state else 'balanced'
        try:
            self._bus.call_sync(
                PPD_SERVICE, PPD_PATH, PROPS_IFACE, 'Set',
                GLib.Variant('(ssv)', (PPD_IFACE, 'ActiveProfile', GLib.Variant('s', target))),
                None, Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error:
            return True
        return False
