"""Browser-based iCloud sign-in for peachOS Settings.

Apple has no OAuth for third-party iCloud access, so the Photos widget uses
pyicloud (a reverse-engineered private API). Doing pyicloud's SRP + 2FA flow
from headless Python is unreliable -- Apple's risk engine often just doesn't
push a code. Instead, embed Apple's OWN web sign-in in a WebKitGTK view: 2FA
works natively there, then harvest the authenticated cookies and drop them
where pyicloud looks (`<session_dir>/<sanitised_apple_id>.cookiejar` + a stub
`.session`).

Apple's login is cross-site (idmsa.apple.com authenticates, *.icloud.com holds
the session), so ITP and third-party-cookie blocking BOTH have to be off or the
session cookie never reaches icloud.com.
"""

import http.cookiejar
import json
import os
import re
import shutil
import sys
import tempfile
import uuid

# Belt-and-suspenders for old GPUs (see the HardwareAccelerationPolicy note in
# ICloudWebAuth) -- must be set before WebKit's compositor initialises.
os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, GLib  # noqa: E402

ICLOUD_URL = 'https://www.icloud.com/'
# Cookie domains that together make up an authenticated iCloud session.
COOKIE_URLS = ['https://www.icloud.com/', 'https://setup.icloud.com/',
               'https://p.icloud.com/', 'https://idmsa.apple.com/',
               'https://account.apple.com/', 'https://appleid.apple.com/']
# Any of these present (with a value) => the web session is authenticated.
AUTH_COOKIES = ('X-APPLE-WEBAUTH-TOKEN', 'X-APPLE-WEBAUTH-USER',
                'X-APPLE-WEBAUTH-HSA-TRUST')


_LOGFILE = os.path.expanduser('~/.cache/peachos/icloud-webauth.log')


