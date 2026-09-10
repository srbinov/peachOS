import json
import os
import shutil
import threading
import time

import gi

gi.require_version('Goa', '1.0')
gi.require_version('Secret', '1')
from gi.repository import Gio, GLib, Goa, Gtk, Secret

import google_signin
import microsoft_signin
from widgets import make_hero_header

try:
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudException
except Exception:  # pyicloud not installed -> iCloud Photos step is skipped
    PyiCloudService = None
    PyiCloudFailedLoginException = PyiCloudException = Exception

try:
    from icloud_webauth import ICloudWebAuth
except Exception:  # WebKit 6.0 gir missing -> fall straight to the app-password step
    ICloudWebAuth = None

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# Shared with the peachos-icloud-photos helper (apps/icloud-photos) -- these must
# stay in step with its DATA_DIR / SESSION_DIR / CONFIG / _SCHEMA.
_ICLOUD_DATA = os.path.expanduser('~/.local/share/peachos/icloud-photos')
_ICLOUD_SESSION = os.path.join(_ICLOUD_DATA, 'session')
_ICLOUD_CONFIG = os.path.join(_ICLOUD_DATA, 'config.json')
_ICLOUD_SCHEMA = Secret.Schema.new(
    'org.peachos.iCloudPhotos', Secret.SchemaFlags.NONE,
    {'account': Secret.SchemaAttributeType.STRING})
# The app-specific password, reused by the peachos-mail helper for IMAP.
_MAIL_SCHEMA = Secret.Schema.new(
    'org.peachos.Mail', Secret.SchemaFlags.NONE,
    {'account': Secret.SchemaAttributeType.STRING})
# Apple's app-specific-passwords page
_APP_PW_URL = 'https://account.apple.com/account/manage'


def _icloud_store_session(apple_id, password, name):
    # password=None for the browser sign-in path -- there's no password to keep,
    # pyicloud authenticates from the harvested cookies alone.
    if password:
        Secret.password_store_sync(
            _ICLOUD_SCHEMA, {'account': apple_id}, Secret.COLLECTION_DEFAULT,
            'peachOS — iCloud Photos', password, None)
    os.makedirs(_ICLOUD_DATA, exist_ok=True)
    try:
        with open(_ICLOUD_CONFIG) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.update(apple_id=apple_id, name=name or apple_id, authed_at=int(time.time()))
    cfg.pop('reauth_needed', None)
    tmp = _ICLOUD_CONFIG + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, _ICLOUD_CONFIG)


