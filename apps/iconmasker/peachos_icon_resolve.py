"""Resolve a .desktop file's Icon= value to an actual image file on disk.

Pure filesystem lookup (no Gtk.IconTheme/Gdk.Display) so this works from a
headless root systemd service with no session/display available. Follows
the standard freedesktop Icon Theme Spec directory layout.
"""
from pathlib import Path

ICON_THEME_SEARCH = ['MacTahoe', 'MacTahoe-dark', 'hicolor']
ICON_SIZE_DIRS = ['scalable', '512x512', '256x256', '128x128', '96x96', '72x72', '64x64', '48x48', '32x32']
ICON_CONTEXT_DIRS = ['apps', 'mimetypes', 'categories', 'places', 'devices', 'status']
PIXMAPS_DIR = Path('/usr/share/pixmaps')
ICONS_ROOT = Path('/usr/share/icons')


def resolve_icon(icon_value):
    """Returns (Path, is_curated) or (None, False). is_curated means the
    icon was found inside a MacTahoe theme dir -- already hand-made for
    this look, never needs masking."""
    if not icon_value:
        return None, False

    if icon_value.startswith('/'):
        p = Path(icon_value)
        return (p, False) if p.exists() else (None, False)

    for theme in ICON_THEME_SEARCH:
        theme_dir = ICONS_ROOT / theme
        if not theme_dir.is_dir():
            continue
        for size_dir in ICON_SIZE_DIRS:
            for ctx in ICON_CONTEXT_DIRS:
                for ext in ('svg', 'png'):
                    p = theme_dir / size_dir / ctx / f'{icon_value}.{ext}'
                    if p.exists():
                        return p, theme.startswith('MacTahoe')

    for ext in ('svg', 'png', 'xpm'):
        p = PIXMAPS_DIR / f'{icon_value}.{ext}'
        if p.exists():
            return p, False

    return None, False
