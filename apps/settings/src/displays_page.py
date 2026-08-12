import os

from gi.repository import Gio, GLib, Gtk

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

POWER_SERVICE = 'org.gnome.SettingsDaemon.Power'
POWER_PATH = '/org/gnome/SettingsDaemon/Power'
SCREEN_IFACE = 'org.gnome.SettingsDaemon.Power.Screen'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

# text-scaling-factor's real range is 0.5-3.0 (org.gnome.desktop.interface),
# but the extremes are unusably tiny/huge -- 0.8-1.3 covers "more space" to
# "larger text" without either end looking broken.
SCALE_MIN = 0.8
SCALE_MAX = 1.3
SCALE_DEFAULT = 1.0


class ScalingSliderRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, SCALE_MIN, SCALE_MAX, 0.01)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.add_mark(SCALE_DEFAULT, Gtk.PositionType.BOTTOM, None)
        self.append(self.scale)

        labels_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        labels_row.append(Gtk.Label(label='More Space', xalign=0, hexpand=True, css_classes=['caption', 'dim-label']))
        labels_row.append(Gtk.Label(label='Default', css_classes=['caption', 'dim-label']))
        end = Gtk.Label(label='Larger Text', xalign=1, hexpand=True, css_classes=['caption', 'dim-label'])
        labels_row.append(end)
        self.append(labels_row)


class BrightnessRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'], spacing=10)
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Image.new_from_icon_name('display-brightness-symbolic'))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.append(self.scale)
        icon2 = Gtk.Image.new_from_icon_name('display-brightness-symbolic')
        icon2.set_pixel_size(20)
        self.append(icon2)


class ToggleRow(Gtk.Box):
    def __init__(self, title: str, subtitle: str = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            text_box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=['caption', 'dim-label']))
        self.append(text_box)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.append(self.switch)


class DisplaysPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._power_settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.power')
        self._syncing = False
        self._brightness_available = False

        self._build_ui()
        self._connect_power_proxy()
        self._refresh_from_settings()

        self._interface_settings.connect(
            'changed::text-scaling-factor', lambda *_a: self._refresh_from_settings()
        )
        self._power_settings.connect(
            'changed::ambient-enabled', lambda *_a: self._refresh_from_settings()
        )

    def _build_ui(self):
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
        icon_path = os.path.join(ICON_DIR, 'laptop.svg')
        if os.path.isfile(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name('computer-symbolic')
        icon.set_pixel_size(96)
        header.append(icon)
        header.append(Gtk.Label(label='Built-in Display', css_classes=['title-4']))
        self.append(header)

        scaling_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._scaling_row = ScalingSliderRow()
        self._scaling_row.set_margin_start(14)
        self._scaling_row.set_margin_end(14)
        self._scaling_row.set_margin_top(14)
        self._scaling_row.set_margin_bottom(10)
        self._scaling_row.scale.connect('value-changed', self._on_scaling_changed)
        scaling_card.append(self._scaling_row)
        self.append(scaling_card)

        brightness_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._brightness_row = BrightnessRow()
        self._brightness_row.scale.connect('value-changed', self._on_brightness_changed)
        brightness_card.append(self._brightness_row)
        brightness_card.append(Gtk.Separator())

        self._auto_brightness_row = ToggleRow('Automatically adjust brightness')
        self._auto_brightness_row.switch.connect('state-set', self._on_auto_brightness_toggled)
        brightness_card.append(self._auto_brightness_row)
        self.append(brightness_card)

        self._brightness_status_label = Gtk.Label(
            label='No display brightness control available on this computer.',
            xalign=0, wrap=True, css_classes=['dim-label', 'caption'],
            margin_start=4, visible=False,
        )
        self.append(self._brightness_status_label)

    def _connect_power_proxy(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            # Probe: a real Get call fails cleanly if the Screen interface
            # was never registered (no backlight hardware detected), unlike
            # proxy creation which succeeds regardless.
            self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Get',
                GLib.Variant('(ss)', (SCREEN_IFACE, 'Brightness')),
                GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
            )
            self._brightness_available = True
            self._bus.signal_subscribe(
                POWER_SERVICE, PROPS_IFACE, 'PropertiesChanged', POWER_PATH, SCREEN_IFACE,
                Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh_from_settings(),
            )
        except GLib.Error:
            self._bus = None
            self._brightness_available = False

        self._brightness_row.set_visible(self._brightness_available)
        self._brightness_status_label.set_visible(not self._brightness_available)

    def _get_brightness(self):
        if not self._brightness_available:
            return None
        try:
            result = self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Get',
                GLib.Variant('(ss)', (SCREEN_IFACE, 'Brightness')),
                GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
            )
            return result.unpack()[0]
        except GLib.Error:
            return None

    def _set_brightness(self, value: int):
        if not self._brightness_available:
            return
        try:
            self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Set',
                GLib.Variant('(ssv)', (SCREEN_IFACE, 'Brightness', GLib.Variant('i', value))),
                None, Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error:
            pass

    def _refresh_from_settings(self):
        self._syncing = True
        self._scaling_row.scale.set_value(self._interface_settings.get_double('text-scaling-factor'))
        self._auto_brightness_row.switch.set_active(self._power_settings.get_boolean('ambient-enabled'))
        if self._brightness_available:
            level = self._get_brightness()
            if level is not None:
                self._brightness_row.scale.set_value(level)
        self._syncing = False

    def _on_scaling_changed(self, scale):
        if self._syncing:
            return
        self._interface_settings.set_double('text-scaling-factor', scale.get_value())

    def _on_brightness_changed(self, scale):
        if self._syncing:
            return
        self._set_brightness(round(scale.get_value()))

    def _on_auto_brightness_toggled(self, switch, state):
        if self._syncing:
            return False
        self._power_settings.set_boolean('ambient-enabled', state)
        return False
