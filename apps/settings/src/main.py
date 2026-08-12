#!/usr/bin/env python3
import os
import sys

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wifi_page import WifiPage
from bluetooth_page import BluetoothPage
from network_page import NetworkPage
from battery_page import BatteryPage
from appearance_page import AppearancePage
from desktopdock_page import DesktopDockPage
from displays_page import DisplaysPage

APP_ID = 'org.peachos.Settings'
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# (id, title, icon name, accent color hex)
SIDEBAR_SECTIONS = [
    [
        ('wifi', 'Wi-Fi', 'network-wireless-symbolic', '#0A84FF'),
        ('bluetooth', 'Bluetooth', 'bluetooth-symbolic', '#0A84FF'),
        ('network', 'Network', 'network-workgroup-symbolic', '#5AC8FA'),
        ('energy', 'Battery', 'battery-full-symbolic', '#34C759'),
    ],
    [
        ('general', 'General', 'applications-system-symbolic', '#8E8E93'),
        ('accessibility', 'Accessibility', 'preferences-desktop-accessibility-symbolic', '#0A84FF'),
        ('appearance', 'Appearance', 'preferences-desktop-theme-symbolic', '#1C1C1E'),
        ('menubar', 'Menu Bar', 'open-menu-symbolic', '#1C1C1E'),
        ('desktopdock', 'Desktop & Dock', 'view-dual-symbolic', '#0A84FF'),
        ('displays', 'Displays', 'video-display-symbolic', '#0A84FF'),
        ('spotlight', 'Spotlight', 'system-search-symbolic', '#48484A'),
        ('wallpaper', 'Wallpaper', 'image-x-generic-symbolic', '#32ADE6'),
        ('notifications', 'Notifications', 'preferences-system-notifications-symbolic', '#FF3B30'),
    ],
]

ACCENT_CLASSES = {
    '#0A84FF': 'accent-blue',
    '#5AC8FA': 'accent-lightblue',
    '#34C759': 'accent-green',
    '#8E8E93': 'accent-gray',
    '#1C1C1E': 'accent-black',
    '#48484A': 'accent-darkgray',
    '#32ADE6': 'accent-teal',
    '#FF3B30': 'accent-red',
}

STYLE_CSS = b"""
.sidebar-icon {
    border-radius: 6px;
}
.sidebar-icon image {
    color: white;
}
.nav-row-label {
    font-size: 13px;
}
list.navigation-sidebar row {
    margin: 0px 4px;
    padding: 0px;
    border-radius: 5px;
    min-height: 26px;
}
button.signin-row {
    padding: 0px;
    border-radius: 8px;
}
button.signin-row label.signin-name {
    font-weight: bold;
    font-size: 13px;
}
button.signin-row label.signin-subtitle {
    opacity: 0.6;
    font-size: 11px;
}
.accent-blue { background-color: #0A84FF; }
.accent-lightblue { background-color: #5AC8FA; }
.accent-green { background-color: #34C759; }
.accent-gray { background-color: #8E8E93; }
.accent-black { background-color: #1C1C1E; }
.accent-darkgray { background-color: #48484A; }
.accent-teal { background-color: #32ADE6; }
.accent-red { background-color: #FF3B30; }
.placeholder-icon {
    opacity: 0.25;
}
.placeholder-title {
    font-size: 1.4em;
    font-weight: bold;
}
.placeholder-subtitle {
    opacity: 0.55;
}
headerbar.flat {
    box-shadow: none;
    background: transparent;
}
.connected-dot {
    background-color: #34C759;
    border-radius: 999px;
}
.disconnected-dot {
    background-color: alpha(currentColor, 0.3);
    border-radius: 999px;
}
.wifi-card {
    background-color: alpha(currentColor, 0.025);
    border-radius: 10px;
    border: none;
    box-shadow: none;
}
.segmented-toggle {
    padding: 8px 4px;
}
/* .network-row used to have a :hover background here, but it only ever
   painted a partial region of the row (not the whole container) across
   every tab that uses it, and reliably fixing GTK's hover-state coverage
   for a Box containing interactive children (switches, dropdowns) wasn't
   worth another round of fighting the theme's cascade -- removed. */
.scheme-photo {
    border-radius: 5px;
}
.scheme-ring {
    padding: 3px;
    border-radius: 8px;
    border: 2px solid transparent;
}
.color-swatch {
    padding: 2px;
    border-radius: 999px;
    border: 2px solid transparent;
}
.color-swatch.selected {
    border-color: #FFFFFF;
}
.color-swatch-dot {
    min-width: 20px;
    min-height: 20px;
    border-radius: 999px;
}
"""


