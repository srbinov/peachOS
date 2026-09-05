import os

from gi.repository import Gio, GLib, Gtk

from widgets import DropdownRow, ToggleRow, load_sized_image, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

POWER_PLUGIN_SCHEMA = 'org.gnome.settings-daemon.plugins.power'

POWER_BUTTON_OPTIONS = [
    ('Suspend', 'suspend'),
    ('Hibernate', 'hibernate'),
    ('Ask What to Do', 'interactive'),
    ('Do Nothing', 'nothing'),
]

SUSPEND_DELAY_OPTIONS = [
    ('After 5 minutes', 300),
    ('After 10 minutes', 600),
    ('After 15 minutes', 900),
    ('After 20 minutes', 1200),
    ('After 30 minutes', 1800),
    ('After 45 minutes', 2700),
    ('After 1 hour', 3600),
    ('After 2 hours', 7200),
    ('After 3 hours', 10800),
]

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
        if os.path.isfile(icon_path):
            icon = load_sized_image(icon_path, 28)
        else:
            icon = Gtk.Image.new_from_icon_name('battery-full-symbolic')
            icon.set_pixel_size(28)
        header.append(icon)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title_box.append(Gtk.Label(label='Battery', xalign=0, css_classes=['title-2']))
        self._status_label = Gtk.Label(label='Checking battery…', xalign=0, css_classes=['dim-label'])
        title_box.append(self._status_label)
        header.append(title_box)
        self.append(header)

        settings_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._low_power_switch = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)
        self._low_power_switch.connect('state-set', self._on_low_power_toggled)
        settings_list.append(InfoRow('Low Power Mode', self._low_power_switch))

        self._health_label = Gtk.Label(label='—', css_classes=['dim-label'])
        settings_list.append(InfoRow('Battery Health', self._health_label))

        self.append(settings_list)

        self._build_power_section()

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

    # ---- Power (gsettings) ------------------------------------------

    def _build_power_section(self):
        self._power_settings = Gio.Settings.new(POWER_PLUGIN_SCHEMA)
        self._syncing = False

        self.append(Gtk.Label(label='Power', xalign=0, css_classes=['heading'], margin_start=4))
        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        dim_row = ToggleRow('Dim Screen When Inactive',
                            'Reduce the screen brightness a while before it turns off.')
        self._power_settings.bind('idle-dim', dim_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(dim_row)

        saver_row = ToggleRow('Automatic Power Saver',
                              'Switch to Power Saver mode automatically when the battery is low.')
        self._power_settings.bind('power-saver-profile-on-low-battery', saver_row.switch, 'active',
                                  Gio.SettingsBindFlags.DEFAULT)
        card.append(saver_row)

        self._power_button_row = DropdownRow('Power Button Behavior', POWER_BUTTON_OPTIONS)
        self._power_button_row.set_selected_value(self._power_settings.get_string('power-button-action'))
        self._power_button_row.dropdown.connect('notify::selected', lambda *_a: (
            None if self._syncing else self._power_settings.set_string(
                'power-button-action', self._power_button_row.get_selected_value())))
        card.append(self._power_button_row)
        self.append(card)

        self.append(Gtk.Label(label='Automatic Suspend', xalign=0, css_classes=['heading'], margin_start=4))
        suspend_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._battery_suspend_row = ToggleRow('On Battery Power')
        self._battery_suspend_row.switch.connect(
            'state-set', lambda _s, on: self._on_suspend_toggled('battery', on))
        suspend_card.append(self._battery_suspend_row)
        self._battery_delay_row = DropdownRow('Delay', SUSPEND_DELAY_OPTIONS)
        self._battery_delay_row.dropdown.connect(
            'notify::selected', lambda *_a: self._on_suspend_delay('battery'))
        suspend_card.append(self._battery_delay_row)

        self._ac_suspend_row = ToggleRow('When Plugged In')
        self._ac_suspend_row.switch.connect(
            'state-set', lambda _s, on: self._on_suspend_toggled('ac', on))
        suspend_card.append(self._ac_suspend_row)
        self._ac_delay_row = DropdownRow('Delay', SUSPEND_DELAY_OPTIONS)
        self._ac_delay_row.dropdown.connect(
            'notify::selected', lambda *_a: self._on_suspend_delay('ac'))
        suspend_card.append(self._ac_delay_row)
        self.append(suspend_card)

        for key in ('sleep-inactive-battery-type', 'sleep-inactive-battery-timeout',
                    'sleep-inactive-ac-type', 'sleep-inactive-ac-timeout'):
            self._power_settings.connect(f'changed::{key}', lambda *_a: self._refresh_suspend())
        self._refresh_suspend()

    def _refresh_suspend(self):
        self._syncing = True
        for which, toggle, delay in (
            ('battery', self._battery_suspend_row, self._battery_delay_row),
            ('ac', self._ac_suspend_row, self._ac_delay_row),
        ):
            on = self._power_settings.get_string(f'sleep-inactive-{which}-type') == 'suspend'
            toggle.switch.set_active(on)
            delay.set_sensitive(on)
            timeout = self._power_settings.get_int(f'sleep-inactive-{which}-timeout')
            delay.set_selected_value(min(SUSPEND_DELAY_OPTIONS, key=lambda o: abs(o[1] - timeout))[1])
        self._syncing = False

    def _on_suspend_toggled(self, which, on):
        if self._syncing:
            return False
        self._power_settings.set_string(f'sleep-inactive-{which}-type', 'suspend' if on else 'nothing')
        (self._battery_delay_row if which == 'battery' else self._ac_delay_row).set_sensitive(on)
        return False

    def _on_suspend_delay(self, which):
        if self._syncing:
            return
        row = self._battery_delay_row if which == 'battery' else self._ac_delay_row
        self._power_settings.set_int(f'sleep-inactive-{which}-timeout', row.get_selected_value())

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
