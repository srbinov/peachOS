import os
import shutil
import time

import cairo
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

# The lock screen (both the in-session one and GDM's own login screen) has to
# read this from a system-readable path -- GDM's greeter runs as a totally
# separate system account with no visibility into this user's own home
# directory, so this can't live under ~/.local/share the way the desktop's
# own custom wallpapers do. A single fixed filename (always re-encoded to
# this exact path+format on apply) rather than one-per-photo, so both
# extensions/peachos-lockscreen@local.dev's background override and any
# future UI here only ever need to check one known location.
LOCK_WALLPAPER_STAGING_PATH = os.path.expanduser('~/.local/share/peachos/wallpapers/lockscreen-staged.jpg')
SYSTEM_LOCK_WALLPAPER_PATH = '/usr/share/backgrounds/peachos/custom-lockscreen.jpg'

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

        self._build_ui()
        self._populate_dynamic_wallpapers()
        self._populate_custom_photos()
        self._refresh_selection()
        self._refresh_lockscreen_preview()

        self._bg_settings.connect('changed::picture-uri', lambda *_a: (self._refresh_selection(), self._refresh_lockscreen_preview()))
        self._bg_settings.connect('changed::picture-uri-dark', lambda *_a: (self._refresh_selection(), self._refresh_lockscreen_preview()))
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

        self.append(Gtk.Label(label='Lock Screen Wallpaper', xalign=0, css_classes=['heading']))
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
            label='Used for both the lock screen and the login screen -- these are always the same.',
            xalign=0, wrap=True, css_classes=['dim-label', 'caption'],
        )
        lock_info_card.append(lock_desc)

        lock_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=6)
        self._lockscreen_choose_btn = Gtk.Button(label='Choose Photo…')
        self._lockscreen_choose_btn.connect('clicked', self._on_lockscreen_choose_clicked)
        lock_buttons.append(self._lockscreen_choose_btn)
        self._lockscreen_reset_btn = Gtk.Button(label='Use Desktop Wallpaper')
        self._lockscreen_reset_btn.connect('clicked', self._on_lockscreen_reset_clicked)
        lock_buttons.append(self._lockscreen_reset_btn)
        lock_info_card.append(lock_buttons)

        self._lockscreen_error_label = Gtk.Label(wrap=True, xalign=0, css_classes=['error'], visible=False)
        lock_info_card.append(self._lockscreen_error_label)

        lock_row.append(lock_info_card)
        self.append(lock_row)

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

    # ---- Lock screen wallpaper (separate from the desktop one) -----------
    #
    # SYSTEM_LOCK_WALLPAPER_PATH is root-owned (0644, under /usr/share) --
    # GDM's greeter can't read anywhere under this user's own home directory
    # at all, so writing/removing it needs a real privilege escalation, not
    # a workaround. pkexec is the standard, correct tool for "one specific
    # native action needs root, prompted right here" -- this isn't shelling
    # out to another *app* (see feedback_settings_no_external_launch.md),
    # it's a single install(1)/rm(1) invocation the same way printers_page.py
    # already goes through lpadmin directly instead of a GUI tool.

    def _refresh_lockscreen_preview(self):
        if os.path.isfile(SYSTEM_LOCK_WALLPAPER_PATH):
            self._lockscreen_preview_picture.set_paintable(
                _load_scaled_texture(SYSTEM_LOCK_WALLPAPER_PATH, 160, 90))
            self._lockscreen_status_label.set_label('Custom lock screen wallpaper set')
            self._lockscreen_reset_btn.set_sensitive(True)
        else:
            # "Same as Desktop Wallpaper" should actually show the desktop
            # wallpaper, not an empty box -- .scheme-photo has no
            # background-color of its own, so with no paintable at all this
            # previously rendered as a blank void instead of a placeholder.
            desktop_path = self._current_path('picture-uri') or self._current_path('picture-uri-dark')
            if desktop_path and os.path.isfile(desktop_path):
                self._lockscreen_preview_picture.set_paintable(
                    _load_scaled_texture(desktop_path, 160, 90))
            else:
                self._lockscreen_preview_picture.set_paintable(None)
            self._lockscreen_status_label.set_label('Same as Desktop Wallpaper')
            self._lockscreen_reset_btn.set_sensitive(False)

    def _set_lockscreen_busy(self, busy: bool):
        self._lockscreen_choose_btn.set_sensitive(not busy)
        self._lockscreen_reset_btn.set_sensitive(not busy and os.path.isfile(SYSTEM_LOCK_WALLPAPER_PATH))
        if busy:
            self._lockscreen_status_label.set_label('Applying…')
        else:
            # Not "restore the previous text" (that'd get stuck on
            # "Applying..." if the pkexec call itself failed) -- just
            # re-derive the label from whatever's actually on disk, which is
            # correct whether the operation just succeeded or failed.
            self._refresh_lockscreen_preview()

    def _on_lockscreen_choose_clicked(self, _btn):
        dialog = Gtk.FileDialog(title='Choose a Lock Screen Photo')
        image_filter = Gtk.FileFilter(name='Images')
        image_filter.add_mime_type('image/jpeg')
        image_filter.add_mime_type('image/png')
        image_filter.add_mime_type('image/webp')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_lockscreen_file_chosen)

    def _on_lockscreen_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        src_path = gfile.get_path() if gfile else None
        if not src_path:
            return

        self._lockscreen_error_label.set_visible(False)

        # Re-encoded to one fixed format/path regardless of source type --
        # the two consumers (peachos-lockscreen@local.dev's JS, and this
        # page's own preview) only ever need to handle one known format.
        os.makedirs(os.path.dirname(LOCK_WALLPAPER_STAGING_PATH), exist_ok=True)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(src_path)
            if pixbuf.get_has_alpha():
                # JPEG has no alpha channel at all -- glycin's JPEG encoder
                # errors out outright on an RGBA8 source (a transparent PNG,
                # for example) rather than silently dropping it.
                # composite_color_simple() was tried first but only zeroes
                # out the alpha *values* -- the pixbuf it returns still
                # reports get_has_alpha() True, so the encoder still rejects
                # it. Painting onto a Cairo FORMAT_RGB24 surface (genuinely
                # no alpha channel in the pixel format) and reading the
                # result back is the same alpha-flatten technique
                # avatar_picker.py already uses elsewhere in this app.
                w, h = pixbuf.get_width(), pixbuf.get_height()
                surface = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
                ctx = cairo.Context(surface)
                ctx.set_source_rgb(1, 1, 1)
                ctx.paint()
                Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
                ctx.paint()
                surface.flush()
                pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)
            pixbuf.savev(LOCK_WALLPAPER_STAGING_PATH, 'jpeg', ['quality'], ['92'])
        except GLib.Error as e:
            self._lockscreen_error_label.set_label(f'Could not use that image: {e.message}')
            self._lockscreen_error_label.set_visible(True)
            return

        self._set_lockscreen_busy(True)
        proc = Gio.Subprocess.new(
            ['pkexec', 'install', '-Dm644', LOCK_WALLPAPER_STAGING_PATH, SYSTEM_LOCK_WALLPAPER_PATH],
            Gio.SubprocessFlags.NONE,
        )
        proc.wait_async(None, self._on_lockscreen_apply_done)

    def _on_lockscreen_apply_done(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error as e:
            self._set_lockscreen_busy(False)
            self._lockscreen_error_label.set_label(f'Could not apply the wallpaper: {e.message}')
            self._lockscreen_error_label.set_visible(True)
            return

        self._set_lockscreen_busy(False)
        if proc.get_exit_status() != 0:
            self._lockscreen_error_label.set_label(
                'Could not apply the wallpaper (the password prompt may have been cancelled).')
            self._lockscreen_error_label.set_visible(True)

    def _on_lockscreen_reset_clicked(self, _btn):
        self._lockscreen_error_label.set_visible(False)
        self._set_lockscreen_busy(True)
        proc = Gio.Subprocess.new(['pkexec', 'rm', '-f', SYSTEM_LOCK_WALLPAPER_PATH], Gio.SubprocessFlags.NONE)
        proc.wait_async(None, self._on_lockscreen_reset_done)

    def _on_lockscreen_reset_done(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error as e:
            self._set_lockscreen_busy(False)
            self._lockscreen_error_label.set_label(f'Could not reset the wallpaper: {e.message}')
            self._lockscreen_error_label.set_visible(True)
            return

        self._set_lockscreen_busy(False)
        if proc.get_exit_status() != 0:
            self._lockscreen_error_label.set_label(
                'Could not reset the wallpaper (the password prompt may have been cancelled).')
            self._lockscreen_error_label.set_visible(True)
