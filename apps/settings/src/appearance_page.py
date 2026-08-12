import os

import gi

gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gdk, GdkPixbuf, Gio, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')


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


class SchemeOption(Gtk.Box):
    """A photo tile + label below it. Plain Box, not a Gtk.ToggleButton --
    same reasoning as ColorSwatch below: the active GTK theme's baked-in
    button checked/hover/focus styling kept winning the cascade fight no
    matter how many states got overridden, so selection here is 100% a
    manually-managed 'selected' CSS class on a widget the theme has no
    opinions about. The selection ring is a separate inner box (ring_box)
    wrapping just the photo -- the label is a sibling outside it, not
    wrapped inside the clickable/ring area."""

    TILE_SIZE = (112, 63)  # 16:9, matches the demo photos' aspect ratio

    def __init__(self, label: str, icon_filename: str, on_click):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        self._selected = False

        self.ring_box = Gtk.Box(css_classes=['scheme-ring'])
        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        picture = _load_scaled_picture(os.path.join(ICON_DIR, icon_filename), *self.TILE_SIZE)
        photo_wrap.append(picture)
        self.ring_box.append(photo_wrap)
        self.append(self.ring_box)

        self.append(Gtk.Label(label=label, css_classes=['caption']))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_a: on_click(self))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')

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


class AppearancePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new('org.gnome.desktop.interface')

        self._build_ui()

        self._settings.connect('changed::color-scheme', lambda *_: self._refresh_all_selection())
        self._settings.connect('changed::accent-color', lambda *_: self._refresh_all_selection())
        self._refresh_all_selection()

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
        self._light_option = SchemeOption('Light', 'lightmode_demophoto.svg', on_click=self._on_scheme_clicked)
        self._dark_option = SchemeOption('Dark', 'darkmode_demophoto.svg', on_click=self._on_scheme_clicked)
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

    # ---- Appearance (color-scheme) -------------------------------------

    def _on_scheme_clicked(self, option):
        value = 'default' if option is self._light_option else 'prefer-dark'
        self._settings.set_string('color-scheme', value)
        self._refresh_scheme_selection()

    def _refresh_scheme_selection(self):
        is_dark = self._settings.get_string('color-scheme') == 'prefer-dark'
        ring_hex = ACCENT_HEX.get(self._settings.get_string('accent-color'), '#0461BE')
        self._light_option.set_selected(not is_dark, ring_hex)
        self._dark_option.set_selected(is_dark, ring_hex)

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
