import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, SliderRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

MOUSE_SCHEMA = 'org.gnome.desktop.peripherals.mouse'


class MousePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(MOUSE_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'mouse.svg'), 'input-mouse-symbolic',
            'Mouse', 'Adjust tracking speed, scrolling, and button behavior.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        speed_row = SliderRow('Tracking Speed', -1.0, 1.0, 0.05)
        self._settings.bind('speed', speed_row.scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)
        card.append(speed_row)

        # accel-profile is a 3-way enum ('default'/'flat'/'adaptive'), not a plain bool, but
        # the row only needs to offer the same on/off choice macOS does -- 'flat' is real
        # 1:1 movement with no acceleration curve applied, so that's "off"; anything else
        # ('adaptive' or 'default', both of which apply one) reads as "on".
        accel_row = ToggleRow('Mouse Acceleration', 'Cursor speed ramps up the faster you move the mouse.')
        accel_row.switch.set_active(self._settings.get_string('accel-profile') != 'flat')
        accel_row.switch.connect('notify::active', lambda sw, _p: self._settings.set_string(
            'accel-profile', 'adaptive' if sw.get_active() else 'flat'))
        self._settings.connect('changed::accel-profile', lambda s, k: accel_row.switch.set_active(
            s.get_string(k) != 'flat'))
        card.append(accel_row)

        natural_row = ToggleRow('Natural Scrolling', 'Content tracks the direction your scroll wheel moves.')
        self._settings.bind('natural-scroll', natural_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(natural_row)

        left_handed_row = ToggleRow('Left-Handed', 'Swap the primary and secondary mouse buttons.')
        self._settings.bind('left-handed', left_handed_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(left_handed_row)

        self.append(card)
