import os
import secrets
import shutil
import socket
import string
import subprocess

from gi.repository import GLib, Gtk

from widgets import ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

GRD_DATA_DIR = os.path.join(GLib.get_user_data_dir(), 'gnome-remote-desktop')
TLS_CERT = os.path.join(GRD_DATA_DIR, 'tls.crt')
TLS_KEY = os.path.join(GRD_DATA_DIR, 'tls.key')


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None


def _card(page, heading=None):
    if heading:
        page.append(Gtk.Label(label=heading, xalign=0, css_classes=['heading'], margin_start=4))
    card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
    page.append(card)
    return card


def _info_row(label, value):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
    row.set_margin_start(14)
    row.set_margin_end(14)
    row.set_margin_top(10)
    row.set_margin_bottom(10)
    row.append(Gtk.Label(label=label, xalign=0, hexpand=True))
    value_label = Gtk.Label(label=value, xalign=1, selectable=True, css_classes=['dim-label'])
    row.append(value_label)
    return row, value_label


class SharingPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self._syncing = False

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'sharing.svg'), 'network-workgroup-symbolic',
            'Sharing', 'Let other devices on your network reach this computer.',
        ))

        self._build_remote_desktop()
        self._build_media_sharing()
        self._build_remote_login()

        self._refresh()

    # ---- Remote Desktop (RDP via gnome-remote-desktop) --------------

    def _build_remote_desktop(self):
        self._grd_available = shutil.which('grdctl') is not None
        card = _card(self, 'Remote Desktop')

        self._rdp_row = ToggleRow(
            'Screen Sharing',
            'Let another device view and control this screen over RDP (Remote Desktop).')
        self._rdp_row.switch.connect('state-set', self._on_rdp_toggled)
        card.append(self._rdp_row)

        self._rdp_detail_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'],
                                            selection_mode=Gtk.SelectionMode.NONE, visible=False)
        self._rdp_address_row, self._rdp_address_label = _info_row('Address', '')
        self._rdp_detail_card.append(self._rdp_address_row)

        user_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        user_row.set_margin_start(14)
        user_row.set_margin_end(14)
        user_row.set_margin_top(10)
        user_row.set_margin_bottom(10)
        user_row.append(Gtk.Label(label='Username', xalign=0, hexpand=True))
        self._rdp_user_entry = Gtk.Entry(width_chars=16, text=os.environ.get('USER', ''))
        self._rdp_user_entry.connect('changed', lambda *_a: self._save_rdp_credentials())
        user_row.append(self._rdp_user_entry)
        self._rdp_detail_card.append(user_row)

        pass_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, css_classes=['network-row'])
        pass_row.set_margin_start(14)
        pass_row.set_margin_end(14)
        pass_row.set_margin_top(10)
        pass_row.set_margin_bottom(10)
        pass_row.append(Gtk.Label(label='Password', xalign=0, hexpand=True))
        self._rdp_pass_entry = Gtk.PasswordEntry(show_peek_icon=True, width_request=160)
        self._rdp_pass_entry.connect('changed', lambda *_a: self._save_rdp_credentials())
        pass_row.append(self._rdp_pass_entry)
        gen_btn = Gtk.Button(icon_name='view-refresh-symbolic', css_classes=['flat'],
                             valign=Gtk.Align.CENTER, tooltip_text='Generate a new password')
        gen_btn.connect('clicked', self._generate_rdp_password)
        pass_row.append(gen_btn)
        self._rdp_detail_card.append(pass_row)

        self._rdp_view_only_row = ToggleRow('View Only', 'Remote users can watch but not control.')
        self._rdp_view_only_row.switch.connect('state-set', self._on_view_only_toggled)
        self._rdp_detail_card.append(self._rdp_view_only_row)
        self.append(self._rdp_detail_card)

        if not self._grd_available:
            self._rdp_row.switch.set_sensitive(False)
            self._rdp_row.append(Gtk.Label(label='Not installed', css_classes=['dim-label', 'caption']))

    def _on_rdp_toggled(self, _switch, state):
        if self._syncing or not self._grd_available:
            return False
        if state:
            if not self._ensure_tls_cert():
                self._rdp_row.switch.set_active(False)
                return True
            _run(['grdctl', 'rdp', 'set-tls-cert', TLS_CERT])
            _run(['grdctl', 'rdp', 'set-tls-key', TLS_KEY])
            self._save_rdp_credentials()
            _run(['grdctl', 'rdp', 'enable'])
            _run(['systemctl', '--user', 'enable', '--now', 'gnome-remote-desktop.service'])
        else:
            _run(['grdctl', 'rdp', 'disable'])
            _run(['systemctl', '--user', 'disable', '--now', 'gnome-remote-desktop.service'])
        self._refresh()
        return False

    def _ensure_tls_cert(self):
        if os.path.isfile(TLS_CERT) and os.path.isfile(TLS_KEY):
            return True
        os.makedirs(GRD_DATA_DIR, exist_ok=True)
        result = _run([
            'openssl', 'req', '-new', '-newkey', 'rsa:4096', '-days', '720', '-nodes', '-x509',
            '-subj', '/C=US/ST=NONE/L=NONE/O=peachOS/CN=peachos-remote-desktop',
            '-out', TLS_CERT, '-keyout', TLS_KEY,
        ])
        return bool(result and result.returncode == 0
                    and os.path.isfile(TLS_CERT) and os.path.isfile(TLS_KEY))

    def _on_view_only_toggled(self, _switch, state):
        if self._syncing or not self._grd_available:
            return False
        _run(['grdctl', 'rdp', 'enable-view-only' if state else 'disable-view-only'])
        return False

    def _generate_rdp_password(self, _btn):
        alphabet = string.ascii_letters + string.digits
        self._rdp_pass_entry.set_text(''.join(secrets.choice(alphabet) for _ in range(12)))

    def _save_rdp_credentials(self):
        if self._syncing or not self._grd_available:
            return
        user = self._rdp_user_entry.get_text().strip()
        password = self._rdp_pass_entry.get_text()
        if user and password:
            _run(['grdctl', 'rdp', 'set-credentials', user, password])

    def _rdp_address(self):
        host = socket.gethostname()
        try:
            ip = socket.gethostbyname(host)
            if not ip.startswith('127.'):
                return f'{ip}:3389'
        except OSError:
            pass
        return f'{host}:3389'

    # ---- Media Sharing (DLNA via Rygel) ---------------------------

    def _build_media_sharing(self):
        self._rygel_available = shutil.which('rygel') is not None
        card = _card(self, 'Media Sharing')
        self._media_row = ToggleRow(
            'Share Media on This Network',
            'Stream your Music, Pictures, and Videos folders to DLNA devices like TVs and consoles.')
        self._media_row.switch.connect('state-set', self._on_media_toggled)
        card.append(self._media_row)
        if not self._rygel_available:
            self._media_row.switch.set_sensitive(False)
            self._media_row.append(Gtk.Label(label='Not installed', css_classes=['dim-label', 'caption']))

    def _on_media_toggled(self, _switch, state):
        if self._syncing or not self._rygel_available:
            return False
        action = 'enable' if state else 'disable'
        _run(['systemctl', '--user', action, '--now', 'rygel.service'])
        return False

    # ---- Remote Login (SSH) --------------------------------------

    def _build_remote_login(self):
        self._ssh_unit = None
        for unit in ('ssh.service', 'sshd.service'):
            listed = _run(['systemctl', 'list-unit-files', unit])
            if listed and unit in (listed.stdout or ''):
                self._ssh_unit = unit
                break
        card = _card(self, 'Remote Login')
        self._ssh_row = ToggleRow(
            'Allow SSH Access', 'Sign in to a terminal on this computer from another device.')
        self._ssh_row.switch.connect('state-set', self._on_ssh_toggled)
        card.append(self._ssh_row)
        self._ssh_addr_row, self._ssh_addr_label = _info_row('Command', '')
        card.append(self._ssh_addr_row)
        if not self._ssh_unit:
            self._ssh_row.switch.set_sensitive(False)
            self._ssh_row.append(Gtk.Label(label='Install openssh-server', css_classes=['dim-label', 'caption']))
            self._ssh_addr_row.set_visible(False)

    def _on_ssh_toggled(self, _switch, state):
        if self._syncing or not self._ssh_unit:
            return False
        action = 'enable' if state else 'disable'
        _run(['pkexec', 'systemctl', action, '--now', self._ssh_unit])
        self._refresh()
        return False

    # ---- refresh ------------------------------------------------

    def _refresh(self):
        self._syncing = True

        if self._grd_available:
            status = _run(['grdctl', 'status', '--show-credentials'])
            text = status.stdout if status else ''
            rdp_enabled = 'Status: enabled' in text
            self._rdp_row.switch.set_active(rdp_enabled)
            self._rdp_detail_card.set_visible(rdp_enabled)
            self._rdp_address_label.set_label(self._rdp_address())
            self._rdp_view_only_row.switch.set_active('View-only: yes' in text)
            for line in text.splitlines():
                line = line.strip()
                if line.startswith('Username:') and not self._rdp_user_entry.get_text():
                    val = line.split(':', 1)[1].strip()
                    if val and val != '(empty)':
                        self._rdp_user_entry.set_text(val)

        if self._rygel_available:
            active = _run(['systemctl', '--user', 'is-active', 'rygel.service'])
            self._media_row.switch.set_active(bool(active and active.stdout.strip() == 'active'))

        if self._ssh_unit:
            active = _run(['systemctl', 'is-active', self._ssh_unit])
            on = bool(active and active.stdout.strip() == 'active')
            self._ssh_row.switch.set_active(on)
            self._ssh_addr_row.set_visible(on)
            self._ssh_addr_label.set_label(f'ssh {os.environ.get("USER", "user")}@{self._rdp_address().split(":")[0]}')

        self._syncing = False
