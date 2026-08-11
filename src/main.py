#!/usr/bin/env python3
import os
import sys

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

APP_ID = 'org.peachos.Settings'
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

# (id, title, icon name, accent color hex)
SIDEBAR_SECTIONS = [
    [
        ('wifi', 'Wi-Fi', 'network-wireless-symbolic', '#0A84FF'),
        ('bluetooth', 'Bluetooth', 'bluetooth-symbolic', '#0A84FF'),
        ('network', 'Network', 'network-workgroup-symbolic', '#5AC8FA'),
        ('energy', 'Energy', 'battery-full-symbolic', '#34C759'),
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
    border-radius: 7px;
    min-width: 26px;
    min-height: 26px;
    padding: 4px;
}
.sidebar-icon image {
    color: white;
}
.accent-blue { background-color: #0A84FF; }
.accent-lightblue { background-color: #5AC8FA; }
.accent-green { background-color: #34C759; }
.accent-gray { background-color: #8E8E93; }
.accent-black { background-color: #1C1C1E; }
.accent-darkgray { background-color: #48484A; }
.accent-teal { background-color: #32ADE6; }
.accent-red { background-color: #FF3B30; }
row.signin-row {
    padding: 6px 4px;
}
row.signin-row label.title {
    font-weight: bold;
}
row.signin-row label.subtitle {
    opacity: 0.6;
    font-size: 0.9em;
}
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
"""


def make_sidebar_icon(icon_name: str, color: str) -> Gtk.Widget:
    box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    box.add_css_class('sidebar-icon')
    box.add_css_class(ACCENT_CLASSES[color])
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(16)
    box.append(image)
    return box


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(820, 600)
        self.set_size_request(680, 480)
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
            transition_type=Gtk.StackTransitionType.CROSSFADE
        )
        self._content_toolbar.set_content(self._placeholder_stack)

        self._pages = {}
        for section in SIDEBAR_SECTIONS:
            for row_id, title, icon_name, color in section:
                self._pages[row_id] = self._build_placeholder(title, icon_name, color)
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
            margin_start=12, margin_end=12, margin_top=4, margin_bottom=8,
        )

        search = Gtk.SearchEntry(placeholder_text='Search')
        top_box.append(search)

        signin_row = Adw.ActionRow(
            title='Sign in',
            subtitle='with your Apple Account',
            activatable=True,
        )
        signin_row.add_css_class('signin-row')
        avatar = Adw.Avatar(size=36, text='?', show_initials=False)
        avatar.set_icon_name('avatar-default-symbolic')
        signin_row.add_prefix(avatar)
        signin_row.add_suffix(Gtk.Image.new_from_icon_name('go-next-symbolic'))
        signin_frame = Gtk.ListBox(css_classes=['boxed-list'])
        signin_frame.set_selection_mode(Gtk.SelectionMode.NONE)
        signin_frame.append(signin_row)
        top_box.append(signin_frame)

        outer.append(top_box)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        list_outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=18,
            margin_start=12, margin_end=12, margin_bottom=12,
        )

        self._listboxes = []
        for section in SIDEBAR_SECTIONS:
            listbox = Gtk.ListBox(css_classes=['navigation-sidebar'])
            listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            for row_id, title, icon_name, color in section:
                row = Adw.ActionRow(title=GLib.markup_escape_text(title), activatable=True)
                row.add_prefix(make_sidebar_icon(icon_name, color))
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

    def _build_placeholder(self, title: str, icon_name: str, color: str) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            vexpand=True,
        )
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(64)
        icon.add_css_class('placeholder-icon')
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