ICON_DIR = os.path.join(DATA_DIR, 'icons')

# The provided SVGs originally had wildly inconsistent amounts of internal
# padding baked into their canvas (ink ranging from ~64% to ~99% of the
# canvas -- see scratchpad/measure_icons.py). Rather than compensating per
# icon at render time, scratchpad/crop_icons.py rewrote each file's
# viewBox to a tight, centered square around its actual artwork, so every
# icon in data/icons/ is now uniformly ~94% ink. That means a single flat
# pixel_size now gives consistent size *and* centering for all of them.
SIDEBAR_ICON_PX = 18
PLACEHOLDER_ICON_PX = 60
ICON_SLOT_PX = 22  # fixed footprint every icon sits in, so labels always start at the same x


def _custom_icon_path(row_id: str):
    for ext in ('.svg', '.png'):
        path = os.path.join(ICON_DIR, row_id + ext)
        if os.path.isfile(path):
            return path
    return None


def make_sidebar_icon(row_id: str, icon_name: str, color: str) -> Gtk.Widget:
    box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    box.set_size_request(ICON_SLOT_PX, ICON_SLOT_PX)

    custom_path = _custom_icon_path(row_id)
    if custom_path:
        image = Gtk.Image.new_from_file(custom_path)
        image.set_pixel_size(SIDEBAR_ICON_PX)
        box.append(image)
        return box

    box.add_css_class('sidebar-icon')
    box.add_css_class(ACCENT_CLASSES[color])
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(14)
    box.append(image)
    return box


