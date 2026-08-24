import os

from gi.repository import Gdk, GdkPixbuf, Gtk


def load_sized_image(path: str, pixel_size: int) -> Gtk.Image:
    """Gtk.Image.new_from_file() routes local SVGs through GTK4's sandboxed
    glycin loader -- confirmed live at ~0.7s PER ICON in this environment
    (bubblewrap + D-Bus round trip per image, same overhead documented in
    provision.sh's icon masker daemon comments), regardless of file size.
    With ~24 sidebar icons plus every page's own hero-header icon all going
    through that path, this alone accounted for most of a ~57s app startup.
    GdkPixbuf's own loader (librsvg-backed, no sandbox) loads the same file
    in single-digit milliseconds -- same fix already used successfully by
    wallpaper_page.py/appearance_page.py's image-preview code."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, pixel_size, pixel_size, True)
    icon = Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
    # Gtk.Image built from a bare paintable (unlike new_from_file/icon-name)
    # doesn't measure itself at the paintable's own pixel size -- confirmed
    # live it defaults to 16x16 regardless, which is why every icon fixed by
    # this helper first rendered tiny. set_pixel_size() still applies here
    # even though the image wasn't constructed from an icon name.
    icon.set_pixel_size(pixel_size)
    return icon


def make_hero_header(icon_path: str, fallback_icon_name: str, title: str, description: str,
                      icon_size: int = 64) -> Gtk.Widget:
    """The big-icon/title/description card that sits at the top of every
    tab, matching the reference "General" page layout. Shared across all
    page modules rather than duplicated per-file."""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    inner = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
        margin_top=22, margin_bottom=22, margin_start=24, margin_end=24,
    )

    if icon_path and os.path.isfile(icon_path):
        icon = load_sized_image(icon_path, icon_size)
    else:
        icon = Gtk.Image.new_from_icon_name(fallback_icon_name)
        icon.set_pixel_size(icon_size)
    inner.append(icon)

    inner.append(Gtk.Label(label=title, css_classes=['title-1']))

    desc = Gtk.Label(
        label=description, wrap=True, justify=Gtk.Justification.CENTER,
        css_classes=['dim-label'],
    )
    desc.set_max_width_chars(56)
    inner.append(desc)

    card.append(inner)
    return card


class ToggleRow(Gtk.Box):
    """A row with a leading title (+ optional subtitle) and a trailing
    switch -- the same shape used for boolean settings across displays_page.py,
    desktopdock_page.py, general_datetime_page.py etc, centralized here
    so new pages (accessibility_*) don't redefine it again."""

    def __init__(self, title: str, subtitle: str = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text_box.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            text_box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=['caption', 'dim-label']))
        self.append(text_box)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.append(self.switch)


class SliderRow(Gtk.Box):
    """A row with a title and a horizontal Gtk.Scale spanning the rest of
    the row -- for numeric settings (zoom factor, pointer size, delays)."""

    def __init__(self, title: str, low: float, high: float, step: float = 1):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.append(self.scale)


class DropdownRow(Gtk.Box):
    """A row with a title and a trailing Gtk.DropDown."""

    def __init__(self, title: str, options: list):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.dropdown = Gtk.DropDown.new_from_strings([label for label, _value in options])
        self._values = [value for _label, value in options]
        self.append(self.dropdown)

    def get_selected_value(self):
        return self._values[self.dropdown.get_selected()]

    def set_selected_value(self, value):
        if value in self._values:
            self.dropdown.set_selected(self._values.index(value))


class IconPlaceholderRow(Gtk.Box):
    """A row for a top-level settings list: a leading icon, a title, and
    either a trailing chevron (drills into a sub-page) or a trailing
    switch (a single on/off setting with no sub-page worth having).

    icon_file (a real, full-color SVG) is preferred when given and it
    exists on disk; otherwise falls back to icon_name rendered as a
    symbolic glyph in a colored square, for rows that don't have a
    custom icon yet."""

    def __init__(self, title: str, icon_name: str, accent_class: str, on_click=None, switch: Gtk.Switch = None,
                 icon_file: str = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(12)
        self.set_margin_end(8)
        self.set_margin_top(10)
        self.set_margin_bottom(10)

        if icon_file and os.path.isfile(icon_file):
            icon = load_sized_image(icon_file, 28)
            self.append(icon)
        else:
            icon_box = Gtk.Box(
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                css_classes=['sidebar-icon', accent_class],
            )
            icon_box.set_size_request(28, 28)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(15)
            icon_box.append(icon)
            self.append(icon_box)

        self.append(Gtk.Label(label=title, xalign=0, hexpand=True, valign=Gtk.Align.CENTER))

        if switch is not None:
            self.append(switch)
        else:
            self.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))
            if on_click:
                click = Gtk.GestureClick()
                click.connect('released', lambda *_a: on_click())
                self.add_controller(click)
                self.set_cursor_from_name('pointer')
