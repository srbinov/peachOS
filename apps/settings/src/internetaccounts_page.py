import os

import gi

gi.require_version('Goa', '1.0')
from gi.repository import Gio, GLib, Goa, Gtk

import google_signin
from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# Providers whose sign-in needs an OAuth2 browser flow (Google) or realm/server
# details GOA's public AddAccount D-Bus call doesn't cover. Their real client
# credentials live inside gnome-control-center / libgoa-backend, so the actual
# sign-in dialog is delegated to `gnome-control-center online-accounts` -- once
# the account is added there it shows up in the list below and works everywhere.
SYSTEM_ACCOUNT_PROVIDERS = [
    ('Google', 'goa-account-google-symbolic'),
    ('Microsoft 365', 'goa-account-ms-graph-symbolic'),
    ('Microsoft Exchange', 'goa-account-exchange-symbolic'),
    ('Nextcloud', 'goa-account-owncloud-symbolic'),
    ('Kerberos', 'goa-account-kerberos-symbolic'),
]


def _open_system_accounts() -> None:
    """Launch GNOME's Online Accounts panel for the OAuth2 sign-in step."""
    try:
        Gio.Subprocess.new(
            ['gnome-control-center', 'online-accounts'],
            Gio.SubprocessFlags.NONE,
        )
    except GLib.Error:
        pass


def _account_icon(account: Goa.Account) -> Gtk.Image:
    # provider-icon is a GOA property serialized the same way Gio.Icon.to_string()/
    # new_for_string() round-trip it (GOA's own control-center panel does the same
    # conversion) -- fall back to a generic icon if a given provider's icon string
    # doesn't parse, rather than let one bad account break the whole list.
    icon_str = account.get_property('provider-icon')
    try:
        gicon = Gio.Icon.new_for_string(icon_str) if icon_str else None
    except Exception:
        gicon = None
    icon = Gtk.Image.new_from_gicon(gicon) if gicon else Gtk.Image.new_from_icon_name('goa-account-symbolic')
    icon.set_pixel_size(32)
    return icon


