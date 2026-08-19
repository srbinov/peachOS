import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, SliderRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

KEYBOARD_SCHEMA = 'org.gnome.desktop.peripherals.keyboard'


class KeyboardPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(KEYBOARD_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'keyboard.svg'), 'input-keyboard-symbolic',
            'Keyboard', 'Set how quickly keys repeat, and manage your typing preferences.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        repeat_row = ToggleRow('Key Repeat', 'Press and hold a key to repeat it.')
        self._settings.bind('repeat', repeat_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(repeat_row)

        # Lower repeat-interval == faster repeats, so the slider is inverted to keep the
        # visual "Slow -> Fast" reading left-to-right natural rather than backwards.
        rate_row = SliderRow('Key Repeat Rate', 20, 200, 5)
        rate_row.scale.set_inverted(True)
        self._settings.bind('repeat-interval', rate_row.scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)
        card.append(rate_row)

        delay_row = SliderRow('Delay Until Repeat', 100, 2000, 50)
        delay_row.scale.set_inverted(True)
        self._settings.bind('delay', delay_row.scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)
        card.append(delay_row)

        self.append(card)
