import os
import subprocess

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

ACCOUNTS_SERVICE = 'org.freedesktop.Accounts'
ACCOUNTS_PATH = '/org/freedesktop/Accounts'
ACCOUNTS_IFACE = 'org.freedesktop.Accounts'
USER_IFACE = 'org.freedesktop.Accounts.User'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

# Just enough to turn the locale codes this VM actually has generated into
# something readable -- unrecognized codes fall back to the raw code
# itself rather than guessing, since `locale -a` is the real source of
# truth for what's installed, not this list.
LANGUAGE_NAMES = {'en': 'English', 'C': 'Default (C)'}
COUNTRY_NAMES = {
    'US': 'United States', 'GB': 'United Kingdom', 'CA': 'Canada', 'AU': 'Australia',
    'IE': 'Ireland', 'IN': 'India', 'NZ': 'New Zealand', 'ZA': 'South Africa',
    'SG': 'Singapore', 'HK': 'Hong Kong', 'PH': 'Philippines', 'NG': 'Nigeria',
    'ZM': 'Zambia', 'ZW': 'Zimbabwe', 'BW': 'Botswana', 'DK': 'Denmark',
    'IL': 'Israel', 'AG': 'Antigua and Barbuda',
}


def _list_locales() -> list:
    """The set of locales actually generated on this system -- `locale -a`,
    not a hardcoded list, since offering a locale that isn't actually
    installed would just fail silently when GNOME tries to use it."""
    try:
        output = subprocess.run(
            ['locale', '-a'], capture_output=True, text=True, timeout=3, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _format_region_label(locale_code: str) -> str:
    base = locale_code.split('.')[0]
    lang, _, country = base.partition('_')
    lang_name = LANGUAGE_NAMES.get(lang, lang)
    if not country:
        return lang_name
    country_name = COUNTRY_NAMES.get(country, country)
    return f'{lang_name} ({country_name})'


class DropdownRow(Gtk.Box):
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
        self.dropdown = Gtk.DropDown(enable_search=True)
        self.append(self.dropdown)
        self._codes = []

    def set_options(self, codes: list, labels: list, selected_code: str = None):
        self._codes = codes
        self.dropdown.set_model(Gtk.StringList.new(labels))
        if not selected_code:
            return
        if selected_code in codes:
            self.dropdown.set_selected(codes.index(selected_code))
            return
        # AccountsService and `locale -a` don't agree on locale string
        # formatting (e.g. FormatsLocale='en_US.UTF-8' vs `locale -a`'s
        # 'en_US.utf8') -- fall back to matching just the lang_COUNTRY
        # base, ignoring the encoding suffix's spelling/casing.
        base = selected_code.split('.')[0].lower()
        for i, code in enumerate(codes):
            if code.split('.')[0].lower() == base:
                self.dropdown.set_selected(i)
                return

    def get_selected_code(self):
        idx = self.dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self._codes):
            return None
        return self._codes[idx]


class GeneralLanguagePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._bus = None
        self._user_path = None
        self._syncing = False

        self._build_ui()
        self._connect_bus()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general_language_region.svg'), 'preferences-desktop-locale-symbolic',
            'Language & Region', 'Set the language peachOS uses and how dates, times, and numbers are formatted.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._language_row = DropdownRow('Language')
        self._language_row.dropdown.connect('notify::selected', self._on_language_changed)
        card.append(self._language_row)

        self._region_row = DropdownRow(
            'Region', 'Affects the format of dates, times, numbers, and measurements.',
        )
        self._region_row.dropdown.connect('notify::selected', self._on_region_changed)
        card.append(self._region_row)
        self.append(card)

        self._note_label = Gtk.Label(
            label='Changes take effect the next time you log in.',
            xalign=0, wrap=True, css_classes=['dim-label', 'caption'], margin_start=4,
        )
        self.append(self._note_label)

        self._status_label = Gtk.Label(label='', wrap=True, css_classes=['dim-label'], visible=False)
        self.append(self._status_label)

    def _connect_bus(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            self._show_error(f'Could not reach the system bus: {e.message}')
            return

        locales = _list_locales()
        # 'C'/'C.utf8'/'POSIX' aren't real regions -- exclude those, keep
        # everything else exactly as `locale -a` reports it.
        region_codes = sorted(l for l in locales if l not in ('C', 'C.utf8', 'POSIX'))
        language_codes = sorted({code.split('_')[0].split('.')[0] for code in region_codes})

        if not region_codes:
            self._show_error('No locales are installed on this computer.')
            self._language_row.set_sensitive(False)
            self._region_row.set_sensitive(False)
            return

        self._region_codes = region_codes
        self._language_codes = language_codes

        try:
            reply = self._bus.call_sync(
                ACCOUNTS_SERVICE, ACCOUNTS_PATH, ACCOUNTS_IFACE, 'FindUserByName',
                GLib.Variant('(s)', (GLib.get_user_name(),)),
                GLib.VariantType.new('(o)'), Gio.DBusCallFlags.NONE, 3000, None,
            )
            self._user_path = reply.unpack()[0]
        except GLib.Error as e:
            self._show_error(f'Could not reach accounts-daemon: {e.message}')
            self._language_row.set_sensitive(False)
            self._region_row.set_sensitive(False)
            return

        self._bus.signal_subscribe(
            ACCOUNTS_SERVICE, PROPS_IFACE, 'PropertiesChanged', self._user_path, None,
            Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh(),
        )
        self._refresh()

    def _get_prop(self, name: str):
        return self._bus.call_sync(
            ACCOUNTS_SERVICE, self._user_path, PROPS_IFACE, 'Get',
            GLib.Variant('(ss)', (USER_IFACE, name)),
            GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
        ).unpack()[0]

    def _refresh(self):
        self._syncing = True
        try:
            current_language = self._get_prop('Language') or 'en'
            current_region = self._get_prop('FormatsLocale') or 'en_US.UTF-8'

            language_labels = [LANGUAGE_NAMES.get(c, c) for c in self._language_codes]
            self._language_row.set_options(self._language_codes, language_labels, selected_code=current_language)

            region_labels = [_format_region_label(c) for c in self._region_codes]
            self._region_row.set_options(self._region_codes, region_labels, selected_code=current_region)
        except GLib.Error as e:
            self._show_error(f'Could not read language settings: {e.message}')
        finally:
            self._syncing = False

    def _show_error(self, message: str):
        self._status_label.set_label(message)
        self._status_label.set_visible(True)

    def _on_language_changed(self, dropdown, _pspec):
        if self._syncing or not self._bus:
            return
        code = self._language_row.get_selected_code()
        if not code:
            return
        try:
            self._bus.call_sync(
                ACCOUNTS_SERVICE, self._user_path, USER_IFACE, 'SetLanguage',
                GLib.Variant('(s)', (code,)), None, Gio.DBusCallFlags.NONE, 5000, None,
            )
        except GLib.Error as e:
            self._show_error(f'Could not change language: {e.message}')

    def _on_region_changed(self, dropdown, _pspec):
        if self._syncing or not self._bus:
            return
        code = self._region_row.get_selected_code()
        if not code:
            return
        try:
            self._bus.call_sync(
                ACCOUNTS_SERVICE, self._user_path, USER_IFACE, 'SetFormatsLocale',
                GLib.Variant('(s)', (code,)), None, Gio.DBusCallFlags.NONE, 5000, None,
            )
        except GLib.Error as e:
            self._show_error(f'Could not change region: {e.message}')
