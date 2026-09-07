"""Native Google sign-in for peachOS Settings.

Runs Google's OAuth2 authorization-code + PKCE flow ourselves -- opens the
consent page in the user's browser, catches the redirect on a loopback
socket, trades the code for tokens, and hands those to GNOME Online Accounts
via `Manager.AddAccount('google', ...)`. No gnome-control-center window, no
GOA browser dialog.

The OAuth client is GNOME's own (the one compiled into libgoa-backend that
every GNOME distro ships) -- read out of that library at runtime so nothing
sensitive lives in this repo and we always match the installed GOA. If it
can't be read, callers fall back to launching the system accounts panel.
"""

import base64
import glob
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import gi

gi.require_version('Goa', '1.0')
from gi.repository import Gio, GLib

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

# The scopes GOA's Google provider itself requests (keep in sync so the account
# is as capable as one added through GNOME).
SCOPES = ' '.join([
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar',
    'https://www.google.com/m8/feeds/',
    'https://www.googleapis.com/auth/carddav',
    'https://mail.google.com/',
    'https://www.googleapis.com/auth/tasks',
])

_LIBGOA_GLOBS = [
    '/usr/lib/*/libgoa-backend-1.0.so*',
    '/usr/lib/libgoa-backend-1.0.so*',
    '/usr/lib64/libgoa-backend-1.0.so*',
    '/usr/local/lib/*/libgoa-backend-1.0.so*',
]


def goa_google_creds():
    """(client_id, client_secret) from the installed libgoa-backend, or None."""
    seen = set()
    for pattern in _LIBGOA_GLOBS:
        for path in glob.glob(pattern):
            if path in seen or not os.path.isfile(path):
                continue
            seen.add(path)
            try:
                data = open(path, 'rb').read()
            except OSError:
                continue
            cid = re.search(rb'[0-9]+-[a-z0-9]{32}\.apps\.googleusercontent\.com', data)
            # the secret is the 24-char token stored right after the "google"
            # provider-name string in libgoa-backend's string table
            sec = re.search(rb'\x00google\x00([A-Za-z0-9_\-]{24})\x00', data)
            if cid and sec:
                return cid.group().decode('ascii'), sec.group(1).decode('ascii')
    return None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.oauth_result = params  # type: ignore[attr-defined]
        body = (b'<!doctype html><meta charset=utf-8>'
                b'<title>peachOS</title>'
                b'<body style="font-family:system-ui;text-align:center;padding:3rem;color:#333">'
                b'<h2>You can close this tab.</h2>'
                b'<p>Return to System Settings to finish.</p>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):  # silence
        pass


class GoogleSignIn:
    """Drive the flow. `on_done(ok: bool, detail: str)` is called on the main
    loop when it finishes (detail = the email on success, an error otherwise)."""

    def __init__(self, on_done):
        self._on_done = on_done
        self._cancelled = False
        self._httpd = None
        self._creds = goa_google_creds()

    @property
    def available(self) -> bool:
        return self._creds is not None

    def cancel(self):
        self._cancelled = True
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass

    def start(self):
        if not self._creds:
            self._finish(False, 'Google credentials unavailable')
            return
        self._verifier = _b64url(os.urandom(40))
        challenge = _b64url(hashlib.sha256(self._verifier.encode()).digest())

        self._httpd = HTTPServer(('127.0.0.1', 0), _RedirectHandler)
        self._httpd.oauth_result = None
        self._httpd.timeout = 300
        self._redirect = f'http://127.0.0.1:{self._httpd.server_address[1]}'

        client_id, _ = self._creds
        url = AUTH_URL + '?' + urllib.parse.urlencode({
            'client_id': client_id,
            'redirect_uri': self._redirect,
            'response_type': 'code',
            'scope': SCOPES,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'access_type': 'offline',
            'prompt': 'consent',
        })

        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    # --- worker thread ------------------------------------------------

    def _run(self, url):
        try:
            GLib.idle_add(lambda: Gio.AppInfo.launch_default_for_uri(url, None))
            self._httpd.handle_request()  # blocks until the redirect (or timeout)
            if self._cancelled:
                return
            result = self._httpd.oauth_result or {}
            if 'error' in result:
                self._finish(False, result['error'][0])
                return
            code = result.get('code', [None])[0]
            if not code:
                self._finish(False, 'No authorization received')
                return

            tokens = self._exchange(code)
            email = self._userinfo(tokens['access_token'])
            self._add_to_goa(email, tokens)
            self._finish(True, email)
        except Exception as exc:  # noqa: BLE001
            self._finish(False, str(exc))
        finally:
            try:
                self._httpd.server_close()
            except Exception:
                pass

    def _post(self, url, fields):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(url, data=data, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    def _exchange(self, code):
        client_id, client_secret = self._creds
        return self._post(TOKEN_URL, {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'code_verifier': self._verifier,
            'redirect_uri': self._redirect,
            'grant_type': 'authorization_code',
        })

    def _userinfo(self, access_token):
        req = urllib.request.Request(
            USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp).get('email', '')

    def _add_to_goa(self, email, tokens):
        expires_at = (datetime.now(timezone.utc)
                      + timedelta(seconds=int(tokens.get('expires_in', 3600))))
        credentials = {
            'access_token': GLib.Variant('s', tokens['access_token']),
            'access_token_expires_at':
                GLib.Variant('s', expires_at.strftime('%Y-%m-%dT%H:%M:%SZ')),
        }
        if tokens.get('refresh_token'):
            credentials['refresh_token'] = GLib.Variant('s', tokens['refresh_token'])

        details = {
            'MailEnabled': 'true',
            'CalendarEnabled': 'true',
            'ContactsEnabled': 'true',
        }

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            'org.gnome.OnlineAccounts', '/org/gnome/OnlineAccounts/Manager',
            'org.gnome.OnlineAccounts.Manager', 'AddAccount',
            GLib.Variant('(sssa{sv}a{ss})',
                         ('google', email or 'account', email or 'account',
                          credentials, details)),
            GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
        )

    def _finish(self, ok, detail):
        GLib.idle_add(self._on_done, ok, detail)
