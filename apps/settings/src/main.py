#!/usr/bin/env python3
import os
import sys

# sound_page.py needs Gvc (PulseAudio device enumeration) for a real Output/Input list.
# Its typelib exists system-wide, but the shared library it references
# (/usr/lib/gnome-shell/libgvc.so) is gnome-shell's own private copy, not on the linker's
# default search path -- and critically, setting GI_TYPELIB_PATH/LD_LIBRARY_PATH via
# os.environ *after* the interpreter has already started doesn't help, because dlopen()'s
# search already resolved by the time gi.require_version('Gvc', ...) runs. Re-executing this
# same script with the corrected environment, before any gi import happens at all, is the
# actual fix -- verified directly (setting os.environ mid-process still failed to find
# libgvc.so; re-exec with the env pre-set did not).
if os.environ.get('_PEACHOS_GVC_ENV') != '1':
    env = dict(os.environ)
    env['GI_TYPELIB_PATH'] = '/usr/lib/gnome-shell:' + env.get('GI_TYPELIB_PATH', '')
    env['LD_LIBRARY_PATH'] = '/usr/lib/gnome-shell:' + env.get('LD_LIBRARY_PATH', '')
    env['_PEACHOS_GVC_ENV'] = '1'
    os.execvpe(sys.executable, [sys.executable] + sys.argv, env)

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import users_page
from wifi_page import WifiPage
from bluetooth_page import BluetoothPage
from network_page import NetworkPage
from battery_page import BatteryPage
from appearance_page import AppearancePage
from custom_icons_page import CustomIconsPage
from dictation_page import DictationPage
from desktopdock_page import DesktopDockPage
from multitasking_page import MultitaskingPage
from displays_page import DisplaysPage
from general_page import GeneralPage
from general_defaultapps_page import GeneralDefaultAppsPage
from general_about_page import GeneralAboutPage
from general_softwareupdate_page import GeneralSoftwareUpdatePage
from general_storage_page import GeneralStoragePage
from general_datetime_page import GeneralDateTimePage
from general_language_page import GeneralLanguagePage
from accessibility_page import AccessibilityPage
from accessibility_zoom_page import AccessibilityZoomPage
from accessibility_display_page import AccessibilityDisplayPage
from accessibility_audio_page import AccessibilityAudioPage
from menubar_page import MenuBarPage
from spotlight_page import SpotlightPage
from wallpaper_page import WallpaperPage
from notifications_page import NotificationsPage
from sound_page import SoundPage
from screentime_page import ScreenTimePage
from privacy_page import PrivacyPage
from lockscreen_page import LockScreenPage
from touchid_page import TouchIDPage
from users_page import UsersPage
from internetaccounts_page import InternetAccountsPage
from keyboard_shortcuts_page import KeyboardShortcutsPage
from keyboard_page import KeyboardPage
from mouse_page import MousePage
from touchpad_page import TouchpadPage
from printers_page import PrintersPage
from widgets import load_sized_image

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
        ('dictation', 'Peach Intelligence', 'audio-input-microphone-symbolic', '#FF3B30'),
        ('appearance', 'Appearance', 'preferences-desktop-theme-symbolic', '#1C1C1E'),
        ('menubar', 'Menu Bar', 'open-menu-symbolic', '#1C1C1E'),
        ('desktopdock', 'Desktop & Dock', 'view-dual-symbolic', '#0A84FF'),
        ('multitasking', 'Multitasking', 'view-app-grid-symbolic', '#0A84FF'),
        ('displays', 'Displays', 'video-display-symbolic', '#0A84FF'),
        ('spotlight', 'peachySearch', 'system-search-symbolic', '#48484A'),
        ('wallpaper', 'Wallpaper', 'image-x-generic-symbolic', '#32ADE6'),
        ('notifications', 'Notifications', 'preferences-system-notifications-symbolic', '#FF3B30'),
        ('sound', 'Sound', 'audio-speakers-symbolic', '#FF3B30'),
        ('screentime', 'Screen Time', 'preferences-system-time-symbolic', '#0A84FF'),
        ('lockscreen', 'Lock Screen', 'changes-prevent-symbolic', '#1C1C1E'),
        ('privacy', 'Privacy & Security', 'preferences-system-privacy-symbolic', '#5AC8FA'),
        ('touchid', 'Touch ID & Password', 'fingerprint-symbolic', '#FF3B30'),
        ('users', 'Users & Groups', 'system-users-symbolic', '#0A84FF'),
        ('internetaccounts', 'Internet Accounts', 'goa-account-symbolic', '#0A84FF'),
        ('keyboard', 'Keyboard', 'input-keyboard-symbolic', '#8E8E93'),
        ('mouse', 'Mouse', 'input-mouse-symbolic', '#8E8E93'),
        ('touchpad', 'Trackpad', 'input-touchpad-symbolic', '#8E8E93'),
        ('printers', 'Printers & Scanners', 'printer-symbolic', '#8E8E93'),
    ],
]