def _icloud_kick_sync():
    try:
        Gio.Subprocess.new(['peachos-icloud-photos', 'sync'], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        pass


def _mail_kick_sync():
    try:
        Gio.Subprocess.new(['peachos-mail', 'sync'], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        pass

# OAuth2 providers signed in entirely in-app: peachOS runs the browser
# authorization-code + PKCE flow itself (google_signin.py / microsoft_signin.py),
# reusing GNOME's own OAuth client from libgoa-backend, then hands the tokens to
# GOA via Manager.AddAccount. No gnome-control-center window.
#
# Exchange (EWS autodiscover) and Nextcloud are intentionally NOT here yet --
# rather than ship a half-working realm/server form or shell out to
# gnome-control-center, they're left out until they get a proper in-app dialog.
SYSTEM_ACCOUNT_PROVIDERS = [
    ('Google', 'account_google.svg'),
    ('Microsoft 365', 'account_ms365.svg'),
]


def _file_icon(name: str, px: int = 28) -> Gtk.Image:
    """A brand logo from data/icons/, sized like the themed icons it replaces."""
    gicon = Gio.FileIcon.new(Gio.File.new_for_path(os.path.join(ICON_DIR, name)))
    img = Gtk.Image.new_from_gicon(gicon)
    img.set_pixel_size(px)
    return img


def _dark_mode() -> bool:
    try:
        return (Gio.Settings.new('org.gnome.desktop.interface')
                .get_string('color-scheme') == 'prefer-dark')
    except Exception:
        return False


def _apple_icon_file() -> str:
    # iCloud row uses the Apple mark -- white on dark, black on light.
    return 'account_apple_white.svg' if _dark_mode() else 'account_apple_black.svg'


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


class _AddICloudDialog(Gtk.Window):
    """One iCloud sign-in that wires up both halves:

      - Photos -> a pyicloud session, seeded from cookies harvested from Apple's
        own web sign-in (icloud_webauth.ICloudWebAuth) so 2FA works reliably.
      - Calendar / Reminders / Contacts + Mail -> GOA CalDAV/CardDAV + IMAP with
        an *app-specific* password (Apple blocks the main password for those).

    Steps: browser sign-in -> app-specific password -> done. Without WebKit or
    pyicloud it degrades to just the app-specific step.
    """

    _WEBAUTH_OK = ICloudWebAuth is not None and PyiCloudService is not None

    def __init__(self, parent, on_added):
        super().__init__(title='Sign in to iCloud', transient_for=parent,
                         modal=True, default_width=440, resizable=False)
        self._parent = parent
        self._on_added = on_added
        self._apple_id = ''
        self._photos_ok = False
        self._caldav_ok = False

        self._stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.set_child(self._stack)
        self._stack.add_named(self._page_signin(), 'signin')
        self._stack.add_named(self._page_caldav(), 'caldav')
        self._stack.add_named(self._page_done(), 'done')

        self._stack.set_visible_child_name(
            'signin' if self._WEBAUTH_OK else 'caldav')

    # ---- shared chrome -------------------------------------------------

    def _shell(self, title, subtitle=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for m in ('start', 'end', 'top', 'bottom'):
            getattr(box, f'set_margin_{m}')(22)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=['title-3']))
        if subtitle:
            box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True,
                                 css_classes=['dim-label']))
        return box

    @staticmethod
    def _footer(*buttons):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                      halign=Gtk.Align.END, margin_top=6)
        for b in buttons:
            row.append(b)
        return row

    # ---- step 1: browser sign-in (Photos) -------------------------

    def _page_signin(self):
        box = self._shell(
            'Sign in to iCloud',
            "Opens Apple's own sign-in page. The verification code shows "
            'on your Apple devices as normal; peachOS only keeps the '
            'resulting session, never your password.')
        box.append(Gtk.Label(label='Apple ID', xalign=0))
        self._id_entry = Gtk.Entry(placeholder_text='you@icloud.com',
                                   input_purpose=Gtk.InputPurpose.EMAIL)
        self._id_entry.connect('activate', lambda *_a: self._on_signin())
        box.append(self._id_entry)

        self._signin_err = Gtk.Label(wrap=True, xalign=0, css_classes=['error'],
                                     visible=False)
        box.append(self._signin_err)
        self._signin_spin = Gtk.Spinner()
        box.append(self._signin_spin)

        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_a: self.close())
        self._signin_btn = Gtk.Button(label='Sign In',
                                      css_classes=['suggested-action'])
        self._signin_btn.connect('clicked', lambda *_a: self._on_signin())
        box.append(self._footer(cancel, self._signin_btn))
        return box

    def _on_signin(self):
        apple_id = self._id_entry.get_text().strip()
        if not apple_id or '@' not in apple_id:
            self._signin_err.set_label('Enter your Apple ID (an email address).')
            self._signin_err.set_visible(True)
            return
        self._apple_id = apple_id
        self._signin_err.set_visible(False)
        self._signin_btn.set_sensitive(False)
        self._signin_spin.start()
        # Clean slate so the harvested session isn't mixed with a stale one.
        shutil.rmtree(_ICLOUD_SESSION, ignore_errors=True)
        os.makedirs(_ICLOUD_SESSION, exist_ok=True)
        ICloudWebAuth(self, apple_id, _ICLOUD_SESSION,
                      self._webauth_done).present()

    def _webauth_done(self, ok, detail):
        self._signin_spin.stop()
        self._signin_btn.set_sensitive(True)
        if not ok:
            if detail and detail != 'cancelled':
                self._signin_err.set_label(f'Sign-in failed: {detail}')
                self._signin_err.set_visible(True)
            return
        self._photos_connected()
        return GLib.SOURCE_REMOVE

    # ---- photos side is done -> persist + move on ------------------

    def _photos_connected(self):
        self._photos_ok = True
        try:
            _icloud_store_session(self._apple_id, None, self._apple_id)
            _icloud_kick_sync()
        except Exception:
            pass
        self._id2_entry.set_text(self._apple_id)
        self._appw_entry.grab_focus()
        self._stack.set_visible_child_name('caldav')


    # ---- step 3: app-specific password (CalDAV / CardDAV) ---------

    def _page_caldav(self):
        box = self._shell(
            'Calendar, Reminders, Contacts & Mail',
            'These sync over CalDAV/CardDAV/IMAP, which Apple only allows with '
            'an app-specific password — not your main one. You’re already '
            'signed in, so creating one takes a few seconds.')

        link = Gtk.LinkButton(
            uri=_APP_PW_URL,
            label='Create an app-specific password at account.apple.com →')
        link.set_halign(Gtk.Align.START)
        box.append(link)

        box.append(Gtk.Label(label='Apple ID', xalign=0))
        self._id2_entry = Gtk.Entry(placeholder_text='you@icloud.com',
                                    input_purpose=Gtk.InputPurpose.EMAIL)
        box.append(self._id2_entry)
        box.append(Gtk.Label(label='App-Specific Password', xalign=0))
        self._appw_entry = Gtk.PasswordEntry(
            placeholder_text='xxxx-xxxx-xxxx-xxxx', show_peek_icon=True)
        self._appw_entry.connect('activate', lambda *_a: self._on_caldav())
        box.append(self._appw_entry)

        self._caldav_err = Gtk.Label(wrap=True, xalign=0, css_classes=['error'],
                                     visible=False)
        box.append(self._caldav_err)
        self._caldav_spin = Gtk.Spinner()
        box.append(self._caldav_spin)

        skip = Gtk.Button(label='Not now', css_classes=['flat'])
        skip.connect('clicked', lambda *_a: self._finish())
        self._caldav_btn = Gtk.Button(label='Connect',
                                      css_classes=['suggested-action'])
        self._caldav_btn.connect('clicked', lambda *_a: self._on_caldav())
        box.append(self._footer(skip, self._caldav_btn))
        return box

    def _on_caldav(self):
        apple_id = self._id2_entry.get_text().strip()
        password = self._appw_entry.get_text().replace(' ', '')
        if not apple_id or not password:
            self._caldav_err.set_label(
                'Enter your Apple ID and an app-specific password.')
            self._caldav_err.set_visible(True)
            return
        self._caldav_err.set_visible(False)
        self._caldav_btn.set_sensitive(False)
        self._caldav_spin.start()
        self._mail_id, self._mail_pw = apple_id, password
        threading.Thread(target=self._do_caldav, args=(apple_id, password),
                         daemon=True).start()

    def _do_caldav(self, apple_id, password):
        credentials = {'password': GLib.Variant('s', password)}
        details = {
            'Enabled': 'true', 'CalendarEnabled': 'true',
            'ContactsEnabled': 'true', 'FilesEnabled': 'false',
            'CalDavUri': 'https://caldav.icloud.com',
            'CardDavUri': 'https://contacts.icloud.com',
            'Uri': 'https://caldav.icloud.com',
            'username': apple_id, 'AcceptSslErrors': 'false',
        }
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call_sync(
                'org.gnome.OnlineAccounts', '/org/gnome/OnlineAccounts/Manager',
                'org.gnome.OnlineAccounts.Manager', 'AddAccount',
                GLib.Variant('(sssa{sv}a{ss})',
                             ('webdav', apple_id, apple_id, credentials, details)),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, 60000, None)
        except GLib.Error as e:
            msg = e.message
            if 'already' in msg.lower() or 'exists' in msg.lower():
                GLib.idle_add(self._caldav_done, True, None)
                return
            if 'auth' in msg.lower() or '401' in msg:
                msg = ('Sign-in failed — check the app-specific password is '
                       'current.')
            GLib.idle_add(self._caldav_done, False, msg)
            return
        GLib.idle_add(self._caldav_done, True, None)

    def _caldav_done(self, ok, error):
        self._caldav_spin.stop()
        self._caldav_btn.set_sensitive(True)
        if not ok:
            self._caldav_err.set_label(error or 'Could not connect.')
            self._caldav_err.set_visible(True)
            return
        self._caldav_ok = True
        # Stash the app-specific password so the Mail widget helper can log in
        # to iCloud IMAP without asking again.
        try:
            Secret.password_store_sync(
                _MAIL_SCHEMA, {'account': self._mail_id},
                Secret.COLLECTION_DEFAULT, 'peachOS — iCloud Mail',
                self._mail_pw, None)
            _mail_kick_sync()
        except Exception:
            pass
        self._finish()

    # ---- step 4: done ---------------------------------------------

    def _page_done(self):
        self._done_box = self._shell('iCloud Connected')
        self._done_list = Gtk.Label(xalign=0, wrap=True)
        self._done_box.append(self._done_list)
        done = Gtk.Button(label='Done', css_classes=['suggested-action'])
        done.connect('clicked', lambda *_a: self.close())
        self._done_box.append(self._footer(done))
        return self._done_box

    def _finish(self):
        mark = "✓" if self._caldav_ok else "—"
        self._done_list.set_label('\n'.join([
            f'{"✓" if self._photos_ok else "—"}  Photos',
            f'{mark}  Calendar',
            f'{mark}  Reminders',
            f'{mark}  Contacts',
            f'{mark}  Mail',
        ]))
        self._stack.set_visible_child_name('done')
        self._on_added()


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

        icloud_row = Gtk.Button(css_classes=['flat'])
        ic_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for m in ('start', 'end', 'top', 'bottom'):
            getattr(ic_content, f'set_margin_{m}')(8)
        self._icloud_icon = _file_icon(_apple_icon_file(), 28)
        ic_content.append(self._icloud_icon)
        # keep the Apple mark right for the current theme, live
        self._iface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._scheme_handler = self._iface_settings.connect(
            'changed::color-scheme',
            lambda *_a: self._icloud_icon.set_from_gicon(Gio.FileIcon.new(
                Gio.File.new_for_path(os.path.join(ICON_DIR, _apple_icon_file())))))
        self.connect('destroy', lambda *_a: self._iface_settings.disconnect(self._scheme_handler))
        ic_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        ic_text.append(Gtk.Label(label='iCloud', xalign=0))
        ic_text.append(Gtk.Label(label='Calendar, Reminders, Contacts', xalign=0,
                                 css_classes=['caption', 'dim-label']))
        ic_content.append(ic_text)
        icloud_row.set_child(ic_content)
        icloud_row.connect('clicked', self._on_icloud_clicked)
        box.append(icloud_row)

        oauth = {
            'Google': (google_signin.goa_google_creds() is not None,
                       google_signin.GoogleSignIn, 'Google'),
            'Microsoft 365': (microsoft_signin.goa_ms_graph_client_id() is not None,
                              microsoft_signin.MicrosoftSignIn, 'Microsoft'),
        }
        for provider_name, icon_file in SYSTEM_ACCOUNT_PROVIDERS:
            available, signin_cls, label = oauth.get(provider_name, (False, None, ''))
            prov_row = Gtk.Button(css_classes=['flat'], sensitive=available)
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            content.set_margin_start(8)
            content.set_margin_end(8)
            content.set_margin_top(8)
            content.set_margin_bottom(8)
            content.append(_file_icon(icon_file, 28))
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            text_box.append(Gtk.Label(label=provider_name, xalign=0))
            text_box.append(Gtk.Label(
                label='Sign in with your browser' if available
                else 'Currently unavailable',
                xalign=0, css_classes=['caption', 'dim-label']))
            content.append(text_box)
            content.append(Gtk.Image.new_from_icon_name('external-link-symbolic'))
            prov_row.set_child(content)
            if available:
                prov_row.connect(
                    'clicked',
                    lambda _b, c=signin_cls, l=label: self._start_oauth(c, l))
            box.append(prov_row)

    def _on_mail_clicked(self, _btn):
        self.close()
        dialog = _AddMailAccountDialog(self._parent, on_added=self._on_added)
        dialog.present()

    def _on_icloud_clicked(self, _btn):
        self.close()
        _AddICloudDialog(self._parent, on_added=self._on_added).present()

    # --- native browser OAuth sign-in (Google, Microsoft) ----------------

    def _start_oauth(self, signin_cls, label):
        old = self._stack.get_child_by_name('status')
        if old is not None:
            self._stack.remove(old)
        self._stack.add_named(self._build_status_page(label), 'status')
        self._stack.set_visible_child_name('status')
        self._signin = signin_cls(on_done=self._on_oauth_done)
        self._signin.start()

    def _build_status_page(self, label):
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
            label=f'A {label} sign-in page has opened. Come back here when '
                  'you’re done.',
            wrap=True, justify=Gtk.Justification.CENTER, css_classes=['dim-label']))
        self._status_error = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                                       css_classes=['error'], visible=False)
        box.append(self._status_error)
        cancel = Gtk.Button(label='Cancel', halign=Gtk.Align.CENTER,
                            css_classes=['flat'])
        cancel.connect('clicked', lambda _b: self._cancel_oauth())
        box.append(cancel)
        return box

    def _cancel_oauth(self):
        if self._signin:
            self._signin.cancel()
        self.close()

    def _on_oauth_done(self, ok, detail):
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
