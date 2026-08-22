import os

import gi

gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

import avatar_picker
from appearance_page import ACCENT_COLORS, ColorSwatch
from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

ACCOUNTS_BUS_NAME = 'org.freedesktop.Accounts'
ACCOUNTS_PATH = '/org/freedesktop/Accounts'
ACCOUNTS_IFACE = 'org.freedesktop.Accounts'
USER_IFACE = 'org.freedesktop.Accounts.User'

ACCOUNT_TYPE_STANDARD = 0
ACCOUNT_TYPE_ADMIN = 1

# Where a newly picked/composited avatar gets staged before being handed to
# SetIconFile. accounts-daemon copies whatever file this points at into its
# own cache (confirmed live: it does NOT just store this path -- IconFile
# reads back as a fixed accounts-daemon-managed location regardless), so
# this only ever needs to hold the most recent staged image, not a
# permanent per-user gallery.
AVATAR_STAGING_DIR = os.path.expanduser('~/.local/share/peachos-settings/avatars')

# accounts-daemon's own icon cache -- confirmed live (see users_page work
# session) that this is where SetIconFile-supplied images actually end up,
# NOT at the IconFile property's own value (that read back as ~/.face even
# though no such file existed on disk). World-readable (0644), so any user
# can display any account's current avatar without elevation.
ACCOUNTS_ICON_CACHE_DIR = '/var/lib/AccountsService/icons'


def _resolve_avatar_display_path(username: str, icon_file: str | None) -> str | None:
    cache_path = os.path.join(ACCOUNTS_ICON_CACHE_DIR, username)
    if os.path.isfile(cache_path):
        return cache_path
    if icon_file and os.path.isfile(icon_file):
        return icon_file
    return None


def get_current_user_path() -> str:
    """The AccountsService object path for whoever is running this process
    -- used both by the sidebar's own sign-in row (main.py) and by
    UsersPage to tell "you edited your own account" apart from any other
    user's row."""
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    reply = bus.call_sync(
        ACCOUNTS_BUS_NAME, ACCOUNTS_PATH, ACCOUNTS_IFACE, 'FindUserByName',
        GLib.Variant('(s)', (GLib.get_user_name(),)),
        GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
    )
    (user_path,) = reply.unpack()
    return user_path