# Sub-pages reached by drilling into a row (e.g. General -> About) rather
# than a sidebar click. They live in the same content stack but aren't
# listed in SIDEBAR_SECTIONS, so they need their own title lookup.
EXTRA_PAGE_TITLES = {
    'general_about': 'About',
    'general_softwareupdate': 'Software Update',
    'general_storage': 'Storage',
    'general_datetime': 'Date & Time',
    'general_language': 'Language & Region',
    'general_defaultapps': 'Default Apps',
    'accessibility_zoom': 'Zoom',
    'accessibility_display': 'Display',
    'accessibility_audio': 'Audio',
    'appearance_custom_icons': 'Custom Icons',
    'keyboard_shortcuts': 'Keyboard Shortcuts',
    'edit_profile': 'Edit Profile',
}

# Which sidebar tab a drill-in sub-page lives under -- drives the search
# index's breadcrumb ("General > Software Update") below. 'edit_profile'
# deliberately has no entry: it's reached by editing a specific account, not
# something worth surfacing as a search result.
EXTRA_PAGE_PARENTS = {
    'general_about': 'general',
    'general_softwareupdate': 'general',
    'general_storage': 'general',
    'general_datetime': 'general',
    'general_language': 'general',
    'general_defaultapps': 'general',
    'accessibility_zoom': 'accessibility',
    'accessibility_display': 'accessibility',
    'accessibility_audio': 'accessibility',
    'appearance_custom_icons': 'appearance',
    'keyboard_shortcuts': 'keyboard',
}

# Extra search terms for pages whose real name doesn't obviously contain the
# word someone would actually type -- kept short and only for genuinely
# common terms, not an attempt to catalog every individual toggle on every
# page (that's a much bigger, separate undertaking).
SEARCH_ALIASES = {
    'general_defaultapps': ['default browser', 'default email', 'browser', 'email client'],
    'appearance': ['dark mode', 'light mode', 'accent color', 'theme'],
    'appearance_custom_icons': ['custom icon', 'app icon', 'icon style', 'upload icon'],
    'dictation': ['dictation', 'speech to text', 'voice typing', 'microphone', 'push to talk',
                  'whisper', 'ai', 'claude', 'openai', 'api key'],
    'displays': ['night light', 'resolution', 'brightness', 'color temperature',
                 'monitor', 'arrangement', 'scale', 'mirror', 'rotate'],
    'multitasking': ['workspaces', 'hot corner', 'edge tiling', 'window tiling',
                     'alt tab', 'app switcher', 'active screen edges'],
    'keyboard': ['input source', 'keyboard layout', 'add layout', 'key repeat', 'shortcuts'],
    'keyboard_shortcuts': ['keyboard shortcuts', 'rebind', 'custom shortcut', 'hotkey',
                           'screenshot shortcut', 'lock screen shortcut'],
    'wifi': ['wireless'],
    'touchid': ['fingerprint', 'change password'],
    'users': ['add user', 'accounts', 'user account'],
    'lockscreen': ['screen lock', 'auto lock'],
    'desktopdock': ['dock size', 'magnification'],
    'privacy': ['location services', 'camera', 'microphone'],
}


def _compact(text: str) -> str:
    """Letters/digits only, lowercased -- 'Wi-Fi' and 'wifi' both reduce to
    the same 'wifi', same for 'Menu Bar'/'menubar', 'Screen Time'/
    'screentime', etc."""
    return ''.join(ch for ch in text.lower() if ch.isalnum())


