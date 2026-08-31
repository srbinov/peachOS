import os

import gi

gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from PIL import Image

from widgets import DropdownRow, make_hero_header

# GNOME Tweaks' Fonts section, ported over -- same org.gnome.desktop.interface
# keys Tweaks itself reads/writes, just presented in peachOS's own Appearance
# tab instead of a separate app (gap found comparing against Tweaks directly;
# peachOS's custom Settings never falls back to a stock app for anything, see
# feedback_settings_no_external_launch).
FONT_HINT_STYLES = [('None', 'none'), ('Slight', 'slight'), ('Medium', 'medium'), ('Full', 'full')]
FONT_ANTIALIASING = [('None', 'none'), ('Grayscale', 'grayscale'), ('Subpixel (RGBA)', 'rgba')]

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')
ICON_APPEARANCE_SCRIPT = '/usr/lib/peachos/iconmasker/peachos-icon-appearance'
PLYMOUTH_SYNC_SCRIPT = '/usr/lib/peachos/plymouth/peachos-plymouth-sync'

DOCK_ORDER_GUARD_BUS_NAME = 'org.peachos.DockOrderGuard'
DOCK_ORDER_GUARD_OBJECT_PATH = '/org/peachos/DockOrderGuard'


def _call_dock_order_guard(method_name: str):
    """Fire-and-forget call into lib/dockOrderGuard.js (see that file for why this has to
    round-trip into the Shell process). Silently does nothing if the extension isn't loaded
    (e.g. running this page outside a real peachOS session) -- this is a nice-to-have
    ordering guard, not something worth surfacing an error dialog over."""
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            DOCK_ORDER_GUARD_BUS_NAME, DOCK_ORDER_GUARD_OBJECT_PATH, DOCK_ORDER_GUARD_BUS_NAME, None,
        )
        proxy.call_sync(method_name, None, Gio.DBusCallFlags.NONE, 500, None)
    except GLib.Error:
        pass


def _load_scaled_picture(path: str, width: int, height: int) -> Gtk.Picture:
    """Pre-rasterize to the *exact* target pixel size rather than asking
    Gtk.Picture to display a full-res source (3840x2160 here) at a small
    size -- Picture's natural size comes from the source image, and
    set_size_request() only sets a minimum, not a cap, so it kept
    rendering huge regardless of the requested display size. A texture
    that's already the target size has an unambiguous natural size."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, False)
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    picture = Gtk.Picture.new_for_paintable(texture)
    picture.set_content_fit(Gtk.ContentFit.FILL)
    return picture


# ---- Light/Dark mode preview compositing --------------------------------------------
#
# lightmode_icon_new.svg/darkmode_icon_new.svg (macOS_Tahoe_SYSICONS) are macOS Setup-
# Assistant-style desktop mockups (menu bar, traffic lights, dock) painted over a solid
# #00bf63 green-screen background instead of a fixed wallpaper -- the idea being these
# preview tiles should always show the user's own actually-equipped wallpaper, not a
# generic stock photo, matching how macOS's own Appearance page previews work. This is a
# real chroma-key composite (soft-edged, not a hard cutoff, so the anti-aliased boundary
# between the green screen and the menu bar/dock artwork doesn't leave a visible green
# fringe) done at runtime against org.gnome.desktop.background's actual picture-uri/
# picture-uri-dark -- which is also why this automatically handles dynamic wallpapers
# correctly with no special-casing: those two keys already hold the right light/dark
# image for whatever's currently equipped (a static wallpaper just has picture-uri ==
# picture-uri-dark), exactly the same mechanism wallpaper_page.py's own _set_wallpaper()
# writes to.
GREEN_SCREEN_RGB = (0, 191, 99)  # #00bf63
SCHEME_PREVIEW_SIZE = (224, 126)  # 2x SchemeOption.TILE_SIZE, for HiDPI sharpness


def _pixbuf_to_pil(pixbuf: GdkPixbuf.Pixbuf) -> Image.Image:
    mode = 'RGBA' if pixbuf.get_has_alpha() else 'RGB'
    im = Image.frombytes(
        mode, (pixbuf.get_width(), pixbuf.get_height()),
        pixbuf.get_pixels(), 'raw', mode, pixbuf.get_rowstride(), 1,
    )
    return im.convert('RGB')


def _rasterize_greenscreen_svg(path: str, width: int, height: int) -> Image.Image:
    """The expensive, wallpaper-independent half of the composite (SVG parsing +
    rasterizing the embedded artwork, ~0.2s measured) -- cached by the caller and only
    ever redone once per mode, since it never changes."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, False)
    return _pixbuf_to_pil(pixbuf)


