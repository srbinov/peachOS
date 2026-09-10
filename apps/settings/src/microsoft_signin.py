"""Native Microsoft 365 sign-in for peachOS Settings.

Same idea as google_signin.py: run Microsoft's OAuth2 authorization-code +
PKCE flow ourselves -- open the consent page in the browser, catch the
redirect on a loopback socket, trade the code for tokens, hand them to GNOME
Online Accounts via `Manager.AddAccount('ms_graph', ...)`. No
gnome-control-center window.

The OAuth client is GNOME's own ms_graph client (compiled into
libgoa-backend, public / PKCE -- no secret), read out of that library at
runtime so nothing lives in this repo and we always match the installed GOA.
Microsoft's identity platform allows the `http://127.0.0.1:<port>` loopback
redirect for public clients without pre-registering the port.
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

AUTH_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
USERINFO_URL = 'https://graph.microsoft.com/v1.0/me'

# The scopes GOA's ms_graph provider itself requests (kept verbatim from
# libgoa-backend so an account added here is exactly as capable as one added
# through GNOME) plus the OIDC basics.
SCOPES = 'openid offline_access ' + ' '.join([
    'https://graph.microsoft.com/User.Read',
    'https://graph.microsoft.com/Mail.ReadWrite',
    'https://graph.microsoft.com/Mail.Send',
    'https://graph.microsoft.com/Calendars.ReadWrite',
    'https://graph.microsoft.com/Contacts.ReadWrite',
    'https://graph.microsoft.com/Files.ReadWrite',
    'https://graph.microsoft.com/Tasks.ReadWrite',
])

_LIBGOA_GLOBS = [
    '/usr/lib/*/libgoa-backend-1.0.so*',
    '/usr/lib/libgoa-backend-1.0.so*',
    '/usr/lib64/libgoa-backend-1.0.so*',
    '/usr/local/lib/*/libgoa-backend-1.0.so*',
]


def goa_ms_graph_client_id():
    """The ms_graph OAuth client id from the installed libgoa-backend, or None.

    In the library's string table the GUID sits immediately before the
    ms_graph scope list ("...\\x00b155a604-...\\x00\\x00offline_access ...").
    """
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
            m = re.search(
                rb'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
                rb'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\x00+offline_access',
                data)
            if m:
                return m.group(1).decode('ascii')
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


class MicrosoftSignIn:
    """Drive the flow. `on_done(ok: bool, detail: str)` runs on the main loop
    when it finishes (detail = the account address on success, else an error)."""

    def __init__(self, on_done):
        self._on_done = on_done
        self._cancelled = False
        self._done = False
        self._httpd = None
        self._client_id = goa_ms_graph_client_id()

    @property
    def available(self) -> bool:
        return self._client_id is not None

    def cancel(self):
        self._cancelled = True
        if self._httpd:
            try:
                self._httpd.socket.close()
            except Exception:
                pass

    def start(self):
        if not self._client_id:
            self._finish(False, 'Microsoft client credentials unavailable')
            return
        self._verifier = _b64url(os.urandom(40))
        challenge = _b64url(hashlib.sha256(self._verifier.encode()).digest())

        self._httpd = HTTPServer(('127.0.0.1', 0), _RedirectHandler)
        self._httpd.oauth_result = None
        self._httpd.timeout = 300
        self._redirect = f'http://127.0.0.1:{self._httpd.server_address[1]}/'

        url = AUTH_URL + '?' + urllib.parse.urlencode({
            'client_id': self._client_id,
            'redirect_uri': self._redirect,
            'response_type': 'code',
            'response_mode': 'query',
            'scope': SCOPES,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'prompt': 'select_account',
        })

        self._open_browser(url)
        threading.Thread(target=self._run, daemon=True).start()

    def _open_browser(self, url):
        if getattr(self, '_browser_opened', False):
            return
        self._browser_opened = True
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
            return
        except GLib.Error:
            pass
        try:
            Gio.Subprocess.new(['xdg-open', url], Gio.SubprocessFlags.NONE)
        except GLib.Error:
            pass

    # --- worker thread ------------------------------------------------

    def _run(self):
        try:
            self._httpd.handle_request()  # blocks until the redirect (or timeout)
            if self._cancelled:
                return
            result = self._httpd.oauth_result or {}
            if 'error' in result:
                self._finish(False, result.get('error_description', result['error'])[0])
                return
            code = result.get('code', [None])[0]
            if not code:
                self._finish(False, 'No authorization received')
                return

            tokens = self._exchange(code)
            if 'access_token' not in tokens:
                self._finish(False, tokens.get('error_description',
                                               tokens.get('error', 'Token exchange failed')))
                return
            address = self._userinfo(tokens['access_token'])
            self._add_to_goa(address, tokens)
            self._finish(True, address)
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
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            try:
                return json.load(e)
            except Exception:
                raise

    def _exchange(self, code):
        return self._post(TOKEN_URL, {
            'client_id': self._client_id,
            'code': code,
            'code_verifier': self._verifier,
            'redirect_uri': self._redirect,
            'grant_type': 'authorization_code',
            'scope': SCOPES,
        })

    def _userinfo(self, access_token):
        req = urllib.request.Request(
            USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            me = json.load(resp)
        return me.get('mail') or me.get('userPrincipalName') or ''

    def _add_to_goa(self, address, tokens):
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
            'FilesEnabled': 'false',
        }

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            'org.gnome.OnlineAccounts', '/org/gnome/OnlineAccounts/Manager',
            'org.gnome.OnlineAccounts.Manager', 'AddAccount',
            GLib.Variant('(sssa{sv}a{ss})',
                         ('ms_graph', address or 'account', address or 'account',
                          credentials, details)),
            GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None,
        )

    def _finish(self, ok, detail):
        if self._done or self._cancelled:
            return
        self._done = True

        def deliver():
            self._on_done(ok, detail)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(deliver)
