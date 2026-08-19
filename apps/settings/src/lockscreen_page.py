import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, DropdownRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

POWER_SCHEMA = 'org.gnome.settings-daemon.plugins.power'
SCREENSAVER_SCHEMA = 'org.gnome.desktop.screensaver'
LOGIN_SCREEN_SCHEMA = 'org.gnome.login-screen'

TIMEOUT_OPTIONS = [
    ('Never', 0),
    ('For 1 minute', 60),
    ('For 2 minutes', 120),
    ('For 5 minutes', 300),
    ('For 10 minutes', 600),
    ('For 15 minutes', 900),
    ('For 30 minutes', 1800),
]

LOCK_DELAY_OPTIONS = [
    ('Immediately', 0),
    ('After 1 minute', 60),
    ('After 5 minutes', 300),
    ('After 15 minutes', 900),
    ('After 30 minutes', 1800),
]


class LockScreenPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._power = Gio.Settings.new(POWER_SCHEMA)
        self._screensaver = Gio.Settings.new(SCREENSAVER_SCHEMA)
        self._login_screen = Gio.Settings.new(LOGIN_SCREEN_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'lockscreen.svg'), 'changes-prevent-symbolic',
            'Lock Screen', "Choose when the screen locks, and what's shown while it's locked.",
        ))

        timing_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        battery_row = DropdownRow('Turn display off on battery when inactive', TIMEOUT_OPTIONS)
        battery_row.set_selected_value(self._power.get_int('sleep-inactive-battery-timeout'))
        battery_row.dropdown.connect('notify::selected', lambda dd, _p: self._power.set_int(
            'sleep-inactive-battery-timeout', battery_row.get_selected_value()))
        timing_card.append(battery_row)

        ac_row = DropdownRow('Turn display off on power adapter when inactive', TIMEOUT_OPTIONS)
        ac_row.set_selected_value(self._power.get_int('sleep-inactive-ac-timeout'))
        ac_row.dropdown.connect('notify::selected', lambda dd, _p: self._power.set_int(
            'sleep-inactive-ac-timeout', ac_row.get_selected_value()))
        timing_card.append(ac_row)

        lock_row = DropdownRow('Require password after screen saver begins', LOCK_DELAY_OPTIONS)
        lock_row.set_selected_value(self._screensaver.get_uint('lock-delay'))
        lock_row.dropdown.connect('notify::selected', lambda dd, _p: self._screensaver.set_uint(
            'lock-delay', lock_row.get_selected_value()))
        timing_card.append(lock_row)

        self.append(timing_card)

        message_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        message_row = ToggleRow('Show message when locked', 'Displayed on the lock screen before anyone signs in.')
        self._login_screen.bind('banner-message-enable', message_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        message_card.append(message_row)

        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        entry_row.set_margin_start(14)
        entry_row.set_margin_end(14)
        entry_row.set_margin_top(8)
        entry_row.set_margin_bottom(10)
        self._message_entry = Gtk.Entry(
            hexpand=True, placeholder_text='Message shown on the lock screen',
            text=self._login_screen.get_string('banner-message-text'),
        )
        self._message_entry.connect('changed', lambda e: self._login_screen.set_string(
            'banner-message-text', e.get_text()))
        self._message_entry.set_sensitive(self._login_screen.get_boolean('banner-message-enable'))
        message_row.switch.connect(
            'notify::active', lambda sw, _p: self._message_entry.set_sensitive(sw.get_active()),
        )
        entry_row.append(self._message_entry)
        message_card.append(entry_row)

        self.append(message_card)

        self.append(Gtk.Label(label='When Switching User', xalign=0, css_classes=['heading']))

        switch_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        radio_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, css_classes=['network-row'])
        radio_row.set_margin_start(14)
        radio_row.set_margin_end(14)
        radio_row.set_margin_top(10)
        radio_row.set_margin_bottom(10)
        radio_row.append(Gtk.Label(label='Login window shows', xalign=0, hexpand=True))

        list_users_btn = Gtk.CheckButton(label='List of users')
        name_password_btn = Gtk.CheckButton(label='Name and password', group=list_users_btn)
        if self._login_screen.get_boolean('disable-user-list'):
            name_password_btn.set_active(True)
        else:
            list_users_btn.set_active(True)
        list_users_btn.connect('toggled', lambda b: b.get_active() and self._login_screen.set_boolean(
            'disable-user-list', False))
        name_password_btn.connect('toggled', lambda b: b.get_active() and self._login_screen.set_boolean(
            'disable-user-list', True))
        radio_row.append(list_users_btn)
        radio_row.append(name_password_btn)
        switch_card.append(radio_row)

        power_buttons_row = ToggleRow('Show the Sleep, Restart, and Shut Down buttons')
        power_buttons_row.switch.set_active(not self._login_screen.get_boolean('disable-restart-buttons'))
        power_buttons_row.switch.connect('notify::active', lambda sw, _p: self._login_screen.set_boolean(
            'disable-restart-buttons', not sw.get_active()))
        switch_card.append(power_buttons_row)

        self.append(switch_card)
