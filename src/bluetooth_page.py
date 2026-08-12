import os

from gi.repository import Gio, GLib, Gtk

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

BLUEZ_SERVICE = 'org.bluez'
ADAPTER_IFACE = 'org.bluez.Adapter1'
DEVICE_IFACE = 'org.bluez.Device1'
BATTERY_IFACE = 'org.bluez.Battery1'
OBJMGR_IFACE = 'org.freedesktop.DBus.ObjectManager'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'


def _device_icon_name(props: dict) -> str:
    hint = props.get('Icon')
    if hint:
        return f'{hint}-symbolic'
    return 'bluetooth-symbolic'


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

        self._build_ui()
        self._connect_bus()

    # ---- UI ---------------------------------------------------------

    def _build_ui(self):
        card = Gtk.Box(css_classes=['wifi-card'])
        card_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
            margin_start=14, margin_end=14, margin_top=14, margin_bottom=14,
        )
        icon_path = os.path.join(ICON_DIR, 'bluetooth.svg')
        icon = Gtk.Image.new_from_file(icon_path) if os.path.isfile(icon_path) \
            else Gtk.Image.new_from_icon_name('bluetooth-symbolic')
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
        self._my_frame = Gtk.Box(css_classes=['wifi-card'], visible=False)
        self._my_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._my_frame.append(self._my_list)
        self.append(self._my_frame)

        self._nearby_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._nearby_header.append(Gtk.Label(label='Nearby Devices', xalign=0, hexpand=True, css_classes=['heading']))
        self._scan_spinner = Gtk.Spinner()
        self._nearby_header.append(self._scan_spinner)
        self.append(self._nearby_header)

        self._nearby_scroller = Gtk.ScrolledWindow(vexpand=True)
        self._nearby_frame = Gtk.Box(css_classes=['wifi-card'])
        self._nearby_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._nearby_frame.append(self._nearby_list)
        self._nearby_scroller.set_child(self._nearby_frame)
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
        self._subscriptions.append(self._bus.signal_subscribe(
            BLUEZ_SERVICE, PROPS_IFACE, 'PropertiesChanged', None, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh(),
        ))

        self._refresh()

    def _get_managed_objects(self):
        result = self._bus.call_sync(
            BLUEZ_SERVICE, '/', OBJMGR_IFACE, 'GetManagedObjects',
            None, GLib.VariantType.new('(a{oa{sa{sv}}})'),
            Gio.DBusCallFlags.NONE, 2000, None,
        )
        return result.unpack()[0]

    def _refresh(self):
        try:
            objects = self._get_managed_objects()
        except GLib.Error as e:
            self._status_label.set_label('No Bluetooth adapter detected on this computer.')
            self._status_label.set_visible(True)
            self._toggle.set_sensitive(False)
            self._my_frame.set_visible(False)
            self._my_label.set_visible(False)
            self._nearby_frame.set_visible(False)
            self._nearby_scroller.set_visible(False)
            self._nearby_header.set_visible(False)
            self._discoverable_label.set_visible(False)
            return

        adapter_path = None
        for path, ifaces in objects.items():
            if ADAPTER_IFACE in ifaces:
                adapter_path = path
                break

        if not adapter_path:
            self._status_label.set_label('No Bluetooth adapter detected on this computer.')
            self._status_label.set_visible(True)
            self._toggle.set_sensitive(False)
            self._my_frame.set_visible(False)
            self._my_label.set_visible(False)
            self._nearby_frame.set_visible(False)
            self._nearby_scroller.set_visible(False)
            self._nearby_header.set_visible(False)
            self._discoverable_label.set_visible(False)
            return

        self._adapter_path = adapter_path
        self._status_label.set_visible(False)
        self._discoverable_label.set_visible(True)
        self._nearby_scroller.set_visible(True)
        self._nearby_header.set_visible(True)
        self._nearby_frame.set_visible(True)

        powered = objects[adapter_path][ADAPTER_IFACE].get('Powered', False)
        self._toggle.set_sensitive(True)
        self._toggle.set_active(powered)

        while (child := self._my_list.get_first_child()) is not None:
            self._my_list.remove(child)
        while (child := self._nearby_list.get_first_child()) is not None:
            self._nearby_list.remove(child)

        my_shown = False
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
            elif powered:
                self._nearby_list.append(DeviceRow(name, icon_name))

        self._my_label.set_visible(my_shown)
        self._my_frame.set_visible(my_shown)

        if powered:
            self._scan_spinner.start()
            self._start_discovery(adapter_path)
        else:
            self._scan_spinner.stop()

    def _start_discovery(self, adapter_path):
        try:
            self._bus.call_sync(
                BLUEZ_SERVICE, adapter_path, ADAPTER_IFACE, 'StartDiscovery',
                None, None, Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error:
            pass  # already discovering, or not supported -- non-fatal

    def _on_toggle_state_set(self, switch, state):
        if not self._bus or not self._adapter_path:
            return True
        try:
            self._bus.call_sync(
                BLUEZ_SERVICE, self._adapter_path, PROPS_IFACE, 'Set',
                GLib.Variant('(ssv)', (ADAPTER_IFACE, 'Powered', GLib.Variant('b', state))),
                None, Gio.DBusCallFlags.NONE, 2000, None,
            )
        except GLib.Error as e:
            self._status_label.set_label(f'Could not change Bluetooth power: {e.message}')
            self._status_label.set_visible(True)
            return True
        return False
