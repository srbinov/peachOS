import os

from gi.repository import Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class PlaceholderRow(Gtk.Box):
    """An inert row: leading colored icon, title, trailing chevron. Used for
    General sub-sections that aren't wired up to real backends yet -- same
    visual language as the built-out tabs (ServiceRow in network_page.py)
    so the placeholders don't look out of place next to working rows."""

    def __init__(self, title: str, icon_name: str, accent_class: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        icon_box = Gtk.Box(
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            css_classes=['sidebar-icon', accent_class],
        )
        icon_box.set_size_request(28, 28)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(15)
        icon_box.append(icon)
        self.append(icon_box)

        self.append(Gtk.Label(label=title, xalign=0, hexpand=True, valign=Gtk.Align.CENTER))
        self.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))


class GroupCard(Gtk.Box):
    def __init__(self, rows: list):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'])
        for i, row in enumerate(rows):
            if i > 0:
                self.append(Gtk.Separator(margin_start=50))
            self.append(row)


class GeneralPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._build_ui()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general.svg'), 'applications-system-symbolic',
            'General', 'Manage your overall setup and preferences for peachOS, such as software '
                        'updates, device language, and more.',
        ))

        self.append(GroupCard([
            PlaceholderRow('About', 'computer-symbolic', 'accent-gray'),
            PlaceholderRow('Software Update', 'software-update-available-symbolic', 'accent-blue'),
            PlaceholderRow('Storage', 'drive-harddisk-symbolic', 'accent-darkgray'),
        ]))

        self.append(GroupCard([
            PlaceholderRow('AppleCare & Warranty', 'security-high-symbolic', 'accent-red'),
        ]))

        self.append(GroupCard([
            PlaceholderRow('AirDrop & Handoff', 'send-to-symbolic', 'accent-blue'),
        ]))

        self.append(GroupCard([
            PlaceholderRow('AutoFill & Passwords', 'dialog-password-symbolic', 'accent-lightblue'),
            PlaceholderRow('Date & Time', 'preferences-system-time-symbolic', 'accent-black'),
            PlaceholderRow('Language & Region', 'preferences-desktop-locale-symbolic', 'accent-teal'),
            PlaceholderRow('Login Items & Extensions', 'system-run-symbolic', 'accent-darkgray'),
        ]))
