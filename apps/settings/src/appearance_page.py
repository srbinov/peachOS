import os

from gi.repository import Gio, GLib, Gtk

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

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


class SchemeOption(Gtk.Box):
    """A photo tile + label below it. The selection ring hugs only the
    photo button -- the label is a separate sibling outside it, not
    wrapped inside the clickable/ring area."""

    def __init__(self, label: str, icon_filename: str, group: 'SchemeOption' = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)

        self.toggle = Gtk.ToggleButton(css_classes=['flat', 'scheme-toggle'])
        if group is not None:
            self.toggle.set_group(group.toggle)

        photo_wrap = Gtk.Box(css_classes=['scheme-photo'])
        photo_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        picture = Gtk.Picture.new_for_filename(os.path.join(ICON_DIR, icon_filename))
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(48, 27)
        photo_wrap.append(picture)
        self.toggle.set_child(photo_wrap)
        self.append(self.toggle)

        self.append(Gtk.Label(label=label, css_classes=['caption']))

        click = Gtk.GestureClick()
        click.connect('released', lambda *_: self.toggle.set_active(True))
        self.add_controller(click)
        self.set_cursor_from_name('pointer')


class ColorSwatch(Gtk.ToggleButton):
    def __init__(self, name: str, hex_color: str, group: Gtk.ToggleButton = None):
        super().__init__(css_classes=['flat', 'color-swatch'], tooltip_text=name.capitalize())
        if group is not None:
            self.set_group(group)
        self.accent_name = name

        dot = Gtk.Box(css_classes=['color-swatch-dot'])
        css = Gtk.CssProvider()
        css.load_from_data(f'box {{ background-color: {hex_color}; }}'.encode())
        dot.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_child(dot)


class AppearancePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._syncing = False

        self._build_ui()

        self._settings.connect('changed::color-scheme', lambda *_: self._sync_scheme())
        self._settings.connect('changed::accent-color', lambda *_: self._sync_accent())
        self._sync_scheme()
        self._sync_accent()

    def _build_ui(self):
        appearance_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL, spacing=10)
        appearance_card.append(Gtk.Label(
            label='Appearance', xalign=0, css_classes=['heading'],
            margin_start=14, margin_top=12,
        ))

        options_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER,
            margin_bottom=14, margin_top=4,
        )
        self._light_option = SchemeOption('Light', 'lightmode_demophoto.svg')
        self._dark_option = SchemeOption('Dark', 'darkmode_demophoto.svg', group=self._light_option)
        self._light_option.toggle.connect('toggled', self._on_scheme_toggled)
        self._dark_option.toggle.connect('toggled', self._on_scheme_toggled)
        options_row.append(self._light_option)
        options_row.append(self._dark_option)
        appearance_card.append(options_row)
        self.append(appearance_card)

        self.append(Gtk.Label(label='Theme', xalign=0, css_classes=['heading'], margin_start=4))

        # Margins go on the children, not on theme_card itself -- margins on
        # the card widget only push it away from its siblings (external
        # spacing), they don't add internal padding for its content.
        theme_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        theme_card.append(Gtk.Label(
            label='Color', xalign=0, hexpand=True,
            margin_start=14, margin_top=10, margin_bottom=10,
        ))

        swatch_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_end=14, margin_top=10, margin_bottom=10,
        )
        self._swatches = {}
        first_swatch = None
        for name, hex_color in ACCENT_COLORS:
            swatch = ColorSwatch(name, hex_color, group=first_swatch)
            if first_swatch is None:
                first_swatch = swatch
            swatch.connect('toggled', self._on_accent_toggled)
            self._swatches[name] = swatch
            swatch_row.append(swatch)
        theme_card.append(swatch_row)
        self.append(theme_card)

    # ---- Appearance (color-scheme) -------------------------------------

    def _on_scheme_toggled(self, button):
        if self._syncing or not button.get_active():
            return
        value = 'default' if button is self._light_option.toggle else 'prefer-dark'
        self._settings.set_string('color-scheme', value)

    def _sync_scheme(self):
        self._syncing = True
        scheme = self._settings.get_string('color-scheme')
        if scheme == 'prefer-dark':
            self._dark_option.toggle.set_active(True)
        else:
            self._light_option.toggle.set_active(True)
        self._syncing = False

    # ---- Theme (accent-color) ------------------------------------------

    def _on_accent_toggled(self, button):
        if self._syncing or not button.get_active():
            return
        self._settings.set_string('accent-color', button.accent_name)

    def _sync_accent(self):
        self._syncing = True
        active = self._settings.get_string('accent-color')
        swatch = self._swatches.get(active)
        if swatch:
            swatch.set_active(True)
        self._syncing = False
