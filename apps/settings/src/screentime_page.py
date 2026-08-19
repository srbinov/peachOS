import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

SCREEN_TIME_SCHEMA = 'org.gnome.desktop.screen-time-limits'


class ScreenTimePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(SCREEN_TIME_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'screentime.svg'), 'preferences-system-time-symbolic',
            'Screen Time', "Track how you use your computer, and set a daily time limit.",
        ))

        top_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        history_row = ToggleRow('Track Screen Time', 'Keep a history of how long the computer is used each day.')
        self._settings.bind('history-enabled', history_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        top_card.append(history_row)

        self.append(top_card)

        self.append(Gtk.Label(label='Daily Limit', xalign=0, css_classes=['heading']))

        limit_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        limit_row = ToggleRow('Enable Daily Limit', 'Get a warning when the computer has been used past the limit.')
        self._settings.bind('daily-limit-enabled', limit_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        limit_card.append(limit_row)

        minutes_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        minutes_row.set_margin_start(14)
        minutes_row.set_margin_end(14)
        minutes_row.set_margin_top(10)
        minutes_row.set_margin_bottom(10)
        minutes_row.append(Gtk.Label(label='Limit (minutes per day)', xalign=0, hexpand=True))
        self._minutes_spin = Gtk.SpinButton.new_with_range(15, 24 * 60, 15)
        self._minutes_spin.set_value(self._settings.get_uint('daily-limit-seconds') // 60)
        self._minutes_spin.connect('value-changed', self._on_minutes_changed)
        minutes_row.append(self._minutes_spin)
        limit_card.append(minutes_row)

        minutes_row.set_sensitive(self._settings.get_boolean('daily-limit-enabled'))
        limit_row.switch.connect(
            'notify::active', lambda sw, _p: minutes_row.set_sensitive(sw.get_active()),
        )

        self.append(limit_card)

        self.append(Gtk.Label(label='Options', xalign=0, css_classes=['heading']))

        options_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        grayscale_row = ToggleRow(
            'Grayscale When Limit Reached',
            'Turn the screen grayscale once the daily limit is reached, as a gentle nudge to step away.',
        )
        self._settings.bind('grayscale', grayscale_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        options_card.append(grayscale_row)

        self.append(options_card)

    def _on_minutes_changed(self, spin):
        self._settings.set_uint('daily-limit-seconds', int(spin.get_value()) * 60)
