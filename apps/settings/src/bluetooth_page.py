import os

from gi.repository import Gio, GLib, Gtk

from widgets import load_sized_image, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

BLUEZ_SERVICE = 'org.bluez'
ADAPTER_IFACE = 'org.bluez.Adapter1'
DEVICE_IFACE = 'org.bluez.Device1'
BATTERY_IFACE = 'org.bluez.Battery1'
OBJMGR_IFACE = 'org.freedesktop.DBus.ObjectManager'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

# How long to wait after the last BlueZ signal before rebuilding the list. An active
# discovery scan fires InterfacesAdded + a stream of PropertiesChanged (RSSI) for every
# device in range -- dozens per second in a dense RF environment. Coalesce them.
_REFRESH_DEBOUNCE_MS = 900


# audio/video (Class-of-Device major 4), by minor device class
_COD_AV_MINOR = {
    1: 'audio-headset-symbolic', 2: 'audio-headset-symbolic',
    4: 'audio-input-microphone-symbolic', 5: 'audio-speakers-symbolic',
    6: 'audio-headphones-symbolic', 7: 'multimedia-player-symbolic',
    8: 'audio-card-symbolic', 10: 'video-display-symbolic',
    11: 'video-display-symbolic', 12: 'video-display-symbolic',
    13: 'camera-video-symbolic',
}
_COD_MAJOR = {1: 'computer-symbolic', 2: 'phone-symbolic',
              3: 'network-wireless-symbolic', 6: 'camera-photo-symbolic'}
_COD_PERIPHERAL = {1: 'input-keyboard-symbolic', 2: 'input-mouse-symbolic',
                   3: 'input-keyboard-symbolic'}


def _device_icon_name(props: dict) -> str:
    # BlueZ usually classifies the device for us in its own Icon property
    # (freedesktop name derived from Class-of-Device / LE Appearance). Kept in
    # sync with deviceIconName() in the top panel's bluetoothData.js.
    hint = props.get('Icon')
    if hint:
        return hint if hint.endswith('-symbolic') else f'{hint}-symbolic'

    cod = props.get('Class') or 0
    if cod:
        major = (cod >> 8) & 0x1f
        minor = (cod >> 2) & 0x3f
        if major == 4:
            return _COD_AV_MINOR.get(minor, 'audio-card-symbolic')
        if major == 5:
            return _COD_PERIPHERAL.get((minor >> 4) & 0x3, 'input-mouse-symbolic')
        if major in _COD_MAJOR:
            return _COD_MAJOR[major]

    name = (props.get('Alias') or props.get('Name') or '').lower()
    if any(w in name for w in ('airpod', 'headphone', 'earbud', ' buds', 'beats')):
        return 'audio-headphones-symbolic'
    if any(w in name for w in ('speaker', 'soundbar', 'homepod', 'sonos')):
        return 'audio-speakers-symbolic'
    if 'keyboard' in name:
        return 'input-keyboard-symbolic'
    if 'mouse' in name or 'trackpad' in name:
        return 'input-mouse-symbolic'
    if 'watch' in name:
        return 'phone-symbolic'
    return 'bluetooth-symbolic'


def _has_real_name(props: dict) -> bool:
    # BlueZ hands back an object for every BLE advertisement it hears -- 150+ in a dense
    # area -- and synthesizes Name/Alias as the device's own dashed MAC address when it
    # broadcasts no real name. Only surface devices that actually identified themselves.
    # (This is the same test gnome-control-center uses.)
    name = props.get('Alias') or props.get('Name') or ''
    if not name:
        return False
    addr = (props.get('Address') or '').upper()
    return name.replace('-', ':').upper() != addr


class DeviceRow(Gtk.Box):
    def __init__(self, name: str, icon_name: str, subtitle: str = None, show_info: bool = False, on_info=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(20)
        self.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=name, xalign=0))
        if subtitle:
            text_box.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['dim-label', 'caption']))
        self.append(text_box)

        if show_info:
            info_btn = Gtk.Button(icon_name='dialog-information-symbolic', css_classes=['flat', 'circular'])
            if on_info:
                info_btn.connect('clicked', lambda *_: on_info())
            self.append(info_btn)


class BluetoothPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._bus = None
        self._adapter_path = None
        self._subscriptions = []
        self._refresh_source_id = 0
        self._get_objects_pending = False
        self._discovering = False
        self._destroyed = False

        self._build_ui()
        self._connect_bus()

        # Stop the scan (and the signal firehose) whenever the user leaves this page, and
        # tear everything down when the page itself goes away.
        self.connect('map', lambda *_: self._refresh())
        self.connect('unmap', lambda *_: self._stop_discovery())
        self.connect('destroy', lambda *_: self._teardown())

    # ---- UI ---------------------------------------------------------

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'bluetooth.svg'), 'bluetooth-symbolic',
            'Bluetooth', 'Connect to accessories you can use for activities such as streaming music, typing, and gaming.',
        ))

        card = Gtk.Box(css_classes=['wifi-card'])
        card_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
            margin_start=14, margin_end=14, margin_top=14, margin_bottom=14,
        )
        icon_path = os.path.join(ICON_DIR, 'bluetooth.svg')
        if os.path.isfile(icon_path):
            icon = load_sized_image(icon_path, 32)
        else:
            icon = Gtk.Image.new_from_icon_name('bluetooth-symbolic')
            icon.set_pixel_size(32)
        card_box.append(icon)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label='Bluetooth', xalign=0, css_classes=['title-4']))
        text_box.append(Gtk.Label(
            label='Connect to accessories you can use for activities such as streaming music, typing, and gaming.',
            xalign=0, wrap=True, css_classes=['dim-label'],
        ))
        card_box.append(text_box)

        self._toggle = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)
        self._toggle.connect('state-set', self._on_toggle_state_set)
        card_box.append(self._toggle)
        card.append(card_box)
        self.append(card)

        host = GLib.get_host_name() or 'this computer'
        self._discoverable_label = Gtk.Label(
            label=f'This computer is discoverable as “{host}” while Bluetooth Settings is open.',
            xalign=0, wrap=True, margin_start=4, css_classes=['dim-label'],
        )
        self.append(self._discoverable_label)

        self._my_label = Gtk.Label(label='My Devices', xalign=0, css_classes=['heading'], visible=False)
        self.append(self._my_label)
        self._my_list = Gtk.ListBox(
            css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE, visible=False,
        )
        self.append(self._my_list)

        self._nearby_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._nearby_header.append(Gtk.Label(label='Nearby Devices', xalign=0, hexpand=True, css_classes=['heading']))
        self._scan_spinner = Gtk.Spinner()
        self._nearby_header.append(self._scan_spinner)
        self.append(self._nearby_header)

        self._nearby_scroller = Gtk.ScrolledWindow(vexpand=True)
        self._nearby_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._nearby_scroller.set_child(self._nearby_list)
        self.append(self._nearby_scroller)

        self._status_label = Gtk.Label(
            label='Checking for Bluetooth hardware…', wrap=True,
            css_classes=['dim-label'], valign=Gtk.Align.CENTER, vexpand=True,
        )
        self.append(self._status_label)

    # ---- D-Bus wiring -------------------------------------------------

    def _connect_bus(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not reach the system bus: {e.message}')
            return

        self._subscriptions.append(self._bus.signal_subscribe(
            BLUEZ_SERVICE, OBJMGR_IFACE, 'InterfacesAdded', None, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh(),
        ))
        self._subscriptions.append(self._bus.signal_subscribe(
            BLUEZ_SERVICE, OBJMGR_IFACE, 'InterfacesRemoved', None, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh(),
        ))
        # Only the adapter's own property changes (Powered / Discovering) and device
        # connect/pair state -- NOT the per-device RSSI stream, which arg0 lets us drop at
        # the bus. PropertiesChanged's first arg is the interface name.
        for iface in (ADAPTER_IFACE, DEVICE_IFACE):
            self._subscriptions.append(self._bus.signal_subscribe(
                BLUEZ_SERVICE, PROPS_IFACE, 'PropertiesChanged', None, iface,
                Gio.DBusSignalFlags.NONE, self._on_props_changed,
            ))

        self._refresh()

    def _on_props_changed(self, *args):
        # args[-1] (or args[5]) = (interface_name, changed_props, invalidated_props). Ignore
        # bursts that only carry RSSI/TxPower churn from a scan -- they never change what we
        # display.
        params = args[5] if len(args) > 5 else None
        try:
            _iface_name, changed, _invalidated = params.unpack()
        except Exception:
            self._refresh()
            return
        if changed and set(changed) <= {'RSSI', 'TxPower', 'ManufacturerData', 'ServiceData', 'AdvertisingFlags'}:
            return
        self._refresh()

    # ---- refresh (debounced + async) --------------------------------

    def _refresh(self):
        if self._destroyed or self._bus is None:
            return
        if self._refresh_source_id:
            return  # a rebuild is already scheduled; this signal folds into it
        self._refresh_source_id = GLib.timeout_add(
            _REFRESH_DEBOUNCE_MS, self._on_refresh_timeout,
        )

    def _on_refresh_timeout(self):
        self._refresh_source_id = 0
        self._do_refresh()
        return GLib.SOURCE_REMOVE

    def _do_refresh(self):
        if self._destroyed or self._bus is None or self._get_objects_pending:
            return
        self._get_objects_pending = True
        self._bus.call(
            BLUEZ_SERVICE, '/', OBJMGR_IFACE, 'GetManagedObjects',
            None, GLib.VariantType.new('(a{oa{sa{sv}}})'),
            Gio.DBusCallFlags.NONE, 3000, None,
            self._on_get_objects_done,
        )

    def _on_get_objects_done(self, _bus, result):
        self._get_objects_pending = False
        if self._destroyed:
            return
        try:
            objects = self._bus.call_finish(result).unpack()[0]
        except GLib.Error:
            self._show_no_adapter()
            return
        self._apply_objects(objects)

    def _show_no_adapter(self):
        self._status_label.set_label('No Bluetooth adapter detected on this computer.')
        self._status_label.set_visible(True)
        self._toggle.set_sensitive(False)
        self._my_list.set_visible(False)
        self._my_label.set_visible(False)
        self._nearby_list.set_visible(False)
        self._nearby_scroller.set_visible(False)
        self._nearby_header.set_visible(False)
        self._discoverable_label.set_visible(False)

    def _apply_objects(self, objects):
        adapter_path = None
        for path, ifaces in objects.items():
            if ADAPTER_IFACE in ifaces:
                adapter_path = path
                break

        if not adapter_path:
            self._show_no_adapter()
            return

        self._adapter_path = adapter_path
        self._status_label.set_visible(False)
        self._discoverable_label.set_visible(True)
        self._nearby_scroller.set_visible(True)
        self._nearby_header.set_visible(True)
        self._nearby_list.set_visible(True)

        powered = objects[adapter_path][ADAPTER_IFACE].get('Powered', False)
        self._toggle.set_sensitive(True)
        self._toggle.set_active(powered)

        while (child := self._my_list.get_first_child()) is not None:
            self._my_list.remove(child)
        while (child := self._nearby_list.get_first_child()) is not None:
            self._nearby_list.remove(child)

        my_shown = False
        nearby = []
        for path, ifaces in objects.items():
            if DEVICE_IFACE not in ifaces or not path.startswith(adapter_path + '/'):
                continue
            props = ifaces[DEVICE_IFACE]
            name = props.get('Alias') or props.get('Name') or props.get('Address') or 'Unknown Device'
            icon_name = _device_icon_name(props)

            if props.get('Paired'):
                subtitle = None
                if props.get('Connected'):
                    battery_props = ifaces.get(BATTERY_IFACE)
                    if battery_props and 'Percentage' in battery_props:
                        subtitle = f'Connected · {battery_props["Percentage"]}%'
                    else:
                        subtitle = 'Connected'
                self._my_list.append(DeviceRow(name, icon_name, subtitle, show_info=True))
                my_shown = True
            elif powered and _has_real_name(props):
                nearby.append((name.lower(), name, icon_name))

        # Deduplicate + cap so a crowded room can't produce an unbounded list.
        seen = set()
        for _key, name, icon_name in sorted(nearby)[:30]:
            if _key in seen:
                continue
            seen.add(_key)
            self._nearby_list.append(DeviceRow(name, icon_name))

        self._my_label.set_visible(my_shown)
        self._my_list.set_visible(my_shown)

        if powered and self.get_mapped():
            self._scan_spinner.start()
            self._start_discovery(adapter_path)
        else:
            self._scan_spinner.stop()
            self._stop_discovery()

    # ---- discovery lifecycle ---------------------------------------

    def _start_discovery(self, adapter_path):
        if self._discovering or self._bus is None:
            return
        self._discovering = True
        self._bus.call(
            BLUEZ_SERVICE, adapter_path, ADAPTER_IFACE, 'StartDiscovery',
            None, None, Gio.DBusCallFlags.NONE, 3000, None, None,
        )

    def _stop_discovery(self):
        if not self._discovering or self._bus is None or not self._adapter_path:
            self._discovering = False
            return
        self._discovering = False
        self._scan_spinner.stop()
        self._bus.call(
            BLUEZ_SERVICE, self._adapter_path, ADAPTER_IFACE, 'StopDiscovery',
            None, None, Gio.DBusCallFlags.NONE, 3000, None, None,
        )

    def _on_toggle_state_set(self, switch, state):
        if not self._bus or not self._adapter_path:
            return True
        self._bus.call(
            BLUEZ_SERVICE, self._adapter_path, PROPS_IFACE, 'Set',
            GLib.Variant('(ssv)', (ADAPTER_IFACE, 'Powered', GLib.Variant('b', state))),
            None, Gio.DBusCallFlags.NONE, 3000, None,
            self._on_power_set_done,
        )
        return False

    def _on_power_set_done(self, _bus, result):
        try:
            self._bus.call_finish(result)
        except GLib.Error as e:
            self._status_label.set_label(f'Could not change Bluetooth power: {e.message}')
            self._status_label.set_visible(True)

    # ---- teardown -------------------------------------------------

    def _teardown(self):
        self._destroyed = True
        if self._refresh_source_id:
            GLib.source_remove(self._refresh_source_id)
            self._refresh_source_id = 0
        self._stop_discovery()
        if self._bus is not None:
            for sub in self._subscriptions:
                self._bus.signal_unsubscribe(sub)
        self._subscriptions = []
