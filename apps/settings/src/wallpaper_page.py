import os
import shutil
import time

import gi

gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from appearance_page import ACCENT_HEX
from widgets import load_extension_settings

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
CUSTOM_WALLPAPER_THUMB_DIR = os.path.join(CUSTOM_WALLPAPER_DIR, '.thumbnails')

# Perfect Lock Screen (extensions/perfect-lockscreen@chris) owns the actual lock/login
# screen rendering -- this page only ever reads/writes its GSettings, never touches GDM
# state directly (that's install-gdm-dlc.sh's job, run once by provision.sh; see its own
# README). GDM's login screen always mirrors the current *desktop* wallpaper regardless of
# what's picked here (the extension exports that itself on lock) -- these settings only
# affect the in-session lock screen (Super+L).
LOCKSCREEN_EXTENSION_UUID = 'perfect-lockscreen@chris'
LOCKSCREEN_SCHEMA_ID = 'org.gnome.shell.extensions.perfect-lockscreen'

# Same real-install-vs-repo-checkout fallback as SYSTEM_WALLPAPER_DIR/REPO_WALLPAPER_DIR
# above.
SYSTEM_LOCKSCREEN_VIDEO_DIR = '/usr/share/peachos/lockscreen'
REPO_LOCKSCREEN_VIDEO_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'assets', 'lockscreen',
))
CUSTOM_LOCKSCREEN_WALLPAPER_DIR = os.path.expanduser('~/.local/share/peachos/wallpapers/lockscreen-custom')
CUSTOM_LOCKSCREEN_WALLPAPER_THUMB_DIR = os.path.join(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, '.thumbnails')

# (display name, preview image, video filename) -- pushed to the icons repo as
# LIVE_LOGIN_SCREEN_WALLPAPER.mp4; the preview is a pre-extracted poster frame
# (ffmpeg -frames:v 1) rather than decoded live, matching every other wallpaper
# preview on this page.
LIVE_WALLPAPERS = [
    ('Ocean Waves', 'live-lockscreen.jpg', 'live-lockscreen.mp4'),
    ('Forest Canopy', 'forest-canopy.jpg', 'forest-canopy.mp4'),
    ('Mountain Mist', 'mountain-mist.jpg', 'mountain-mist.mp4'),
    ('Rolling Hills', 'rolling-hills.jpg', 'rolling-hills.mp4'),
]

# (display name, preview image, light wallpaper filename, dark wallpaper filename)
# peachOS Nectar first per the reference layout / the distro's own default.
#
# preview_file used to point at the full-resolution wallpaper itself (two of these were a
# full-5K SVG with an embedded raster image, 9-11MB each) -- decoded fresh on every single
# Settings app wallpaper-page load, the dominant cost behind "takes forever to load" /
# "Settings app not responding". Regenerated as small real JPEGs (see
# provision/wallpaper-previews/gen_wallpaper_previews.py), matching the pattern
# LIVE_WALLPAPERS already used correctly.
DYNAMIC_WALLPAPERS = [
    ('peachOS Nectar', 'peachOS_Nectar.jpg', 'peachOS_Nectar_Light.jpg', 'peachOS_Nectar_Dark.jpg'),
    ('macOS Tahoe', 'macOS_Tahoe.jpg', 'macOS_Tahoe_Light.jpg', 'macOS_Tahoe_Dark.jpg'),
    ('macOS Sonoma', 'macOS_Sonoma.jpg', 'macOS_Sonoma_Light.jpg', 'macOS_Sonoma_Dark.jpg'),
    ('macOS Sequoia', 'macOS_Sequoia.jpg', 'macOS_Sequoia_Light.jpg', 'macOS_Sequoia_Dark.jpg'),
    ('macOS Golden Gate', 'macOS_GoldenGate.jpg', 'macOS_GoldenGate_Light.png', 'macOS_GoldenGate_Dark.png'),
]

