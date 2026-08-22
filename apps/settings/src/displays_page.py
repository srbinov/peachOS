import os

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

POWER_SERVICE = 'org.gnome.SettingsDaemon.Power'
POWER_PATH = '/org/gnome/SettingsDaemon/Power'
SCREEN_IFACE = 'org.gnome.SettingsDaemon.Power.Screen'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

# Resolution/refresh-rate/scale/orientation go through Mutter's own display
# config service -- the exact same API GNOME Settings' Displays panel uses,
# not a simpler gsettings key. GetCurrentState returns the full monitor/mode
# list; ApplyMonitorsConfig replaces the logical monitor layout wholesale
# (there's no "just change one field" call -- every apply resends x/y/scale/
# transform/mode together).
DISPLAYCONFIG_SERVICE = 'org.gnome.Mutter.DisplayConfig'
DISPLAYCONFIG_PATH = '/org/gnome/Mutter/DisplayConfig'
DISPLAYCONFIG_IFACE = 'org.gnome.Mutter.DisplayConfig'
GET_STATE_REPLY_TYPE = '(ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv})'
APPLY_METHOD_PERSISTENT = 2

# Mutter's Transform enum, exposed in the Displays panel as "Orientation."
# Only the 4 plain rotations are offered, same as real GNOME Settings --
# the flipped variants (4-7) exist in the protocol but aren't user-facing.
ORIENTATIONS = [
    ('Normal', 0),
    ('Rotate 90°', 1),
    ('Rotate 180°', 2),
    ('Rotate 270°', 3),
]


class MonitorConfig:
    """Wraps the one monitor this VM has via Mutter's DisplayConfig D-Bus
    API. Real hardware state, not mocked -- verified the exact GVariant
    construction with a live no-op ApplyMonitorsConfig call (method=1,
    temporary) before wiring this up for real."""

    def __init__(self):
        self.available = False
        self.connector = None
        self.modes = []
        self.serial = 0
        self.logical = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None
            return
        self.refresh_state()

    def refresh_state(self):
        if not self._bus:
            return
        try:
            result = self._bus.call_sync(
                DISPLAYCONFIG_SERVICE, DISPLAYCONFIG_PATH, DISPLAYCONFIG_IFACE, 'GetCurrentState',
                None, GLib.VariantType.new(GET_STATE_REPLY_TYPE),
                Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error:
            self.available = False
            return

        serial, monitors, logical_monitors, _props = result.unpack()
        if not monitors or not logical_monitors:
            self.available = False
            return

        self.serial = serial
        mon_spec, modes, _mon_props = monitors[0]
        self.connector = mon_spec[0]
        self.modes = [
            {
                'id': mode_id, 'w': w, 'h': h, 'refresh': refresh, 'scales': scales,
                'is_current': mprops.get('is-current', False),
            }
            for mode_id, w, h, refresh, _pref_scale, scales, mprops in modes
        ]
        x, y, scale, transform, is_primary, _lmons, _lprops = logical_monitors[0]
        self.logical = {'x': x, 'y': y, 'scale': scale, 'transform': transform, 'primary': is_primary}
        self.available = True

    def current_mode(self):
        return next((m for m in self.modes if m['is_current']), None)

    def resolutions(self):
        """Unique (w, h) pairs, keeping each one's highest-refresh mode,
        sorted largest first."""
        best = {}
        for m in self.modes:
            key = (m['w'], m['h'])
            if key not in best or m['refresh'] > best[key]['refresh']:
                best[key] = m
        return sorted(best.values(), key=lambda m: m['w'] * m['h'], reverse=True)

    def modes_for_resolution(self, w, h):
        return sorted(
            (m for m in self.modes if m['w'] == w and m['h'] == h),
            key=lambda m: m['refresh'], reverse=True,
        )

    def apply(self, mode_id=None, scale=None, transform=None):
        if not self.available:
            return
        mode_id = mode_id or self.current_mode()['id']
        scale = self.logical['scale'] if scale is None else scale
        transform = self.logical['transform'] if transform is None else transform

        args = GLib.Variant('(uua(iiduba(ssa{sv}))a{sv})', (
            self.serial, APPLY_METHOD_PERSISTENT,
            [(self.logical['x'], self.logical['y'], scale, transform, self.logical['primary'],
              [(self.connector, mode_id, {})])],
            {},
        ))
        try:
            self._bus.call_sync(
                DISPLAYCONFIG_SERVICE, DISPLAYCONFIG_PATH, DISPLAYCONFIG_IFACE, 'ApplyMonitorsConfig',
                args, None, Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error:
            pass
        self.refresh_state()


def _format_refresh(hz: float) -> str:
    return f'{hz:.0f} Hz'


def _format_resolution(w: int, h: int) -> str:
    return f'{w} × {h}'


def _format_scale(scale: float) -> str:
    return f'{round(scale * 100)}%'

# text-scaling-factor's real range is 0.5-3.0 (org.gnome.desktop.interface),
# but the extremes are unusably tiny/huge -- 0.8-1.3 covers "more space" to
# "larger text" without either end looking broken.
SCALE_MIN = 0.8
SCALE_MAX = 1.3
SCALE_DEFAULT = 1.0


class ScalingSliderRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(Gtk.Label(label='Text Scaling', xalign=0, css_classes=['heading']))
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


class DropdownRow(Gtk.Box):
    def __init__(self, title: str, options: list):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.dropdown = Gtk.DropDown.new_from_strings([label for label, _value in options] or [' '])
        self._values = [value for _label, value in options]
        self.append(self.dropdown)

    def set_options(self, options: list):
        self.dropdown.set_model(Gtk.StringList.new([label for label, _value in options] or [' ']))
        self._values = [value for _label, value in options]

    def get_selected_value(self):
        if not self._values:
            return None
        return self._values[self.dropdown.get_selected()]

    def set_selected_value(self, value):
        if value in self._values:
            self.dropdown.set_selected(self._values.index(value))


class TemperatureRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'], spacing=10)
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label='Color Temperature', xalign=0))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1700, 4700, 50)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        # No set_inverted() -- 1700 (warm) is already the range's own minimum, so a plain,
        # non-inverted scale already reads left=warmer/right=cooler on its own. An explicit
        # set_inverted(True) used to sit here; confirmed live (same bug as keyboard_page.py's
        # rate/delay sliders) that inverting a Gtk.Scale flips the handle's value-to-position
        # mapping but leaves the theme's highlighted-track fill on the wrong side of it.
        self.append(self.scale)


class DisplaysPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._power_settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.power')
        self._color_settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.color')
        self._monitor = MonitorConfig()
        self._syncing = False
        self._brightness_available = False

        self._build_ui()
        self._connect_power_proxy()
        self._refresh_from_settings()
        self._refresh_monitor_row()
        self._refresh_night_light()

        self._interface_settings.connect(
            'changed::text-scaling-factor', lambda *_a: self._refresh_from_settings()
        )
        self._power_settings.connect(
            'changed::ambient-enabled', lambda *_a: self._refresh_from_settings()
        )
        for key in ('night-light-enabled', 'night-light-schedule-automatic', 'night-light-temperature'):
            self._color_settings.connect(f'changed::{key}', lambda *_a: self._refresh_night_light())

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'displays.svg'), 'video-display-symbolic',
            'Displays', 'Manage the arrangement, resolution, and color of your displays.',
        ))

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
        icon_path = os.path.join(ICON_DIR, 'laptop.svg')
        if os.path.isfile(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name('computer-symbolic')
        icon.set_pixel_size(115)
        header.append(icon)
        header.append(Gtk.Label(label='Built-in Display', css_classes=['title-4']))
        self.append(header)

        self._monitor_card = monitor_card = Gtk.ListBox(
            css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE,
        )
        self._orientation_row = DropdownRow('Orientation', ORIENTATIONS)
        self._orientation_row.dropdown.connect('notify::selected', self._on_orientation_changed)
        monitor_card.append(self._orientation_row)

        self._resolution_row = DropdownRow('Resolution', [])
        self._resolution_row.dropdown.connect('notify::selected', self._on_resolution_changed)
        monitor_card.append(self._resolution_row)

        self._refresh_rate_row = DropdownRow('Refresh Rate', [])
        self._refresh_rate_row.dropdown.connect('notify::selected', self._on_refresh_rate_changed)
        monitor_card.append(self._refresh_rate_row)

        self._scale_row = DropdownRow('Scale', [])
        self._scale_row.dropdown.connect('notify::selected', self._on_display_scale_changed)
        monitor_card.append(self._scale_row)
        self.append(monitor_card)

        self._monitor_status_label = Gtk.Label(
            label='No configurable display detected.',
            xalign=0, wrap=True, css_classes=['dim-label', 'caption'],
            margin_start=4, visible=False,
        )
        self.append(self._monitor_status_label)

        scaling_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._scaling_row = ScalingSliderRow()
        self._scaling_row.set_margin_start(14)
        self._scaling_row.set_margin_end(14)
        self._scaling_row.set_margin_top(14)
        self._scaling_row.set_margin_bottom(10)
        self._scaling_row.scale.connect('value-changed', self._on_scaling_changed)
        scaling_card.append(self._scaling_row)
        self.append(scaling_card)

        brightness_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._brightness_row = BrightnessRow()
        self._brightness_row.scale.connect('value-changed', self._on_brightness_changed)
        brightness_card.append(self._brightness_row)

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

        self.append(Gtk.Label(label='Night Light', xalign=0, css_classes=['heading'], margin_start=4))
        night_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._night_light_row = ToggleRow(
            'Night Light',
            'Shifts the display to warmer colors to reduce eye strain.',
        )
        self._night_light_row.switch.connect('state-set', self._on_night_light_toggled)
        night_card.append(self._night_light_row)

        self._schedule_row = DropdownRow('Schedule', [('Sunset to Sunrise', True), ('Manual', False)])
        self._schedule_row.dropdown.connect('notify::selected', self._on_schedule_changed)
        night_card.append(self._schedule_row)

        self._temperature_row = TemperatureRow()
        self._temperature_row.scale.connect('value-changed', self._on_temperature_changed)
        night_card.append(self._temperature_row)
        self.append(night_card)

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

    # ---- Monitor (orientation/resolution/refresh/scale) -----------------

    def _refresh_monitor_row(self):
        available = self._monitor.available
        self._monitor_card.set_visible(available)
        self._monitor_status_label.set_visible(not available)
        if not available:
            return

        self._syncing = True

        self._orientation_row.set_selected_value(self._monitor.logical['transform'])

        resolutions = self._monitor.resolutions()
        self._resolution_row.set_options([
            (_format_resolution(m['w'], m['h']), (m['w'], m['h'])) for m in resolutions
        ])
        current = self._monitor.current_mode()
        if current:
            self._resolution_row.set_selected_value((current['w'], current['h']))
            self._populate_refresh_rates(current['w'], current['h'], select_mode_id=current['id'])
            self._populate_scales(current['id'], select_scale=self._monitor.logical['scale'])

        self._syncing = False

    def _populate_refresh_rates(self, w, h, select_mode_id=None):
        modes = self._monitor.modes_for_resolution(w, h)
        self._refresh_rate_row.set_options([(_format_refresh(m['refresh']), m['id']) for m in modes])
        if select_mode_id:
            self._refresh_rate_row.set_selected_value(select_mode_id)
        elif modes:
            self._refresh_rate_row.set_selected_value(modes[0]['id'])

    def _populate_scales(self, mode_id, select_scale=None):
        mode = next((m for m in self._monitor.modes if m['id'] == mode_id), None)
        scales = mode['scales'] if mode else [1.0]
        self._scale_row.set_options([(_format_scale(s), s) for s in scales])
        if select_scale is not None and select_scale in scales:
            self._scale_row.set_selected_value(select_scale)
        elif scales:
            self._scale_row.set_selected_value(scales[0])

    def _on_orientation_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        self._monitor.apply(transform=self._orientation_row.get_selected_value())
        self._refresh_monitor_row()

    def _on_resolution_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        w, h = self._resolution_row.get_selected_value()
        modes = self._monitor.modes_for_resolution(w, h)
        if not modes:
            return
        best_mode = modes[0]
        self._syncing = True
        self._populate_refresh_rates(w, h, select_mode_id=best_mode['id'])
        self._populate_scales(best_mode['id'])
        self._syncing = False
        self._monitor.apply(mode_id=best_mode['id'], scale=self._scale_row.get_selected_value())
        self._refresh_monitor_row()

    def _on_refresh_rate_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        mode_id = self._refresh_rate_row.get_selected_value()
        if not mode_id:
            return
        self._syncing = True
        self._populate_scales(mode_id, select_scale=self._monitor.logical['scale'])
        self._syncing = False
        self._monitor.apply(mode_id=mode_id, scale=self._scale_row.get_selected_value())
        self._refresh_monitor_row()

    def _on_display_scale_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        mode_id = self._refresh_rate_row.get_selected_value()
        self._monitor.apply(mode_id=mode_id, scale=self._scale_row.get_selected_value())
        self._refresh_monitor_row()

    # ---- Night Light ------------------------------------------------------

    def _refresh_night_light(self):
        self._syncing = True
        self._night_light_row.switch.set_active(self._color_settings.get_boolean('night-light-enabled'))
        self._schedule_row.set_selected_value(self._color_settings.get_boolean('night-light-schedule-automatic'))
        self._temperature_row.scale.set_value(self._color_settings.get_uint('night-light-temperature'))
        self._syncing = False

    def _on_night_light_toggled(self, switch, state):
        if self._syncing:
            return False
        self._color_settings.set_boolean('night-light-enabled', state)
        return False

    def _on_schedule_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        self._color_settings.set_boolean('night-light-schedule-automatic', self._schedule_row.get_selected_value())

    def _on_temperature_changed(self, scale):
        if self._syncing:
            return
        self._color_settings.set_uint('night-light-temperature', round(scale.get_value()))