def _log(*a):
    line = '[icloud-webauth] ' + ' '.join(str(x) for x in a)
    print(line, file=sys.stderr, flush=True)
    try:
        os.makedirs(os.path.dirname(_LOGFILE), exist_ok=True)
        with open(_LOGFILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def _sanitise(apple_id: str) -> str:
    return ''.join(c for c in apple_id if re.match(r'\w', c))


def _write_pyicloud_session(session_dir: str, apple_id: str, soup_cookies) -> int:
    """Write the files pyicloud loads on next run. Returns how many cookies."""
    os.makedirs(session_dir, exist_ok=True)
    base = os.path.join(session_dir, _sanitise(apple_id))

    jar = http.cookiejar.LWPCookieJar(base + '.cookiejar')
    trust_token = ''
    n = 0
    for c in soup_cookies:
        name, value, domain = c.get_name(), c.get_value(), c.get_domain()
        if not name:
            continue
        if name == 'X-APPLE-WEBAUTH-HSA-TRUST':
            trust_token = value
        expires = c.get_expires()
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=name, value=value or '',
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
        n += 1
    jar.save(ignore_discard=True, ignore_expires=True)

    # Stub session: session_token only needs to be truthy so authenticate()
    # tries _validate_token() (cookie-only) before the SRP path.
    with open(base + '.session', 'w', encoding='utf-8') as f:
        json.dump({
            'session_token': 'web',
            'client_id': 'auth-%s' % uuid.uuid4(),
            'account_country': 'USA',
            'trust_token': trust_token,
            'trust_eligible': True,
        }, f)
    return n


class ICloudWebAuth(Gtk.Window):
    """`on_done(ok: bool, detail: str)` -- detail = '' on success, else an error
    ('cancelled' when the user just closed the window)."""

    def __init__(self, parent, apple_id: str, session_dir: str, on_done):
        super().__init__(title='Sign in to iCloud', transient_for=parent,
                         modal=True, default_width=980, default_height=760)
        self._apple_id = apple_id
        self._session_dir = session_dir
        self._on_done = on_done
        self._finished = False
        self._poll_id = 0
        self._tmp = tempfile.mkdtemp(prefix='peachos-icloud-web-')

        # Persistent (not ephemeral) session in a throwaway dir: ephemeral
        # sessions are flakier for get_all_cookies and impossible to inspect.
        self._net = WebKit.NetworkSession.new(self._tmp, self._tmp)
        self._net.set_itp_enabled(False)               # cross-site: idmsa -> icloud
        self._cookies = self._net.get_cookie_manager()
        self._cookies.set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)
        self._cookies.set_persistent_storage(
            os.path.join(self._tmp, 'cookies.sqlite'),
            WebKit.CookiePersistentStorage.SQLITE)

        self._web = WebKit.WebView(network_session=self._net)
        self._web.set_vexpand(True)
        self._web.set_hexpand(True)

        # CPU rendering only -- WebKit's GPU path (Vulkan on the dev MacBook's
        # Ivy Bridge / nouveau) hard-crashes the Wayland session.
        st = self._web.get_settings()
        st.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.NEVER)
        st.set_enable_webgl(False)
        st.set_enable_2d_canvas_acceleration(False)

        header = Gtk.HeaderBar(show_title_buttons=False)
        self._status = Gtk.Label(
            label='Sign in with your Apple ID — the code appears on your Apple devices.',
            css_classes=['dim-label'], ellipsize=3)
        header.set_title_widget(self._status)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_a: self.close())
        header.pack_start(cancel)
        self._continue_btn = Gtk.Button(label='I’ve signed in',
                                        css_classes=['suggested-action'])
        self._continue_btn.connect('clicked', lambda *_a: self._harvest('manual'))
        header.pack_end(self._continue_btn)
        self.set_titlebar(header)

        self.set_child(self._web)
        self.connect('close-request', self._on_close)
        self._web.load_uri(ICLOUD_URL)

        self._poll_id = GLib.timeout_add_seconds(2, self._poll)

    # ---- detect / harvest -------------------------------------------------

    def _poll(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        self._cookies.get_all_cookies(ICLOUD_URL, None, self._probe_done)
        return GLib.SOURCE_CONTINUE

    def _probe_done(self, mgr, res):
        try:
            cookies = mgr.get_all_cookies_finish(res)
        except GLib.Error:
            return
        names = {c.get_name() for c in cookies if c.get_value()}
        if names & set(AUTH_COOKIES):
            _log('auth cookie seen:', sorted(names & set(AUTH_COOKIES)))
            self._harvest('auto')

    def _harvest(self, how):
        if self._finished:
            return
        self._finished = True
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        self._status.set_label('Finishing…')
        self._continue_btn.set_sensitive(False)
        _log('harvest (%s)' % how)
        self._all = []
        self._pending = list(COOKIE_URLS)
        self._collect_next()

    def _collect_next(self):
        if not self._pending:
            self._write_and_done()
            return
        self._cookies.get_all_cookies(self._pending.pop(), None, self._collected)

    def _collected(self, mgr, res):
        try:
            self._all.extend(mgr.get_all_cookies_finish(res))
        except GLib.Error:
            pass
        self._collect_next()

    def _write_and_done(self):
        seen = {}
        for c in self._all:
            if c.get_value():
                seen[(c.get_name(), c.get_domain())] = c
        cookies = list(seen.values())
        names = {c.get_name() for c in cookies}
        _log('harvested %d cookies:' % len(cookies), sorted(names))

        if not names & set(AUTH_COOKIES):
            self._deliver(
                False,
                'The sign-in didn’t finish — no iCloud session cookie was set. '
                'Make sure you completed two-factor and "Trust this browser", '
                'then use "I’ve signed in".')
            return
        try:
            n = _write_pyicloud_session(self._session_dir, self._apple_id, cookies)
            _log('wrote session, %d cookies in the jar' % n)
        except Exception as e:  # noqa: BLE001
            self._deliver(False, str(e))
            return
        self._deliver(True, '')

    # ---- teardown ------------------------------------------------------

    def _deliver(self, ok, detail):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        self._finished = True
        shutil.rmtree(self._tmp, ignore_errors=True)
        on_done, self._on_done = self._on_done, None
        self.destroy()
        if on_done:
            def _fire():
                on_done(ok, detail)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_fire)

    def _on_close(self, *_a):
        if not self._finished:
            self._deliver(False, 'cancelled')
        return False