def _cover_crop_scale(path: str, width: int, height: int) -> Image.Image:
    """Crops to the target aspect ratio before downscaling (same approach
    provision/wallpaper-previews/gen_wallpaper_previews.py uses) rather than a plain
    stretch -- correct regardless of the source wallpaper's own aspect ratio, since
    unlike the green-screen artwork above it isn't guaranteed to already be 16:9."""
    im = Image.open(path).convert('RGB')
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


def _composite_scheme_preview(fg: Image.Image, wallpaper_path) -> Gdk.Texture:
    """fg is the already-rasterized green-screen artwork (see
    _rasterize_greenscreen_svg). Replaces every pixel close to GREEN_SCREEN_RGB with the
    corresponding pixel from wallpaper_path, cover-cropped to the same size; soft-blends
    a band around the threshold so anti-aliased edges don't fringe. Falls back to the
    green screen unmodified if wallpaper_path is missing/unreadable, rather than raising
    -- a broken preview tile is a much smaller problem than a crashed Appearance page."""
    width, height = fg.size
    try:
        bg = _cover_crop_scale(wallpaper_path, width, height) if wallpaper_path else None
    except (GLib.Error, OSError):
        bg = None

    if bg is None:
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            fg.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, width, height, width * 3)
        return Gdk.Texture.new_for_pixbuf(pixbuf)

    fg_px = fg.load()
    bg_px = bg.load()
    out = Image.new('RGB', (width, height))
    out_px = out.load()
    gr, gg, gb = GREEN_SCREEN_RGB
    for y in range(height):
        for x in range(width):
            r, g, b = fg_px[x, y]
            dist = ((r - gr) ** 2 + (g - gg) ** 2 + (b - gb) ** 2) ** 0.5
            if dist < 40:
                out_px[x, y] = bg_px[x, y]
            elif dist < 100:
                t = (dist - 40) / 60
                br, bgc, bb = bg_px[x, y]
                out_px[x, y] = (
                    int(r * t + br * (1 - t)), int(g * t + bgc * (1 - t)), int(b * t + bb * (1 - t)),
                )
            else:
                out_px[x, y] = (r, g, b)

    pixbuf = GdkPixbuf.Pixbuf.new_from_data(
        out.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, width, height, width * 3)
    return Gdk.Texture.new_for_pixbuf(pixbuf)


# Real GNOME accent-color enum (org.gnome.desktop.interface accent-color) with
# their actual rendered hex values, read from Adw.AccentColor.to_standalone_rgba()
# rather than guessed -- these are the exact colors GNOME itself uses, not a
# copy of macOS's palette. No "multicolor" option: GNOME doesn't have one.
ACCENT_COLORS = [
    ('blue', '#0461BE'),
    ('teal', '#007184'),
    ('green', '#15772E'),
    ('yellow', '#905300'),
    ('orange', '#B62200'),
    ('red', '#C00023'),
    ('pink', '#A2326C'),
    ('purple', '#8939A4'),
    ('slate', '#526678'),
    ('brown', '#7C5C36'),
]

ACCENT_HEX = dict(ACCENT_COLORS)


def _apply_css(widget: Gtk.Widget, css: str):
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode())
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# ---- Liquid Glass intensity ---------------------------------------------------------
#
# Mirrors macOS-TopBar-Gnome/lib/liquidGlassIntensity.js's interpolation exactly (same
# solid targets, same recipe values, same linear blend) so this preview shows the real
# math the extension itself uses, not an approximation. See that file for the full
# rationale -- at intensity 100 this is the shared glass recipe already in
# stylesheet.css, unchanged; at 0 it's fully solid (white in light mode, a dark
# macOS-style surface gray in dark mode); everything between is a straight blend.
LIQUID_GLASS_SOLID_LIGHT = (255, 255, 255)
LIQUID_GLASS_SOLID_DARK = (28, 28, 30)

# Same values as stylesheet.css's shared glass recipe block.
LIQUID_GLASS_RECIPE = {
    'fill': (255, 255, 255, 0.12),
    'gradient_start': (255, 255, 255, 0.28),
    'gradient_end': (255, 255, 255, 0.08),
    'border': (255, 255, 255, 0.42),
    'shadow': (255, 255, 255, 0.5),
}


def _glass_lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _glass_interpolate(base_rgba, intensity: int, is_dark: bool, solid_alpha: float = 1.0):
    t = max(0, min(100, intensity)) / 100
    solid = LIQUID_GLASS_SOLID_DARK if is_dark else LIQUID_GLASS_SOLID_LIGHT
    r, g, b, a = base_rgba
    return (
        round(_glass_lerp(solid[0], r, t)),
        round(_glass_lerp(solid[1], g, t)),
        round(_glass_lerp(solid[2], b, t)),
        _glass_lerp(solid_alpha, a, t),
    )


