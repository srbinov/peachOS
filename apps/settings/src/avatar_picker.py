"""Profile-picture picking for Users & Groups: a photo (center-cropped to a
square) or an emoji on a solid background color the user picks -- rendered
to a real PNG file that gets handed to AccountsService's SetIconFile (see
users_page.py's _EditUserDialog).

Emoji source is the macOS_Tahoe_SYSICONS/apple-emoji set, classified into
categories by data/emoji_manifest.json (~3700 SVGs pre-sorted) -- reused
here as shared read-only data, same as this app's own data/icons/.
"""
import json
import os

import cairo
import gi

gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, GObject, Gtk

# provision.sh sparse-checks the apple-emoji set out to this system path; the
# ~/macOS_Tahoe_SYSICONS checkout is the fallback for running from a dev tree.
_SYSTEM_EMOJI_DIR = '/usr/share/peachos/emoji'
_DEV_EMOJI_DIR = os.path.expanduser('~/macOS_Tahoe_SYSICONS/apple-emoji')
EMOJI_DIR = _SYSTEM_EMOJI_DIR if os.path.isdir(_SYSTEM_EMOJI_DIR) else _DEV_EMOJI_DIR

EMOJI_MANIFEST_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'emoji_manifest.json'))

AVATAR_SIZE = 512
EMOJI_FILL_FRACTION = 0.62  # emoji reads as a badge on the color, not a full-bleed fill

_CATEGORY_TAB_EMOJI = {
    'Smileys & People': 'how-grinning-face.svg',
    'Animals & Nature': 'how-dog-face.svg',
    'Food & Drink': 'how-pizza.svg',
    'Activity': 'how-basketball.svg',
    'Travel & Places': 'how-airplane.svg',
    'Objects': 'how-light-bulb.svg',
    'Symbols': 'how-red-heart.svg',
    'Flags': 'how-chequered-flag.svg',
}

_TILE_SIZE = 40
_GRID_SEARCH_LIMIT = 300

_manifest_cache: dict | None = None
_texture_cache: dict[tuple[str, int], Gdk.Texture | None] = {}


def _load_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    try:
        with open(EMOJI_MANIFEST_PATH) as f:
            _manifest_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _manifest_cache = {'categories': [], 'emoji': []}
    return _manifest_cache


def _load_contained_texture(path: str, size: int) -> Gdk.Texture | None:
    key = (path, size)
    if key in _texture_cache:
        return _texture_cache[key]
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, False)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    except GLib.Error:
        texture = None
    _texture_cache[key] = texture
    return texture


def _make_emoji_picture(file_name: str, size: int) -> Gtk.Widget:
    path = os.path.join(EMOJI_DIR, file_name)
    wrapper = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=False, vexpand=False)
    wrapper.set_size_request(size, size)
    texture = _load_contained_texture(path, size)
    picture = Gtk.Picture.new_for_paintable(texture) if texture is not None else Gtk.Picture()
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_size_request(size, size)
    picture.set_hexpand(False)
    picture.set_vexpand(False)
    picture.set_halign(Gtk.Align.CENTER)
    picture.set_valign(Gtk.Align.CENTER)
    wrapper.append(picture)
    return wrapper


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def render_emoji_avatar(emoji_path: str, hex_color: str, out_path: str, size: int = AVATAR_SIZE):
    """Solid-color square background + the emoji centered on top, at
    EMOJI_FILL_FRACTION of the canvas -- same "badge on a color" look
    bluebubbles-native uses for emoji contact avatars."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    r, g, b = _hex_to_rgb(hex_color)
    ctx.set_source_rgb(r, g, b)
    ctx.paint()

    emoji_size = round(size * EMOJI_FILL_FRACTION)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(emoji_path, emoji_size, emoji_size, True)
    x = (size - pixbuf.get_width()) / 2
    y = (size - pixbuf.get_height()) / 2
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, x, y)
    ctx.paint()

    surface.write_to_png(out_path)


def render_photo_avatar(src_path: str, out_path: str, size: int = AVATAR_SIZE):
    """Center-crops to a square (no letterboxing) then scales to `size`."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(src_path)
    w, h = pixbuf.get_width(), pixbuf.get_height()
    crop = min(w, h)
    x, y = (w - crop) // 2, (h - crop) // 2
    cropped = pixbuf.new_subpixbuf(x, y, crop, crop)
    scaled = cropped.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
    scaled.savev(out_path, 'png', [], [])


