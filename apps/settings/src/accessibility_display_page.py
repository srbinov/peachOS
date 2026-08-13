import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class AccessibilityDisplayPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._syncing = False
        self._a11y_settings = Gio.Settings.new('org.gnome.desktop.a11y.interface')
        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility_display.svg'), 'video-display-symbolic',
            'Display', 'Adjust contrast, pointer size, and text size to make the screen easier to see.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._contrast_row = ToggleRow('Increase Contrast', 'Increase the contrast of on-screen elements.')
        self._contrast_row.switch.connect('state-set', self._on_contrast_toggled)
        card.append(self._contrast_row)

        self._pointer_row = SliderRow('Pointer Size', 24, 96, 1)
        self._pointer_row.scale.connect('value-changed', self._on_pointer_changed)
        card.append(self._pointer_row)

        self._text_row = SliderRow('Text Size', 0.5, 3.0, 0.05)
        self._text_row.scale.connect('value-changed', self._on_text_changed)
        card.append(self._text_row)

        self.append(card)

    def _connect_settings(self):
        self._a11y_settings.connect('changed::high-contrast', lambda *_a: self._refresh())
        self._interface_settings.connect('changed::cursor-size', lambda *_a: self._refresh())
        self._interface_settings.connect('changed::text-scaling-factor', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._contrast_row.switch.set_active(self._a11y_settings.get_boolean('high-contrast'))
            self._pointer_row.scale.set_value(self._interface_settings.get_int('cursor-size'))
            self._text_row.scale.set_value(self._interface_settings.get_double('text-scaling-factor'))
        finally:
            self._syncing = False

    def _on_contrast_toggled(self, switch, state):
        if not self._syncing:
            self._a11y_settings.set_boolean('high-contrast', state)
        return False

    def _on_pointer_changed(self, scale):
        if not self._syncing:
            self._interface_settings.set_int('cursor-size', round(scale.get_value()))

    def _on_text_changed(self, scale):
        if not self._syncing:
            self._interface_settings.set_double('text-scaling-factor', scale.get_value())
