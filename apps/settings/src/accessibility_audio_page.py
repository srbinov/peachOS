import os

from gi.repository import Gio, Gtk

from widgets import DropdownRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

FLASH_OPTIONS = [
    ('Flash Entire Screen', 'fullscreen-flash'),
    ('Flash Window Title', 'frame-flash'),
]


class AccessibilityAudioPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._syncing = False
        self._wm_settings = Gio.Settings.new('org.gnome.desktop.wm.preferences')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'audio-volume-high-symbolic',
            'Audio', 'Use visual alerts instead of, or in addition to, alert sounds.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._audible_row = ToggleRow('Play Alert Sound')
        self._audible_row.switch.connect('state-set', self._on_audible_toggled)
        card.append(self._audible_row)

        self._flash_row = ToggleRow('Flash Screen for Alert Sound')
        self._flash_row.switch.connect('state-set', self._on_flash_toggled)
        card.append(self._flash_row)

        self._flash_type_row = DropdownRow('Flash Type', FLASH_OPTIONS)
        self._flash_type_row.dropdown.connect('notify::selected', self._on_flash_type_changed)
        card.append(self._flash_type_row)

        self.append(card)

    def _connect_settings(self):
        self._wm_settings.connect('changed::audible-bell', lambda *_a: self._refresh())
        self._wm_settings.connect('changed::visual-bell', lambda *_a: self._refresh())
        self._wm_settings.connect('changed::visual-bell-type', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._audible_row.switch.set_active(self._wm_settings.get_boolean('audible-bell'))
            self._flash_row.switch.set_active(self._wm_settings.get_boolean('visual-bell'))
            self._flash_type_row.set_selected_value(self._wm_settings.get_string('visual-bell-type'))
        finally:
            self._syncing = False

    def _on_audible_toggled(self, switch, state):
        if not self._syncing:
            self._wm_settings.set_boolean('audible-bell', state)
        return False

    def _on_flash_toggled(self, switch, state):
        if not self._syncing:
            self._wm_settings.set_boolean('visual-bell', state)
        return False

    def _on_flash_type_changed(self, dropdown, _pspec):
        if not self._syncing:
            self._wm_settings.set_string('visual-bell-type', self._flash_type_row.get_selected_value())
