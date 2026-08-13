import os

from gi.repository import Gtk


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
        icon = Gtk.Image.new_from_file(icon_path)
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


def add_hover_highlight(widget: Gtk.Widget, css_class: str = 'row-hover'):
    """Manually toggle a CSS class on enter/leave instead of relying on the
    :hover pseudo-class. For a Box containing interactive children (Switch,
    DropDown, another GestureClick) GTK4's :hover state on the container
    reads as only covering *part* of the row -- the same failure mode
    already worked around elsewhere in this app (see SchemeOption/
    ColorSwatch in appearance_page.py) by not trusting the theme's state
    cascade at all. A motion controller on the row itself doesn't have
    that problem: enter/leave fire for the row's whole allocated area
    regardless of what's drawn on top of it."""
    motion = Gtk.EventControllerMotion()
    motion.connect('enter', lambda *_a: widget.add_css_class(css_class))
    motion.connect('leave', lambda *_a: widget.remove_css_class(css_class))
    widget.add_controller(motion)