class EmojiPickerDialog(Adw.Window):
    """Same shape as bluebubbles-native's own emoji picker (bottom category
    strip, search, lazy-built grids) -- see that file's docstring for why
    this layout instead of top tabs. A separate implementation (not an
    import of that app's module) so the two apps' UI code stays
    independent; the underlying emoji data is shared, see module docstring."""

    __gtype_name__ = 'SettingsEmojiPickerDialog'

    __gsignals__ = {
        'emoji-picked': (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # full file path
    }

    def __init__(self, parent: Gtk.Window):
        super().__init__(transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_title('Choose an Emoji')
        self.set_default_size(400, 480)

        self._manifest = _load_manifest()
        self._by_category: dict[str, list[dict]] = {cat: [] for cat in self._manifest['categories']}
        for entry in self._manifest['emoji']:
            self._by_category.setdefault(entry['category'], []).append(entry)
        self._built_categories: set[str] = set()

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)
        toolbar.add_top_bar(Adw.HeaderBar(show_title=False))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.add_css_class('emoji-picker-panel')
        root.set_margin_top(4)
        root.set_margin_start(10)
        root.set_margin_end(10)
        root.set_margin_bottom(10)
        toolbar.set_content(root)

        self._search_entry = Gtk.SearchEntry(placeholder_text='Search Emoji')
        self._search_entry.add_css_class('emoji-picker-search')
        self._search_entry.connect('search-changed', self._on_search_changed)
        root.append(self._search_entry)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        root.append(self._stack)

        self._search_page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._search_flow = self._make_flow_box()
        self._search_page.set_child(self._search_flow)
        self._stack.add_named(self._search_page, 'search')

        self._tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.CENTER)
        self._tab_bar.add_css_class('emoji-picker-tabs')
        root.append(self._tab_bar)

        self._tab_buttons: dict[str, Gtk.ToggleButton] = {}
        self._first_category: str | None = None
        first_button = None
        for category in self._manifest['categories']:
            btn = Gtk.ToggleButton(css_classes=['flat', 'circular'])
            icon_file = _CATEGORY_TAB_EMOJI.get(category)
            btn.set_child(_make_emoji_picture(icon_file, 22) if icon_file else Gtk.Label(label=category[:2]))
            btn.set_tooltip_text(category)
            if first_button is None:
                first_button = btn
                self._first_category = category
            else:
                btn.set_group(first_button)
            btn.connect('toggled', self._on_tab_toggled, category)
            self._tab_bar.append(btn)
            self._tab_buttons[category] = btn

            page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            self._stack.add_named(page, category)

        if first_button is not None:
            first_button.set_active(True)
            self._stack.set_visible_child_name(self._first_category)
            GLib.idle_add(self._build_category, self._first_category)

    def _make_flow_box(self) -> Gtk.FlowBox:
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                            row_spacing=6, column_spacing=6, valign=Gtk.Align.START)
        flow.connect('child-activated', self._on_emoji_activated)
        return flow

    def _populate_flow(self, flow: Gtk.FlowBox, entries: list[dict]):
        child = flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            flow.remove(child)
            child = nxt
        for entry in entries:
            tile = _make_emoji_picture(entry['file'], _TILE_SIZE)
            tile.emoji_file = entry['file']
            tile.set_tooltip_text(entry['label'])
            flow.append(tile)

    def _build_category(self, category: str):
        if category in self._built_categories:
            return GLib.SOURCE_REMOVE
        self._built_categories.add(category)
        flow = self._make_flow_box()
        page = self._stack.get_child_by_name(category)
        page.set_child(flow)
        self._populate_flow(flow, self._by_category.get(category, []))
        return GLib.SOURCE_REMOVE

    def _on_tab_toggled(self, button: Gtk.ToggleButton, category: str):
        if not button.get_active():
            return
        self._search_entry.set_text('')
        self._stack.set_visible_child_name(category)
        self._build_category(category)

    def _on_search_changed(self, entry: Gtk.SearchEntry):
        query = entry.get_text().strip().lower()
        if not query:
            for category, btn in self._tab_buttons.items():
                if btn.get_active():
                    self._stack.set_visible_child_name(category)
                    return
            return
        matches = [e for e in self._manifest['emoji'] if query in e['name']][:_GRID_SEARCH_LIMIT]
        self._populate_flow(self._search_flow, matches)
        self._stack.set_visible_child_name('search')

    def _on_emoji_activated(self, _flow, child):
        tile = child.get_child()
        file_name = getattr(tile, 'emoji_file', None)
        if file_name:
            self.emit('emoji-picked', os.path.join(EMOJI_DIR, file_name))
        self.close()
