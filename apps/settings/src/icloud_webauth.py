"""Browser-based iCloud sign-in for peachOS Settings.

Apple has no OAuth for third-party iCloud access, so the Photos widget uses
pyicloud (a reverse-engineered private API). Doing pyicloud's SRP + 2FA flow
from headless Python is unreliable -- Apple's risk engine often just doesn't
push a code. Instead, embed Apple's OWN web sign-in (idmsa.apple.com /
icloud.com) in a WebKitGTK view: 2FA works natively there because it's Apple's
real page, then harvest the authenticated cookies and drop them where pyicloud
looks (`<session_dir>/<sanitised_apple_id>.cookiejar` + a stub `.session`).

pyicloud then authenticates purely from those cookies -- `authenticate()`
tries `_validate_token()` first when the `.session` has any `session_token`,
and that path only needs the `X-APPLE-WEBAUTH-TOKEN` cookie, not the password.
"""

import http.cookiejar
import json
import os
import re
import time
import uuid

# Belt-and-suspenders for old GPUs (see the HardwareAccelerationPolicy note in
# ICloudWebAuth) -- must be set before WebKit's compositor initialises, i.e.
# before the first WebView, which is why it lives at import time here.
os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, GLib, Gio  # noqa: E402

ICLOUD_URL = 'https://www.icloud.com/'
# Domains whose cookies together make up an authenticated iCloud session.
COOKIE_DOMAINS = ['https://www.icloud.com/', 'https://icloud.com/',
                  'https://setup.icloud.com/', 'https://idmsa.apple.com/',
                  'https://apple.com/', 'https://account.apple.com/']
# Presence of this cookie = the web session is authenticated.
AUTH_COOKIE = 'X-APPLE-WEBAUTH-TOKEN'


def _sanitise(apple_id: str) -> str:
    return ''.join(c for c in apple_id if re.match(r'\w', c))


def _write_pyicloud_session(session_dir: str, apple_id: str, soup_cookies):
    """Turn a list of Soup.Cookie into the files pyicloud loads on next run."""
    os.makedirs(session_dir, exist_ok=True)
    base = os.path.join(session_dir, _sanitise(apple_id))

    jar = http.cookiejar.LWPCookieJar(base + '.cookiejar')
    trust_token = ''
    for c in soup_cookies:
        name = c.get_name()
        value = c.get_value()
        domain = c.get_domain()
        if name == 'X-APPLE-WEBAUTH-HSA-TRUST':
            trust_token = value
        expires = c.get_expires()
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=name, value=value,
            port=None, port_specified=False,
            domain=domain, domain_specified=bool(domain),
            domain_initial_dot=domain.startswith('.'),
            path=c.get_path() or '/', path_specified=True,
            secure=c.get_secure(),
            expires=int(expires.to_unix()) if expires else None,
            discard=expires is None,
            comment=None, comment_url=None,
            rest={'HttpOnly': None} if c.get_http_only() else {},
        ))
    jar.save(ignore_discard=True, ignore_expires=True)

    # A stub session file: the value of session_token is never used on the
    # cookie path (only its truthiness, to make authenticate() try
    # _validate_token first), but account_country / client_id are read if the
    # token ever needs refreshing.
    with open(base + '.session', 'w', encoding='utf-8') as f:
        json.dump({
            'session_token': 'web',
            'client_id': 'auth-%s' % uuid.uuid4(),
            'account_country': 'USA',
            'trust_token': trust_token,
            'trust_eligible': True,
        }, f)


class ICloudWebAuth(Gtk.Window):
    """`on_done(ok: bool, detail: str)` -- detail = '' on success, else an error."""

    def __init__(self, parent, apple_id: str, session_dir: str, on_done):
        super().__init__(title='Sign in to iCloud', transient_for=parent,
                         modal=True, default_width=960, default_height=720)
        self._apple_id = apple_id
        self._session_dir = session_dir
        self._on_done = on_done
        self._finished = False
        self._poll_id = 0

        # A private, non-persistent network session so this login can't be
        # polluted by (or leak into) anything else.
        self._net = WebKit.NetworkSession.new_ephemeral()
        self._cookies = self._net.get_cookie_manager()

        self._web = WebKit.WebView(network_session=self._net)
        self._web.set_vexpand(True)
        self._web.set_hexpand(True)

        # This is a login page, not a game. Force CPU rendering: the target
        # hardware includes a 2012 MacBook Pro on nouveau where WebKit's GPU
        # path (Vulkan on Ivy Bridge) hard-crashes the Wayland session.
        st = self._web.get_settings()
        st.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.NEVER)
        st.set_enable_webgl(False)
        st.set_enable_2d_canvas_acceleration(False)

        header = Gtk.HeaderBar()
        self._status = Gtk.Label(label='Sign in with your Apple ID — the '
                                 'verification code will appear on your Apple '
                                 'devices.', css_classes=['dim-label'])
        header.set_title_widget(self._status)
        self.set_titlebar(header)

        self.set_child(self._web)
        self.connect('close-request', self._on_close)
        self._web.load_uri(ICLOUD_URL)

        # Poll for the auth cookie rather than trying to guess the "logged in"
        # URL (Apple's redirects change often).
        self._poll_id = GLib.timeout_add_seconds(2, self._poll)

    def _poll(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        self._cookies.get_all_cookies(
            'https://www.icloud.com/', None, self._got_cookies_probe)
        return GLib.SOURCE_CONTINUE

    def _got_cookies_probe(self, mgr, res):
        try:
            cookies = mgr.get_all_cookies_finish(res)
        except GLib.Error:
            return
        if any(c.get_name() == AUTH_COOKIE and c.get_value() for c in cookies):
            self._harvest()

    def _harvest(self):
        if self._finished:
            return
        self._finished = True
        self._status.set_label('Finishing…')
        self._all = []
        self._pending = list(COOKIE_DOMAINS)
        self._collect_next()

    def _collect_next(self):
        if not self._pending:
            self._write_and_done()
            return
        url = self._pending.pop()
        self._cookies.get_all_cookies(url, None, self._collected)

    def _collected(self, mgr, res):
        try:
            self._all.extend(mgr.get_all_cookies_finish(res))
        except GLib.Error:
            pass
        self._collect_next()

    def _write_and_done(self):
        try:
            # de-dup by (name, domain)
            seen = {}
            for c in self._all:
                seen[(c.get_name(), c.get_domain())] = c
            _write_pyicloud_session(self._session_dir, self._apple_id,
                                    list(seen.values()))
        except Exception as e:  # noqa: BLE001
            self._deliver(False, str(e))
            return
        self._deliver(True, '')

    def _deliver(self, ok, detail):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        on_done = self._on_done
        self._on_done = None
        self.destroy()
        if on_done:
            GLib.idle_add(lambda: (on_done(ok, detail), GLib.SOURCE_REMOVE)[1])

    def _on_close(self, *_a):
        if not self._finished:
            self._deliver(False, 'cancelled')
        return False
