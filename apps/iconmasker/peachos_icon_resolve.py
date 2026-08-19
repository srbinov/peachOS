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

# Absolute-path icon dirs peachOS itself hand-picks -- pixel-perfect real Apple assets,
# never touched at all, regardless of fill ratio (Mail sits at 81% canvas fill with real
# margin baked in, Numbers/Notes fill edge-to-edge at ~100% -- both are correct as shipped).
OWN_DIRS = [
    ICONS_ROOT / 'icloud-for-linux',
    ICONS_ROOT / 'peachos',
]

# MacTahoe is curated art (never needs re-masking/re-coloring/re-shaping) but its own SVGs
# run close to full-bleed (~90-95% fill) rather than our 81% Apple-matched target, which reads
# visibly larger/more prominent than everything else at the same allocated dock/grid pixel
# size. These get a lighter touch: proportional shrink + transparent margin only, no masking.
THEME_DIRS = [
    ICONS_ROOT / 'MacTahoe',
    ICONS_ROOT / 'MacTahoe-dark',
    ICONS_ROOT / 'MacTahoe-light',
]

CATEGORY_OWN = 'own'
CATEGORY_THEME = 'theme'


def _categorize(path):
    for d in OWN_DIRS:
        if d in path.parents:
            return CATEGORY_OWN
    for d in THEME_DIRS:
        if d in path.parents:
            return CATEGORY_THEME
    return None


def resolve_icon(icon_value):
    """Returns (Path, category) or (None, None). category is CATEGORY_OWN
    (peachOS's own hand-picked absolute-path icons, never touched at all),
    CATEGORY_THEME (MacTahoe -- shape/color is already right, only checked
    for oversized fill and padded if needed), or None (uncurated, goes
    through the full masking pipeline)."""
    if not icon_value:
        return None, None

    if icon_value.startswith('/'):
        p = Path(icon_value)
        if not p.exists():
            return None, None
        return p, _categorize(p.resolve())

    for theme in ICON_THEME_SEARCH:
        theme_dir = ICONS_ROOT / theme
        if not theme_dir.is_dir():
            continue
        for size_dir in ICON_SIZE_DIRS:
            for ctx in ICON_CONTEXT_DIRS:
                for ext in ('svg', 'png'):
                    # Icon Theme Spec doesn't mandate one nesting order, and themes vary in
                    # practice: hicolor is <size>/<context> (e.g. scalable/apps/), but MacTahoe
                    # is <context>/<size> (e.g. apps/scalable/) -- try both, since guessing
                    # wrong here means silently never finding MacTahoe's own icons at all.
                    for p in (theme_dir / size_dir / ctx / f'{icon_value}.{ext}',
                              theme_dir / ctx / size_dir / f'{icon_value}.{ext}'):
                        if p.exists():
                            return p, _categorize(p)

    for ext in ('svg', 'png', 'xpm'):
        p = PIXMAPS_DIR / f'{icon_value}.{ext}'
        if p.exists():
            return p, None

    return None, None
