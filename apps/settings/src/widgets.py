import os

from gi.repository import Gtk


def make_hero_header(icon_path: str, fallback_icon_name: str, title: str, description: str) -> Gtk.Widget:
    """The big-icon/title/description card that sits at the top of every
    tab, matching the reference "General" page layout. Shared across all
    page modules rather than duplicated per-file."""
    card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
    inner = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
        margin_top=22, margin_bottom=22, margin_start=24, margin_end=24,
    )

    if icon_path and os.path.isfile(icon_path):
        icon = Gtk.Image.new_from_file(icon_path)
    else:
        icon = Gtk.Image.new_from_icon_name(fallback_icon_name)
    icon.set_pixel_size(64)
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
