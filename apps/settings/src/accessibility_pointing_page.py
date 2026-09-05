import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

A11Y_MOUSE = 'org.gnome.desktop.a11y.mouse'
A11Y_KEYBOARD = 'org.gnome.desktop.a11y.keyboard'
INTERFACE = 'org.gnome.desktop.interface'
MOUSE = 'org.gnome.desktop.peripherals.mouse'


class _DoubleBoundSlider(SliderRow):
    """SliderRow bound to a settings key that stores seconds as a double, but
    reads more naturally to the user as a plain 0.5-3.0 range."""

    def __init__(self, title, settings, key):
        super().__init__(title, 0.5, 3.0, 0.1)
        settings.bind(key, self.scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)


class AccessibilityPointingPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._mouse_a11y = Gio.Settings.new(A11Y_MOUSE)
        self._kbd_a11y = Gio.Settings.new(A11Y_KEYBOARD)
        self._interface = Gio.Settings.new(INTERFACE)
        self._mouse = Gio.Settings.new(MOUSE)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'input-mouse-symbolic',
            'Pointing & Clicking', 'Assistance for using the pointer, including click alternatives.',
        ))

        general = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        mousekeys_row = ToggleRow('Mouse Keys', 'Move the pointer with the numeric keypad.')
        self._kbd_a11y.bind('mousekeys-enable', mousekeys_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(mousekeys_row)

        locate_row = ToggleRow('Locate Pointer', 'Press Ctrl to highlight the pointer location.')
        self._interface.bind('locate-pointer', locate_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(locate_row)

        self._double_click = SliderRow('Double-Click Delay', 100, 1000, 50)
        self._mouse.bind('double-click', self._double_click.scale.get_adjustment(),
                         'value', Gio.SettingsBindFlags.DEFAULT)
        general.append(self._double_click)
        self.append(general)

        self.append(Gtk.Label(label='Click Assist', xalign=0, css_classes=['heading'], margin_start=4))
        assist = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        secondary_row = ToggleRow('Simulated Secondary Click',
                                  'Trigger a right-click by holding down the primary button.')
        self._mouse_a11y.bind('secondary-click-enabled', secondary_row.switch, 'active',
                              Gio.SettingsBindFlags.DEFAULT)
        assist.append(secondary_row)
        assist.append(_DoubleBoundSlider('Hold Delay', self._mouse_a11y, 'secondary-click-time'))

        hover_row = ToggleRow('Hover Click', 'Click automatically when the pointer stops moving.')
        self._mouse_a11y.bind('dwell-click-enabled', hover_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        assist.append(hover_row)
        assist.append(_DoubleBoundSlider('Hover Delay', self._mouse_a11y, 'dwell-time'))
        self.append(assist)
