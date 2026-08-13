import os
import re

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# Same source-of-truth as the top-bar's "About This PC" window
# (macOS-TopBar-Gnome/app/aboutWindow.js) -- read hardware/OS facts
# straight from /proc, /sys and /etc/os-release rather than duplicating
# them by hand, so the two "About" surfaces can't drift out of sync.
DMI_PLACEHOLDER = re.compile(
    r'^(to be filled|system product name|system version|default string|none|unknown|not applicable|oem)',
    re.I,
)


def _read_file_trimmed(path: str):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_dmi_field(name: str):
    value = _read_file_trimmed(f'/sys/devices/virtual/dmi/id/{name}')
    if value and not DMI_PLACEHOLDER.match(value):
        return value
    return None


def _read_cpu_model():
    contents = _read_file_trimmed('/proc/cpuinfo') or ''
    match = re.search(r'^model name\s*:\s*(.+)$', contents, re.M)
    if not match:
        return None
    model = match.group(1)
    model = re.sub(r'\((?:R|TM|C)\)', '', model, flags=re.I)
    model = re.sub(r'\s*CPU\s*@\s*[\d.]+\s*[GM]Hz', '', model, flags=re.I)
    model = re.sub(r'\s+(?:w/|with)\s+.*$', '', model, flags=re.I)
    return re.sub(r'\s+', ' ', model).strip() or None


def _read_memory():
    contents = _read_file_trimmed('/proc/meminfo') or ''
    match = re.search(r'^MemTotal:\s+(\d+)\s+kB', contents, re.M)
    if not match:
        return None
    return f'{round(int(match.group(1)) / 1048576)} GB'


def _read_os_release():
    fields = {}
    contents = _read_file_trimmed('/etc/os-release') or ''
    for line in contents.splitlines():
        match = re.match(r'^(\w+)="?([^"]*)"?$', line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def _read_desktop_version():
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(
            'org.gnome.Shell', '/org/gnome/Shell', 'org.freedesktop.DBus.Properties', 'Get',
            GLib.Variant('(ss)', ('org.gnome.Shell', 'ShellVersion')),
            GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None,
        )
        version = reply.unpack()[0]
        return f'GNOME {version}' if version else None
    except GLib.Error:
        return None


class InfoRow(Gtk.Box):
    def __init__(self, key: str, value: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=key, xalign=0))
        self.append(Gtk.Label(label=value, xalign=1, hexpand=True, css_classes=['dim-label']))


class GeneralAboutPage(Gtk.Box):
    def __init__(self, on_back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self._on_back = on_back
        self._build_ui()

    def _build_ui(self):
        if self._on_back:
            back_btn = Gtk.Button(css_classes=['flat'], halign=Gtk.Align.START)
            back_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            back_content.append(Gtk.Image.new_from_icon_name('go-previous-symbolic'))
            back_content.append(Gtk.Label(label='General'))
            back_btn.set_child(back_content)
            back_btn.connect('clicked', lambda *_a: self._on_back())
            self.append(back_btn)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'laptop.svg'), 'computer-symbolic',
            'About', 'An overview of the hardware and software running this Mac.',
        ))

        os_release = _read_os_release()
        model_name = (
            _read_dmi_field('product_family')
            or _read_dmi_field('product_name')
            or _read_dmi_field('product_version')
        )
        if model_name:
            model_name = re.sub(r'\s*\([^)]*\)', '', model_name).strip()
        vendor = _read_dmi_field('sys_vendor')
        model = ' '.join(filter(None, [vendor, model_name])) or None
        os_name = ' '.join(filter(None, [os_release.get('NAME'), os_release.get('VERSION_ID')])) or 'Linux'

        details = [
            ('Name', GLib.get_host_name()),
            ('Model', model),
            ('Chip', _read_cpu_model()),
            ('Memory', _read_memory()),
            ('Desktop', _read_desktop_version()),
            ('OS', os_name),
        ]
        details = [(key, value) for key, value in details if value]

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'])
        for i, (key, value) in enumerate(details):
            if i > 0:
                card.append(Gtk.Separator(margin_start=14))
            card.append(InfoRow(key, value))
        self.append(card)
