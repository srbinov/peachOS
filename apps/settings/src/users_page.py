import os

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

ACCOUNTS_BUS_NAME = 'org.freedesktop.Accounts'
ACCOUNTS_PATH = '/org/freedesktop/Accounts'
ACCOUNTS_IFACE = 'org.freedesktop.Accounts'
USER_IFACE = 'org.freedesktop.Accounts.User'

ACCOUNT_TYPE_STANDARD = 0
ACCOUNT_TYPE_ADMIN = 1


def _user_row(user_proxy) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
    row.set_margin_start(14)
    row.set_margin_end(14)
    row.set_margin_top(8)
    row.set_margin_bottom(8)

    icon_file = user_proxy.get_cached_property('IconFile').unpack()
    if icon_file and os.path.isfile(icon_file):
        icon = Gtk.Image.new_from_file(icon_file)
    else:
        icon = Gtk.Image.new_from_icon_name('avatar-default-symbolic')
    icon.set_pixel_size(32)
    row.append(icon)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
    real_name = user_proxy.get_cached_property('RealName').unpack() or user_proxy.get_cached_property(
        'UserName').unpack()
    text_box.append(Gtk.Label(label=real_name, xalign=0))
    account_type = user_proxy.get_cached_property('AccountType').unpack()
    locked = user_proxy.get_cached_property('Locked').unpack()
    subtitle = 'Disabled' if locked else ('Admin' if account_type == ACCOUNT_TYPE_ADMIN else 'Standard')
    text_box.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['caption', 'dim-label']))
    row.append(text_box)

    return row


class _AddUserDialog(Gtk.Window):
    def __init__(self, parent, on_added):
        super().__init__(
            title='Add User', transient_for=parent, modal=True,
            default_width=380, resizable=False,
        )
        self._on_added = on_added

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        self.set_child(box)

        box.append(Gtk.Label(label='Full Name', xalign=0))
        self._fullname_entry = Gtk.Entry(placeholder_text='e.g. Alex Rivera')
        self._fullname_entry.connect('changed', self._on_fullname_changed)
        box.append(self._fullname_entry)

        box.append(Gtk.Label(label='Account Name', xalign=0))
        self._username_entry = Gtk.Entry(placeholder_text='e.g. alex')
        box.append(self._username_entry)
        self._username_edited = False
        self._username_entry.connect('changed', lambda _e: setattr(self, '_username_edited', True))

        box.append(Gtk.Label(label='Password', xalign=0))
        self._password_entry = Gtk.PasswordEntry(show_peek_icon=True)
        box.append(self._password_entry)

        type_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        type_row.append(Gtk.Label(label='Account Type', xalign=0, hexpand=True))
        self._standard_btn = Gtk.CheckButton(label='Standard', active=True)
        self._admin_btn = Gtk.CheckButton(label='Admin', group=self._standard_btn)
        type_row.append(self._standard_btn)
        type_row.append(self._admin_btn)
        box.append(type_row)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        box.append(self._error_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label='Cancel')
        cancel_btn.connect('clicked', lambda *_a: self.close())
        button_row.append(cancel_btn)
        self._add_btn = Gtk.Button(label='Create User', css_classes=['suggested-action'])
        self._add_btn.connect('clicked', self._on_create_clicked)
        button_row.append(self._add_btn)
        box.append(button_row)

    def _on_fullname_changed(self, entry):
        # Keeps the account-name suggestion in sync with the full name, same as GNOME's
        # own Add User dialog -- but only until the user actually types their own
        # username, so it never clobbers a deliberate choice.
        if self._username_edited:
            return
        suggestion = entry.get_text().strip().lower().split(' ')
        suggestion = ''.join(ch for ch in (suggestion[0] if suggestion else '') if ch.isalnum())
        self._username_entry.set_text(suggestion)
        self._username_edited = False

    def _on_create_clicked(self, _btn):
        fullname = self._fullname_entry.get_text().strip()
        username = self._username_entry.get_text().strip()
        password = self._password_entry.get_text()
        if not fullname or not username or not password:
            self._error_label.set_label('Fill in a full name, account name, and password.')
            self._error_label.set_visible(True)
            return

        account_type = ACCOUNT_TYPE_ADMIN if self._admin_btn.get_active() else ACCOUNT_TYPE_STANDARD
        self._add_btn.set_sensitive(False)

        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        try:
            reply = bus.call_sync(
                ACCOUNTS_BUS_NAME, ACCOUNTS_PATH, ACCOUNTS_IFACE, 'CreateUser',
                GLib.Variant('(ssi)', (username, fullname, account_type)),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
            )
            (user_path,) = reply.unpack()
            bus.call_sync(
                ACCOUNTS_BUS_NAME, user_path, USER_IFACE, 'SetPassword',
                GLib.Variant('(ss)', (password, '')),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error as e:
            self._add_btn.set_sensitive(True)
            self._error_label.set_label(e.message)
            self._error_label.set_visible(True)
            return

        self._on_added()
        self.close()


class UsersPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'users.svg'), 'system-users-symbolic',
            'Users & Groups', 'Manage who can sign in to this computer, and what they can do.',
        ))

        self._user_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._user_list)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        add_btn = Gtk.Button(label='Add User…', css_classes=['flat'])
        add_btn.connect('clicked', self._on_add_clicked)
        button_row.append(add_btn)
        self.append(button_row)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['dim-label'], visible=False)
        self.append(self._error_label)

        self._load_users()

    def _on_add_clicked(self, _btn):
        dialog = _AddUserDialog(self.get_root(), on_added=self._load_users)
        dialog.present()

    def _load_users(self):
        child = self._user_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._user_list.remove(child)
            child = next_child

        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            ACCOUNTS_BUS_NAME, ACCOUNTS_PATH, ACCOUNTS_IFACE, None,
            self._on_accounts_proxy_ready,
        )

    def _on_accounts_proxy_ready(self, _source, result):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
            reply = proxy.call_sync('ListCachedUsers', None, Gio.DBusCallFlags.NONE, -1, None)
            user_paths = reply.unpack()[0]
        except GLib.Error as e:
            self._error_label.set_label(f'Could not load users: {e.message}')
            self._error_label.set_visible(True)
            return

        for path in user_paths:
            try:
                user_proxy = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                    ACCOUNTS_BUS_NAME, path, USER_IFACE, None,
                )
            except GLib.Error:
                continue
            self._user_list.append(_user_row(user_proxy))
