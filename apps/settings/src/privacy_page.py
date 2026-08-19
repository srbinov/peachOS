import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

PRIVACY_SCHEMA = 'org.gnome.desktop.privacy'
LOCATION_SCHEMA = 'org.gnome.system.location'


def _section(page: Gtk.Box, heading: str):
    page.append(Gtk.Label(label=heading, xalign=0, css_classes=['heading']))
    card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
    page.append(card)
    return card


class PrivacyPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._privacy = Gio.Settings.new(PRIVACY_SCHEMA)
        self._location = Gio.Settings.new(LOCATION_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'privacy.svg'), 'preferences-system-privacy-symbolic',
            'Privacy & Security', "Control what apps can access, and how your data is handled.",
        ))

        location_card = _section(self, 'Location Services')
        location_row = ToggleRow('Location Services', 'Allow apps to determine your approximate location.')
        self._location.bind('enabled', location_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        location_card.append(location_row)

        hardware_card = _section(self, 'Camera & Microphone')
        camera_row = ToggleRow('Camera', 'Allow apps to access the camera.')
        self._bind_inverted('disable-camera', camera_row.switch)
        hardware_card.append(camera_row)

        mic_row = ToggleRow('Microphone', 'Allow apps to access the microphone.')
        self._bind_inverted('disable-microphone', mic_row.switch)
        hardware_card.append(mic_row)

        sound_row = ToggleRow('Sound Output', 'Allow apps to play sound.')
        self._bind_inverted('disable-sound-output', sound_row.switch)
        hardware_card.append(sound_row)

        files_card = _section(self, 'File History & Trash')
        recent_row = ToggleRow('Remember Recent Files', 'Keep a list of recently opened files and folders.')
        self._privacy.bind('remember-recent-files', recent_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        files_card.append(recent_row)

        trash_row = ToggleRow('Automatically Empty Trash', 'Permanently delete old items from the Trash.')
        self._privacy.bind('remove-old-trash-files', trash_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        files_card.append(trash_row)

        temp_row = ToggleRow('Automatically Delete Temporary Files', 'Remove old temporary files apps no longer need.')
        self._privacy.bind('remove-old-temp-files', temp_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        files_card.append(temp_row)

        diagnostics_card = _section(self, 'Analytics & Diagnostics')
        usage_row = ToggleRow('Share System & App Usage Data', 'Help improve peachOS by sharing anonymous usage statistics.')
        self._privacy.bind('send-software-usage-stats', usage_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        diagnostics_card.append(usage_row)

        reports_row = ToggleRow('Automatically Send Technical Reports', 'Send crash and technical reports to help fix problems.')
        self._privacy.bind('report-technical-problems', reports_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        diagnostics_card.append(reports_row)

        app_usage_row = ToggleRow('Remember Application Usage', 'Let the system learn which apps you use most, for smarter suggestions.')
        self._privacy.bind('remember-app-usage', app_usage_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        diagnostics_card.append(app_usage_row)

        security_card = _section(self, 'Security')
        usb_row = ToggleRow('USB Protection', 'Block new USB devices from accessing the system while the screen is locked.')
        self._privacy.bind('usb-protection', usb_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        security_card.append(usb_row)

    def _bind_inverted(self, key: str, switch: Gtk.Switch):
        """disable-camera/-microphone/-sound-output are phrased as "disable",
        but the row reads as the positive "allow" action -- bind manually
        instead of Gio.Settings.bind's INVERT_BOOLEAN flag combo, which
        needs matching property types on both ends and is easy to get
        backwards; this is unambiguous in both directions."""
        switch.set_active(not self._privacy.get_boolean(key))
        switch.connect('notify::active', lambda sw, _p: self._privacy.set_boolean(key, not sw.get_active()))
        self._privacy.connect(f'changed::{key}', lambda s, k: switch.set_active(not s.get_boolean(k)))
