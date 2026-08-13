import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class AccessibilityPointerPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._syncing = False
        self._mouse_settings = Gio.Settings.new('org.gnome.desktop.a11y.mouse')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'input-mouse-symbolic',
            'Pointer Control', 'Adjust how clicks work if pressing a physical button is difficult.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._hover_row = ToggleRow('Hover Click', 'Trigger a click by holding the pointer still.')
        self._hover_row.switch.connect('state-set', self._on_hover_toggled)
        card.append(self._hover_row)

        self._hover_delay_row = SliderRow('Hover Click Delay', 0.3, 5.0, 0.1)
        self._hover_delay_row.scale.connect('value-changed', self._on_hover_delay_changed)
        card.append(self._hover_delay_row)

        self._secondary_row = ToggleRow('Simulated Secondary Click', 'Trigger a right-click by holding the left button down.')
        self._secondary_row.switch.connect('state-set', self._on_secondary_toggled)
        card.append(self._secondary_row)

        self._secondary_delay_row = SliderRow('Secondary Click Delay', 0.3, 5.0, 0.1)
        self._secondary_delay_row.scale.connect('value-changed', self._on_secondary_delay_changed)
        card.append(self._secondary_delay_row)

        self.append(card)

    def _connect_settings(self):
        for key in ('dwell-click-enabled', 'dwell-time', 'secondary-click-enabled', 'secondary-click-time'):
            self._mouse_settings.connect(f'changed::{key}', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._hover_row.switch.set_active(self._mouse_settings.get_boolean('dwell-click-enabled'))
            self._hover_delay_row.scale.set_value(self._mouse_settings.get_double('dwell-time'))
            self._secondary_row.switch.set_active(self._mouse_settings.get_boolean('secondary-click-enabled'))
            self._secondary_delay_row.scale.set_value(self._mouse_settings.get_double('secondary-click-time'))
        finally:
            self._syncing = False

    def _on_hover_toggled(self, switch, state):
        if not self._syncing:
            self._mouse_settings.set_boolean('dwell-click-enabled', state)
        return False

    def _on_hover_delay_changed(self, scale):
        if not self._syncing:
            self._mouse_settings.set_double('dwell-time', scale.get_value())

    def _on_secondary_toggled(self, switch, state):
        if not self._syncing:
            self._mouse_settings.set_boolean('secondary-click-enabled', state)
        return False

    def _on_secondary_delay_changed(self, scale):
        if not self._syncing:
            self._mouse_settings.set_double('secondary-click-time', scale.get_value())
