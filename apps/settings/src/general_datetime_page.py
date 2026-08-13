import os

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

TIMEDATE_SERVICE = 'org.freedesktop.timedate1'
TIMEDATE_PATH = '/org/freedesktop/timedate1'
TIMEDATE_IFACE = 'org.freedesktop.timedate1'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'


class ToggleRow(Gtk.Box):
    def __init__(self, title: str, subtitle: str = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            text_box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=['caption', 'dim-label']))
        self.append(text_box)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.append(self.switch)


class DropdownRow(Gtk.Box):
    def __init__(self, title: str, options: list, enable_search: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.dropdown = Gtk.DropDown.new_from_strings(options)
        self.dropdown.set_enable_search(enable_search)
        if enable_search:
            # Default match mode is PREFIX, which only matches strings
            # starting with the typed text -- useless for something like
            # "America/Denver" where the useful search term is the city,
            # not the leading "America/". SUBSTRING matches anywhere.
            self.dropdown.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
            # new_from_strings() never sets an expression, so the search
            # filter has no idea what string to compare against and
            # silently matches nothing at all -- confirmed by walking the
            # popover's real GtkListView model after typing into its
            # search entry: 4 items in, 4 items still shown, until this
            # expression is set explicitly.
            self.dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
        self.append(self.dropdown)

    def set_options(self, options: list, selected: str = None):
        self.dropdown.set_model(Gtk.StringList.new(options))
        if selected in options:
            self.dropdown.set_selected(options.index(selected))

    def get_selected_text(self):
        item = self.dropdown.get_selected_item()
        return item.get_string() if item else None

    def set_selected_text(self, text: str):
        model = self.dropdown.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == text:
                self.dropdown.set_selected(i)
                return


class GeneralDateTimePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._bus = None
        self._syncing = False
        self._clock_id = 0

        self._build_ui()
        self._connect_bus()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general_date_time.svg'), 'preferences-system-time-symbolic',
            'Date & Time', 'Set the date, time, and time zone for this computer.',
        ))

        self._clock_label = Gtk.Label(
            label='—', halign=Gtk.Align.CENTER, css_classes=['title-1'],
        )
        self.append(self._clock_label)

        card1 = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._ntp_row = ToggleRow(
            'Set Date and Time Automatically',
            'Uses network time synchronization (NTP) to keep the clock accurate.',
        )
        self._ntp_row.switch.connect('state-set', self._on_ntp_toggled)
        card1.append(self._ntp_row)

        self._tz_row = DropdownRow('Time Zone', [], enable_search=True)
        self._tz_row.dropdown.connect('notify::selected', self._on_timezone_changed)
        card1.append(self._tz_row)
        self.append(card1)

        card2 = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._clock_format_row = ToggleRow('24-Hour Time')
        self._clock_format_row.switch.connect('state-set', self._on_clock_format_toggled)
        card2.append(self._clock_format_row)
        self.append(card2)

        self._status_label = Gtk.Label(
            label='', wrap=True, css_classes=['dim-label'], visible=False,
        )
        self.append(self._status_label)

        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        clock_format = self._interface_settings.get_string('clock-format')
        self._clock_format_row.switch.set_active(clock_format == '24h')
        self._interface_settings.connect(
            'changed::clock-format',
            lambda *_a: self._clock_format_row.switch.set_active(
                self._interface_settings.get_string('clock-format') == '24h',
            ),
        )

        self._clock_id = GLib.timeout_add_seconds(1, self._tick)
        self._tick()

    def _tick(self):
        now = GLib.DateTime.new_now_local()
        fmt = '%A, %B %-e, %Y  %l:%M:%S %p' if self._interface_settings.get_string('clock-format') != '24h' \
            else '%A, %B %-e, %Y  %H:%M:%S'
        self._clock_label.set_label(now.format(fmt).strip())
        return GLib.SOURCE_CONTINUE

    # ---- D-Bus wiring (systemd-timedated) ------------------------------

    def _connect_bus(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            self._show_error(f'Could not reach the system bus: {e.message}')
            return

        try:
            timezones = self._bus.call_sync(
                TIMEDATE_SERVICE, TIMEDATE_PATH, TIMEDATE_IFACE, 'ListTimezones',
                None, GLib.VariantType.new('(as)'), Gio.DBusCallFlags.NONE, 3000, None,
            ).unpack()[0]
        except GLib.Error as e:
            self._show_error(f'Could not reach systemd-timedated: {e.message}')
            self._tz_row.set_sensitive(False)
            self._ntp_row.set_sensitive(False)
            return

        self._bus.signal_subscribe(
            TIMEDATE_SERVICE, PROPS_IFACE, 'PropertiesChanged', TIMEDATE_PATH, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh(sorted(timezones)),
        )
        self._refresh(sorted(timezones))

    def _get_prop(self, name: str):
        return self._bus.call_sync(
            TIMEDATE_SERVICE, TIMEDATE_PATH, PROPS_IFACE, 'Get',
            GLib.Variant('(ss)', (TIMEDATE_IFACE, name)),
            GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
        ).unpack()[0]

    def _refresh(self, timezones: list):
        self._syncing = True
        try:
            current_tz = self._get_prop('Timezone')
            self._tz_row.set_options(timezones, selected=current_tz)
            self._ntp_row.switch.set_active(self._get_prop('NTP'))
        except GLib.Error as e:
            self._show_error(f'Could not read time settings: {e.message}')
        finally:
            self._syncing = False

    def _show_error(self, message: str):
        self._status_label.set_label(message)
        self._status_label.set_visible(True)

    def _on_ntp_toggled(self, switch, state):
        if self._syncing or not self._bus:
            return False
        try:
            self._bus.call_sync(
                TIMEDATE_SERVICE, TIMEDATE_PATH, TIMEDATE_IFACE, 'SetNTP',
                GLib.Variant('(bb)', (state, True)), None, Gio.DBusCallFlags.NONE, 5000, None,
            )
        except GLib.Error as e:
            self._show_error(f'Could not change network time sync: {e.message}')
            return True
        return False

    def _on_timezone_changed(self, dropdown, _pspec):
        if self._syncing or not self._bus:
            return
        tz = self._tz_row.get_selected_text()
        if not tz:
            return
        try:
            self._bus.call_sync(
                TIMEDATE_SERVICE, TIMEDATE_PATH, TIMEDATE_IFACE, 'SetTimezone',
                GLib.Variant('(sb)', (tz, True)), None, Gio.DBusCallFlags.NONE, 5000, None,
            )
        except GLib.Error as e:
            self._show_error(f'Could not change time zone: {e.message}')

    def _on_clock_format_toggled(self, switch, state):
        self._interface_settings.set_string('clock-format', '24h' if state else '12h')
        return False
