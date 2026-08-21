"""Categorized emoji picker (Add Photo / Pick Emoji flow from Contact
Details) -- tabs matching the standard iOS/macOS emoji-picker categories.
Emoji source: macOS_Tahoe_SYSICONS/apple-emoji (3700+ SVGs, no bundled
category metadata -- classified once by scratchpad/classify_emoji.py into
data/emoji_manifest.json, which this just loads).

Rendering all ~2500 Smileys-category SVGs at once would be a lot of GdkPixbuf
decodes on this app's software (cairo) renderer, so each category's grid is
built lazily on first visit; image_utils.load_contained_texture() also caches
every decoded texture at module scope, so a category (or the whole picker,
reopened) only ever pays that decode cost once per process.
"""
import json
import os

from gi.repository import Adw, GLib, GObject, Gtk

from image_utils import load_contained_texture

_EMOJI_DIR = "/home/user/macOS_Tahoe_SYSICONS/apple-emoji"
_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                               "emoji_manifest.json")

# One representative emoji file per category, used as that category's tab
# icon -- avoids needing a separate curated icon set for the tab bar.
_CATEGORY_TAB_EMOJI = {
    "Smileys & People": "how-grinning-face.svg",
    "Animals & Nature": "how-dog-face.svg",
    "Food & Drink": "how-pizza.svg",
    "Activity": "how-basketball.svg",
    "Travel & Places": "how-airplane.svg",
    "Objects": "how-light-bulb.svg",
    "Symbols": "how-red-heart.svg",
    "Flags": "how-chequered-flag.svg",
}

_TILE_SIZE = 44
_GRID_SEARCH_LIMIT = 300

_manifest_cache: dict | None = None


def _load_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    try:
        with open(_MANIFEST_PATH) as f:
            _manifest_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _manifest_cache = {"categories": [], "emoji": []}
    return _manifest_cache


def make_emoji_picture(file_name: str, size: int) -> Gtk.Widget:
    """Same crop-then-CONTAIN technique as chat_list_view.make_color_avatar --
    content_fit=COVER scaling up to whatever a permissive parent allocates
    was the exact bug that made avatar photos balloon to fill a whole pane
    (measured and fixed there); emoji tiles need the same guard."""
    path = os.path.join(_EMOJI_DIR, file_name)
    wrapper = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=False, vexpand=False)
    wrapper.set_size_request(size, size)
    texture = load_contained_texture(path, size)
    picture = Gtk.Picture.new_for_paintable(texture) if texture is not None else Gtk.Picture()
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_size_request(size, size)
    picture.set_hexpand(False)
    picture.set_vexpand(False)
    picture.set_halign(Gtk.Align.CENTER)
    picture.set_valign(Gtk.Align.CENTER)
    wrapper.append(picture)
    return wrapper


class EmojiPickerDialog(Adw.Window):
    """Adw.Window (not a plain Gtk.Window) specifically because a plain
    Gtk.Window on this system's theme got its own auto-generated titlebar
    *in addition to* the Adw.HeaderBar added as content below -- confirmed
    live: two stacked "Choose an Emoji" bars, two close buttons. Adw.Window
    is the libadwaita-native single-titlebar top-level window and doesn't
    have that problem."""

    __gtype_name__ = "EmojiPickerDialog"

    __gsignals__ = {
        "emoji-picked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # full file path
    }

    def __init__(self, parent: Gtk.Window):
        super().__init__(transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_title("Choose an Emoji")
        self.set_default_size(460, 560)

        self._manifest = _load_manifest()
        self._by_category: dict[str, list[dict]] = {cat: [] for cat in self._manifest["categories"]}
        for entry in self._manifest["emoji"]:
            self._by_category.setdefault(entry["category"], []).append(entry)

        self._built_categories: set[str] = set()

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        # No title text (matches the compact, label-less picker this mirrors)
        # -- still a real Adw.HeaderBar so the window keeps the same
        # traffic-light close button as every other peachOS window, rather
        # than fiddling with window decoration.
        header = Adw.HeaderBar(show_title=False)
        toolbar.add_top_bar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.add_css_class("emoji-picker-panel")
        root.set_margin_top(4)
        root.set_margin_start(10)
        root.set_margin_end(10)
        root.set_margin_bottom(10)
        toolbar.set_content(root)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Search Emoji")
        self._search_entry.add_css_class("emoji-picker-search")
        self._search_entry.connect("search-changed", self._on_search_changed)
        root.append(self._search_entry)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        root.append(self._stack)

        # Category switcher as a bottom icon strip (matches the real
        # emoji-picker layout) rather than a top tab row.
        self._tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.CENTER)
        self._tab_bar.add_css_class("emoji-picker-tabs")
        root.append(self._tab_bar)

        self._search_page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._search_flow = self._make_flow_box()
        self._search_page.set_child(self._search_flow)
        self._stack.add_named(self._search_page, "search")

        self._tab_buttons: dict[str, Gtk.ToggleButton] = {}
        self._first_category: str | None = None
        first_button = None
        for category in self._manifest["categories"]:
            btn = Gtk.ToggleButton()
            btn.add_css_class("flat")
            btn.add_css_class("circular")
            icon_file = _CATEGORY_TAB_EMOJI.get(category)
            btn.set_child(make_emoji_picture(icon_file, 22) if icon_file else Gtk.Label(label=category[:2]))
            btn.set_tooltip_text(category)
            if first_button is None:
                first_button = btn
                self._first_category = category
            else:
                btn.set_group(first_button)
            btn.connect("toggled", self._on_tab_toggled, category)
            self._tab_bar.append(btn)
            self._tab_buttons[category] = btn

            page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            self._stack.add_named(page, category)

        if first_button is not None:
            first_button.set_active(True)
            self._stack.set_visible_child_name(self._first_category)
            # Deferred rather than built synchronously here: decoding an
            # entire category (Smileys & People alone is ~2500 SVGs) before
            # the window's first paint is what made opening the picker feel
            # slow (confirmed live). Presenting first and populating on the
            # next idle slice lets the window/search bar/tabs show up
            # immediately instead of blocking on that decode.
            GLib.idle_add(self._build_category, self._first_category)

    def _make_flow_box(self) -> Gtk.FlowBox:
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                            row_spacing=6, column_spacing=6, valign=Gtk.Align.START)
        flow.connect("child-activated", self._on_emoji_activated)
        return flow

    def _populate_flow(self, flow: Gtk.FlowBox, entries: list[dict]):
        child = flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            flow.remove(child)
            child = nxt
        for entry in entries:
            tile = make_emoji_picture(entry["file"], _TILE_SIZE)
            tile.emoji_file = entry["file"]
            tile.set_tooltip_text(entry["label"])
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
        self._search_entry.set_text("")
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

        matches = [e for e in self._manifest["emoji"] if query in e["name"]][:_GRID_SEARCH_LIMIT]
        self._populate_flow(self._search_flow, matches)
        self._stack.set_visible_child_name("search")

    def _on_emoji_activated(self, _flow, child):
        tile = child.get_child()
        file_name = getattr(tile, "emoji_file", None)
        if file_name:
            self.emit("emoji-picked", os.path.join(_EMOJI_DIR, file_name))
        self.close()