class _AddMailAccountDialog(Gtk.Window):
    """The one GOA provider (imap_smtp) genuinely addable through the public
    Manager.AddAccount D-Bus call without an embedded OAuth browser flow --
    field/key names verified directly against GOA's own source
    (goaimapsmtpprovider.c's add_account_store_credentials), not guessed."""

    def __init__(self, parent, on_added):
        super().__init__(
            title='Add Mail Account', transient_for=parent, modal=True,
            default_width=420, resizable=False,
        )
        self._on_added = on_added

        outer = Gtk.ScrolledWindow(min_content_height=440, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.set_child(outer)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        outer.set_child(box)

        box.append(Gtk.Label(label='Name', xalign=0))
        self._name_entry = Gtk.Entry(placeholder_text='e.g. Work Email')
        box.append(self._name_entry)

        box.append(Gtk.Label(label='Email Address', xalign=0))
        self._email_entry = Gtk.Entry(placeholder_text='you@example.com')
        box.append(self._email_entry)

        box.append(Gtk.Label(label='IMAP Server', xalign=0, css_classes=['heading']))
        self._imap_host_entry = Gtk.Entry(placeholder_text='imap.example.com')
        box.append(self._imap_host_entry)
        self._imap_user_entry = Gtk.Entry(placeholder_text='Username (defaults to email address)')
        box.append(self._imap_user_entry)
        self._imap_password_entry = Gtk.PasswordEntry(placeholder_text='Password', show_peek_icon=True)
        box.append(self._imap_password_entry)
        self._imap_ssl_check = Gtk.CheckButton(label='Use SSL', active=True)
        box.append(self._imap_ssl_check)

        box.append(Gtk.Label(label='SMTP Server (optional)', xalign=0, css_classes=['heading']))
        self._smtp_host_entry = Gtk.Entry(placeholder_text='smtp.example.com')
        box.append(self._smtp_host_entry)
        self._smtp_user_entry = Gtk.Entry(placeholder_text='Username (defaults to email address)')
        box.append(self._smtp_user_entry)
        self._smtp_password_entry = Gtk.PasswordEntry(placeholder_text='Password', show_peek_icon=True)
        box.append(self._smtp_password_entry)
        self._smtp_ssl_check = Gtk.CheckButton(label='Use SSL', active=True)
        box.append(self._smtp_ssl_check)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        box.append(self._error_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label='Cancel')
        cancel_btn.connect('clicked', lambda *_a: self.close())
        button_row.append(cancel_btn)
        self._add_btn = Gtk.Button(label='Add Account', css_classes=['suggested-action'])
        self._add_btn.connect('clicked', self._on_add_clicked)
        button_row.append(self._add_btn)
        box.append(button_row)

    def _on_add_clicked(self, _btn):
        name = self._name_entry.get_text().strip()
        email = self._email_entry.get_text().strip()
        imap_host = self._imap_host_entry.get_text().strip()
        imap_password = self._imap_password_entry.get_text()
        if not name or not email or not imap_host or not imap_password:
            self._error_label.set_label('Fill in a name, email address, IMAP server, and password.')
            self._error_label.set_visible(True)
            return

        imap_username = self._imap_user_entry.get_text().strip() or email
        smtp_host = self._smtp_host_entry.get_text().strip()
        smtp_username = self._smtp_user_entry.get_text().strip() or email
        smtp_password = self._smtp_password_entry.get_text()
        smtp_use_auth = bool(smtp_host and smtp_password)

        credentials = {'imap-password': GLib.Variant('s', imap_password)}
        if smtp_use_auth:
            credentials['smtp-password'] = GLib.Variant('s', smtp_password)

        details = {
            'Enabled': 'true',
            'EmailAddress': email,
            'Name': name,
            'ImapHost': imap_host,
            'ImapUserName': imap_username,
            'ImapUseSsl': 'true' if self._imap_ssl_check.get_active() else 'false',
            'ImapUseTls': 'false',
            'ImapAcceptSslErrors': 'false',
        }
        if smtp_host:
            details['SmtpHost'] = smtp_host
            details['SmtpUseAuth'] = 'true' if smtp_use_auth else 'false'
            if smtp_use_auth:
                details['SmtpUserName'] = smtp_username
                details['SmtpAuthLogin'] = 'true'
                details['SmtpAuthPlain'] = 'false'
            details['SmtpUseSsl'] = 'true' if self._smtp_ssl_check.get_active() else 'false'
            details['SmtpUseTls'] = 'false'
            details['SmtpAcceptSslErrors'] = 'false'

        self._add_btn.set_sensitive(False)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        try:
            bus.call_sync(
                'org.gnome.OnlineAccounts', '/org/gnome/OnlineAccounts/Manager',
                'org.gnome.OnlineAccounts.Manager', 'AddAccount',
                GLib.Variant('(sssa{sv}a{ss})', ('imap_smtp', email, email, credentials, details)),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error as e:
            self._add_btn.set_sensitive(True)
            self._error_label.set_label(e.message)
            self._error_label.set_visible(True)
            return

        self._on_added()
        self.close()


class _AddAccountDialog(Gtk.Window):
    def __init__(self, parent, on_added):
        super().__init__(
            title='Add Account', transient_for=parent, modal=True,
            default_width=340, resizable=False,
        )
        self._parent = parent
        self._on_added = on_added
        self._signin = None

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.set_child(self._stack)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        self._stack.add_named(box, 'list')

        mail_row = Gtk.Button(css_classes=['flat'])
        mail_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mail_content.set_margin_start(8)
        mail_content.set_margin_end(8)
        mail_content.set_margin_top(8)
        mail_content.set_margin_bottom(8)
        mail_icon = Gtk.Image.new_from_icon_name('mail-unread-symbolic')
        mail_icon.set_pixel_size(28)
        mail_content.append(mail_icon)
        mail_content.append(Gtk.Label(label='Mail Account (IMAP/SMTP)', xalign=0, hexpand=True))
        mail_row.set_child(mail_content)
        mail_row.connect('clicked', self._on_mail_clicked)
        box.append(mail_row)

        native_google = google_signin.goa_google_creds() is not None
        for provider_name, icon_name in SYSTEM_ACCOUNT_PROVIDERS:
            is_google = provider_name == 'Google'
            prov_row = Gtk.Button(css_classes=['flat'])
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            content.set_margin_start(8)
            content.set_margin_end(8)
            content.set_margin_top(8)
            content.set_margin_bottom(8)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(28)
            content.append(icon)
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            text_box.append(Gtk.Label(label=provider_name, xalign=0))
            text_box.append(Gtk.Label(
                label='Sign in with your browser' if (is_google and native_google)
                else 'Opens System Accounts to sign in',
                xalign=0, css_classes=['caption', 'dim-label']))
            content.append(text_box)
            content.append(Gtk.Image.new_from_icon_name('external-link-symbolic'))
            prov_row.set_child(content)
            if is_google and native_google:
                prov_row.connect('clicked', self._on_google_clicked)
            else:
                prov_row.connect('clicked', self._on_system_clicked)
            box.append(prov_row)

    def _on_mail_clicked(self, _btn):
        self.close()
        dialog = _AddMailAccountDialog(self._parent, on_added=self._on_added)
        dialog.present()

    def _on_system_clicked(self, _btn):
        self.close()
        _open_system_accounts()

    # --- native Google sign-in ---------------------------------------

    def _on_google_clicked(self, _btn):
        self._stack.add_named(self._build_status_page(), 'status')
        self._stack.set_visible_child_name('status')
        self._signin = google_signin.GoogleSignIn(on_done=self._on_google_done)
        self._signin.start()

    def _build_status_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      valign=Gtk.Align.CENTER)
        box.set_margin_start(28)
        box.set_margin_end(28)
        box.set_margin_top(28)
        box.set_margin_bottom(20)
        spinner = Gtk.Spinner(width_request=32, height_request=32,
                              halign=Gtk.Align.CENTER)
        spinner.start()
        box.append(spinner)
        box.append(Gtk.Label(label='Continue in your browser',
                             css_classes=['title-4']))
        box.append(Gtk.Label(
            label='A Google sign-in page has opened. Come back here when '
                  'you’re done.',
            wrap=True, justify=Gtk.Justification.CENTER, css_classes=['dim-label']))
        self._status_error = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                                       css_classes=['error'], visible=False)
        box.append(self._status_error)
        cancel = Gtk.Button(label='Cancel', halign=Gtk.Align.CENTER,
                            css_classes=['flat'])
        cancel.connect('clicked', lambda _b: self._cancel_google())
        box.append(cancel)
        return box

    def _cancel_google(self):
        if self._signin:
            self._signin.cancel()
        self.close()

    def _on_google_done(self, ok, detail):
        if ok:
            self._on_added()
            self.close()
        else:
            self._status_error.set_label(f'Sign-in failed: {detail}')
            self._status_error.set_visible(True)
        return GLib.SOURCE_REMOVE


