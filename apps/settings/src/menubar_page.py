import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

PANEL_SCHEMA = 'org.gnome.shell.extensions.macos-top-panel'


def _make_control_row(icon_file, icon_name, title, *, checkbox=None, trailing=None):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
    row.set_margin_start(14)
    row.set_margin_end(14)
    row.set_margin_top(8)
    row.set_margin_bottom(8)

    if checkbox is not None:
        row.append(checkbox)
    else:
        # Rows without a checkbox (just Clock right now) still line up with ones that
        # have it, rather than having their icon start further left.
        spacer = Gtk.Box()
        spacer.set_size_request(20, 1)
        row.append(spacer)

    if icon_file and os.path.isfile(icon_file):
        icon = Gtk.Image.new_from_file(icon_file)
        icon.set_pixel_size(22)
    else:
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
    row.append(icon)

    row.append(Gtk.Label(label=title, xalign=0, hexpand=True, valign=Gtk.Align.CENTER))

    if trailing is not None:
        row.append(trailing)
    return row


class MenuBarPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(PANEL_SCHEMA)
        self._build_ui()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'menubar.svg'), 'open-menu-symbolic',
            'Menu Bar', "Customize what shows in peachOS's menu bar.",
        ))

        self.append(Gtk.Label(label='Menu Bar Controls', xalign=0, css_classes=['heading']))

        controls_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        controls_card.append(self._build_clock_row())
        controls_card.append(self._build_checkbox_row(
            'peachySearch', 'spotlight.svg', 'system-search-symbolic', 'show-spotlight-icon'))
        controls_card.append(self._build_checkbox_row(
            'Wi-Fi', 'wifi.svg', 'network-wireless-symbolic', 'show-wifi-icon'))
        controls_card.append(self._build_checkbox_row(
            'Bluetooth', 'bluetooth.svg', 'bluetooth-symbolic', 'show-bluetooth-icon'))
        controls_card.append(self._build_battery_row())
        self.append(controls_card)

    def _build_checkbox_row(self, title, icon_filename, icon_name, settings_key):
        checkbox = Gtk.CheckButton(active=self._settings.get_boolean(settings_key), valign=Gtk.Align.CENTER)
        checkbox.connect('toggled', lambda c: self._settings.set_boolean(settings_key, c.get_active()))
        return _make_control_row(os.path.join(ICON_DIR, icon_filename), icon_name, title, checkbox=checkbox)

    def _build_clock_row(self):
        menu_btn = Gtk.MenuButton(label='Clock Options…', css_classes=['flat'], valign=Gtk.Align.CENTER)
        menu_btn.set_popover(self._build_clock_popover())
        return _make_control_row(
            os.path.join(ICON_DIR, 'menubar_clock.svg'), 'preferences-system-time-symbolic', 'Clock',
            trailing=menu_btn)

    def _build_clock_popover(self):
        popover = Gtk.Popover()
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=10, margin_bottom=10, margin_start=12, margin_end=12,
        )

        def add_option(label, key):
            row = Gtk.Box(spacing=8)
            check = Gtk.CheckButton(active=self._settings.get_boolean(key))
            check.connect('toggled', lambda c: self._settings.set_boolean(key, c.get_active()))
            row.append(check)
            row.append(Gtk.Label(label=label, xalign=0))
            box.append(row)

        add_option('24-Hour Time', 'clock-24-hour')
        add_option('Show Seconds', 'clock-show-seconds')
        add_option('Show Date', 'clock-show-date')

        popover.set_child(box)
        return popover

    def _build_battery_row(self):
        checkbox = Gtk.CheckButton(active=self._settings.get_boolean('show-battery-icon'), valign=Gtk.Align.CENTER)
        checkbox.connect('toggled', lambda c: self._settings.set_boolean('show-battery-icon', c.get_active()))

        menu_btn = Gtk.MenuButton(label='Battery Options…', css_classes=['flat'], valign=Gtk.Align.CENTER)
        menu_btn.set_popover(self._build_battery_popover())

        return _make_control_row(
            os.path.join(ICON_DIR, 'energy.svg'), 'battery-full-symbolic', 'Battery',
            checkbox=checkbox, trailing=menu_btn)

    def _build_battery_popover(self):
        popover = Gtk.Popover()
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2,
            margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
        )

        show_percentage = self._settings.get_boolean('battery-show-percentage')
        show_btn = Gtk.CheckButton(label='Show Percentage', active=show_percentage)
        hide_btn = Gtk.CheckButton(label="Don't Show Percentage", active=not show_percentage)
        hide_btn.set_group(show_btn)
        show_btn.connect('toggled', lambda c: c.get_active() and self._settings.set_boolean(
            'battery-show-percentage', True))
        hide_btn.connect('toggled', lambda c: c.get_active() and self._settings.set_boolean(
            'battery-show-percentage', False))
        box.append(show_btn)
        box.append(hide_btn)

        popover.set_child(box)
        return popover
