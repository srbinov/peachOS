import os
import re
import urllib.parse

from gi.repository import Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# e.g. "printer Brother_HL_L2460DW is idle.  enabled since Tue 19 Aug 2026 04:12:00 PM UTC"
_PRINTER_LINE_RE = re.compile(r'^printer (\S+) (is (idle|printing)|disabled)')
# e.g. "network ipp://192.168.1.50/ipp/print" or "direct usb://HP/LaserJet?serial=1234"
_DEVICE_LINE_RE = re.compile(r'^(\S+) (\S+://\S+)')
# e.g. "device 'net:192.168.1.50:airscan:e0:HP OfficeJet Pro' is a HP OfficeJet Pro ... scanner"
_SCANNER_LINE_RE = re.compile(r"^device `([^']+)' is a (.+)$")


def _run(argv):
    proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
    ok, stdout, _stderr = proc.communicate_utf8(None, None)
    return stdout if ok else ''


def _run_async(argv, callback):
    """callback(stdout: str) on completion -- errors just come back as ''. Both discovery
    scans this page uses (lpinfo -v ~2.6s, scanimage -L ~10s on real hardware, both do
    genuine network/USB probing) are slow enough that running them synchronously froze the
    whole dialog with no feedback -- this is what actually lets a search animation show
    while they run instead of blocking the main loop."""
    proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)

    def on_done(source, result):
        try:
            ok, stdout, _stderr = source.communicate_utf8_finish(result)
        except GLib.Error:
            ok, stdout = False, ''
        callback(stdout if ok else '')

    proc.communicate_utf8_async(None, None, on_done)


def _list_printers():
    printers = []
    for line in _run(['lpstat', '-p']).splitlines():
        match = _PRINTER_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        status = 'Idle' if 'idle' in line else ('Printing' if 'printing' in line else 'Disabled')
        printers.append((name, status))
    return printers


def _default_printer():
    out = _run(['lpstat', '-d']).strip()
    if ':' not in out:
        return None
    name = out.split(':', 1)[1].strip()
    return name or None


def _friendly_name_from_uri(uri: str) -> str:
    parsed = urllib.parse.urlsplit(uri)
    host = parsed.hostname or parsed.netloc or uri
    # DNS-SD URIs (dnssd://My%20Printer._ipp._tcp.local/...) encode the device's real
    # advertised name as the first label of the hostname -- everything else here is
    # protocol/service-type boilerplate, not something worth showing.
    if parsed.scheme == 'dnssd':
        label = host.split('.')[0]
        return urllib.parse.unquote(label).replace('%20', ' ') or uri
    if parsed.scheme in ('usb', 'ipp', 'ipps'):
        segment = parsed.path.strip('/').split('/')[0] if parsed.path else ''
        if segment:
            return urllib.parse.unquote(segment)
    return host or uri


def _add_printer(name: str, uri: str) -> tuple:
    driver = 'everywhere' if uri.startswith(('ipp://', 'ipps://')) else 'raw'
    proc = Gio.Subprocess.new(
        ['lpadmin', '-p', name, '-E', '-v', uri, '-m', driver],
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_PIPE,
    )
    ok, _stdout, stderr = proc.communicate_utf8(None, None)
    success = proc.get_exit_status() == 0
    return success, (stderr or '').strip()


class _DiscoveredRow(Gtk.Button):
    def __init__(self, icon_name: str, title: str, subtitle: str):
        super().__init__(css_classes=['flat'])
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(28)
        content.append(icon)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text_box.append(Gtk.Label(label=title, xalign=0))
        text_box.append(Gtk.Label(label=subtitle, xalign=0, css_classes=['caption', 'dim-label']))
        content.append(text_box)
        self.set_child(content)