# (display name, filename) -- single static images (not light/dark pairs),
# pushed to the icons repo alongside the Tahoe dynamic wallpaper. Live under
# a presets/ subdirectory of the same wallpaper dir so provisioning can keep
# treating "the wallpaper dir" as one thing.
PRESET_WALLPAPERS = [
    ('Nectar Island', 'nectar_island.jpg'),
    ('Tahoe Beach (Dawn)', 'tahoe_beach_dawn.jpg'),
    ('Tahoe Beach (Day)', 'tahoe_beach_day.jpg'),
    ('Tahoe Beach (Dusk)', 'tahoe_beach_dusk.jpg'),
    ('Tahoe Beach (Night)', 'tahoe_beach_night.jpg'),
    ('Apple Event 2021', 'apple_event_2021.jpg'),
    ('Big Sur Coastline', 'bigsur_coastline.jpg'),
    ('Big Sur Layers', 'bigsur_layers.jpg'),
    ('Big Sur Sunrise', 'bigsur_sunrise.jpg'),
    ('Catalina Island', 'catalina_island.jpg'),
    ('Leopard', 'leopard.jpg'),
    ('Lion Andromeda', 'lion_andromeda.jpg'),
    ('Lion Beach', 'lion_beach.jpg'),
    ('Lion Tranquil', 'lion_tranquil.jpg'),
    ('Lion Twilight', 'lion_twilight.jpg'),
    ('Mavericks Tide', 'mavericks_tide.jpg'),
    ('Mojave Fusion', 'mojave_fusion.png'),
    ('Mojave Desert', 'mojave_desert.jpg'),
    ('Mojave Starry Night', 'mojave_starry.jpg'),
    ('Mountain Lion', 'mountain_lion_1.jpg'),
    ('Mountain Lion 2', 'mountain_lion_2.jpg'),
    ('Mountain Lion 3', 'mountain_lion_3.jpg'),
    ('Mountain Lion 4', 'mountain_lion_4.jpg'),
    ('Mountain Lion 5', 'mountain_lion_5.jpg'),
    ('Monterey (Black)', 'monterey_black.jpg'),
    ('Monterey (Blue)', 'monterey_blue.jpg'),
    ('Monterey (Green)', 'monterey_green.jpg'),
    ('Monterey (Orange)', 'monterey_orange.jpg'),
    ('Monterey WWDC', 'monterey_wwdc.jpg'),
    ('Sequoia Forest', 'sequoia_forest.jpg'),
    ('Sierra Peak', 'sierra_peak.jpg'),
    ('Sonoma', 'sonoma.jpg'),
]


def _wallpaper_dir() -> str:
    if os.path.isfile(os.path.join(SYSTEM_WALLPAPER_DIR, 'peachOS_Nectar_Light.jpg')):
        return SYSTEM_WALLPAPER_DIR
    return REPO_WALLPAPER_DIR


def _preset_dir() -> str:
    return os.path.join(_wallpaper_dir(), 'presets')


def _lockscreen_video_dir() -> str:
    if os.path.isfile(os.path.join(SYSTEM_LOCKSCREEN_VIDEO_DIR, LIVE_WALLPAPERS[0][2])):
        return SYSTEM_LOCKSCREEN_VIDEO_DIR
    return REPO_LOCKSCREEN_VIDEO_DIR


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


def _ensure_thumbnail(source_path: str, thumb_dir: str, size=(224, 126)) -> str:
    """Generate+cache a small preview once per user-added photo, alongside the same fix
    applied to preset/dynamic wallpapers above -- without this, every custom "Your Photos"
    tile re-decoded the full original (a phone photo can easily be 4000x3000+) on every
    single page load. Returns source_path unchanged if generation fails, so a tile still
    renders (just slower) rather than going blank."""
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, os.path.basename(source_path) + '.jpg')
    if os.path.isfile(thumb_path) and os.path.getmtime(thumb_path) >= os.path.getmtime(source_path):
        return thumb_path
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(source_path, size[0], size[1], False)
        pixbuf.savev(thumb_path, 'jpeg', ['quality'], ['85'])
    except GLib.Error:
        return source_path
    return thumb_path


def _apply_css(widget: Gtk.Widget, css: str):
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode())
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class WallpaperTile(Gtk.Box):
    """Same shape and selection-ring mechanism as appearance_page.py's
    SchemeOption -- plain Box + manual 'selected' CSS class, not a
    ToggleButton, for the same reasons documented there."""

    TILE_SIZE = (112, 63)

    def __init__(self, label: str, preview_path: str, on_click, on_right_click=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        self._selected = False

        self.ring_box = Gtk.Box(css_classes=['scheme-ring'])
        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        # Without an explicit size floor, GTK's layout solver can squeeze this
        # Box to 0x0 once total sibling content pushes the (non-scrolling)
        # page past its available width -- the exact bug already root-caused
        # and fixed for appearance_page.py's SchemeOption/IconStyleOption,
        # which this tile never got the same protection for.
        photo_wrap.set_size_request(*self.TILE_SIZE)
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        picture = _load_scaled_picture(preview_path, *self.TILE_SIZE)
        photo_wrap.append(picture)
        self.ring_box.append(photo_wrap)
        self.append(self.ring_box)

        self.append(Gtk.Label(label=label, css_classes=['caption'], max_width_chars=16, ellipsize=3))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click(self))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')

        if on_right_click is not None:
            right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            right_click.connect('released', lambda _g, _n, x, y: on_right_click(self, x, y))
            self.add_controller(right_click)

    def set_selected(self, selected: bool, ring_hex: str):
        self._selected = selected
        if selected:
            self.ring_box.add_css_class('selected')
            _apply_css(self.ring_box, f'box.selected {{ border-color: {ring_hex}; }}')
        else:
            self.ring_box.remove_css_class('selected')


