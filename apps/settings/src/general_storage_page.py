import os
import shutil
import subprocess
import threading

from gi.repository import GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# (label, color) in the same order the reference macOS Storage panel uses.
CATEGORY_COLORS = [
    ('Documents', '#FF3B30'),
    ('Applications', '#FF9500'),
    ('Trash', '#FFCC00'),
    ('System Data', '#8E8E93'),
    ('Other Volumes', '#C7C7CC'),
]

# Snap's loop-mounted squashfs images and virtual filesystems (tmpfs,
# proc, cgroup...) aren't real "other volumes" a user would recognize --
# filtered out of the Other Volumes category by fstype.
EXCLUDED_FSTYPES = {
    'tmpfs', 'devtmpfs', 'proc', 'sysfs', 'cgroup', 'cgroup2', 'overlay',
    'squashfs', 'devpts', 'securityfs', 'pstore', 'efivarfs', 'bpf',
    'configfs', 'autofs', 'tracefs', 'debugfs', 'hugetlbfs', 'mqueue',
    'fusectl', 'binfmt_misc', 'nsfs',
}


def _dir_size_bytes(path: str) -> int:
    if not os.path.isdir(path):
        return 0
    try:
        result = subprocess.run(['du', '-sb', path], capture_output=True, text=True, timeout=60)
        return int(result.stdout.split()[0])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return 0


def _dpkg_installed_bytes() -> int:
    try:
        result = subprocess.run(
            ['dpkg-query', '-Wf', '${Installed-Size}\n'],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return 0
    total_kb = sum(int(line) for line in result.stdout.splitlines() if line.strip().isdigit())
    return total_kb * 1024


def _other_volumes_used_bytes() -> int:
    total = 0
    seen_devices = set()
    try:
        with open('/proc/mounts') as f:
            lines = f.readlines()
    except OSError:
        return 0
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mountpoint, fstype = parts[0], parts[1], parts[2]
        if not device.startswith('/dev/') or mountpoint == '/' or fstype in EXCLUDED_FSTYPES:
            continue
        if device in seen_devices:
            continue
        seen_devices.add(device)
        try:
            total += shutil.disk_usage(mountpoint).used
        except OSError:
            continue
    return total


def _gather_storage_info() -> dict:
    """Runs on a background thread (du over the whole home directory can
    take a while on a real, full disk) -- never call this on the main
    loop."""
    total, used, _free = shutil.disk_usage('/')
    home = os.path.expanduser('~')
    trash_dir = os.path.join(home, '.local', 'share', 'Trash')

    trash_bytes = _dir_size_bytes(trash_dir)
    home_bytes = _dir_size_bytes(home)
    # "Documents" here means "everything else in the home directory"
    # (Desktop, Downloads, dotfiles, caches...) -- Linux has no
    # per-category filesystem metadata the way macOS/APFS does, so this
    # is the closest honest equivalent to macOS's own catch-all
    # user-files category, not a literal ~/Documents-only size.
    documents_bytes = max(0, home_bytes - trash_bytes)
    applications_bytes = _dpkg_installed_bytes()
    other_volumes_bytes = _other_volumes_used_bytes()
    # Whatever's left after home directory contents and dpkg-tracked
    # package files -- kernel, logs, snap/flatpak images, container
    # layers, swap, etc. Same catch-all role "System Data" plays in
    # macOS's own Storage panel.
    system_bytes = max(0, used - documents_bytes - trash_bytes - applications_bytes)

    return {
        'total': total,
        'used': used,
        'categories': [documents_bytes, applications_bytes, trash_bytes, system_bytes, other_volumes_bytes],
    }


def _format_gb(num_bytes: int) -> str:
    return f'{num_bytes / 1e9:.2f} GB'


def _apply_css(widget: Gtk.Widget, css: str):
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode())
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class StorageBar(Gtk.Box):
    """The segmented usage bar itself, drawn with a CSS linear-gradient
    using hard (repeated-percentage) color stops rather than a
    Gtk.DrawingArea -- this VM is missing the python3-gi-cairo system
    package (no gi._gi_cairo module), which pycairo needs to hand a real
    cairo.Context to a DrawingArea's draw func, and installing it needs
    sudo. A CSS gradient needs no cairo at all and GTK's CSS engine
    already supports hard stops fine."""

    def __init__(self):
        super().__init__(css_classes=['storage-bar'], hexpand=True)
        self.set_size_request(-1, 22)
        self._provider = Gtk.CssProvider()
        self.get_style_context().add_provider(self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_segments([])

    def set_segments(self, segments: list):
        stops = []
        pct = 0.0
        for hex_color, fraction in segments:
            start = pct
            pct = min(100.0, pct + fraction * 100)
            if pct <= start:
                continue
            stops.append(f'{hex_color} {start:.4f}%, {hex_color} {pct:.4f}%')
        if stops and pct < 100.0:
            # Without an explicit final stop, CSS extends the *last*
            # color to fill the rest of the gradient box instead of
            # leaving it alone -- transparent here reveals the bar's own
            # background-color as the free-space remainder.
            stops.append(f'transparent {pct:.4f}%')
        # linear-gradient() needs at least 2 color stops -- with no
        # segments yet (initial empty state before the scan finishes)
        # there's nothing to draw, so skip the gradient entirely rather
        # than emit a degenerate one-stop gradient.
        gradient = ', '.join(stops)
        image = f'linear-gradient(to right, {gradient})' if len(stops) >= 2 else 'none'
        css = (
            '.storage-bar {'
            f'  border-radius: 6px; background-color: alpha(currentColor, 0.06); background-image: {image};'
            '}'
        )
        self._provider.load_from_data(css.encode())


class LegendDot(Gtk.Box):
    def __init__(self, label: str, hex_color: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dot = Gtk.Box(width_request=8, height_request=8, valign=Gtk.Align.CENTER)
        _apply_css(dot, f'box {{ background-color: {hex_color}; border-radius: 999px; }}')
        self.append(dot)
        self.append(Gtk.Label(label=label, css_classes=['caption']))


class GeneralStoragePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._build_ui()
        self._start_scan()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general_storage.svg'), 'drive-harddisk-symbolic',
            'Storage', 'See how much space is being used on this computer, and by what.',
        ))

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'])
        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10,
            margin_start=16, margin_end=16, margin_top=16, margin_bottom=16,
        )

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header_row.append(Gtk.Label(
            label=GLib.get_host_name() or 'This Computer', xalign=0, hexpand=True, css_classes=['heading'],
        ))
        self._usage_label = Gtk.Label(label='Calculating…', xalign=1, css_classes=['dim-label'])
        header_row.append(self._usage_label)
        inner.append(header_row)

        self._bar = StorageBar()
        inner.append(self._bar)

        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16, halign=Gtk.Align.CENTER)
        for label, hex_color in CATEGORY_COLORS:
            legend.append(LegendDot(label, hex_color))
        inner.append(legend)

        card.append(inner)
        self.append(card)

    def _start_scan(self):
        def worker():
            info = _gather_storage_info()
            GLib.idle_add(self._on_scan_done, info)

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, info: dict):
        total = info['total']
        used = info['used']
        self._usage_label.set_label(f'{_format_gb(used)} of {_format_gb(total)} used')

        segments = [
            (hex_color, (num_bytes / total) if total else 0)
            for (_label, hex_color), num_bytes in zip(CATEGORY_COLORS, info['categories'])
        ]
        self._bar.set_segments(segments)
        return GLib.SOURCE_REMOVE