class _AddPrinterDialog(Gtk.Window):
    def __init__(self, parent, on_added):
        super().__init__(
            title='Add Printer or Scanner', transient_for=parent, modal=True,
            default_width=420, default_height=420,
        )
        self._on_added = on_added
        self._pending_scans = 2  # lpinfo + scanimage
        self._printer_uris = []
        self._scanners = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(20)
        root.set_margin_bottom(20)
        self.set_child(root)

        self._searching_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.CENTER, vexpand=True,
        )
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32, halign=Gtk.Align.CENTER)
        self._searching_box.append(spinner)
        self._searching_box.append(Gtk.Label(
            label='Searching for printers and scanners on your network…', css_classes=['dim-label']))
        root.append(self._searching_box)

        self._results_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, visible=False,
        )
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._results_scroller.set_child(self._results_box)
        root.append(self._results_scroller)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        root.append(self._error_label)

        manual_btn = Gtk.LinkButton(label='Add Manually by Network Address…')
        manual_btn.set_has_frame(False)
        manual_btn.connect('activate-link', self._on_manual_clicked)
        root.append(manual_btn)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
        close_btn = Gtk.Button(label='Cancel')
        close_btn.connect('clicked', lambda *_a: self.close())
        button_row.append(close_btn)
        root.append(button_row)

        _run_async(['lpinfo', '-v'], self._on_printers_found)
        _run_async(['scanimage', '-L'], self._on_scanners_found)

    def _on_printers_found(self, stdout):
        for line in stdout.splitlines():
            match = _DEVICE_LINE_RE.match(line)
            if match:
                self._printer_uris.append(match.group(2))
        self._scan_finished()

    def _on_scanners_found(self, stdout):
        for line in stdout.splitlines():
            match = _SCANNER_LINE_RE.match(line)
            if match:
                self._scanners.append((match.group(1), match.group(2)))
        self._scan_finished()

    def _scan_finished(self):
        self._pending_scans -= 1
        if self._pending_scans > 0:
            return

        self._searching_box.set_visible(False)
        self._results_scroller.set_visible(True)

        if not self._printer_uris and not self._scanners:
            self._results_box.append(Gtk.Label(
                label="No printers or scanners were found on this network.",
                wrap=True, css_classes=['dim-label'],
            ))
            return

        if self._printer_uris:
            self._results_box.append(Gtk.Label(label='Printers', xalign=0, css_classes=['heading']))
            printer_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
            for uri in self._printer_uris:
                row = _DiscoveredRow('printer-symbolic', _friendly_name_from_uri(uri), uri)
                row.connect('clicked', lambda _b, u=uri: self._on_printer_chosen(u))
                printer_list.append(row)
            self._results_box.append(printer_list)

        if self._scanners:
            self._results_box.append(Gtk.Label(label='Scanners', xalign=0, css_classes=['heading']))
            scanner_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
            for device_id, description in self._scanners:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_margin_start(8)
                row.set_margin_end(8)
                row.set_margin_top(8)
                row.set_margin_bottom(8)
                icon = Gtk.Image.new_from_icon_name('scanner-symbolic')
                icon.set_pixel_size(28)
                row.append(icon)
                text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                text_box.append(Gtk.Label(label=description, xalign=0))
                text_box.append(Gtk.Label(
                    label='Ready to use in any scanning app', xalign=0, css_classes=['caption', 'dim-label']))
                row.append(text_box)
                scanner_list.append(row)
            self._results_box.append(scanner_list)

    def _on_printer_chosen(self, uri):
        name = re.sub(r'[^A-Za-z0-9_]+', '_', _friendly_name_from_uri(uri)).strip('_') or 'Printer'
        success, error = _add_printer(name, uri)
        if success:
            self._on_added()
            self.close()
        else:
            self._error_label.set_label(error or 'Could not add that printer.')
            self._error_label.set_visible(True)

    def _on_manual_clicked(self, _btn):
        self.close()
        dialog = _ManualAddPrinterDialog(self.get_transient_for(), on_added=self._on_added)
        dialog.present()
        return True