def _build_search_index() -> list:
    """One entry per searchable destination: every top-level sidebar row,
    plus every drill-in sub-page that has a known parent (see
    EXTRA_PAGE_PARENTS). Each entry carries what it takes to render a result
    row (icon/color/title, and a breadcrumb for sub-pages) and to navigate
    to it (target) -- built once at import time, not on every keystroke."""
    by_row_id = {row_id: (title, icon_name, color)
                 for section in SIDEBAR_SECTIONS for row_id, title, icon_name, color in section}

    index = []
    for row_id, (title, icon_name, color) in by_row_id.items():
        keywords = [title.lower()] + [kw.lower() for kw in SEARCH_ALIASES.get(row_id, [])]
        index.append({
            'target': row_id, 'title': title, 'breadcrumb': None,
            'icon_name': icon_name, 'color': color, 'icon_row_id': row_id, 'keywords': keywords,
        })

    for page_id, parent_id in EXTRA_PAGE_PARENTS.items():
        title = EXTRA_PAGE_TITLES[page_id]
        parent_title, parent_icon, parent_color = by_row_id[parent_id]
        keywords = [title.lower(), f'{parent_title.lower()} {title.lower()}']
        keywords += [kw.lower() for kw in SEARCH_ALIASES.get(page_id, [])]
        # icon_row_id is the PARENT's id, not the sub-page's own -- there's
        # no 'general_softwareupdate.svg' custom icon file, only
        # 'general.svg'. Using the sub-page's own id here was a real bug:
        # make_sidebar_icon's custom-icon lookup silently missed and fell
        # back to a plain symbolic glyph that doesn't exist in the icon
        # theme either, rendering as a blank gray square (confirmed against
        # a live screenshot -- General's own top-level row, which does
        # resolve 'general.svg' correctly, looked completely different from
        # its own sub-page rows in the exact same search results list).
        index.append({
            'target': page_id, 'title': title, 'breadcrumb': parent_title,
            'icon_name': parent_icon, 'color': parent_color, 'icon_row_id': parent_id, 'keywords': keywords,
        })
    return index


