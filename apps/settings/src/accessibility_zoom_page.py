import os

from gi.repository import Gio, Gtk

from widgets import SliderRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class AccessibilityZoomPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._syncing = False
        self._apps_settings = Gio.Settings.new('org.gnome.desktop.a11y.applications')
        self._mag_settings = Gio.Settings.new('org.gnome.desktop.a11y.magnifier')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'zoom-in-symbolic',
            'Zoom', 'Use the pointer or keyboard shortcuts to zoom in on the screen.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._enabled_row = ToggleRow('Use Zoom', 'Magnify the screen to make it easier to see.')
        self._enabled_row.switch.connect('state-set', self._on_enabled_toggled)
        card.append(self._enabled_row)

        self._zoom_row = SliderRow('Zoom Level', 1.0, 8.0, 0.1)
        self._zoom_row.scale.connect('value-changed', self._on_zoom_changed)
        card.append(self._zoom_row)

        self._lens_row = ToggleRow('Lens Mode', 'Move a magnifying lens around with the pointer, instead of zooming the whole screen.')
        self._lens_row.switch.connect('state-set', self._on_lens_toggled)
        card.append(self._lens_row)

        self.append(card)

    def _connect_settings(self):
        self._apps_settings.connect('changed::screen-magnifier-enabled', lambda *_a: self._refresh())
        self._mag_settings.connect('changed::mag-factor', lambda *_a: self._refresh())
        self._mag_settings.connect('changed::lens-mode', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._enabled_row.switch.set_active(self._apps_settings.get_boolean('screen-magnifier-enabled'))
            self._zoom_row.scale.set_value(self._mag_settings.get_double('mag-factor'))
            self._lens_row.switch.set_active(self._mag_settings.get_boolean('lens-mode'))
        finally:
            self._syncing = False

    def _on_enabled_toggled(self, switch, state):
        if not self._syncing:
            self._apps_settings.set_boolean('screen-magnifier-enabled', state)
        return False

    def _on_zoom_changed(self, scale):
        if not self._syncing:
            self._mag_settings.set_double('mag-factor', scale.get_value())

    def _on_lens_toggled(self, switch, state):
        if not self._syncing:
            self._mag_settings.set_boolean('lens-mode', state)
        return False