def make_placeholder_icon(row_id: str, icon_name: str) -> Gtk.Widget:
    custom_path = _custom_icon_path(row_id)
    if custom_path:
        image = Gtk.Image.new_from_file(custom_path)
        image.set_pixel_size(PLACEHOLDER_ICON_PX)
        return image
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(64)
    image.add_css_class('placeholder-icon')
    return image


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(820, 600)
        # A real minimum, not a stand-in for "whatever the tallest tab's
        # content needs" -- that job now belongs to the ScrolledWindow
        # around _placeholder_stack below. Without it, every card added to
        # a tab (Displays/Desktop & Dock especially) pushed the window's
        # forced minimum height higher, to the point the window couldn't
        # be shrunk at all and, once taller than the work area, had
        # nowhere to go but under the dock.
        self.set_size_request(680, 420)
        self.set_title('System Settings')

        self._history = []
        self._history_index = -1

        split_view = Adw.NavigationSplitView(min_sidebar_width=260, max_sidebar_width=300)
        self.set_content(split_view)

        sidebar_page = Adw.NavigationPage(title='System Settings')
        sidebar_page.set_child(self._build_sidebar())
        split_view.set_sidebar(sidebar_page)

        self._content_page = Adw.NavigationPage(title='System Settings')
        self._content_toolbar = Adw.ToolbarView()
        self._content_page.set_child(self._content_toolbar)
        split_view.set_content(self._content_page)

        self._build_content_header()
        self._placeholder_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            vhomogeneous=False,  # size to the visible page, not the tallest one
        )
        # Every page used to sit directly in the toolbar's content area, so
        # a tall page's natural height became the *window's* forced minimum
        # height -- nothing absorbed the overflow. A ScrolledWindow lets
        # tab content scroll instead of dictating the window's own size.
        content_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
        )
        content_scroller.set_child(self._placeholder_stack)
        self._content_toolbar.set_content(content_scroller)

        self._pages = {}
        for section in SIDEBAR_SECTIONS:
            for row_id, title, icon_name, color in section:
                if row_id == 'wifi':
                    self._pages[row_id] = WifiPage()
                elif row_id == 'bluetooth':
                    self._pages[row_id] = BluetoothPage()
                elif row_id == 'network':
                    self._pages[row_id] = NetworkPage()
                elif row_id == 'energy':
                    self._pages[row_id] = BatteryPage()
                elif row_id == 'appearance':
                    self._pages[row_id] = AppearancePage()
                elif row_id == 'desktopdock':
                    self._pages[row_id] = DesktopDockPage()
                elif row_id == 'displays':
                    self._pages[row_id] = DisplaysPage()
                else:
                    self._pages[row_id] = self._build_placeholder(row_id, title, icon_name)
                self._placeholder_stack.add_named(self._pages[row_id], row_id)

        first_id = SIDEBAR_SECTIONS[0][0][0]
        self._go_to(first_id, record_history=True)

    def _build_sidebar(self) -> Gtk.Widget:
        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_title(False)
        header.add_css_class('flat')
        toolbar.add_top_bar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        top_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10,
            margin_start=4, margin_end=4, margin_top=4, margin_bottom=8,
        )

        search = Gtk.SearchEntry(placeholder_text='Search')
        top_box.append(search)

        account_name = GLib.get_real_name()
        if not account_name or account_name == 'Unknown':
            account_name = GLib.get_user_name()

        signin_button = Gtk.Button(css_classes=['flat', 'signin-row'])
        signin_content = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=4, margin_top=4, margin_bottom=4,
        )
        avatar = Adw.Avatar(size=32, text=account_name, show_initials=True)
        signin_content.append(avatar)
        signin_labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        signin_labels.append(Gtk.Label(label=account_name, xalign=0, css_classes=['signin-name']))
        signin_labels.append(Gtk.Label(label='peachOS Account', xalign=0, css_classes=['signin-subtitle']))
        signin_content.append(signin_labels)
        signin_button.set_child(signin_content)
        top_box.append(signin_button)

        outer.append(top_box)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        list_outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6,
            margin_start=4, margin_end=4, margin_bottom=12,
        )

        self._listboxes = []
        for section in SIDEBAR_SECTIONS:
            listbox = Gtk.ListBox(css_classes=['navigation-sidebar'])
            listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            for row_id, title, icon_name, color in section:
                row = Gtk.ListBoxRow()
                content = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                    margin_start=0, margin_end=6, margin_top=3, margin_bottom=3,
                )
                content.append(make_sidebar_icon(row_id, icon_name, color))
                content.append(Gtk.Label(label=title, xalign=0, css_classes=['nav-row-label']))
                row.set_child(content)
                row._row_id = row_id
                listbox.append(row)
            listbox.connect('row-selected', self._on_sidebar_row_selected)
            list_outer.append(listbox)
            self._listboxes.append(listbox)

        scroller.set_child(list_outer)
        outer.append(scroller)

        toolbar.set_content(outer)
        return toolbar

    def _build_content_header(self):
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)

        nav_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            css_classes=['linked'],
        )
        self._back_btn = Gtk.Button(icon_name='go-previous-symbolic', sensitive=False)
        self._forward_btn = Gtk.Button(icon_name='go-next-symbolic', sensitive=False)
        self._back_btn.connect('clicked', lambda *_: self._navigate(-1))
        self._forward_btn.connect('clicked', lambda *_: self._navigate(1))
        nav_box.append(self._back_btn)
        nav_box.append(self._forward_btn)
        header.pack_start(nav_box)

        self._content_title_label = Gtk.Label(css_classes=['title'])
        header.set_title_widget(self._content_title_label)

        self._content_toolbar.add_top_bar(header)

    def _build_placeholder(self, row_id: str, title: str, icon_name: str) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            vexpand=True,
        )
        icon = make_placeholder_icon(row_id, icon_name)
        box.append(icon)

        title_label = Gtk.Label(label=title, css_classes=['placeholder-title'])
        box.append(title_label)

        subtitle = Gtk.Label(
            label='This section is a placeholder — content coming soon.',
            css_classes=['placeholder-subtitle'],
        )
        box.append(subtitle)
        return box

    def _on_sidebar_row_selected(self, listbox, row):
        if row is None:
            return
        for other in self._listboxes:
            if other is not listbox:
                other.select_row(None)
        self._go_to(row._row_id, record_history=True)

    def _go_to(self, row_id: str, record_history: bool):
        self._placeholder_stack.set_visible_child_name(row_id)
        for section, listbox in zip(SIDEBAR_SECTIONS, self._listboxes):
            for idx, (rid, *_rest) in enumerate(section):
                if rid == row_id:
                    listbox.select_row(listbox.get_row_at_index(idx))

        title = next(
            title for section in SIDEBAR_SECTIONS for rid, title, *_ in section if rid == row_id
        )
        self._content_title_label.set_label(title)

        if record_history:
            self._history = self._history[: self._history_index + 1]
            self._history.append(row_id)
            self._history_index = len(self._history) - 1
        self._update_nav_buttons()

    def _navigate(self, delta: int):
        new_index = self._history_index + delta
        if 0 <= new_index < len(self._history):
            self._history_index = new_index
            self._go_to(self._history[new_index], record_history=False)

    def _update_nav_buttons(self):
        self._back_btn.set_sensitive(self._history_index > 0)
        self._forward_btn.set_sensitive(self._history_index < len(self._history) - 1)


class SettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = self.props.active_window
        if not win:
            win = SettingsWindow(application=self)
        win.present()


def main():
    app = SettingsApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
