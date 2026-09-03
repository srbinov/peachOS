"""Live preview for the Desktop & Dock tab's Liquid Glass slider -- a miniature dock
(rounded glass plate + a few app icons) floating on a horizontal sliver of the user's
currently-equipped wallpaper, restyled as the slider moves.

Mirrors macOS-Dock-2026-peachOS/liquidGlass.js's interpolation exactly (same LIGHT/DARK
recipes, same solid targets, same linear blend) so the preview shows the real math the
dock extension itself uses at that intensity, not an approximation.
"""
import os

import gi

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gio, Gtk
from PIL import Image

# --- glass math (mirror of liquidGlass.js) -------------------------------------------

_SOLID_LIGHT = (255, 255, 255)
_SOLID_DARK = (28, 28, 30)

# liquidGlass.js's LIGHT / DARK recipes, (r, g, b, a).
_RECIPE_LIGHT = {
    'fill': (255, 255, 255, 0.12),
    'gs': (255, 255, 255, 0.28),
    'ge': (255, 255, 255, 0.08),
    'border': (255, 255, 255, 0.42),
    'inset': (255, 255, 255, 0.5),
}
_RECIPE_DARK = {
    'fill': (0, 0, 0, 0.32),
    'gs': (255, 255, 255, 0.16),
    'ge': (0, 0, 0, 0.38),
    'border': (255, 255, 255, 0.32),
    'inset': (255, 255, 255, 0.45),
}


def _lerp(a, b, t):
    return a + (b - a) * t


def _interp(rgba, is_dark, t, solid_alpha=1.0):
    solid = _SOLID_DARK if is_dark else _SOLID_LIGHT
    r, g, b, a = rgba
    return (
        round(_lerp(solid[0], r, t)),
        round(_lerp(solid[1], g, t)),
        round(_lerp(solid[2], b, t)),
        _lerp(solid_alpha, a, t),
    )


def _rgba(c):
    r, g, b, a = c
    return f'rgba({r}, {g}, {b}, {round(a, 3)})'


# --- wallpaper sliver ---------------------------------------------------------------

BACKDROP_SIZE = (900, 120)  # wide + short band, like the Appearance-tab preview


def _cover_crop_scale(path, width, height):
    im = Image.open(path)
    # draft() lets the JPEG decoder skip straight to a near-target resolution instead of
    # decoding the full (often 4-6K) wallpaper then downscaling -- the slow part.
    try:
        im.draft('RGB', (width * 2, height * 2))
    except (AttributeError, OSError):
        pass
    im = im.convert('RGB')
    src_ratio = im.width / im.height
    tile_ratio = width / height
    if src_ratio > tile_ratio:
        new_w = int(im.height * tile_ratio)
        x0 = (im.width - new_w) // 2
        im = im.crop((x0, 0, x0 + new_w, im.height))
    else:
        new_h = int(im.width / tile_ratio)
        y0 = (im.height - new_h) // 2
        im = im.crop((0, y0, im.width, y0 + new_h))
    return im.resize((width, height), Image.LANCZOS)


def wallpaper_sliver_texture(path, width=BACKDROP_SIZE[0], height=BACKDROP_SIZE[1]):
    """A Gdk.Texture holding a centre band of the wallpaper, or None if unreadable."""
    if not path:
        return None
    try:
        im = _cover_crop_scale(path, width, height)
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            im.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, im.width, im.height, im.width * 3)
        return Gdk.Texture.new_for_pixbuf(pixbuf)
    except (GLib.Error, OSError):
        return None


def current_wallpaper_path(is_dark):
    key = 'picture-uri-dark' if is_dark else 'picture-uri'
    uri = Gio.Settings.new('org.gnome.desktop.background').get_string(key)
    if not uri:
        return None
    try:
        path, _ = GLib.filename_from_uri(uri)
        return path if os.path.isfile(path) else None
    except GLib.Error:
        return None


# --- the widget -------------------------------------------------------------------

# A handful of recognisable apps for the sample dock. ThemedIcon falls through the list
# until one resolves, so this stays populated whatever's actually installed.
_SAMPLE_APPS = [
    ['org.gnome.Nautilus', 'system-file-manager', 'folder'],
    ['firefox', 'firefox_firefox', 'web-browser'],
    ['org.gnome.Calculator', 'accessories-calculator', 'x-office-spreadsheet'],
    ['org.gnome.TextEditor', 'org.gnome.gedit', 'text-editor'],
    ['org.gnome.Settings', 'preferences-system', 'emblem-system'],
]


class DockGlassPreview(Gtk.Overlay):
    def __init__(self):
        super().__init__(css_classes=['dock-glass-preview'])
        self.set_size_request(-1, 132)
        self.set_hexpand(True)
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self._backdrop = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self._backdrop.set_can_target(False)
        self._backdrop.set_size_request(0, 132)
        self.set_child(self._backdrop)

        self._plate = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            css_classes=['dock-glass-preview-plate'],
        )
        self._plate.set_margin_top(12)
        self._plate.set_margin_bottom(12)
        for names in _SAMPLE_APPS:
            img = Gtk.Image.new_from_gicon(Gio.ThemedIcon.new_from_names(names))
            img.set_pixel_size(44)
            self._plate.append(img)
        self.add_overlay(self._plate)

        self._provider = Gtk.CssProvider()
        for w in (self, self._plate):
            w.get_style_context().add_provider(self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def set_backdrop_texture(self, texture):
        self._backdrop.set_paintable(texture)

    def update(self, intensity, is_dark):
        t = max(0.0, min(100.0, intensity)) / 100.0
        recipe = _RECIPE_DARK if is_dark else _RECIPE_LIGHT
        fill = _interp(recipe['fill'], is_dark, t)
        gs = _interp(recipe['gs'], is_dark, t)
        ge = _interp(recipe['ge'], is_dark, t)
        border = _interp(recipe['border'], is_dark, t, solid_alpha=0.18)
        inset = _interp(recipe['inset'], is_dark, t, solid_alpha=0.0)
        fallback_tint = '#2a2340' if is_dark else '#efe4d6'

        css = f"""
        .dock-glass-preview {{
            background-color: {fallback_tint};
            border-radius: 14px;
        }}
        .dock-glass-preview-plate {{
            background-color: {_rgba(fill)};
            background-image: linear-gradient(to bottom, {_rgba(gs)}, {_rgba(ge)});
            border: 1px solid {_rgba(border)};
            border-radius: 22px;
            box-shadow: inset 0 1px 0 {_rgba(inset)};
            padding: 8px 12px;
        }}
        """
        self._provider.load_from_data(css.encode())