class AddPhotoTile(Gtk.Box):
    """Deliberately does NOT reuse WallpaperTile's ring_box (a second
    .scheme-ring instance triggered a live-rendering glitch on the
    *existing* wallpaper tiles in this VM, even though this tile's own
    code was otherwise correct -- see peachos_ring_inset_gotcha memory).
    Matches its footprint to a ring-wrapped photo (112x63 + 5px margin
    each side, mirroring .scheme-ring's 3px padding + 2px border) with
    plain margins on the existing box instead -- no new widget, no new
    CSS class instance, nothing that touches WallpaperTile at all."""

    TILE_SIZE = WallpaperTile.TILE_SIZE

    def __init__(self, on_click):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        w, h = self.TILE_SIZE
        box = Gtk.Box(
            css_classes=['scheme-photo', 'add-photo-tile'],
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            width_request=w, height_request=h,
            margin_start=5, margin_end=5, margin_top=5, margin_bottom=5,
        )
        plus_icon = Gtk.Image.new_from_icon_name('list-add-symbolic')
        plus_icon.set_halign(Gtk.Align.CENTER)
        plus_icon.set_valign(Gtk.Align.CENTER)
        plus_icon.set_hexpand(True)
        plus_icon.set_vexpand(True)
        box.append(plus_icon)
        self.append(box)
        self.append(Gtk.Label(label='Add Photo…', css_classes=['caption']))

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
        self._lockscreen_tiles = []  # [(tile, kind, path), ...] kind: 'video' | 'still'

        self._lockscreen_settings = load_extension_settings(LOCKSCREEN_EXTENSION_UUID, LOCKSCREEN_SCHEMA_ID)

        self._build_ui()
        self._populate_dynamic_wallpapers()
        self._populate_preset_wallpapers()
        self._populate_custom_photos()
        self._populate_live_wallpapers()
        self._populate_lockscreen_custom_photos()
        self._refresh_selection()
        self._refresh_lockscreen_selection()

        self._bg_settings.connect('changed::picture-uri', lambda *_a: (self._refresh_selection(), self._refresh_lockscreen_selection()))
        self._bg_settings.connect('changed::picture-uri-dark', lambda *_a: (self._refresh_selection(), self._refresh_lockscreen_selection()))
        self._interface_settings.connect('changed::accent-color', lambda *_a: (self._refresh_selection(), self._refresh_lockscreen_selection()))
        if self._lockscreen_settings:
            self._lockscreen_settings.connect('changed::background-source', lambda *_a: self._refresh_lockscreen_selection())
            self._lockscreen_settings.connect('changed::background-video-path', lambda *_a: self._refresh_lockscreen_selection())
            self._lockscreen_settings.connect('changed::lockscreen-wallpaper-path', lambda *_a: self._refresh_lockscreen_selection())

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

        self.append(Gtk.Separator())

        self.append(Gtk.Label(label='Lock Screen', xalign=0, css_classes=['heading']))

        if not self._lockscreen_settings:
            self.append(Gtk.Label(
                label='Perfect Lock Screen is not installed, so the lock screen wallpaper can’t be changed here.',
                wrap=True, css_classes=['dim-label'], xalign=0,
            ))
        else:
            lock_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

            lock_preview_wrap = Gtk.Box(css_classes=['scheme-photo'], width_request=160, height_request=90)
            lock_preview_wrap.set_overflow(Gtk.Overflow.HIDDEN)
            self._lockscreen_preview_picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
            lock_preview_wrap.append(self._lockscreen_preview_picture)
            lock_row.append(lock_preview_wrap)

            lock_info_card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, css_classes=['wifi-card'], hexpand=True, spacing=4,
                margin_start=14, margin_end=14, margin_top=10, margin_bottom=10,
            )
            self._lockscreen_status_label = Gtk.Label(label='—', xalign=0)
            lock_info_card.append(self._lockscreen_status_label)
            lock_desc = Gtk.Label(
                label='Used when you lock your screen (Super+L). The login screen always '
                      'shows your desktop wallpaper, separately from this.',
                xalign=0, wrap=True, css_classes=['dim-label', 'caption'],
            )
            lock_info_card.append(lock_desc)

            self._lockscreen_reset_btn = Gtk.Button(label='Use Desktop Wallpaper', margin_top=6, halign=Gtk.Align.START)
            self._lockscreen_reset_btn.connect('clicked', self._on_lockscreen_use_desktop_clicked)
            lock_info_card.append(self._lockscreen_reset_btn)

            lock_row.append(lock_info_card)
            self.append(lock_row)

            self.append(Gtk.Label(label='Live Wallpapers', xalign=0, css_classes=['heading']))
            self._live_flow = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
                max_children_per_line=8, min_children_per_line=1,
            )
            self.append(self._live_flow)

            self.append(Gtk.Label(label='Your Photos', xalign=0, css_classes=['heading']))
            self._lockscreen_photos_flow = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
                max_children_per_line=8, min_children_per_line=1,
            )
            self._lockscreen_photos_flow.append(AddPhotoTile(self._on_lockscreen_add_photo_clicked))
            self.append(self._lockscreen_photos_flow)

        self.append(Gtk.Separator())

        self.append(Gtk.Label(label='Dynamic Wallpapers', xalign=0, css_classes=['heading']))
        self._dynamic_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
            max_children_per_line=8, min_children_per_line=1,
        )
        self.append(self._dynamic_flow)

        self.append(Gtk.Label(label='Preset Wallpapers', xalign=0, css_classes=['heading']))
        self._preset_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            row_spacing=14, column_spacing=14, halign=Gtk.Align.START, valign=Gtk.Align.START,
            max_children_per_line=8, min_children_per_line=1,
        )
        self.append(self._preset_flow)

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

    # ---- Preset wallpapers -------------------------------------------------

    def _populate_preset_wallpapers(self):
        preset_dir = _preset_dir()
        for name, filename in PRESET_WALLPAPERS:
            path = os.path.join(preset_dir, filename)
            if not os.path.isfile(path):
                continue
            # Tile preview uses the small pre-generated thumbnail (see
            # provision/wallpaper-previews/gen_wallpaper_previews.py) -- decoding these
            # full-resolution source wallpapers directly, once per tile, on every page
            # load was the dominant cost behind "takes forever to load"/"not responding".
            # _tiles still stores the real full-res `path` -- that's what actually gets
            # applied as the wallpaper via _set_wallpaper, unaffected by this.
            preview_path = os.path.join(PREVIEW_DIR, f'preset_{os.path.splitext(filename)[0]}.jpg')
            if not os.path.isfile(preview_path):
                preview_path = path  # fall back to the full-res source rather than a blank tile
            # Single static image -- light and dark are the same file, same
            # as a custom photo tile below.
            tile = WallpaperTile(name, preview_path, self._on_preset_tile_clicked)
            self._preset_flow.append(tile)
            self._tiles.append((tile, path, path))

    def _on_preset_tile_clicked(self, tile):
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
        preview_path = _ensure_thumbnail(path, CUSTOM_WALLPAPER_THUMB_DIR)
        tile = WallpaperTile(name, preview_path, self._on_custom_tile_clicked, on_right_click=self._on_custom_tile_right_click)
        # Insert before the trailing "Add Photo..." tile.
        insert_at = self._photos_flow.observe_children().get_n_items() - 1
        self._photos_flow.insert(tile, insert_at)
        self._tiles.append((tile, path, path))

    def _on_custom_tile_clicked(self, tile):
        for t, light_path, dark_path in self._tiles:
            if t is tile:
                self._set_wallpaper(light_path, dark_path)
                return

    def _on_custom_tile_right_click(self, tile, _x, _y):
        path = None
        for t, light_path, _dark_path in self._tiles:
            if t is tile:
                path = light_path
                break
        if path is None:
            return

        dialog = Adw.AlertDialog(
            heading='Remove Photo?',
            body=f'“{os.path.splitext(os.path.basename(path))[0]}” will be removed from Your Photos.',
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Remove')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.connect('response', self._on_remove_custom_photo_response, tile, path)
        dialog.present(self.get_root())

    def _on_remove_custom_photo_response(self, _dialog, response, tile, path):
        if response != 'remove':
            return

        is_active = self._current_path('picture-uri') == path and self._current_path('picture-uri-dark') == path

        self._photos_flow.remove(tile)
        self._tiles = [(t, l, d) for t, l, d in self._tiles if t is not tile]
        try:
            os.remove(path)
        except OSError:
            pass
        try:
            os.remove(os.path.join(CUSTOM_WALLPAPER_THUMB_DIR, os.path.basename(path) + '.jpg'))
        except OSError:
            pass

        if is_active and self._tiles:
            _fallback_tile, fallback_light, fallback_dark = self._tiles[0]
            self._set_wallpaper(fallback_light, fallback_dark)
        else:
            self._refresh_selection()

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
                preset_dir = _preset_dir()
                for name_, filename in PRESET_WALLPAPERS:
                    if display_path == os.path.join(preset_dir, filename):
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

    # ---- Lock screen wallpaper (separate from the desktop one) -----------
    #
    # All of this reads/writes extensions/perfect-lockscreen@chris's own GSettings
    # (org.gnome.shell.extensions.perfect-lockscreen) -- no pkexec/root needed here,
    # unlike the desktop wallpaper's GDM/login-screen picker above: that one writes a
    # root-owned file GDM's separate system account has to read, this one is a normal
    # per-user setting the extension itself (running in this same user's session) reads
    # directly. GDM's own login screen still always mirrors the desktop wallpaper,
    # regardless of what's picked here -- see LOCKSCREEN_EXTENSION_UUID's docstring.

    def _populate_live_wallpapers(self):
        video_dir = _lockscreen_video_dir()
        for name, preview_file, video_file in LIVE_WALLPAPERS:
            preview_path = os.path.join(PREVIEW_DIR, preview_file)
            video_path = os.path.join(video_dir, video_file)
            if not (os.path.isfile(preview_path) and os.path.isfile(video_path)):
                continue
            tile = WallpaperTile(name, preview_path, self._on_live_tile_clicked)
            self._live_flow.append(tile)
            self._lockscreen_tiles.append((tile, 'video', video_path))

    def _on_live_tile_clicked(self, tile):
        for t, kind, path in self._lockscreen_tiles:
            if t is tile and kind == 'video':
                self._lockscreen_settings.set_string('background-video-path', path)
                self._lockscreen_settings.set_string('background-source', 'video')
                return

    def _populate_lockscreen_custom_photos(self):
        os.makedirs(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, exist_ok=True)
        for filename in sorted(os.listdir(CUSTOM_LOCKSCREEN_WALLPAPER_DIR)):
            path = os.path.join(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, filename)
            if not os.path.isfile(path):
                continue
            self._add_lockscreen_custom_photo_tile(path)

    def _add_lockscreen_custom_photo_tile(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        preview_path = _ensure_thumbnail(path, CUSTOM_LOCKSCREEN_WALLPAPER_THUMB_DIR)
        tile = WallpaperTile(
            name, preview_path, self._on_lockscreen_custom_tile_clicked,
            on_right_click=self._on_lockscreen_custom_tile_right_click,
        )
        # Insert before the trailing "Add Photo..." tile.
        insert_at = self._lockscreen_photos_flow.observe_children().get_n_items() - 1
        self._lockscreen_photos_flow.insert(tile, insert_at)
        self._lockscreen_tiles.append((tile, 'still', path))

    def _on_lockscreen_custom_tile_clicked(self, tile):
        for t, kind, path in self._lockscreen_tiles:
            if t is tile and kind == 'still':
                self._lockscreen_settings.set_string('lockscreen-wallpaper-path', path)
                self._lockscreen_settings.set_boolean('lockscreen-wallpaper-enable', True)
                self._lockscreen_settings.set_string('background-source', 'still')
                return

    def _on_lockscreen_custom_tile_right_click(self, tile, _x, _y):
        path = None
        for t, kind, p in self._lockscreen_tiles:
            if t is tile and kind == 'still':
                path = p
                break
        if path is None:
            return

        dialog = Adw.AlertDialog(
            heading='Remove Photo?',
            body=f'“{os.path.splitext(os.path.basename(path))[0]}” will be removed from Your Photos.',
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Remove')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.connect('response', self._on_remove_lockscreen_custom_photo_response, tile, path)
        dialog.present(self.get_root())

    def _on_remove_lockscreen_custom_photo_response(self, _dialog, response, tile, path):
        if response != 'remove':
            return

        is_active = (
            self._lockscreen_settings.get_string('background-source') == 'still'
            and self._lockscreen_settings.get_string('lockscreen-wallpaper-path') == path
        )

        self._lockscreen_photos_flow.remove(tile)
        self._lockscreen_tiles = [(t, k, p) for t, k, p in self._lockscreen_tiles if t is not tile]
        try:
            os.remove(path)
        except OSError:
            pass
        try:
            os.remove(os.path.join(CUSTOM_LOCKSCREEN_WALLPAPER_THUMB_DIR, os.path.basename(path) + '.jpg'))
        except OSError:
            pass

        if is_active:
            # Deleted photo was in use -- fall back to the desktop wallpaper rather
            # than leaving background-source pointed at a file that's now gone.
            self._lockscreen_settings.set_string('background-source', 'desktop')
        else:
            self._refresh_lockscreen_selection()

    def _on_lockscreen_add_photo_clicked(self):
        dialog = Gtk.FileDialog(title='Add Photo')
        image_filter = Gtk.FileFilter(name='Images')
        image_filter.add_mime_type('image/jpeg')
        image_filter.add_mime_type('image/png')
        image_filter.add_mime_type('image/webp')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_lockscreen_photo_file_dialog_done)

    def _on_lockscreen_photo_file_dialog_done(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        if not gfile:
            return

        src_path = gfile.get_path()
        if not src_path:
            return

        os.makedirs(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, exist_ok=True)
        basename = os.path.basename(src_path)
        dest_path = os.path.join(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, basename)
        if os.path.exists(dest_path):
            root, ext = os.path.splitext(basename)
            dest_path = os.path.join(CUSTOM_LOCKSCREEN_WALLPAPER_DIR, f'{root}-{int(time.time())}{ext}')
        shutil.copyfile(src_path, dest_path)

        self._add_lockscreen_custom_photo_tile(dest_path)
        self._lockscreen_settings.set_string('lockscreen-wallpaper-path', dest_path)
        self._lockscreen_settings.set_boolean('lockscreen-wallpaper-enable', True)
        self._lockscreen_settings.set_string('background-source', 'still')

    def _on_lockscreen_use_desktop_clicked(self, _btn):
        self._lockscreen_settings.set_string('background-source', 'desktop')

    def _refresh_lockscreen_selection(self):
        if not self._lockscreen_settings:
            return

        source = self._lockscreen_settings.get_string('background-source')
        video_path = self._lockscreen_settings.get_string('background-video-path')
        still_path = self._lockscreen_settings.get_string('lockscreen-wallpaper-path')

        for tile, kind, path in self._lockscreen_tiles:
            is_selected = (
                (source == 'video' and kind == 'video' and path == video_path)
                or (source == 'still' and kind == 'still' and path == still_path)
            )
            ring_hex = ACCENT_HEX.get(self._interface_settings.get_string('accent-color'), '#0461BE')
            tile.set_selected(is_selected, ring_hex)

        self._lockscreen_reset_btn.set_sensitive(source != 'desktop')

        if source == 'video' and os.path.isfile(video_path):
            name = next((n for n, _p, v in LIVE_WALLPAPERS
                         if os.path.join(_lockscreen_video_dir(), v) == video_path), None)
            preview_file = next((p for n, p, v in LIVE_WALLPAPERS
                                  if os.path.join(_lockscreen_video_dir(), v) == video_path), None)
            preview_path = os.path.join(PREVIEW_DIR, preview_file) if preview_file else video_path
            if os.path.isfile(preview_path):
                self._lockscreen_preview_picture.set_paintable(_load_scaled_texture(preview_path, 160, 90))
            self._lockscreen_status_label.set_label(name or os.path.splitext(os.path.basename(video_path))[0])
        elif source == 'still' and os.path.isfile(still_path):
            self._lockscreen_preview_picture.set_paintable(_load_scaled_texture(still_path, 160, 90))
            self._lockscreen_status_label.set_label(os.path.splitext(os.path.basename(still_path))[0])
        else:
            # Desktop-synced (or a stale path that no longer exists) -- show the
            # actual desktop wallpaper rather than an empty box, same reasoning as
            # the login-screen preview above.
            desktop_path = self._current_path('picture-uri') or self._current_path('picture-uri-dark')
            if desktop_path and os.path.isfile(desktop_path):
                self._lockscreen_preview_picture.set_paintable(_load_scaled_texture(desktop_path, 160, 90))
            else:
                self._lockscreen_preview_picture.set_paintable(None)
            self._lockscreen_status_label.set_label('Same as Desktop Wallpaper')
