import os

from gi.repository import Gio, Gtk

from widgets import IconPlaceholderRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class GroupCard(Gtk.ListBox):
    def __init__(self, rows: list):
        super().__init__(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        for row in rows:
            self.append(row)


class AccessibilityPage(Gtk.Box):
    def __init__(self, on_open_zoom=None, on_open_display=None, on_open_audio=None,
                 on_open_pointer=None, on_open_keyboard=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_open_zoom = on_open_zoom
        self._on_open_display = on_open_display
        self._on_open_audio = on_open_audio
        self._on_open_pointer = on_open_pointer
        self._on_open_keyboard = on_open_keyboard

        self._syncing = False
        self._a11y_apps = Gio.Settings.new('org.gnome.desktop.a11y.applications')
        self._a11y_interface = Gio.Settings.new('org.gnome.desktop.a11y.interface')

        self._build_ui()
        self._connect_settings()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'accessibility.svg'), 'preferences-desktop-accessibility-symbolic',
            'Accessibility', 'Personalize peachOS in ways that work best for you, with accessibility '
                              'features for vision, hearing, and motor control.',
        ))

        self.append(Gtk.Label(label='Vision', xalign=0, css_classes=['heading'], margin_start=4))
        self._voiceover_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._voiceover_switch.connect('state-set', self._on_voiceover_toggled)
        self._motion_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._motion_switch.connect('state-set', self._on_motion_toggled)
        self.append(GroupCard([
            IconPlaceholderRow('VoiceOver', 'audio-speakers-symbolic', 'accent-black', switch=self._voiceover_switch),
            IconPlaceholderRow('Zoom', 'zoom-in-symbolic', 'accent-black', on_click=self._on_open_zoom),
            IconPlaceholderRow('Display', 'video-display-symbolic', 'accent-blue', on_click=self._on_open_display),
            IconPlaceholderRow('Motion', 'object-rotate-right-symbolic', 'accent-green', switch=self._motion_switch),
        ]))

        self.append(Gtk.Label(label='Hearing', xalign=0, css_classes=['heading'], margin_start=4))
        self.append(GroupCard([
            IconPlaceholderRow('Audio', 'audio-volume-high-symbolic', 'accent-red', on_click=self._on_open_audio),
        ]))

        self.append(Gtk.Label(label='Motor', xalign=0, css_classes=['heading'], margin_start=4))
        self._osk_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._osk_switch.connect('state-set', self._on_osk_toggled)
        self.append(GroupCard([
            IconPlaceholderRow('Pointer Control', 'input-mouse-symbolic', 'accent-teal', on_click=self._on_open_pointer),
            IconPlaceholderRow(
                'Keyboard', 'preferences-desktop-keyboard-shortcuts-symbolic', 'accent-lightblue',
                on_click=self._on_open_keyboard,
            ),
            IconPlaceholderRow('On-Screen Keyboard', 'input-keyboard-symbolic', 'accent-darkgray', switch=self._osk_switch),
        ]))

    def _connect_settings(self):
        self._a11y_apps.connect('changed::screen-reader-enabled', lambda *_a: self._refresh())
        self._a11y_apps.connect('changed::screen-keyboard-enabled', lambda *_a: self._refresh())
        self._a11y_interface.connect('changed::reduced-motion', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        try:
            self._voiceover_switch.set_active(self._a11y_apps.get_boolean('screen-reader-enabled'))
            self._osk_switch.set_active(self._a11y_apps.get_boolean('screen-keyboard-enabled'))
            self._motion_switch.set_active(self._a11y_interface.get_string('reduced-motion') == 'reduce')
        finally:
            self._syncing = False

    def _on_voiceover_toggled(self, switch, state):
        if not self._syncing:
            self._a11y_apps.set_boolean('screen-reader-enabled', state)
        return False

    def _on_osk_toggled(self, switch, state):
        if not self._syncing:
            self._a11y_apps.set_boolean('screen-keyboard-enabled', state)
        return False

    def _on_motion_toggled(self, switch, state):
        if not self._syncing:
            self._a11y_interface.set_string('reduced-motion', 'reduce' if state else 'no-preference')
        return False
