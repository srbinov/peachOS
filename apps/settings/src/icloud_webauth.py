"""Browser-based iCloud sign-in for peachOS Settings.

Apple has no OAuth for third-party iCloud access, so the Photos widget uses
pyicloud (a reverse-engineered private API). pyicloud's own SRP + 2FA flow from
headless Python is unreliable -- Apple's risk engine often just doesn't push a
code. Instead, embed Apple's OWN web sign-in in a WebKitGTK view: 2FA works
natively there, then harvest the session cookies, confirm them against
setup.icloud.com (which also tells us the Apple ID), and drop everything where
pyicloud looks: `<session_dir>/<sanitised_apple_id>.cookiejar` + a stub
`.session`.

Apple's login is cross-site (idmsa.apple.com authenticates, *.icloud.com holds
the session), so ITP and third-party-cookie blocking BOTH have to be off.
"""

import http.cookiejar
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
import uuid

# Belt-and-suspenders for old GPUs -- must be set before WebKit's compositor
# initialises (see the HardwareAccelerationPolicy note in ICloudWebAuth).
os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit, GLib  # noqa: E402

ICLOUD_URL = 'https://www.icloud.com/'
VALIDATE_URL = 'https://setup.icloud.com/setup/ws/1/validate'
# Any of these present (with a value) => the web session is probably ready.
AUTH_COOKIES = ('X-APPLE-WEBAUTH-TOKEN', 'X-APPLE-WEBAUTH-USER')
# Only cookies from these domains are worth keeping.
KEEP_DOMAIN_RE = re.compile(r'(^|\.)(icloud\.com|apple\.com)$')

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


def _jar_from_soup(soup_cookies) -> http.cookiejar.LWPCookieJar:
    jar = http.cookiejar.LWPCookieJar()
    for c in soup_cookies:
        name, value, domain = c.get_name(), c.get_value(), c.get_domain() or ''
        if not name or not KEEP_DOMAIN_RE.search(domain.lstrip('.')):
            continue
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
    return jar


def _validate(jar):
    """POST setup.icloud.com/validate with the harvested cookies (same call
    pyicloud's _validate_token makes). Returns the Apple ID on success, else
    raises."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        VALIDATE_URL, data=b'null', method='POST',
        headers={'Content-Type': 'text/plain',
                 'Origin': 'https://www.icloud.com',
                 'Referer': 'https://www.icloud.com/',
                 'User-Agent': 'Mozilla/5.0'})
    with opener.open(req, timeout=25) as resp:
        data = json.load(resp)
    apple_id = (data.get('dsInfo') or {}).get('appleId')
    if not apple_id:
        raise RuntimeError('session did not validate (no dsInfo.appleId)')
    return apple_id


def _write_session(session_dir, apple_id, jar) -> None:
    os.makedirs(session_dir, exist_ok=True)
    base = os.path.join(session_dir, _sanitise(apple_id))
    jar.filename = base + '.cookiejar'
    jar.save(ignore_discard=True, ignore_expires=True)
    trust = ''
    for c in jar:
        if c.name == 'X-APPLE-WEBAUTH-HSA-TRUST':
            trust = c.value
    with open(base + '.session', 'w', encoding='utf-8') as f:
        # session_token only needs to be truthy so pyicloud's authenticate()
        # tries the cookie-only _validate_token() before the SRP path.
        json.dump({'session_token': 'web', 'client_id': 'auth-%s' % uuid.uuid4(),
                   'account_country': 'USA', 'trust_token': trust,
                   'trust_eligible': True}, f)


class ICloudWebAuth(Gtk.Window):
    """`on_done(ok: bool, detail: str)` -- on success detail is the Apple ID;
    on failure it's an error string ('cancelled' if the user closed the window)."""

    def __init__(self, parent, session_dir: str, on_done):
        super().__init__(title='Sign in to iCloud', transient_for=parent,
                         modal=True, default_width=980, default_height=760)
        self._session_dir = session_dir
        self._on_done = on_done
        self._finished = False
        self._poll_id = 0
        self._tmp = tempfile.mkdtemp(prefix='peachos-icloud-web-')

        # Persistent (not ephemeral) session in a throwaway dir.
        self._net = WebKit.NetworkSession.new(self._tmp, self._tmp)
        self._net.set_itp_enabled(False)               # cross-site: idmsa -> icloud
        self._cookies = self._net.get_cookie_manager()
        self._cookies.set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)

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

    # ---- detect ---------------------------------------------------------

    def _poll(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        self._cookies.get_all_cookies(None, self._probe_done)
        return GLib.SOURCE_CONTINUE

    def _probe_done(self, mgr, res):
        try:
            cookies = mgr.get_all_cookies_finish(res)
        except GLib.Error:
            return
        names = {c.get_name() for c in cookies if c.get_value()}
        if names & set(AUTH_COOKIES):
            _log('auto: saw', sorted(names & set(AUTH_COOKIES)))
            self._harvest('auto')

    # ---- harvest + validate (off the UI thread) -----------------------

    def _harvest(self, how):
        if self._finished:
            return
        self._finished = True
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        self._status.set_label('Checking the session…')
        self._continue_btn.set_sensitive(False)
        _log('harvest (%s)' % how)
        self._cookies.get_all_cookies(None, self._got_all)

    def _got_all(self, mgr, res):
        try:
            cookies = list(mgr.get_all_cookies_finish(res))
        except GLib.Error as e:
            self._deliver(False, str(e))
            return
        jar = _jar_from_soup(cookies)
        names = sorted({c.name for c in jar})
        _log('kept %d apple cookies:' % len(names), names)
        if not set(names) & set(AUTH_COOKIES):
            self._deliver(
                False,
                'The sign-in didn’t finish — no iCloud session cookie was set. '
                'Complete two-factor and "Trust this browser", then press '
                '"I’ve signed in".')
            return

        def work():
            try:
                apple_id = _validate(jar)
                _write_session(self._session_dir, apple_id, jar)
                _log('validated as', apple_id)
                GLib.idle_add(self._deliver, True, apple_id)
            except Exception as e:  # noqa: BLE001
                _log('validate failed:', repr(e))
                GLib.idle_add(
                    self._deliver, False,
                    'Could not confirm the iCloud session. Try signing in again.')
        threading.Thread(target=work, daemon=True).start()

    # ---- teardown ----------------------------------------------------

    def _deliver(self, ok, detail):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        self._finished = True
        shutil.rmtree(self._tmp, ignore_errors=True)
        on_done, self._on_done = self._on_done, None
        try:
            self.destroy()
        except Exception:
            pass
        if on_done:
            on_done(ok, detail)
        return GLib.SOURCE_REMOVE

    def _on_close(self, *_a):
        if not self._finished:
            self._deliver(False, 'cancelled')
        return False
