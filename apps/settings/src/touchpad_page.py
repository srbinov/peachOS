import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, DropdownRow, SliderRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

TOUCHPAD_SCHEMA = 'org.gnome.desktop.peripherals.touchpad'

SECONDARY_CLICK_OPTIONS = [
    ('Off', 'none'),
    ('Click in Corner', 'areas'),
    ('Click or Tap with Two Fingers', 'fingers'),
]


class TouchpadPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(TOUCHPAD_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'touchpad.svg'), 'input-touchpad-symbolic',
            'Trackpad', 'Adjust tracking speed, clicking, and scrolling gestures.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        speed_row = SliderRow('Tracking Speed', -1.0, 1.0, 0.05)
        self._settings.bind('speed', speed_row.scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)
        card.append(speed_row)

        # accel-profile is a 3-way enum ('default'/'flat'/'adaptive'), not a plain bool --
        # 'flat' is real 1:1 movement with no acceleration curve, so that's "off"; anything
        # else ('adaptive' or 'default', both of which apply one) reads as "on".
        accel_row = ToggleRow('Trackpad Acceleration', 'Cursor speed ramps up the faster you move your finger.')
        accel_row.switch.set_active(self._settings.get_string('accel-profile') != 'flat')
        accel_row.switch.connect('notify::active', lambda sw, _p: self._settings.set_string(
            'accel-profile', 'adaptive' if sw.get_active() else 'flat'))
        self._settings.connect('changed::accel-profile', lambda s, k: accel_row.switch.set_active(
            s.get_string(k) != 'flat'))
        card.append(accel_row)

        tap_row = ToggleRow('Tap to Click', 'Tap the trackpad with one finger to click.')
        self._settings.bind('tap-to-click', tap_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(tap_row)

        natural_row = ToggleRow('Natural Scrolling', 'Content tracks the direction your fingers move.')
        self._settings.bind('natural-scroll', natural_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(natural_row)

        two_finger_row = ToggleRow('Two-Finger Scrolling', 'Scroll by dragging two fingers on the trackpad.')
        self._settings.bind(
            'two-finger-scrolling-enabled', two_finger_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(two_finger_row)

        secondary_row = DropdownRow('Secondary Click', SECONDARY_CLICK_OPTIONS)
        secondary_row.set_selected_value(self._settings.get_string('click-method'))
        secondary_row.dropdown.connect('notify::selected', lambda dd, _p: self._settings.set_string(
            'click-method', secondary_row.get_selected_value()))
        card.append(secondary_row)

        self.append(card)