def _glass_rgba(c) -> str:
    r, g, b, a = c
    return f'rgba({r}, {g}, {b}, {round(a, 3)})'


class LiquidGlassPreview(Gtk.Box):
    """A sample notification card, live-restyled as the slider moves, so the effect is
    visible immediately without needing a real notification to fire. The backdrop is a
    plain CSS gradient, not a photo -- an earlier version used one of the demo photos
    behind a Gtk.Overlay, which rendered visibly broken (stray artifacts bleeding
    through). A CSS gradient on this same box needs no Overlay/Picture/SVG-rasterizing
    at all, just something varied enough behind the card to actually show translucency
    against, which is the only reason a backdrop is here at all."""

    def __init__(self):
        super().__init__(css_classes=['liquid-glass-preview'])
        self.set_size_request(-1, 108)
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self._card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER,
            css_classes=['liquid-glass-preview-card'],
        )
        # Matches the real .notification-banner's own proportions (stylesheet.css in
        # macOS-TopBar-Gnome): min-height 42px, the app icon there is explicitly 20%
        # bigger than MacTahoe's stock 48px (-> 58px), and -- unlike an earlier version of
        # this preview, which stretched the card to fill whatever width the Settings
        # window happened to have -- a real notification banner is a fixed, fairly narrow
        # 28.8em bar (~460px at the toolkit's default 16px root em) that never stretches
        # regardless of screen width. halign=CENTER + this width keeps the backdrop box
        # itself full-width (still reads as "desktop behind the banner"), only the card
        # itself is pinned to realistic proportions.
        self._card.set_size_request(460, -1)
        self._card.set_margin_top(8)
        self._card.set_margin_bottom(8)
        self._card.set_margin_start(12)
        self._card.set_margin_end(16)

        # Same curated icon BlueBubbles itself uses (its default/light-mode variant) --
        # a real sample notification, not a generic placeholder glyph.
        messages_gicon = Gio.icon_new_for_string(os.path.join(ICON_DIR, 'messages_preview.svg'))
        self._icon = Gtk.Image.new_from_gicon(messages_gicon)
        self._icon.set_pixel_size(58)
        self._card.append(self._icon)

        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        self._title_label = Gtk.Label(label='Messages', xalign=0)
        self._body_label = Gtk.Label(label='This is what a notification looks like', xalign=0)
        self._body_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_col.append(self._title_label)
        text_col.append(self._body_label)
        self._card.append(text_col)

        self.append(self._card)

        self._provider = Gtk.CssProvider()
        for widget in (self, self._card, self._title_label, self._body_label):
            widget.get_style_context().add_provider(self._provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def update(self, intensity: int, is_dark: bool):
        backdrop = (
            'linear-gradient(135deg, #2c2450, #6a3a8f, #b3487a)' if is_dark
            else 'linear-gradient(135deg, #ffd36e, #ff8a5c, #ff5e7a)'
        )

        fill = _glass_interpolate(LIQUID_GLASS_RECIPE['fill'], intensity, is_dark)
        gradient_start = _glass_interpolate(LIQUID_GLASS_RECIPE['gradient_start'], intensity, is_dark)
        gradient_end = _glass_interpolate(LIQUID_GLASS_RECIPE['gradient_end'], intensity, is_dark)
        border = _glass_interpolate(LIQUID_GLASS_RECIPE['border'], intensity, is_dark, solid_alpha=0.18)
        shadow = _glass_interpolate(LIQUID_GLASS_RECIPE['shadow'], intensity, is_dark, solid_alpha=0.0)
        # Real .notification-banner text color (notificationBannerGlass.js's own _apply()) is
        # ONE shared rgba(...) value for title AND body alike -- MacTahoe's theme only ever
        # sets `font-weight: bold` on .message-title, no separate color/opacity for either --
        # and it isn't simply tied to system dark/light mode the way this preview had it
        # (a real, confirmed mismatch this preview had before, not a stylistic choice worth
        # keeping). It's the shouldUseDarkContent() adaptive rule instead: dark content is
        # forced in light mode once intensity drops below 50 (the glass has gone opaque
        # enough that light text would stop being readable), and never happens at all in dark
        # mode (that solid target is already dark). Ported 1:1 from that function rather than
        # approximated.
        needs_dark_content = (not is_dark) and intensity < 50
        text_color = 'rgba(28, 28, 30, 0.95)' if needs_dark_content else 'rgba(222, 222, 222, 0.95)'
        body_color = text_color

        css = f"""
        .liquid-glass-preview {{
            background-image: {backdrop};
            border-radius: 12px;
        }}
        .liquid-glass-preview-card {{
            background-color: {_glass_rgba(fill)};
            background-image: linear-gradient(to bottom, {_glass_rgba(gradient_start)}, {_glass_rgba(gradient_end)});
            border: 1px solid {_glass_rgba(border)};
            border-radius: 14px;
            box-shadow: inset 0 1px 0 {_glass_rgba(shadow)};
        }}
        .liquid-glass-preview-card label:first-child {{
            color: {text_color};
            font-weight: bold;
        }}
        .liquid-glass-preview-card label:last-child {{
            color: {body_color};
        }}
        """
        self._provider.load_from_data(css.encode())


class SchemeOption(Gtk.Box):
    """A photo tile + label below it. Plain Box, not a Gtk.ToggleButton --
    same reasoning as ColorSwatch below: the active GTK theme's baked-in
    button checked/hover/focus styling kept winning the cascade fight no
    matter how many states got overridden, so selection here is 100% a
    manually-managed 'selected' CSS class on a widget the theme has no
    opinions about. The selection ring is a separate inner box (ring_box)
    wrapping just the photo -- the label is a sibling outside it, not
    wrapped inside the clickable/ring area."""

    TILE_SIZE = (112, 63)  # 16:9, matches the green-screen artwork's own aspect ratio

    def __init__(self, label: str, on_click):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        self._selected = False

        self.ring_box = Gtk.Box(css_classes=['scheme-ring'])
        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        # Protects the tile's own minimum size -- without this, the tile had
        # no size floor of its own (relying purely on the Picture's natural
        # size), and adding enough width-hungry content elsewhere on the page
        # (the Fonts section's dropdowns) made the page's total minimum width
        # exceed the content pane's fixed, never-horizontally-scrolling width
        # -- confirmed live: GTK's layout solver squeezed this exact
        # unprotected tile down to 0x0 to make everything else fit, while
        # widgets with their own minimum-size floor didn't budge.
        photo_wrap.set_size_request(*self.TILE_SIZE)
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        # No static picture here -- the real content is pushed in by
        # AppearancePage via set_preview_texture() once the wallpaper-composited
        # preview is ready (see the green-screen compositing block above).
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.FILL)
        photo_wrap.append(self.picture)
        self.ring_box.append(photo_wrap)
        self.append(self.ring_box)

        self.append(Gtk.Label(label=label, css_classes=['caption']))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click(self))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')

    def set_preview_texture(self, texture: Gdk.Texture):
        self.picture.set_paintable(texture)

    def get_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool, ring_hex: str):
        self._selected = selected
        if selected:
            self.ring_box.add_css_class('selected')
            _apply_css(self.ring_box, f'box.selected {{ border-color: {ring_hex}; }}')
        else:
            self.ring_box.remove_css_class('selected')


