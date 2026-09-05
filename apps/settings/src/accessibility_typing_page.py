import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

A11Y_KEYBOARD = 'org.gnome.desktop.a11y.keyboard'
A11Y_APPS = 'org.gnome.desktop.a11y.applications'
INTERFACE = 'org.gnome.desktop.interface'


class AccessibilityTypingPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._kbd = Gio.Settings.new(A11Y_KEYBOARD)
        self._apps = Gio.Settings.new(A11Y_APPS)
        self._interface = Gio.Settings.new(INTERFACE)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'input-keyboard-symbolic',
            'Typing', 'Assistance for typing, including an on-screen keyboard and key filters.',
        ))

        general = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        osk_row = ToggleRow('On-Screen Keyboard', 'Show a keyboard on screen for typing without hardware keys.')
        self._apps.bind('screen-keyboard-enabled', osk_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(osk_row)

        blink_row = ToggleRow('Cursor Blinking', 'Blink the text cursor in editable fields.')
        self._interface.bind('cursor-blink', blink_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(blink_row)

        self._blink_speed = SliderRow('Cursor Blink Speed', 100, 2500, 100)
        self._interface.bind('cursor-blink-time', self._blink_speed.scale.get_adjustment(),
                             'value', Gio.SettingsBindFlags.DEFAULT)
        general.append(self._blink_speed)

        enable_row = ToggleRow('Enable by Keyboard',
                               'Turn accessibility features on or off from the keyboard.')
        self._kbd.bind('enable', enable_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(enable_row)
        self.append(general)

        self.append(Gtk.Label(label='Key Filters', xalign=0, css_classes=['heading'], margin_start=4))
        filters = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        sticky_row = ToggleRow('Sticky Keys', 'Press modifier keys one at a time instead of together.')
        self._kbd.bind('stickykeys-enable', sticky_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        filters.append(sticky_row)

        slow_row = ToggleRow('Slow Keys', 'Require a key to be held down briefly before it registers.')
        self._kbd.bind('slowkeys-enable', slow_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        filters.append(slow_row)
        self._slow_delay = SliderRow('Slow Keys Delay', 0, 500, 10)
        self._kbd.bind('slowkeys-delay', self._slow_delay.scale.get_adjustment(),
                       'value', Gio.SettingsBindFlags.DEFAULT)
        filters.append(self._slow_delay)

        bounce_row = ToggleRow('Bounce Keys', 'Ignore fast repeated presses of the same key.')
        self._kbd.bind('bouncekeys-enable', bounce_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        filters.append(bounce_row)
        self._bounce_delay = SliderRow('Bounce Keys Delay', 0, 900, 10)
        self._kbd.bind('bouncekeys-delay', self._bounce_delay.scale.get_adjustment(),
                       'value', Gio.SettingsBindFlags.DEFAULT)
        filters.append(self._bounce_delay)
        self.append(filters)
