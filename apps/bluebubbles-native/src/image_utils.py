"""Shared helpers for loading an avatar image (real photo or emoji SVG) as a
GdkPixbuf/Gdk.Texture for circular avatar tiles.

Real photos and emoji get different treatment (explicit user request): a
photo fills the whole circle edge-to-edge; an emoji renders smaller (~70% of
the circle) with the surrounding gray background visible, like a badge --
matching how a Memoji/emoji "photo" actually looks on a real iOS/macOS
contact. Callers pick the emoji vs. photo path themselves (chat_list_view.py
treats a ".svg" avatar_path as an emoji, anything else as a photo).

Both functions solve the same underlying Gtk.Picture problem, confirmed by
direct measurement rather than guessed: content_fit=COVER scales UP to fill
*whatever* space its parent allocates, and Gtk.HeaderBar's title_widget slot
allocates far more than a widget's own size_request/hexpand=False asks for
(measured: a 22px request got a 274px allocation there). content_fit=CONTAIN
never scales past the paintable's own intrinsic size, which is what actually
keeps a pre-scaled avatar small even inside that oversized allocation -- so
both helpers here pre-decode to the exact final pixel size themselves rather
than trusting Gtk.Picture's own scaling, and callers must keep using CONTAIN,
never COVER.
"""
import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib

# Real photos: crop-zoom to fill the circle completely, no letterboxing.
_COVER_ZOOM = 1.15

# Keyed by (path, size, mode) -- avoids re-decoding the same SVG/photo from
# disk on every avatar render and every time the emoji picker is reopened (a
# fresh GdkPixbuf decode of a full emoji category, ~2500 files for Smileys
# alone, is the actual slow part of "opening" the picker; caching is what
# makes the second open -- and every re-render of an already-picked avatar --
# instant).
_texture_cache: dict[tuple[str, int, str], Gdk.Texture | None] = {}


def _decode(path: str, size: int) -> GdkPixbuf.Pixbuf:
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, False)


def load_cover_texture(path: str, size: int) -> Gdk.Texture | None:
    """For real photos: decode oversized and crop the center square out of
    that, so the photo fills the circle completely (matches a real iOS/macOS
    contact photo -- cropped, never letterboxed)."""
    key = (path, size, "cover")
    if key in _texture_cache:
        return _texture_cache[key]
    try:
        zoomed = round(size * _COVER_ZOOM)
        pixbuf = _decode(path, zoomed)
        offset = (zoomed - size) // 2
        cropped = pixbuf.new_subpixbuf(offset, offset, size, size)
        texture = Gdk.Texture.new_for_pixbuf(cropped)
    except GLib.GError:
        texture = None
    _texture_cache[key] = texture
    return texture


def load_bounded_texture(path: str, max_size: int) -> Gdk.Texture | None:
    """For message-bubble attachment thumbnails: scale to fit within
    max_size x max_size while preserving the source's real aspect ratio.
    Unlike the two decoders above (both intentionally force a square, since
    avatars/emoji tiles are always circular), an arbitrary photo squished to
    square here would visibly distort it -- new_from_file_at_size (not
    _at_scale) is GdkPixbuf's own aspect-preserving "fit within a box"
    scaler."""
    key = (path, max_size, "bounded")
    if key in _texture_cache:
        return _texture_cache[key]
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, max_size, max_size)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    except GLib.GError:
        texture = None
    _texture_cache[key] = texture
    return texture


def load_contained_texture(path: str, size: int) -> Gdk.Texture | None:
    """For emoji: decode straight to the target size with no cropping, so the
    whole glyph is always visible (never clipped) -- callers render this at a
    *smaller* size than the surrounding circle (chat_list_view.py: ~70% of
    it) so the emoji reads as a badge on the circle rather than filling it,
    since forcing an emoji to fill the frame is what clipped real content
    (confirmed live: faces/flags cut off) before this was split from the
    photo cover-crop path."""
    key = (path, size, "contained")
    if key in _texture_cache:
        return _texture_cache[key]
    try:
        texture = Gdk.Texture.new_for_pixbuf(_decode(path, size))
    except GLib.GError:
        texture = None
    _texture_cache[key] = texture
    return texture
