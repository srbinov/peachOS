import os
import shutil
import time

import gi

gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from appearance_page import ACCENT_HEX

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')
PREVIEW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'wallpaper-previews')

# Real install target (see provision.sh -- wallpapers get copied here
# system-wide so a fresh account has them with zero setup). This dev VM
# has no passwordless sudo to populate that path directly, so fall back
# to the repo's own assets/wallpapers/ checkout, which is exactly what
# provision.sh copies FROM. On a real installed system the first path
# always wins.
SYSTEM_WALLPAPER_DIR = '/usr/share/backgrounds/peachos'
REPO_WALLPAPER_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'assets', 'wallpapers',
))
CUSTOM_WALLPAPER_DIR = os.path.expanduser('~/.local/share/peachos/wallpapers/custom')

# (display name, preview image, light wallpaper filename, dark wallpaper filename)
# peachOS Nectar first per the reference layout / the distro's own default.
DYNAMIC_WALLPAPERS = [
    ('peachOS Nectar', 'peachOS_Nectar.svg', 'peachOS_Nectar_Light.jpg', 'peachOS_Nectar_Dark.png'),
    ('macOS Sonoma', 'macOS_Sonoma.svg', 'macOS_Sonoma_Light.jpg', 'macOS_Sonoma_Dark.jpg'),
    ('macOS Sequoia', 'macOS_Sequoia.svg', 'macOS_Sequoia_Light.jpg', 'macOS_Sequoia_Dark.jpg'),
    ('macOS Golden Gate', 'macOS_GoldenGate.png', 'macOS_GoldenGate_Light.png', 'macOS_GoldenGate_Dark.png'),
]


def _wallpaper_dir() -> str:
    if os.path.isfile(os.path.join(SYSTEM_WALLPAPER_DIR, 'peachOS_Nectar_Light.jpg')):
        return SYSTEM_WALLPAPER_DIR
    return REPO_WALLPAPER_DIR


def _load_scaled_texture(path: str, width: int, height: int) -> Gdk.Texture:
    """Pre-rasterize to the exact target pixel size -- see appearance_page.py's
    identical helper for why (Gtk.Picture's natural size otherwise comes
    from the multi-megapixel source image, not the requested display size)."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, False)
    return Gdk.Texture.new_for_pixbuf(pixbuf)


def _load_scaled_picture(path: str, width: int, height: int) -> Gtk.Picture:
    picture = Gtk.Picture.new_for_paintable(_load_scaled_texture(path, width, height))
    picture.set_content_fit(Gtk.ContentFit.COVER)
    return picture


def _apply_css(widget: Gtk.Widget, css: str):
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode())
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class WallpaperTile(Gtk.Box):
    """Same shape and selection-ring mechanism as appearance_page.py's
    SchemeOption -- plain Box + manual 'selected' CSS class, not a
    ToggleButton, for the same reasons documented there."""

    TILE_SIZE = (112, 63)

    def __init__(self, label: str, preview_path: str, on_click):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
            halign=Gtk.Align.CENTER, width_request=self.TILE_SIZE[0],
        )
        self._selected = False

        self.ring_box = Gtk.Box(css_classes=['scheme-ring'])
        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        picture = _load_scaled_picture(preview_path, *self.TILE_SIZE)
        photo_wrap.append(picture)
        self.ring_box.append(photo_wrap)
        self.append(self.ring_box)

        self.append(Gtk.Label(label=label, css_classes=['caption'], max_width_chars=14, ellipsize=3))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click(self))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')

    def set_selected(self, selected: bool, ring_hex: str):
        self._selected = selected
        if selected:
            self.ring_box.add_css_class('selected')
            _apply_css(self.ring_box, f'box.selected {{ border-color: {ring_hex}; }}')
        else:
            self.ring_box.remove_css_class('selected')


class AddPhotoTile(Gtk.Box):
    """Same ring_box/photo_wrap structure as WallpaperTile (just with a
    permanently-empty, unselectable ring) so its visible box lines up
    exactly with every wallpaper tile above it -- without the ring_box's
    padding this box's edges sat ~5px further out than the photo inside
    a WallpaperTile's ring, reading as misaligned between the two rows."""

    TILE_SIZE = WallpaperTile.TILE_SIZE

    def __init__(self, on_click):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
            halign=Gtk.Align.CENTER, width_request=self.TILE_SIZE[0],
        )
        w, h = self.TILE_SIZE
        ring_box = Gtk.Box(css_classes=['scheme-ring'])
        box = Gtk.Box(
            css_classes=['scheme-photo', 'add-photo-tile'],
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            width_request=w, height_request=h,
        )
        box.append(Gtk.Image.new_from_icon_name('list-add-symbolic'))
        ring_box.append(box)
        self.append(ring_box)
        self.append(Gtk.Label(label='Add Photo…', css_classes=['caption'], max_width_chars=14, ellipsize=3))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click())
        self.add_controller(click)
        self.set_cursor_from_name('pointer')


class WallpaperPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._bg_settings = Gio.Settings.new('org.gnome.desktop.background')
        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._tiles = []  # [(tile, light_path, dark_path), ...]

        self._build_ui()
        self._populate_dynamic_wallpapers()
        self._populate_custom_photos()
        self._refresh_selection()

        self._bg_settings.connect('changed::picture-uri', lambda *_a: self._refresh_selection())
        self._bg_settings.connect('changed::picture-uri-dark', lambda *_a: self._refresh_selection())
        self._interface_settings.connect('changed::accent-color', lambda *_a: self._refresh_selection())

    # ---- UI construction -----------------------------------------------

    def _build_ui(self):
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        preview_wrap = Gtk.Box(css_classes=['scheme-photo'], width_request=320, height_request=180)
        preview_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        self._preview_picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        preview_wrap.append(self._preview_picture)
        top_row.append(preview_wrap)

        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'], hexpand=True)
        self._name_label = Gtk.Label(
            label='—', xalign=0, css_classes=['title-4'],
            margin_start=14, margin_end=14, margin_top=12, margin_bottom=10,
        )
        info_card.append(self._name_label)
        info_card.append(Gtk.Separator())

        spaces_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            margin_start=14, margin_end=14, margin_top=10, margin_bottom=12,
        )
        spaces_row.append(Gtk.Label(label='Show on all Spaces', xalign=0, hexpand=True))
        # Inert per the ask -- not wired to a real Mutter/workspace
        # setting yet, just present and defaulting on like the reference.
        self._spaces_switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=True)
        spaces_row.append(self._spaces_switch)
        info_card.append(spaces_row)
        top_row.append(info_card)

        self.append(top_row)

        # Also inert for now -- no screensaver or clock-appearance
        # settings wired up yet.
        buttons_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons_row.append(Gtk.Button(label='Screen Saver…'))
        buttons_row.append(Gtk.Button(label='Clock Appearance…'))
        self.append(buttons_row)

        self.append(Gtk.Separator())

        self.append(Gtk.Label(label='Dynamic Wallpapers', xalign=0, css_classes=['heading']))
        self._dynamic_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
            max_children_per_line=8, min_children_per_line=1,
        )
        self.append(self._dynamic_flow)

        self.append(Gtk.Label(label='Your Photos', xalign=0, css_classes=['heading']))
        self._photos_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
            max_children_per_line=8, min_children_per_line=1,
        )
        self._photos_flow.append(AddPhotoTile(self._on_add_photo_clicked))
        self.append(self._photos_flow)

    # ---- Dynamic wallpapers ---------------------------------------------

    def _populate_dynamic_wallpapers(self):
        wallpaper_dir = _wallpaper_dir()
        for name, preview_file, light_file, dark_file in DYNAMIC_WALLPAPERS:
            preview_path = os.path.join(PREVIEW_DIR, preview_file)
            light_path = os.path.join(wallpaper_dir, light_file)
            dark_path = os.path.join(wallpaper_dir, dark_file)
            if not (os.path.isfile(preview_path) and os.path.isfile(light_path) and os.path.isfile(dark_path)):
                continue
            tile = WallpaperTile(name, preview_path, self._on_dynamic_tile_clicked)
            self._dynamic_flow.append(tile)
            self._tiles.append((tile, light_path, dark_path))

    def _on_dynamic_tile_clicked(self, tile):
        for t, light_path, dark_path in self._tiles:
            if t is tile:
                self._set_wallpaper(light_path, dark_path)
                return

    # ---- Custom photos ---------------------------------------------------

    def _populate_custom_photos(self):
        os.makedirs(CUSTOM_WALLPAPER_DIR, exist_ok=True)
        for filename in sorted(os.listdir(CUSTOM_WALLPAPER_DIR)):
            path = os.path.join(CUSTOM_WALLPAPER_DIR, filename)
            if not os.path.isfile(path):
                continue
            self._add_custom_photo_tile(path)

    def _add_custom_photo_tile(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        tile = WallpaperTile(name, path, self._on_custom_tile_clicked)
        # Insert before the trailing "Add Photo..." tile.
        insert_at = self._photos_flow.observe_children().get_n_items() - 1
        self._photos_flow.insert(tile, insert_at)
        self._tiles.append((tile, path, path))

    def _on_custom_tile_clicked(self, tile):
        for t, light_path, dark_path in self._tiles:
            if t is tile:
                self._set_wallpaper(light_path, dark_path)
                return

    def _on_add_photo_clicked(self):
        dialog = Gtk.FileDialog(title='Add Photo')
        image_filter = Gtk.FileFilter(name='Images')
        image_filter.add_mime_type('image/jpeg')
        image_filter.add_mime_type('image/png')
        image_filter.add_mime_type('image/webp')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)

        root = self.get_root()
        dialog.open(root, None, self._on_file_dialog_done)

    def _on_file_dialog_done(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        if not gfile:
            return

        src_path = gfile.get_path()
        if not src_path:
            return

        os.makedirs(CUSTOM_WALLPAPER_DIR, exist_ok=True)
        basename = os.path.basename(src_path)
        dest_path = os.path.join(CUSTOM_WALLPAPER_DIR, basename)
        if os.path.exists(dest_path):
            root, ext = os.path.splitext(basename)
            dest_path = os.path.join(CUSTOM_WALLPAPER_DIR, f'{root}-{int(time.time())}{ext}')
        shutil.copyfile(src_path, dest_path)

        self._add_custom_photo_tile(dest_path)
        self._set_wallpaper(dest_path, dest_path)

    # ---- Applying + reflecting the real wallpaper -------------------------

    def _set_wallpaper(self, light_path: str, dark_path: str):
        self._bg_settings.set_string('picture-uri', GLib.filename_to_uri(light_path, None))
        self._bg_settings.set_string('picture-uri-dark', GLib.filename_to_uri(dark_path, None))

    def _refresh_selection(self):
        current_light = self._current_path('picture-uri')
        current_dark = self._current_path('picture-uri-dark')

        ring_hex = ACCENT_HEX.get(self._interface_settings.get_string('accent-color'), '#0461BE')
        for tile, light_path, dark_path in self._tiles:
            is_selected = (light_path == current_light and dark_path == current_dark)
            tile.set_selected(is_selected, ring_hex)

        display_path = current_light or current_dark
        if display_path and os.path.isfile(display_path):
            self._preview_picture.set_paintable(_load_scaled_texture(display_path, 320, 180))
            name = None
            wallpaper_dir = _wallpaper_dir()
            for name_, _preview_file, light_file, dark_file in DYNAMIC_WALLPAPERS:
                if display_path in (os.path.join(wallpaper_dir, light_file), os.path.join(wallpaper_dir, dark_file)):
                    name = name_
                    break
            if not name:
                name = os.path.splitext(os.path.basename(display_path))[0]
            self._name_label.set_label(name)
        else:
            self._name_label.set_label('No wallpaper set')

    def _current_path(self, key: str):
        uri = self._bg_settings.get_string(key)
        if not uri:
            return None
        try:
            path, _ = GLib.filename_from_uri(uri)
            return path
        except GLib.Error:
            return None