def _load_scaled_picture(path: str, size: int) -> Gtk.Widget:
    """Cover-fit, pre-rasterized to `size` -- same reasoning as this app's
    other _load_scaled_picture helpers (appearance_page.py/wallpaper_page.py):
    Gtk.Picture's natural size otherwise comes from the source file, not the
    requested display size."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, False)
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    picture = Gtk.Picture.new_for_paintable(texture)
    picture.set_content_fit(Gtk.ContentFit.COVER)
    return picture


def _circular_avatar(path: str | None, size: int, fallback_text: str = '') -> Gtk.Widget:
    """A real photo/emoji composite when one's set; otherwise the same
    colored-initials look the sidebar's own sign-in row already uses
    (Adw.Avatar) -- a plain gray silhouette here read as broken/inconsistent
    next to that (explicit user feedback), not just "no photo yet"."""
    if not path:
        return Adw.Avatar(size=size, text=fallback_text, show_initials=True)
    wrap = Gtk.Box(width_request=size, height_request=size, css_classes=['avatar-circle'])
    wrap.set_overflow(Gtk.Overflow.HIDDEN)
    wrap.append(_load_scaled_picture(path, size))
    return wrap


def _user_row(user_proxy, user_path: str) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.user_path = user_path

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
    box.set_margin_start(14)
    box.set_margin_end(14)
    box.set_margin_top(8)
    box.set_margin_bottom(8)
    row.set_child(box)

    username = user_proxy.get_cached_property('UserName').unpack()
    row.username = username
    icon_file = user_proxy.get_cached_property('IconFile').unpack()
    real_name = user_proxy.get_cached_property('RealName').unpack() or username
    box.append(_circular_avatar(_resolve_avatar_display_path(username, icon_file), 32, fallback_text=real_name))

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
    text_box.append(Gtk.Label(label=real_name, xalign=0))
    account_type = user_proxy.get_cached_property('AccountType').unpack()
    locked = user_proxy.get_cached_property('Locked').unpack()
    subtitle = 'Disabled' if locked else ('Admin' if account_type == ACCOUNT_TYPE_ADMIN else 'Standard')
    text_box.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['caption', 'dim-label']))
    box.append(text_box)

    chevron = Gtk.Image.new_from_icon_name('go-next-symbolic')
    chevron.add_css_class('dim-label')
    box.append(chevron)

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


class EditProfilePage(Gtk.Box):
    """A real page in the same nav stack as every other tab (General, About,
    ...) -- not a popup window. Explicit user correction: the sign-in row
    and Users & Groups both used to open this as a separate Gtk.Window,
    which read as inconsistent next to the rest of the app's drill-in pages
    (General -> About, etc.), all of which slide within the one content
    pane and share its back/forward history instead of stacking a floating
    dialog on top.

    One instance is built once (see main.py) and reused for whichever
    account is being edited -- load_user(path) repopulates it rather than
    constructing a fresh page per click, same reasoning as bluebubbles-
    native's ConversationView.show_chat().

    Rename / re-photo an existing account -- SetRealName + SetIconFile,
    both confirmed live to work self-service (no polkit prompt) for a
    user's own account; editing someone else's account still routes through
    the exact same calls; whatever polkit does with those (prompt, deny) is
    surfaced through the normal error label below, not special-cased here.
    """

    def __init__(self, on_saved, go_back):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_saved = on_saved
        self._go_back = go_back
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self._user_path: str | None = None
        self._username = ''
        self._real_name = ''
        self._current_display_path: str | None = None
        self._staged_avatar_path: str | None = None
        self._chosen_emoji_path: str | None = None

        self._avatar_holder = Gtk.Box(halign=Gtk.Align.CENTER)
        self.append(self._avatar_holder)

        change_photo_btn = Gtk.Button(label='Change Photo…', halign=Gtk.Align.CENTER, css_classes=['flat'])
        change_photo_btn.connect('clicked', self._on_avatar_button_clicked)
        self.append(change_photo_btn)

        self._color_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER, visible=False)
        self._color_swatches: list[tuple[ColorSwatch, str]] = []
        for name, hex_color in ACCENT_COLORS:
            swatch = ColorSwatch(name, hex_color, self._on_color_clicked)
            self._color_swatches.append((swatch, hex_color))
            self._color_row.append(swatch)
        self.append(self._color_row)

        self.append(Gtk.Label(label='Full Name', xalign=0))
        self._name_entry = Gtk.Entry()
        self.append(self._name_entry)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        self.append(self._error_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
        self._save_btn = Gtk.Button(label='Save', css_classes=['suggested-action'])
        self._save_btn.connect('clicked', self._on_save_clicked)
        button_row.append(self._save_btn)
        self.append(button_row)

    def load_user(self, user_path: str):
        """Repopulates the page for a (possibly different) account --
        called every time navigation lands here, see main.py."""
        self._user_path = user_path
        self._staged_avatar_path = None
        self._chosen_emoji_path = None
        self._error_label.set_visible(False)
        self._color_row.set_visible(False)
        self._save_btn.set_sensitive(True)

        user_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            ACCOUNTS_BUS_NAME, user_path, USER_IFACE, None,
        )
        self._username = user_proxy.get_cached_property('UserName').unpack()
        self._real_name = user_proxy.get_cached_property('RealName').unpack() or self._username
        icon_file = user_proxy.get_cached_property('IconFile').unpack()
        self._current_display_path = _resolve_avatar_display_path(self._username, icon_file)

        self._name_entry.set_text(self._real_name)
        self._render_avatar_preview()

    # ---- avatar preview / editing -----------------------------------

    def _render_avatar_preview(self):
        child = self._avatar_holder.get_first_child()
        if child is not None:
            self._avatar_holder.remove(child)
        path = self._staged_avatar_path or self._current_display_path
        self._avatar_holder.append(_circular_avatar(path, 96, fallback_text=self._real_name))

    def _on_avatar_button_clicked(self, btn):
        popover = Gtk.Popover()
        popover.set_parent(btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        popover.set_child(box)

        photo_btn = Gtk.Button(label='Choose Photo…', css_classes=['flat'])
        photo_btn.get_child().set_halign(Gtk.Align.START)
        photo_btn.connect('clicked', lambda _b: (popover.popdown(), self._on_choose_photo()))
        box.append(photo_btn)

        emoji_btn = Gtk.Button(label='Choose Emoji…', css_classes=['flat'])
        emoji_btn.get_child().set_halign(Gtk.Align.START)
        emoji_btn.connect('clicked', lambda _b: (popover.popdown(), self._on_choose_emoji()))
        box.append(emoji_btn)

        popover.popup()

    def _on_choose_photo(self):
        dialog = Gtk.FileDialog(title='Choose a Photo')
        image_filter = Gtk.FileFilter(name='Images')
        for mime in ('image/png', 'image/jpeg', 'image/webp'):
            image_filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_photo_chosen)

    def _on_photo_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        if gfile is None:
            return
        src_path = gfile.get_path()
        if not src_path:
            return

        os.makedirs(AVATAR_STAGING_DIR, exist_ok=True)
        staged_path = os.path.join(AVATAR_STAGING_DIR, f'{self._username}-staged.png')
        try:
            avatar_picker.render_photo_avatar(src_path, staged_path)
        except GLib.Error as e:
            self._error_label.set_label(f'Could not use that image: {e.message}')
            self._error_label.set_visible(True)
            return

        self._chosen_emoji_path = None
        self._color_row.set_visible(False)
        self._staged_avatar_path = staged_path
        self._render_avatar_preview()

    def _on_choose_emoji(self):
        picker = avatar_picker.EmojiPickerDialog(self.get_root())
        picker.connect('emoji-picked', self._on_emoji_picked)
        picker.present()

    def _on_emoji_picked(self, _picker, emoji_path: str):
        self._chosen_emoji_path = emoji_path
        self._color_row.set_visible(True)
        default_swatch, default_hex = self._color_swatches[0]
        for swatch, _hex in self._color_swatches:
            swatch.set_selected(swatch is default_swatch, '#FFFFFF')
        self._apply_emoji_background(default_hex)

    def _on_color_clicked(self, swatch: ColorSwatch):
        hex_color = next(h for s, h in self._color_swatches if s is swatch)
        for s, _h in self._color_swatches:
            s.set_selected(s is swatch, '#FFFFFF')
        self._apply_emoji_background(hex_color)

    def _apply_emoji_background(self, hex_color: str):
        if not self._chosen_emoji_path:
            return
        os.makedirs(AVATAR_STAGING_DIR, exist_ok=True)
        staged_path = os.path.join(AVATAR_STAGING_DIR, f'{self._username}-staged.png')
        avatar_picker.render_emoji_avatar(self._chosen_emoji_path, hex_color, staged_path)
        self._staged_avatar_path = staged_path
        self._render_avatar_preview()

    # ---- saving -------------------------------------------------------

    def _on_save_clicked(self, _btn):
        new_name = self._name_entry.get_text().strip()
        if not new_name:
            self._error_label.set_label('Name cannot be empty.')
            self._error_label.set_visible(True)
            return

        self._save_btn.set_sensitive(False)
        try:
            self._bus.call_sync(
                ACCOUNTS_BUS_NAME, self._user_path, USER_IFACE, 'SetRealName',
                GLib.Variant('(s)', (new_name,)), None, Gio.DBusCallFlags.NONE, -1, None,
            )
            if self._staged_avatar_path and os.path.isfile(self._staged_avatar_path):
                self._bus.call_sync(
                    ACCOUNTS_BUS_NAME, self._user_path, USER_IFACE, 'SetIconFile',
                    GLib.Variant('(s)', (self._staged_avatar_path,)), None, Gio.DBusCallFlags.NONE, -1, None,
                )
        except GLib.Error as e:
            self._save_btn.set_sensitive(True)
            self._error_label.set_label(e.message)
            self._error_label.set_visible(True)
            return

        self._on_saved(self._user_path)
        self._go_back()


class UsersPage(Gtk.Box):
    def __init__(self, on_edit_user):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        # Navigates to the shared EditProfilePage (see main.py) rather than
        # opening a dialog here -- this page doesn't own any nav-stack state
        # itself, just asks the window to go there.
        self._on_edit_user = on_edit_user
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'users.svg'), 'system-users-symbolic',
            'Users & Groups', 'Manage who can sign in to this computer, and what they can do.',
        ))

        self._user_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._user_list.connect('row-activated', self._on_row_activated)
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

    def _on_row_activated(self, _listbox, row):
        self._on_edit_user(row.user_path)

    def reload(self):
        self._load_users()

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
            self._user_list.append(_user_row(user_proxy, path))