def _account_row(account: Goa.Account, on_removed) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
    row.set_margin_start(14)
    row.set_margin_end(14)
    row.set_margin_top(10)
    row.set_margin_bottom(10)

    row.append(_account_icon(account))

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
    text_box.append(Gtk.Label(label=account.get_property('provider-name') or 'Account', xalign=0))
    identity = account.get_property('presentation-identity') or ''
    if identity:
        text_box.append(Gtk.Label(label=identity, xalign=0, css_classes=['caption', 'dim-label']))
    row.append(text_box)

    remove_btn = Gtk.Button(icon_name='user-trash-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)

    def do_remove(_btn):
        try:
            account.call_remove_sync(None)
        except GLib.Error:
            pass
        on_removed()

    remove_btn.connect('clicked', do_remove)
    row.append(remove_btn)

    return row


class InternetAccountsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'internetaccounts.svg'), 'goa-account-symbolic',
            'Internet Accounts', 'Add your email, calendar, and other online accounts.',
        ))

        self._account_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._account_list)

        self._empty_label = Gtk.Label(
            label='No accounts added yet.', css_classes=['dim-label'], margin_top=4, visible=False,
        )
        self.append(self._empty_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
        add_btn = Gtk.Button(label='Add Account…', css_classes=['flat'])
        add_btn.connect('clicked', self._on_add_clicked)
        button_row.append(add_btn)
        self.append(button_row)

        self._client = None
        Goa.Client.new(None, self._on_client_ready)

    def _on_add_clicked(self, _btn):
        dialog = _AddAccountDialog(self.get_root(), on_added=self._reload)
        dialog.present()

    def _on_client_ready(self, _source, result):
        try:
            self._client = Goa.Client.new_finish(result)
        except Exception:
            self._empty_label.set_label('Could not connect to the account service.')
            self._empty_label.set_visible(True)
            return
        # Refresh when an account is added elsewhere (e.g. the user just added
        # Google in the System Accounts panel and came back).
        for signal in ('account-added', 'account-removed', 'account-changed'):
            self._client.connect(signal, lambda *_a: self._reload())
        self._reload()

    def _reload(self):
        child = self._account_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._account_list.remove(child)
            child = next_child

        if not self._client:
            return

        objects = self._client.get_accounts()
        self._empty_label.set_visible(not objects)
        for obj in objects:
            account = obj.get_account()
            if account:
                self._account_list.append(_account_row(account, on_removed=self._reload))
