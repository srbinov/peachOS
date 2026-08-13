import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class AccessibilityKeyboardPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._syncing = False
        self._kbd_settings = Gio.Settings.new('org.gnome.desktop.a11y.keyboard')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'input-keyboard-symbolic',
            'Keyboard', 'Adjust how the keyboard responds to make it easier to type.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._sticky_row = ToggleRow('Sticky Keys', 'Press modifier keys (like Ctrl or Shift) one at a time instead of together.')
        self._sticky_row.switch.connect('state-set', self._on_sticky_toggled)
        card.append(self._sticky_row)

        self._slow_row = ToggleRow('Slow Keys', 'Require keys to be held down for a while before they register.')
        self._slow_row.switch.connect('state-set', self._on_slow_toggled)
        card.append(self._slow_row)

        self._slow_delay_row = SliderRow('Acceptance Delay', 100, 2000, 50)
        self._slow_delay_row.scale.connect('value-changed', self._on_slow_delay_changed)
        card.append(self._slow_delay_row)

        self._bounce_row = ToggleRow('Bounce Keys', 'Ignore fast, repeated key presses of the same key.')
        self._bounce_row.switch.connect('state-set', self._on_bounce_toggled)
        card.append(self._bounce_row)

        self._bounce_delay_row = SliderRow('Acceptance Delay', 100, 2000, 50)
        self._bounce_delay_row.scale.connect('value-changed', self._on_bounce_delay_changed)
        card.append(self._bounce_delay_row)

        self.append(card)

    def _connect_settings(self):
        for key in ('stickykeys-enable', 'slowkeys-enable', 'slowkeys-delay', 'bouncekeys-enable', 'bouncekeys-delay'):
            self._kbd_settings.connect(f'changed::{key}', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._sticky_row.switch.set_active(self._kbd_settings.get_boolean('stickykeys-enable'))
            self._slow_row.switch.set_active(self._kbd_settings.get_boolean('slowkeys-enable'))
            self._slow_delay_row.scale.set_value(self._kbd_settings.get_int('slowkeys-delay'))
            self._bounce_row.switch.set_active(self._kbd_settings.get_boolean('bouncekeys-enable'))
            self._bounce_delay_row.scale.set_value(self._kbd_settings.get_int('bouncekeys-delay'))
        finally:
            self._syncing = False

    def _on_sticky_toggled(self, switch, state):
        if not self._syncing:
            self._kbd_settings.set_boolean('stickykeys-enable', state)
        return False

    def _on_slow_toggled(self, switch, state):
        if not self._syncing:
            self._kbd_settings.set_boolean('slowkeys-enable', state)
        return False

    def _on_slow_delay_changed(self, scale):
        if not self._syncing:
            self._kbd_settings.set_int('slowkeys-delay', round(scale.get_value()))

    def _on_bounce_toggled(self, switch, state):
        if not self._syncing:
            self._kbd_settings.set_boolean('bouncekeys-enable', state)
        return False

    def _on_bounce_delay_changed(self, scale):
        if not self._syncing:
            self._kbd_settings.set_int('bouncekeys-delay', round(scale.get_value()))