class _ManualAddPrinterDialog(Gtk.Window):
    def __init__(self, parent, on_added):
        super().__init__(
            title='Add Printer Manually', transient_for=parent, modal=True,
            default_width=420, resizable=False,
        )
        self._on_added = on_added

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        self.set_child(box)

        box.append(Gtk.Label(label='Printer Name', xalign=0))
        self._name_entry = Gtk.Entry(placeholder_text='e.g. Office Printer')
        box.append(self._name_entry)

        box.append(Gtk.Label(label='Connection', xalign=0))
        self._uri_entry = Gtk.Entry(placeholder_text='ipp://192.168.1.50/ipp/print or socket://192.168.1.50:9100')
        box.append(self._uri_entry)

        self._error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        box.append(self._error_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label='Cancel')
        cancel_btn.connect('clicked', lambda *_a: self.close())
        button_row.append(cancel_btn)
        self._add_btn = Gtk.Button(label='Add', css_classes=['suggested-action'])
        self._add_btn.connect('clicked', self._on_add_clicked)
        button_row.append(self._add_btn)
        box.append(button_row)

    def _on_add_clicked(self, _btn):
        name = self._name_entry.get_text().strip().replace(' ', '_')
        uri = self._uri_entry.get_text().strip()
        if not name or not uri:
            self._error_label.set_label('Enter both a name and a connection.')
            self._error_label.set_visible(True)
            return

        self._add_btn.set_sensitive(False)
        success, error = _add_printer(name, uri)
        if success:
            self._on_added()
            self.close()
        else:
            self._add_btn.set_sensitive(True)
            self._error_label.set_label(error or 'Could not add the printer.')
            self._error_label.set_visible(True)


class PrintersPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'printers.svg'), 'printer-symbolic',
            'Printers & Scanners', 'Add and manage the printers and scanners connected to this computer.',
        ))

        self._default_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._default_card)

        self.append(Gtk.Label(label='Printers', xalign=0, css_classes=['heading']))
        self._printer_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._printer_list)

        self._empty_label = Gtk.Label(label='No printers added yet.', css_classes=['dim-label'], visible=False)
        self.append(self._empty_label)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.END)
        add_btn = Gtk.Button(label='Add Printer or Scanner…', css_classes=['flat'])
        add_btn.connect('clicked', self._on_add_clicked)
        button_row.append(add_btn)
        self.append(button_row)

        GLib.idle_add(self._load)

    def _on_add_clicked(self, _btn):
        dialog = _AddPrinterDialog(self.get_root(), on_added=self._load)
        dialog.present()

    def _load(self):
        child = self._default_card.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._default_card.remove(child)
            child = next_child
        child = self._printer_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._printer_list.remove(child)
            child = next_child

        printers = _list_printers()
        default = _default_printer()

        self._empty_label.set_visible(not printers)
        if not printers:
            return GLib.SOURCE_REMOVE

        default_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        default_row.set_margin_start(14)
        default_row.set_margin_end(14)
        default_row.set_margin_top(10)
        default_row.set_margin_bottom(10)
        default_row.append(Gtk.Label(label='Default printer', xalign=0, hexpand=True))
        dropdown = Gtk.DropDown.new_from_strings([name for name, _status in printers])
        if default:
            names = [name for name, _status in printers]
            if default in names:
                dropdown.set_selected(names.index(default))
        dropdown.connect('notify::selected', lambda dd, _p: _run(
            ['lpoptions', '-d', printers[dd.get_selected()][0]]))
        default_row.append(dropdown)
        self._default_card.append(default_row)

        for name, status in printers:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
            row.set_margin_start(14)
            row.set_margin_end(14)
            row.set_margin_top(8)
            row.set_margin_bottom(8)
            icon = Gtk.Image.new_from_icon_name('printer-symbolic')
            icon.set_pixel_size(28)
            row.append(icon)
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
            text_box.append(Gtk.Label(label=name.replace('_', ' '), xalign=0))
            text_box.append(Gtk.Label(label=status, xalign=0, css_classes=['caption', 'dim-label']))
            row.append(text_box)
            self._printer_list.append(row)

        return GLib.SOURCE_REMOVE
