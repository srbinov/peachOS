import os

from gi.repository import Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


class PlaceholderRow(Gtk.Box):
    """An inert row: leading icon, title, trailing chevron. Used for
    General sub-sections that aren't wired up to real backends yet -- same
    visual language as the built-out tabs (ServiceRow in network_page.py)
    so the placeholders don't look out of place next to working rows."""

    def __init__(self, title: str, icon_file: str, on_click=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        icon = Gtk.Image.new_from_file(icon_file)
        icon.set_pixel_size(28)
        self.append(icon)

        self.append(Gtk.Label(label=title, xalign=0, hexpand=True, valign=Gtk.Align.CENTER))
        self.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))

        if on_click:
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a: on_click())
            self.add_controller(click)
            self.set_cursor_from_name('pointer')


class GroupCard(Gtk.Box):
    def __init__(self, rows: list):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'])
        for i, row in enumerate(rows):
            if i > 0:
                self.append(Gtk.Separator(margin_start=50))
            self.append(row)


class GeneralPage(Gtk.Box):
    def __init__(self, on_open_about=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_open_about = on_open_about
        self._build_ui()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general.svg'), 'applications-system-symbolic',
            'General', 'Manage your overall setup and preferences for peachOS, such as software '
                        'updates, device language, and more.',
        ))

        # Only rows with a real icon supplied in the icons repo are shown --
        # the rest (AppleCare & Warranty, AirDrop & Handoff, AutoFill &
        # Passwords, Login Items & Extensions) were dropped rather than
        # faked with placeholder icons.
        self.append(GroupCard([
            PlaceholderRow('About', os.path.join(ICON_DIR, 'general_about.svg'), on_click=self._on_open_about),
            PlaceholderRow('Software Update', os.path.join(ICON_DIR, 'general_software_update.svg')),
            PlaceholderRow('Storage', os.path.join(ICON_DIR, 'general_storage.svg')),
        ]))

        self.append(GroupCard([
            PlaceholderRow('Date & Time', os.path.join(ICON_DIR, 'general_date_time.svg')),
            PlaceholderRow('Language & Region', os.path.join(ICON_DIR, 'general_language_region.svg')),
        ]))
