import os

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

LOGIN_SCREEN_SCHEMA = 'org.gnome.login-screen'
FPRINT_BUS_NAME = 'net.reactivated.Fprint'
FPRINT_MANAGER_PATH = '/net/reactivated/Fprint/Manager'
FPRINT_MANAGER_IFACE = 'net.reactivated.Fprint.Manager'
FPRINT_DEVICE_IFACE = 'net.reactivated.Fprint.Device'

ACCOUNTS_BUS_NAME = 'org.freedesktop.Accounts'
ACCOUNTS_PATH = '/org/freedesktop/Accounts'
ACCOUNTS_IFACE = 'org.freedesktop.Accounts'
USER_IFACE = 'org.freedesktop.Accounts.User'


class _ChangePasswordDialog(Gtk.Window):
    def __init__(self, parent):
        super().__init__(
            title='Change Password', transient_for=parent, modal=True,
            default_width=360, resizable=False,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        self.set_child(box)

        # No "current password" field: AccountsService's SetPassword doesn't take or
        # check one (that's a passwd/PAM-CLI constraint, not this D-Bus API's) -- the
        # polkit prompt this call triggers is what actually confirms it's really you,
        # the same way GNOME's own Users panel relies on it rather than a second,
        # client-side check this dialog isn't in a position to perform correctly anyway.
        box.append(Gtk.Label(label='New Password', xalign=0))
        self._new_entry = Gtk.PasswordEntry(show_peek_icon=True)
        box.append(self._new_entry)

        box.append(Gtk.Label(label='Confirm New Password', xalign=0))
        self._confirm_entry = Gtk.PasswordEntry(show_peek_icon=True)
        box.append(self._confirm_entry)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        box.append(self._error_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label='Cancel')
        cancel_btn.connect('clicked', lambda *_a: self.close())
        button_row.append(cancel_btn)
        self._change_btn = Gtk.Button(label='Change Password', css_classes=['suggested-action'])
        self._change_btn.connect('clicked', self._on_change_clicked)
        button_row.append(self._change_btn)
        box.append(button_row)

    def _on_change_clicked(self, _btn):
        new_password = self._new_entry.get_text()
        if not new_password or new_password != self._confirm_entry.get_text():
            self._error_label.set_label('Passwords must match, and cannot be empty.')
            self._error_label.set_visible(True)
            return

        self._change_btn.set_sensitive(False)
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        try:
            reply = bus.call_sync(
                ACCOUNTS_BUS_NAME, ACCOUNTS_PATH, ACCOUNTS_IFACE, 'FindUserByName',
                GLib.Variant('(s)', (GLib.get_user_name(),)),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
            )
            (user_path,) = reply.unpack()
            bus.call_sync(
                ACCOUNTS_BUS_NAME, user_path, USER_IFACE, 'SetPassword',
                GLib.Variant('(ss)', (new_password, '')),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error as e:
            self._change_btn.set_sensitive(True)
            self._error_label.set_label(e.message)
            self._error_label.set_visible(True)
            return

        self.close()


class TouchIDPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._login_screen = Gio.Settings.new(LOGIN_SCREEN_SCHEMA)
        self._device = None
        self._enrolling = False

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'touchid.svg'), 'fingerprint-symbolic',
            'Touch ID & Password', 'Use a fingerprint reader to unlock peachOS, and manage your password.',
        ))

        self.append(Gtk.Label(label='Password', xalign=0, css_classes=['heading']))
        password_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        password_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        password_row.set_margin_start(14)
        password_row.set_margin_end(14)
        password_row.set_margin_top(10)
        password_row.set_margin_bottom(10)
        password_row.append(Gtk.Label(
            label='A login password has been set for this user.', xalign=0, hexpand=True))
        change_btn = Gtk.Button(label='Change…', css_classes=['flat'])
        change_btn.connect('clicked', self._on_change_password_clicked)
        password_row.append(change_btn)
        password_card.append(password_row)
        self.append(password_card)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'touchid.svg'), 'fingerprint-symbolic',
            'Fingerprint', 'Use your fingerprint reader to unlock peachOS instead of typing your password.',
            icon_size=40,
        ))

        self._fp_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._fp_card)

        self._status_label = Gtk.Label(wrap=True, xalign=0, css_classes=['dim-label'])
        self.append(self._status_label)

        self._enroll_btn = Gtk.Button(label='Enroll Fingerprint…', halign=Gtk.Align.START, visible=False)
        self._enroll_btn.connect('clicked', self._on_enroll_clicked)
        self.append(self._enroll_btn)

        unlock_row = ToggleRow('Use Fingerprint to Unlock peachOS')
        self._login_screen.bind(
            'enable-fingerprint-authentication', unlock_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        self._unlock_row = unlock_row

        self.connect('destroy', self._on_destroy)
        self._probe_device()

    def _on_change_password_clicked(self, _btn):
        dialog = _ChangePasswordDialog(self.get_root())
        dialog.present()

    def _probe_device(self):
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            FPRINT_BUS_NAME, FPRINT_MANAGER_PATH, FPRINT_MANAGER_IFACE, None,
            self._on_manager_proxy_ready,
        )

    def _on_manager_proxy_ready(self, _source, result):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
            devices = proxy.call_sync('GetDevices', None, Gio.DBusCallFlags.NONE, -1, None)
            device_paths = devices.unpack()[0]
        except GLib.Error as e:
            self._show_no_device(f'Fingerprint service is unavailable ({e.message}).')
            return

        if not device_paths:
            self._show_no_device('No fingerprint reader was found on this computer.')
            return

        self._device = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            FPRINT_BUS_NAME, device_paths[0], FPRINT_DEVICE_IFACE, None,
        )
        self._fp_card.append(self._unlock_row)
        self._status_label.set_label('Ready to enroll a fingerprint.')
        self._enroll_btn.set_visible(True)

    def _show_no_device(self, message):
        self._status_label.set_label(message)
        self._enroll_btn.set_visible(False)

    def _on_enroll_clicked(self, _btn):
        if not self._device or self._enrolling:
            return
        self._enrolling = True
        self._enroll_btn.set_sensitive(False)
        self._status_label.set_label('Touch the fingerprint reader…')

        self._signal_id = self._device.connect('g-signal', self._on_device_signal)
        try:
            self._device.call_sync(
                'Claim', GLib.Variant('(s)', ('',)), Gio.DBusCallFlags.NONE, -1, None)
            self._device.call_sync(
                'EnrollStart', GLib.Variant('(s)', ('right-index-finger',)),
                Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not start enrollment: {e.message}')
            self._finish_enrolling()

    def _on_device_signal(self, _proxy, _sender, signal_name, params):
        if signal_name != 'EnrollStatus':
            return
        result, done = params.unpack()
        self._status_label.set_label(f'Enrollment: {result}')
        if done:
            try:
                self._device.call_sync('EnrollStop', None, Gio.DBusCallFlags.NONE, -1, None)
                self._device.call_sync('Release', None, Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error:
                pass
            self._status_label.set_label(
                'Fingerprint enrolled.' if result == 'enroll-completed' else f'Enrollment ended: {result}')
            self._finish_enrolling()

    def _finish_enrolling(self):
        self._enrolling = False
        self._enroll_btn.set_sensitive(True)
        if hasattr(self, '_signal_id') and self._signal_id:
            self._device.disconnect(self._signal_id)
            self._signal_id = 0

    def _on_destroy(self, _widget):
        if self._device and self._enrolling:
            try:
                self._device.call_sync('EnrollStop', None, Gio.DBusCallFlags.NONE, -1, None)
                self._device.call_sync('Release', None, Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error:
                pass