SEARCH_INDEX = _build_search_index()
SEARCH_RESULTS_LIMIT = 8

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
    font-size: 14px;
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
.add-photo-tile {
    border: 2px dashed alpha(currentColor, 0.3);
    background-color: alpha(currentColor, 0.04);
}
.add-photo-tile image {
    opacity: 0.5;
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
/* A search-enabled Gtk.DropDown's popup shrinks its list to fit however
   many rows match the typed text, and GTK repositions the whole popover
   to keep it on-screen every time that height changes -- from the
   outside this reads as the popup jumping to a different spot on every
   keystroke. Pinning the internal scrolledwindow to a fixed height keeps
   the popover's own size (and position) constant regardless of how many
   rows are currently showing. */
dropdown.searchable-dropdown popover scrolledwindow {
    min-height: 300px;
}
/* Circular avatar clip -- users_page.py's user-list rows and the Edit
   Profile dialog's preview both wrap a photo/emoji PNG in a Box with this
   class + overflow=HIDDEN, same clip-shape technique as .scheme-photo but
   round instead of the wallpaper tiles' square-with-corner-radius. */
.avatar-circle {
    border-radius: 999px;
}
/* Emoji picker (Users & Groups' avatar editor) -- light rounded card with a
   bottom category strip, matching bluebubbles-native's own emoji picker. */
.emoji-picker-panel {
    background-color: alpha(currentColor, 0.03);
    border-radius: 14px;
    padding: 8px;
}
.emoji-picker-search entry, .emoji-picker-search {
    border-radius: 999px;
}
.emoji-picker-tabs {
    padding: 4px 8px;
    border-radius: 999px;
    background-color: alpha(currentColor, 0.06);
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
SIDEBAR_ICON_PX = 20  # +10% from 18
PLACEHOLDER_ICON_PX = 60
ICON_SLOT_PX = 24  # +10% from 22, fixed footprint every icon sits in, so labels always start at the same x


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
        image = load_sized_image(custom_path, SIDEBAR_ICON_PX)
        box.append(image)
        return box

    box.add_css_class('sidebar-icon')
    box.add_css_class(ACCENT_CLASSES[color])
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(15)  # +10% from 14
    box.append(image)
    return box


def make_placeholder_icon(row_id: str, icon_name: str) -> Gtk.Widget:
    custom_path = _custom_icon_path(row_id)
    if custom_path:
        return load_sized_image(custom_path, PLACEHOLDER_ICON_PX)
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(64)
    image.add_css_class('placeholder-icon')
    return image


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(867, 646)
        # A real minimum, not a stand-in for "whatever the tallest tab's
        # content needs" -- that job now belongs to the ScrolledWindow
        # around _placeholder_stack below. Without it, every card added to
        # a tab (Displays/Desktop & Dock especially) pushed the window's
        # forced minimum height higher, to the point the window couldn't
        # be shrunk at all and, once taller than the work area, had
        # nowhere to go but under the dock.
        # 867x646 is a deliberately-chosen floor, not a leftover default --
        # it's the exact size the user had the window dragged to when they
        # asked for it to become the minimum (read live via this app's own
        # AT-SPI window extents, since Wayland has no X-style window-geometry
        # query tool: org.a11y.atspi.Component.GetExtents on the app's
        # 'window'-role accessible child).
        self.set_size_request(867, 646)
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

        # Pages are built lazily (see _ensure_page), not all ~35 of them up
        # front -- constructing every page eagerly (including ones a given
        # session never visits: Bluetooth, Printers, Touch ID, ...) measured
        # at ~57s to first paint, most of it pure accumulation across pages
        # nobody asked for yet. Only row-id/title/icon metadata is needed
        # before a page is actually opened, so that's all this collects here.
        self._pages = {}
        self._page_row_meta = {}
        for section in SIDEBAR_SECTIONS:
            for row_id, title, icon_name, color in section:
                self._page_row_meta[row_id] = (title, icon_name)

        first_id = SIDEBAR_SECTIONS[0][0][0]
        self._go_to(first_id, record_history=True)

    def _ensure_page(self, row_id: str):
        """Builds and registers row_id's page on first visit; a no-op on
        every later visit. _go_to() calls this before showing anything, so
        it's the single place new pages come into existence."""
        if row_id in self._pages:
            return

        title, icon_name = self._page_row_meta.get(row_id, (EXTRA_PAGE_TITLES.get(row_id, ''), ''))

        if row_id == 'wifi':
            page = WifiPage()
        elif row_id == 'bluetooth':
            page = BluetoothPage()
        elif row_id == 'network':
            page = NetworkPage(
                on_open_wifi=lambda: self._go_to('wifi', record_history=True))
        elif row_id == 'energy':
            page = BatteryPage()
        elif row_id == 'appearance':
            page = AppearancePage(
                on_open_custom_icons=lambda: self._go_to('appearance_custom_icons', record_history=True))
        elif row_id == 'appearance_custom_icons':
            page = CustomIconsPage()
        elif row_id == 'dictation':
            page = DictationPage()
        elif row_id == 'desktopdock':
            page = DesktopDockPage()
        elif row_id == 'multitasking':
            page = MultitaskingPage()
        elif row_id == 'displays':
            page = DisplaysPage()
        elif row_id == 'general':
            page = GeneralPage(
                on_open_about=lambda: self._go_to('general_about', record_history=True),
                on_open_software_update=lambda: self._go_to('general_softwareupdate', record_history=True),
                on_open_storage=lambda: self._go_to('general_storage', record_history=True),
                on_open_datetime=lambda: self._go_to('general_datetime', record_history=True),
                on_open_language=lambda: self._go_to('general_language', record_history=True),
                on_open_defaultapps=lambda: self._go_to('general_defaultapps', record_history=True),
            )
        elif row_id == 'accessibility':
            page = AccessibilityPage(
                on_open_zoom=lambda: self._go_to('accessibility_zoom', record_history=True),
                on_open_display=lambda: self._go_to('accessibility_display', record_history=True),
                on_open_audio=lambda: self._go_to('accessibility_audio', record_history=True),
            )
        elif row_id == 'spotlight':
            page = SpotlightPage()
        elif row_id == 'menubar':
            page = MenuBarPage()
        elif row_id == 'wallpaper':
            page = WallpaperPage()
        elif row_id == 'notifications':
            page = NotificationsPage()
        elif row_id == 'sound':
            page = SoundPage()
        elif row_id == 'screentime':
            page = ScreenTimePage()
        elif row_id == 'privacy':
            page = PrivacyPage()
        elif row_id == 'lockscreen':
            page = LockScreenPage()
        elif row_id == 'touchid':
            page = TouchIDPage()
        elif row_id == 'users':
            page = UsersPage(on_edit_user=self._open_edit_profile)
        elif row_id == 'internetaccounts':
            page = InternetAccountsPage()
        elif row_id == 'keyboard':
            page = KeyboardPage(
                on_open_shortcuts=lambda: self._go_to('keyboard_shortcuts', record_history=True))
        elif row_id == 'keyboard_shortcuts':
            page = KeyboardShortcutsPage()
        elif row_id == 'mouse':
            page = MousePage()
        elif row_id == 'touchpad':
            page = TouchpadPage()
        elif row_id == 'printers':
            page = PrintersPage()
        elif row_id == 'general_about':
            page = GeneralAboutPage()
        elif row_id == 'general_softwareupdate':
            page = GeneralSoftwareUpdatePage()
        elif row_id == 'general_storage':
            page = GeneralStoragePage()
        elif row_id == 'general_datetime':
            page = GeneralDateTimePage()
        elif row_id == 'general_language':
            page = GeneralLanguagePage()
        elif row_id == 'general_defaultapps':
            page = GeneralDefaultAppsPage()
        elif row_id == 'accessibility_zoom':
            page = AccessibilityZoomPage()
        elif row_id == 'accessibility_display':
            page = AccessibilityDisplayPage()
        elif row_id == 'accessibility_audio':
            page = AccessibilityAudioPage()
        elif row_id == 'edit_profile':
            page = users_page.EditProfilePage(
                on_saved=self._on_profile_saved, go_back=lambda: self._navigate(-1))
        else:
            page = self._build_placeholder(row_id, title, icon_name)

        self._pages[row_id] = page
        self._placeholder_stack.add_named(page, row_id)

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
        self._search_entry = search
        search.connect('search-changed', self._on_search_changed)
        search.connect('stop-search', self._on_search_stopped)
        search.connect('activate', self._on_search_activate)
        top_box.append(search)

        # Live view of the actual account (AccountsService), not a static
        # GLib.get_real_name() snapshot -- so a name/photo change made here
        # or from Users & Groups shows up immediately, in both places. See
        # _refresh_signin_row.
        self._signin_button = Gtk.Button(css_classes=['flat', 'signin-row'])
        self._signin_button.connect('clicked', self._on_signin_clicked)
        top_box.append(self._signin_button)
        self._refresh_signin_row()

        outer.append(top_box)

        # hscrollbar_policy=NEVER -- without it, this defaulted to AUTOMATIC
        # and a hair of row-content overflow (long labels like "Printers &
        # Scanners" with no ellipsize) was enough to spawn a horizontal
        # scrollbar across the whole sidebar. A sidebar list should never
        # need to scroll sideways; the content_scroller below already gets
        # this right, this one just didn't.
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
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
                    margin_start=6, margin_end=6, margin_top=3, margin_bottom=3,
                )
                content.append(make_sidebar_icon(row_id, icon_name, color))
                label = Gtk.Label(label=title, xalign=0, hexpand=True, ellipsize=3, css_classes=['nav-row-label'])
                content.append(label)
                row.set_child(content)
                row._row_id = row_id
                listbox.append(row)
            listbox.connect('row-selected', self._on_sidebar_row_selected)
            list_outer.append(listbox)
            self._listboxes.append(listbox)

        scroller.set_child(list_outer)
        self._sidebar_scroller = scroller
        outer.append(scroller)

        # Search results: a plain always-in-the-tree list, visibility
        # toggled instead of a Gtk.Popover -- a popover here was tried
        # first and confirmed live to have two real problems: popup()
        # stole keyboard focus onto its first row (only the first typed
        # character ever reached the entry), and autohide's own input
        # grab could flat-out get stuck, leaving the whole window
        # unresponsive to clicks elsewhere. A plain widget with
        # .set_visible() has none of that -- it's the same mechanism
        # already used safely all over this app (e.g. the emoji-avatar
        # color row in users_page.py).
        self._search_results_list = Gtk.ListBox(
            css_classes=['boxed-list'], selection_mode=Gtk.SelectionMode.NONE, visible=False,
            margin_start=4, margin_end=4,
        )
        self._search_results_list.connect('row-activated', self._on_search_result_activated)
        outer.append(self._search_results_list)

        self._search_empty_label = Gtk.Label(
            label='No results found.', css_classes=['dim-label'], margin_top=12, visible=False,
        )
        outer.append(self._search_empty_label)

        toolbar.set_content(outer)
        return toolbar

    # ---- search ---------------------------------------------------------

    def _search_matches(self, query: str) -> list:
        query = query.strip().lower()
        if not query:
            return []
        # A "compact" (letters/digits only) form of the query is checked
        # too, alongside the literal one -- so "wifi" still finds "Wi-Fi",
        # "menubar" still finds "Menu Bar", "screentime" still finds
        # "Screen Time", without hand-aliasing every title that happens to
        # have a space or hyphen a real search term wouldn't.
        compact_query = _compact(query)
        scored = []
        for entry in SEARCH_INDEX:
            best = None
            for kw in entry['keywords']:
                if kw.startswith(query):
                    best = 0  # prefix match -- best
                    break
                if query in kw:
                    best = 1 if best is None else best  # contains, not a prefix
                    continue
                compact_kw = _compact(kw)
                if compact_query and compact_kw.startswith(compact_query):
                    best = 1 if best is None else best
                elif compact_query and compact_query in compact_kw and best is None:
                    best = 2
            if best is not None:
                scored.append((best, entry['title'], entry))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [entry for _score, _title, entry in scored[:SEARCH_RESULTS_LIMIT]]

    def _build_search_result_row(self, entry: dict) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_start(6)
        row.set_margin_end(6)
        row.set_margin_top(4)
        row.set_margin_bottom(4)
        row.append(make_sidebar_icon(entry['icon_row_id'], entry['icon_name'], entry['color']))

        if entry['breadcrumb']:
            label = Gtk.Label(xalign=0, use_markup=True)
            label.set_markup(
                f'<span alpha="65%">{GLib.markup_escape_text(entry["breadcrumb"])} ›</span> '
                f'{GLib.markup_escape_text(entry["title"])}'
            )
        else:
            label = Gtk.Label(label=entry['title'], xalign=0)
        row.append(label)
        row._search_target = entry['target']
        return row

    def _show_search_results(self, searching: bool):
        self._sidebar_scroller.set_visible(not searching)
        self._search_results_list.set_visible(searching)

    def _refresh_search_results(self, query: str):
        child = self._search_results_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._search_results_list.remove(child)
            child = nxt

        query = query.strip()
        if not query:
            self._search_empty_label.set_visible(False)
            self._show_search_results(False)
            return

        matches = self._search_matches(query)
        self._search_empty_label.set_visible(not matches)
        for entry in matches:
            self._search_results_list.append(self._build_search_result_row(entry))
        self._show_search_results(True)

    def _on_search_changed(self, entry: Gtk.SearchEntry):
        self._refresh_search_results(entry.get_text())

    def _on_search_stopped(self, entry: Gtk.SearchEntry):
        entry.set_text('')
        self._search_empty_label.set_visible(False)
        self._show_search_results(False)

    def _on_search_activate(self, entry: Gtk.SearchEntry):
        # Enter with no manual click -- jump straight to the top match.
        matches = self._search_matches(entry.get_text())
        if matches:
            self._go_to_search_result(matches[0]['target'])

    def _on_search_result_activated(self, _listbox, row):
        self._go_to_search_result(row.get_child()._search_target)

    def _go_to_search_result(self, target: str):
        self._search_entry.set_text('')
        self._search_empty_label.set_visible(False)
        self._show_search_results(False)
        self._go_to(target, record_history=True)

    def _refresh_signin_row(self):
        try:
            user_path = users_page.get_current_user_path()
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                users_page.ACCOUNTS_BUS_NAME, user_path, users_page.USER_IFACE, None,
            )
            username = proxy.get_cached_property('UserName').unpack()
            real_name = proxy.get_cached_property('RealName').unpack() or username
            icon_file = proxy.get_cached_property('IconFile').unpack()
            avatar_path = users_page._resolve_avatar_display_path(username, icon_file)
        except GLib.Error:
            # No AccountsService reachable (e.g. running outside a real
            # peachOS session) -- fall back to the static local values
            # rather than leaving the row blank.
            real_name = GLib.get_real_name()
            if not real_name or real_name == 'Unknown':
                real_name = GLib.get_user_name()
            avatar_path = None

        content = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=4, margin_top=4, margin_bottom=4,
        )
        content.append(users_page._circular_avatar(avatar_path, 32, fallback_text=real_name))
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        labels.append(Gtk.Label(label=real_name, xalign=0, css_classes=['signin-name']))
        labels.append(Gtk.Label(label='peachOS Account', xalign=0, css_classes=['signin-subtitle']))
        content.append(labels)
        self._signin_button.set_child(content)

    def _on_signin_clicked(self, _btn):
        try:
            user_path = users_page.get_current_user_path()
        except GLib.Error:
            return
        self._open_edit_profile(user_path)

    def _open_edit_profile(self, user_path: str):
        self._ensure_page('edit_profile')
        self._pages['edit_profile'].load_user(user_path)
        self._go_to('edit_profile', record_history=True)

    def _on_profile_saved(self, _user_path: str):
        # Both live views of account data (the sidebar's own sign-in row,
        # and Users & Groups' list) need to pick up a save regardless of
        # which one was used to get to the edit page -- cheap enough to
        # just always refresh both rather than tracking which one launched it.
        # Reachable via the sidebar's sign-in row directly, without ever
        # visiting Users & Groups first -- that page may not be built yet
        # (see _ensure_page), in which case there's nothing to refresh: it'll
        # load fresh data on its own whenever it does get opened.
        self._refresh_signin_row()
        users_tab = self._pages.get('users')
        if users_tab:
            users_tab.reload()

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

    def _is_sidebar_page(self, row_id: str) -> bool:
        return any(rid == row_id for section in SIDEBAR_SECTIONS for rid, *_ in section)

    def _go_to(self, row_id: str, record_history: bool):
        self._ensure_page(row_id)

        # Drilling into a detail page (e.g. General -> About) slides left,
        # like macOS's own settings; returning to a sidebar page slides
        # back right. Switching between two sidebar pages just crossfades.
        old_id = self._placeholder_stack.get_visible_child_name()
        if not self._is_sidebar_page(row_id):
            transition = Gtk.StackTransitionType.SLIDE_LEFT
        elif old_id and not self._is_sidebar_page(old_id):
            transition = Gtk.StackTransitionType.SLIDE_RIGHT
        else:
            transition = Gtk.StackTransitionType.CROSSFADE
        self._placeholder_stack.set_transition_type(transition)
        self._placeholder_stack.set_visible_child_name(row_id)

        # Always explicitly syncs (or clears) every listbox's selection to
        # match row_id -- not just "select it if found". A sub-page (About,
        # Software Update, a search result, ...) isn't in SIDEBAR_SECTIONS
        # at all, so the old code simply never touched selection for those,
        # leaving whichever sidebar row was selected *before* still marked
        # selected underneath. Confirmed live: re-clicking that exact same
        # row later then does nothing, since GtkListBox doesn't re-fire
        # row-selected for a no-op reselect -- the sidebar looked dead.
        for section, listbox in zip(SIDEBAR_SECTIONS, self._listboxes):
            matched_row = None
            for idx, (rid, *_rest) in enumerate(section):
                if rid == row_id:
                    matched_row = listbox.get_row_at_index(idx)
                    break
            if listbox.get_selected_row() is not matched_row:
                listbox.select_row(matched_row)

        title = next(
            (title for section in SIDEBAR_SECTIONS for rid, title, *_ in section if rid == row_id),
            EXTRA_PAGE_TITLES.get(row_id, ''),
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
        # HANDLES_COMMAND_LINE is required for do_command_line() below to actually receive
        # argv at all -- without it, GApplication's own default local-command-line handling
        # treats a bare non-option argument like "sound" as a file URI to open instead
        # (confirmed live: DEFAULT_FLAGS alone produced a real
        # "GLib-GIO-CRITICAL: This application can not open files" warning when launched as
        # `peachos-settings sound`, not assumed from documentation).
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._target_page = None

    def do_command_line(self, command_line):
        # DEFAULT_FLAGS makes this a normal single-instance GApplication -- a second
        # `peachos-settings <page>` invocation while the window's already open (e.g.
        # clicking "Sound Settings" in the top bar's sound menu while Settings is open on
        # some other page) is delivered here too, via D-Bus, NOT as a fresh do_activate()
        # with args -- do_activate() never receives argv at all, only this does. That's
        # the whole reason this override exists rather than just reading sys.argv in main().
        args = command_line.get_arguments()
        self._target_page = args[1] if len(args) > 1 else None
        self.activate()
        return 0

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
        if self._target_page:
            win._go_to(self._target_page, record_history=True)
            self._target_page = None
        win.present()


def main():
    app = SettingsApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
