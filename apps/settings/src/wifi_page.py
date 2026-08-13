import os

import gi

gi.require_version('NM', '1.0')

from gi.repository import Adw, Gio, GLib, GObject, Gtk, NM

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


def _signal_icon_name(strength: int) -> str:
    if strength >= 80:
        return 'network-wireless-signal-excellent-symbolic'
    if strength >= 55:
        return 'network-wireless-signal-good-symbolic'
    if strength >= 30:
        return 'network-wireless-signal-ok-symbolic'
    if strength > 0:
        return 'network-wireless-signal-weak-symbolic'
    return 'network-wireless-signal-none-symbolic'


def _ap_is_secured(ap: NM.AccessPoint) -> bool:
    if ap.get_wpa_flags() != NM.AccessPointSecurityFlags.NONE:
        return True
    if ap.get_rsn_flags() != NM.AccessPointSecurityFlags.NONE:
        return True
    return bool(ap.get_flags() & NM.AccessPointFlags.PRIVACY)


def _ap_ssid(ap: NM.AccessPoint):
    ssid = ap.get_ssid()
    if ssid is None:
        return None
    return NM.utils_ssid_to_utf8(ssid.get_data())


class NetworkRow(Gtk.Box):
    """One row in the known/other-networks list: name, lock, signal bars, menu."""

    def __init__(self, title: str, secured: bool, strength: int, show_check: bool = False, on_activate=None, on_menu=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        check = Gtk.Image.new_from_icon_name('object-select-symbolic')
        check.set_opacity(1.0 if show_check else 0.0)
        self.append(check)

        label = Gtk.Label(label=title, xalign=0, hexpand=True)
        self.append(label)

        if secured:
            self.append(Gtk.Image.new_from_icon_name('channel-secure-symbolic'))
        self.append(Gtk.Image.new_from_icon_name(_signal_icon_name(strength)))

        menu_btn = Gtk.MenuButton(icon_name='view-more-symbolic', css_classes=['flat', 'circular'])
        self.append(menu_btn)

        if on_activate:
            click = Gtk.GestureClick()
            click.connect('released', lambda *_: on_activate())
            self.add_controller(click)
            self.set_cursor_from_name('pointer')


class WifiPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._client = None
        self._device = None
        self._scan_timeout_id = 0

        self._build_ui()
        self._set_loading(True)

        NM.Client.new_async(None, self._on_client_ready)

    # ---- UI construction ----------------------------------------------

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'wifi.svg'), 'network-wireless-symbolic',
            'Wi-Fi', 'Connect to available networks or manage your Wi-Fi settings.',
        ))

        # Top info card: icon, title, description, toggle
        card = Gtk.Box(css_classes=['wifi-card'])
        card_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
            margin_start=14, margin_end=14, margin_top=14, margin_bottom=14,
        )
        icon_path = os.path.join(ICON_DIR, 'wifi.svg')
        if os.path.isfile(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name('network-wireless-symbolic')
        icon.set_pixel_size(32)
        card_box.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label='Wi-Fi', xalign=0, css_classes=['title-4']))
        desc = Gtk.Label(
            label='Set up Wi-Fi to wirelessly connect this computer to the internet.',
            xalign=0, wrap=True, css_classes=['dim-label'],
        )
        text_box.append(desc)
        card_box.append(text_box)

        self._toggle = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._toggle.connect('state-set', self._on_toggle_state_set)
        card_box.append(self._toggle)

        card.append(card_box)
        self.append(card)

        # Connected-network status row (hidden until connected)
        self._connected_frame = Gtk.Box(css_classes=['wifi-card'], visible=False)
        connected_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            margin_start=14, margin_end=14, margin_top=10, margin_bottom=10,
        )
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self._connected_name_label = Gtk.Label(xalign=0)
        status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dot = Gtk.Box(width_request=8, height_request=8, css_classes=['connected-dot'], valign=Gtk.Align.CENTER)
        status_line.append(dot)
        status_line.append(Gtk.Label(label='Connected', xalign=0, css_classes=['dim-label']))
        status_box.append(self._connected_name_label)
        status_box.append(status_line)
        connected_box.append(status_box)
        connected_box.append(Gtk.Image.new_from_icon_name('channel-secure-symbolic'))
        self._connected_signal_icon = Gtk.Image.new_from_icon_name('network-wireless-signal-excellent-symbolic')
        connected_box.append(self._connected_signal_icon)
        details_btn = Gtk.Button(label='Details…')
        details_btn.connect('clicked', self._on_details_clicked)
        connected_box.append(details_btn)
        self._connected_frame.append(connected_box)
        self.append(self._connected_frame)

        # Known network
        self._known_label = Gtk.Label(label='Known Network', xalign=0, css_classes=['heading'], visible=False)
        self.append(self._known_label)
        self._known_list = Gtk.ListBox(
            css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE, visible=False,
        )
        self.append(self._known_list)

        # Other networks
        other_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        other_header.append(Gtk.Label(label='Other Networks', xalign=0, hexpand=True, css_classes=['heading']))
        self._scan_spinner = Gtk.Spinner()
        other_header.append(self._scan_spinner)
        self.append(other_header)

        self._other_header = other_header
        self._other_scroller = Gtk.ScrolledWindow(vexpand=True)
        self._other_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._other_scroller.set_child(self._other_list)
        self.append(self._other_scroller)

        self._status_label = Gtk.Label(
            label='Checking for Wi-Fi hardware…', wrap=True,
            css_classes=['dim-label'], valign=Gtk.Align.CENTER, vexpand=True,
        )
        self.append(self._status_label)

    def _set_loading(self, loading: bool):
        self._toggle.set_sensitive(not loading)

    # ---- NetworkManager wiring ------------------------------------------

    def _on_client_ready(self, source, result):
        try:
            self._client = NM.Client.new_finish(result)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not connect to NetworkManager: {e.message}')
            self._status_label.set_visible(True)
            return

        self._device = self._find_wifi_device()
        self._set_loading(False)

        if not self._device:
            self._status_label.set_label('No Wi-Fi hardware detected on this computer.')
            self._status_label.set_visible(True)
            self._toggle.set_sensitive(False)
            self._other_list.set_visible(False)
            self._other_scroller.set_visible(False)
            self._other_header.set_visible(False)
            return

        self._status_label.set_visible(False)
        self._device.connect('notify::active-access-point', lambda *_: self._refresh())
        self._device.connect('state-changed', lambda *_: self._refresh())
        self._device.connect('access-point-added', lambda *_a: self._refresh())
        self._device.connect('access-point-removed', lambda *_a: self._refresh())
        self._client.connect('notify::wireless-enabled', lambda *_: self._refresh())

        self._refresh()
        self._request_scan()
        self._scan_timeout_id = GLib.timeout_add_seconds(15, self._periodic_scan)

    def _find_wifi_device(self):
        for device in self._client.get_devices():
            if device.get_device_type() == NM.DeviceType.WIFI:
                return device
        return None

    def _periodic_scan(self):
        self._request_scan()
        return GLib.SOURCE_CONTINUE

    def _request_scan(self):
        if not self._device or not self._client.wireless_get_enabled():
            return
        self._scan_spinner.start()
        try:
            self._device.request_scan_async(None, self._on_scan_done)
        except GLib.Error:
            self._scan_spinner.stop()

    def _on_scan_done(self, device, result):
        self._scan_spinner.stop()
        try:
            device.request_scan_finish(result)
        except GLib.Error:
            pass
        self._refresh()

    def _on_toggle_state_set(self, switch, state):
        if self._client:
            self._client.wireless_set_enabled(state)
        return False  # let GTK still update the switch visual state

    # ---- Rendering ------------------------------------------------------

    def _refresh(self):
        if not self._client or not self._device:
            return

        enabled = self._client.wireless_get_enabled()
        self._toggle.set_active(enabled)

        active_ap = self._device.get_active_access_point() if enabled else None
        active_ssid = _ap_ssid(active_ap) if active_ap else None

        self._connected_frame.set_visible(bool(active_ap))
        if active_ap:
            self._connected_name_label.set_label(active_ssid or '(hidden network)')
            self._connected_signal_icon.set_from_icon_name(_signal_icon_name(active_ap.get_strength()))

        while (child := self._known_list.get_first_child()) is not None:
            self._known_list.remove(child)
        while (child := self._other_list.get_first_child()) is not None:
            self._other_list.remove(child)

        if not enabled:
            self._known_label.set_visible(False)
            self._known_list.set_visible(False)
            self._other_list.set_visible(False)
            self._other_scroller.set_visible(False)
            self._other_header.set_visible(False)
            return

        self._other_scroller.set_visible(True)
        self._other_header.set_visible(True)
        self._other_list.set_visible(True)

        known_conns = [
            c for c in self._client.get_connections()
            if c.get_connection_type() == '802-11-wireless'
        ]

        aps = sorted(self._device.get_access_points(), key=lambda a: a.get_strength(), reverse=True)
        seen_ssids = set()
        known_shown = False

        for ap in aps:
            ssid = _ap_ssid(ap)
            if not ssid or ssid in seen_ssids:
                continue
            seen_ssids.add(ssid)

            is_active = active_ssid is not None and ssid == active_ssid
            matching_conn = next((c for c in known_conns if ap.connection_valid(c)), None)

            if is_active:
                if matching_conn:
                    row = NetworkRow(ssid, _ap_is_secured(ap), ap.get_strength(), show_check=True)
                    self._known_list.append(row)
                    self._known_list.set_visible(True)
                    self._known_label.set_visible(True)
                    known_shown = True
                continue

            row = NetworkRow(
                ssid, _ap_is_secured(ap), ap.get_strength(),
                on_activate=lambda a=ap, c=matching_conn: self._connect_to(a, c),
            )
            self._other_list.append(row)

        if not known_shown:
            self._known_label.set_visible(False)
            self._known_list.set_visible(False)

    # ---- Connecting -------------------------------------------------------

    def _connect_to(self, ap: NM.AccessPoint, known_connection):
        if known_connection is not None:
            self._client.activate_connection_async(
                known_connection, self._device, ap.get_path(), None, self._on_activate_done,
            )
            return

        if not _ap_is_secured(ap):
            self._client.add_and_activate_connection_async(
                None, self._device, ap.get_path(), None, self._on_activate_done,
            )
            return

        self._prompt_password(ap)

    def _prompt_password(self, ap: NM.AccessPoint):
        ssid = _ap_ssid(ap) or ''
        dialog = Adw.AlertDialog(
            heading=f'Enter the password for “{ssid}”',
            body='This network requires a password to join.',
        )
        entry = Gtk.PasswordEntry(show_peek_icon=True)
        entry.set_margin_top(8)
        dialog.set_extra_child(entry)
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('connect', 'Connect')
        dialog.set_response_appearance('connect', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('connect')

        def on_response(_dialog, response):
            if response != 'connect':
                return
            password = entry.get_text()

            connection = NM.SimpleConnection.new()
            s_con = NM.SettingConnection.new()
            s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
            s_con.set_property(NM.SETTING_CONNECTION_TYPE, '802-11-wireless')
            connection.add_setting(s_con)

            s_wifi = NM.SettingWireless.new()
            s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode('utf-8')))
            connection.add_setting(s_wifi)

            s_sec = NM.SettingWirelessSecurity.new()
            s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, 'wpa-psk')
            s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            connection.add_setting(s_sec)

            self._client.add_and_activate_connection_async(
                connection, self._device, ap.get_path(), None, self._on_activate_done,
            )

        dialog.connect('response', on_response)
        dialog.present(self.get_root())

    def _on_activate_done(self, client, result):
        try:
            client.add_and_activate_connection_finish(result)
        except TypeError:
            try:
                client.activate_connection_finish(result)
            except GLib.Error as e:
                self._status_label.set_label(f'Could not connect: {e.message}')
                self._status_label.set_visible(True)
                return
        except GLib.Error as e:
            self._status_label.set_label(f'Could not connect: {e.message}')
            self._status_label.set_visible(True)
            return
        self._refresh()

    def _on_details_clicked(self, _btn):
        active_ap = self._device.get_active_access_point() if self._device else None
        if not active_ap:
            return
        ssid = _ap_ssid(active_ap) or '(hidden network)'
        secured = 'Secured' if _ap_is_secured(active_ap) else 'Open'
        dialog = Adw.AlertDialog(
            heading=ssid,
            body=f'{secured} network\nSignal strength: {active_ap.get_strength()}%',
        )
        dialog.add_response('close', 'Close')
        dialog.present(self.get_root())