class ColorSwatch(Gtk.Box):
    def __init__(self, name: str, hex_color: str, on_click):
        super().__init__(css_classes=['color-swatch'], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.accent_name = name
        self._selected = False

        dot = Gtk.Box(css_classes=['color-swatch-dot'])
        _apply_css(dot, f'box {{ background-color: {hex_color}; }}')
        self.append(dot)

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click(self))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')

    def get_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool, ring_hex: str = '#FFFFFF'):
        self._selected = selected
        if selected:
            self.add_css_class('selected')
            _apply_css(self, f'box.selected {{ border-color: {ring_hex}; }}')
        else:
            self.remove_css_class('selected')


ICON_STYLE_TILE_SIZE = (45, 45)  # 20% down from the original 56x56, per explicit request

ICON_STYLES = [
    ('default', 'Default', 'appearance_default.svg', True),
    ('dark', 'Dark', 'appearance_dark.svg', True),
    ('clear', 'Clear', 'appearance_clear.svg', True),
]


class IconStyleOption(Gtk.Box):
    """Same tile+label+selection-ring shape as SchemeOption, but square.
    Still supports a disabled state (unused now that all four styles are
    implemented) so a future not-yet-ready style can be shown inert rather
    than hidden."""

    def __init__(self, label: str, icon_filename: str, enabled: bool, on_click):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        self._selected = False
        self.enabled = enabled

        self.ring_box = Gtk.Box(css_classes=['scheme-ring'])
        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        photo_wrap.set_size_request(*ICON_STYLE_TILE_SIZE)  # see SchemeOption's identical fix for why
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        picture = _load_scaled_picture(os.path.join(ICON_DIR, icon_filename), *ICON_STYLE_TILE_SIZE)
        photo_wrap.append(picture)
        self.ring_box.append(photo_wrap)
        self.append(self.ring_box)

        self.append(Gtk.Label(label=label, css_classes=['caption'] + ([] if enabled else ['dim-label'])))

        if enabled:
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a: on_click(self))
            self.add_controller(click)
            self.set_cursor_from_name('pointer')
        else:
            self.ring_box.set_opacity(0.45)

    def get_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool, ring_hex: str):
        self._selected = selected
        if selected:
            self.ring_box.add_css_class('selected')
            _apply_css(self.ring_box, f'box.selected {{ border-color: {ring_hex}; }}')
        else:
            self.ring_box.remove_css_class('selected')


class AppearancePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._appearance_settings = Gio.Settings.new('org.peachos.appearance')
        # Same schema id menubar_page.py already uses Gio.Settings.new() against directly
        # (it's in the global schema registry on a real peachOS install) -- matching that
        # instead of widgets.py's load_extension_settings() helper for consistency.
        self._panel_settings = Gio.Settings.new('org.gnome.shell.extensions.macos-top-panel')
        # User Themes (already vendored/enabled in peachOS -- extensions/user-theme@...) is
        # what actually decides which gnome-shell.css the Shell loads. Real gap found
        # investigating "dropdown menus don't respect dark mode": this key was NEVER wired
        # to color-scheme, so the Shell always loaded MacTahoe-Light regardless of dark
        # mode -- only GTK/libadwaita apps (which follow color-scheme directly) ever looked
        # dark. _sync_shell_theme() below keeps it in lockstep with color-scheme from here
        # on; only affects genuine system-styled popups (like the top-left/global menu's
        # dropdowns) since this project's own Control Center/notifications already do their
        # own explicit light/dark overrides instead of relying on the shell theme at all.
        self._user_theme_settings = Gio.Settings.new('org.gnome.shell.extensions.user-theme')
        self._bg_settings = Gio.Settings.new('org.gnome.desktop.background')
        self._icon_style_busy = False

        # The expensive half of the Light/Dark preview composite (SVG rasterization,
        # ~0.2s each measured) never changes -- cached once here so a wallpaper change
        # later only re-does the cheap chroma-key + wallpaper crop step (~0.02s).
        self._light_scheme_fg = _rasterize_greenscreen_svg(
            os.path.join(ICON_DIR, 'lightmode_icon_new.svg'), *SCHEME_PREVIEW_SIZE)
        self._dark_scheme_fg = _rasterize_greenscreen_svg(
            os.path.join(ICON_DIR, 'darkmode_icon_new.svg'), *SCHEME_PREVIEW_SIZE)

        # Correct any pre-existing desync on open (e.g. dark mode was already on before
        # this sync existed) rather than only fixing it forward from the next toggle.
        self._sync_shell_theme(self._settings.get_string('color-scheme') == 'prefer-dark')

        self._build_ui()

        self._settings.connect('changed::color-scheme', lambda *_: self._refresh_all_selection())
        self._settings.connect('changed::color-scheme', lambda *_: self._refresh_liquid_glass_preview())
        self._settings.connect('changed::accent-color', lambda *_: self._refresh_all_selection())
        self._appearance_settings.connect('changed::icon-style', lambda *_: self._refresh_icon_style_selection())
        self._panel_settings.connect(
            'changed::liquid-glass-intensity', lambda *_: self._refresh_liquid_glass_preview())
        self._bg_settings.connect('changed::picture-uri', lambda *_: self._refresh_scheme_previews())
        self._bg_settings.connect('changed::picture-uri-dark', lambda *_: self._refresh_scheme_previews())
        self._refresh_all_selection()
        self._refresh_icon_style_selection()
        self._refresh_liquid_glass_preview()
        self._refresh_scheme_previews()

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'appearance.svg'), 'preferences-desktop-theme-symbolic',
            'Appearance', 'Choose a light or dark appearance for peachOS, and pick an accent color.',
        ))

        # Single horizontal row: "Appearance" label pinned top-left, tiles
        # on the right. Margins go on the children, not appearance_card
        # itself -- margins on the card widget only push it away from its
        # siblings (external spacing), they don't add internal padding.
        appearance_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.HORIZONTAL)
        appearance_card.append(Gtk.Label(
            label='Appearance', xalign=0, css_classes=['heading'],
            hexpand=True, valign=Gtk.Align.START,
            margin_start=14, margin_top=14,
        ))

        options_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=14, valign=Gtk.Align.CENTER,
            margin_end=14, margin_top=12, margin_bottom=12,
        )
        self._light_option = SchemeOption('Light', on_click=self._on_scheme_clicked)
        self._dark_option = SchemeOption('Dark', on_click=self._on_scheme_clicked)
        options_row.append(self._light_option)
        options_row.append(self._dark_option)
        appearance_card.append(options_row)
        self.append(appearance_card)

        self.append(Gtk.Label(label='Theme', xalign=0, css_classes=['heading'], margin_start=4))

        theme_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        theme_card.append(Gtk.Label(
            label='Color', xalign=0, hexpand=True,
            margin_start=14, margin_top=10, margin_bottom=10,
        ))

        swatch_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            margin_end=14, margin_top=10, margin_bottom=10,
        )
        self._swatches = {}
        for name, hex_color in ACCENT_COLORS:
            swatch = ColorSwatch(name, hex_color, on_click=self._on_swatch_clicked)
            self._swatches[name] = swatch
            swatch_row.append(swatch)
        theme_card.append(swatch_row)
        self.append(theme_card)

        # Second card under the same "Theme" heading, matching the real Settings layout
        # (Icon & widget style sits with Folder color, not with Color/Text highlight color).
        icon_style_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.HORIZONTAL)
        icon_style_card.append(Gtk.Label(
            label='Icon & widget style', xalign=0, hexpand=True, valign=Gtk.Align.CENTER,
            margin_start=14, margin_top=14, margin_bottom=14,
        ))

        icon_style_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=14, valign=Gtk.Align.CENTER,
            margin_end=14, margin_top=12, margin_bottom=12,
        )
        self._icon_style_options = {}
        for style_id, label, icon_filename, enabled in ICON_STYLES:
            option = IconStyleOption(label, icon_filename, enabled, on_click=self._on_icon_style_clicked)
            self._icon_style_options[style_id] = option
            icon_style_row.append(option)
        icon_style_card.append(icon_style_row)
        self.append(icon_style_card)

        self.append(Gtk.Label(label='Liquid Glass', xalign=0, css_classes=['heading'], margin_start=4))

        # Controls the Control Center, Notification Center, and notification banners'
        # translucency -- not the dock, which has its own separate liquid-glass-mode
        # concept in macOS-Dock-2026-peachOS. 100 (max, the slider's own default) is the
        # original translucent look; 0 is fully solid/opaque. See
        # macOS-TopBar-Gnome/lib/liquidGlassIntensity.js for the shared interpolation math
        # this preview mirrors exactly.
        glass_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, css_classes=['wifi-card'])

        glass_preview_wrap = Gtk.Box(margin_start=14, margin_end=14, margin_top=14)
        self._liquid_glass_preview = LiquidGlassPreview()
        glass_preview_wrap.append(self._liquid_glass_preview)
        glass_card.append(glass_preview_wrap)

        glass_slider_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            margin_start=14, margin_end=14, margin_top=12, margin_bottom=14,
        )
        glass_slider_row.append(Gtk.Label(label='Solid', css_classes=['dim-label']))
        self._liquid_glass_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._liquid_glass_scale.set_draw_value(False)
        self._liquid_glass_scale.set_hexpand(True)
        self._liquid_glass_scale.set_value(self._panel_settings.get_int('liquid-glass-intensity'))
        self._liquid_glass_scale.connect('value-changed', self._on_liquid_glass_scale_changed)
        glass_slider_row.append(self._liquid_glass_scale)
        glass_slider_row.append(Gtk.Label(label='Liquid Glass', css_classes=['dim-label']))
        glass_card.append(glass_slider_row)

        self.append(glass_card)

        self.append(Gtk.Label(label='Fonts', xalign=0, css_classes=['heading'], margin_start=4))

        font_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        font_card.append(self._make_font_picker_row('Interface Font', 'font-name'))
        font_card.append(self._make_font_picker_row('Document Font', 'document-font-name'))
        font_card.append(self._make_font_picker_row('Monospace Font', 'monospace-font-name'))
        self.append(font_card)

        scaling_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14, css_classes=['network-row'])
        scaling_row.set_margin_start(14)
        scaling_row.set_margin_end(14)
        scaling_row.set_margin_top(10)
        scaling_row.set_margin_bottom(10)
        scaling_row.append(Gtk.Label(label='Scaling Factor', xalign=0))
        scaling_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.05)
        scaling_scale.set_draw_value(False)
        scaling_scale.set_hexpand(True)
        self._settings.bind(
            'text-scaling-factor', scaling_scale.get_adjustment(), 'value', Gio.SettingsBindFlags.DEFAULT)
        scaling_row.append(scaling_scale)

        self._hinting_row = DropdownRow('Hinting', FONT_HINT_STYLES)
        self._hinting_row.set_selected_value(self._settings.get_string('font-hinting'))
        self._hinting_row.dropdown.connect('notify::selected', self._on_hinting_changed)

        self._antialiasing_row = DropdownRow('Antialiasing', FONT_ANTIALIASING)
        self._antialiasing_row.set_selected_value(self._settings.get_string('font-antialiasing'))
        self._antialiasing_row.dropdown.connect('notify::selected', self._on_antialiasing_changed)

        scaling_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        scaling_card.append(scaling_row)
        scaling_card.append(self._hinting_row)
        scaling_card.append(self._antialiasing_row)
        self.append(scaling_card)

    def _make_font_picker_row(self, title: str, key: str) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(10)
        row.set_margin_bottom(10)
        row.append(Gtk.Label(label=title, xalign=0, hexpand=True))

        font_dialog = Gtk.FontDialog()
        button = Gtk.FontDialogButton(dialog=font_dialog, valign=Gtk.Align.CENTER)
        button.set_font_desc(Pango.FontDescription.from_string(self._settings.get_string(key)))
        button.connect('notify::font-desc', lambda btn, _p, k=key: self._settings.set_string(k, btn.get_font_desc().to_string()))
        row.append(button)
        return row

    def _on_hinting_changed(self, _dropdown, _pspec):
        self._settings.set_string('font-hinting', self._hinting_row.get_selected_value())

    def _on_antialiasing_changed(self, _dropdown, _pspec):
        self._settings.set_string('font-antialiasing', self._antialiasing_row.get_selected_value())

    # ---- Appearance (color-scheme) -------------------------------------

    def _on_scheme_clicked(self, option):
        value = 'default' if option is self._light_option else 'prefer-dark'
        is_dark = value == 'prefer-dark'
        self._settings.set_string('color-scheme', value)
        self._sync_shell_theme(is_dark)
        self._sync_plymouth_theme(is_dark)
        self._refresh_scheme_selection()

    def _sync_shell_theme(self, is_dark):
        try:
            self._user_theme_settings.set_string('name', 'MacTahoe-Dark' if is_dark else 'MacTahoe-Light')
        except GLib.Error:
            pass  # User Themes extension not present/enabled -- nothing to sync.

    def _sync_plymouth_theme(self, is_dark):
        """Boot splash colors/logo (peachos-plymouth-sync) live in /usr, so this needs real
        root, unlike _sync_shell_theme's plain (user-writable) GSettings key above -- pkexec
        will prompt once. Only called from an actual toggle click (not from __init__, unlike
        _sync_shell_theme's own startup desync-correction call) so opening this page never
        surprises the user with an auth prompt when nothing's actually changed -- the script
        itself is idempotent (skips the slow initramfs rebuild if the mode already matches),
        but pkexec still has to authenticate before it can even ask the script that, so the
        no-op has to be avoided on this side instead."""
        try:
            Gio.Subprocess.new(
                ['pkexec', PLYMOUTH_SYNC_SCRIPT, 'dark' if is_dark else 'light'],
                Gio.SubprocessFlags.NONE,
            )
        except GLib.Error:
            pass  # Nothing more useful to do than leave the boot splash as it was.

    def _refresh_scheme_selection(self):
        is_dark = self._settings.get_string('color-scheme') == 'prefer-dark'
        ring_hex = ACCENT_HEX.get(self._settings.get_string('accent-color'), '#0461BE')
        self._light_option.set_selected(not is_dark, ring_hex)
        self._dark_option.set_selected(is_dark, ring_hex)

    def _current_wallpaper_path(self, key: str):
        """Same picture-uri -> local path resolution wallpaper_page.py's own
        _current_path() does, duplicated rather than imported -- these are two separate
        page modules with independent lifecycles, not worth coupling over one helper."""
        uri = self._bg_settings.get_string(key)
        if not uri:
            return None
        try:
            path, _ = GLib.filename_from_uri(uri)
            return path
        except GLib.Error:
            return None

    def _refresh_scheme_previews(self):
        """Re-composites both Light/Dark preview tiles against whatever's actually
        equipped right now. picture-uri/picture-uri-dark already resolve dynamic
        wallpapers correctly on their own (see this module's green-screen-compositing
        docstring above) -- no dynamic-vs-static branching needed here."""
        light_path = self._current_wallpaper_path('picture-uri')
        dark_path = self._current_wallpaper_path('picture-uri-dark')
        self._light_option.set_preview_texture(
            _composite_scheme_preview(self._light_scheme_fg, light_path))
        self._dark_option.set_preview_texture(
            _composite_scheme_preview(self._dark_scheme_fg, dark_path))

    # ---- Theme (accent-color) ------------------------------------------

    def _on_swatch_clicked(self, swatch):
        self._settings.set_string('accent-color', swatch.accent_name)
        self._refresh_all_selection()

    def _refresh_all_selection(self):
        active = self._settings.get_string('accent-color')
        # Ring needs to contrast with the background, not just the swatch's
        # own color, so it tracks light/dark rather than staying fixed white.
        is_dark = self._settings.get_string('color-scheme') == 'prefer-dark'
        swatch_ring_hex = '#FFFFFF' if is_dark else '#000000'
        for name, swatch in self._swatches.items():
            swatch.set_selected(name == active, swatch_ring_hex)
        self._refresh_scheme_selection()

    # ---- Icon & widget style ---------------------------------------------

    def _on_icon_style_clicked(self, option):
        if self._icon_style_busy:
            return
        style_id = next(sid for sid, opt in self._icon_style_options.items() if opt is option)
        if self._appearance_settings.get_string('icon-style') == style_id:
            return

        def on_success():
            self._appearance_settings.set_string('icon-style', style_id)
            self._refresh_icon_style_selection()

        self._run_icon_appearance(style_id, on_success)

    def _run_icon_appearance(self, style_id, on_success):
        self._icon_style_busy = True
        for opt in self._icon_style_options.values():
            opt.set_opacity(0.6 if opt.enabled else 0.45)

        # peachos-icon-appearance only ever adds/removes files under ~/.local/share -- no
        # system-wide writes, so no pkexec/auth prompt needed for what's really just a
        # personal preference. Snapshotting the shell's own app-grid layout and restoring it
        # after is a belt-and-suspenders guard: GNOME Shell has been observed resetting
        # app-picker-layout on its own when a burst of desktop-file changes come through, and
        # icon appearance changing should never reshuffle anyone's app grid.
        shell_settings = Gio.Settings.new('org.gnome.shell')
        layout_snapshot = shell_settings.get_value('app-picker-layout')
        favorites_snapshot = shell_settings.get_strv('favorite-apps')

        # Separately: GNOME's own dash.js _redisplay() admits in its own source comment that
        # its diffing algorithm assumes only one item moves at a time, and touching several at
        # once (exactly what changing every app's icon does) can make it "remove all the
        # launchers and add them back in a new order" -- a real Shell limitation, not a
        # gsettings issue, so app-picker-layout/favorite-apps staying byte-identical doesn't
        # stop it. dockOrderGuard (lib/dockOrderGuard.js in the extension) snapshots the dock's
        # actual on-screen actor order before, and forces it back after -- that has to happen
        # inside the Shell process, where those actors live, hence the D-Bus round-trip here.
        _call_dock_order_guard('Snapshot')

        proc = Gio.Subprocess.new(
            [ICON_APPEARANCE_SCRIPT, style_id],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_PIPE,
        )

        def on_done(source, result):
            self._icon_style_busy = False
            for opt in self._icon_style_options.values():
                opt.set_opacity(1.0)
            try:
                ok, _stdout, stderr = source.communicate_utf8_finish(result)
                success = ok and source.get_exit_status() == 0
            except GLib.Error as e:
                success, stderr = False, str(e)

            shell_settings.set_value('app-picker-layout', layout_snapshot)
            shell_settings.set_strv('favorite-apps', favorites_snapshot)
            # Give Shell's own (mis-ordering) redisplay pass time to actually happen before we
            # force the real order back -- restoring too early would just get overwritten by a
            # redisplay that hadn't run yet.
            GLib.timeout_add(1200, lambda: _call_dock_order_guard('Restore') or GLib.SOURCE_REMOVE)

            if success:
                on_success()
            elif stderr and stderr.strip():
                dialog = Adw.AlertDialog(
                    heading='Couldn’t change icon appearance',
                    body=stderr.strip(),
                )
                dialog.add_response('ok', 'OK')
                dialog.present(self.get_root())

        proc.communicate_utf8_async(None, None, on_done)

    def _refresh_icon_style_selection(self):
        active = self._appearance_settings.get_string('icon-style')
        ring_hex = ACCENT_HEX.get(self._settings.get_string('accent-color'), '#0461BE')
        for style_id, option in self._icon_style_options.items():
            option.set_selected(style_id == active, ring_hex)

    # ---- Liquid Glass ----------------------------------------------------

    def _on_liquid_glass_scale_changed(self, scale):
        intensity = round(scale.get_value())
        self._panel_settings.set_int('liquid-glass-intensity', intensity)
        self._refresh_liquid_glass_preview()

    def _refresh_liquid_glass_preview(self):
        intensity = self._panel_settings.get_int('liquid-glass-intensity')
        if round(self._liquid_glass_scale.get_value()) != intensity:
            self._liquid_glass_scale.set_value(intensity)
        is_dark = self._settings.get_string('color-scheme') == 'prefer-dark'
        self._liquid_glass_preview.update(intensity, is_dark)
