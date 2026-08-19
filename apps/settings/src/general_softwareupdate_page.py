import os

from gi.repository import Gtk

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

PEACHOS_VERSION = '10.0'


class GeneralSoftwareUpdatePage(Gtk.Box):
    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL, spacing=10,
            valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, vexpand=True,
        )

        icon = Gtk.Image.new_from_file(os.path.join(ICON_DIR, 'peachos_nectar.svg'))
        icon.set_pixel_size(96)
        self.append(icon)

        self.append(Gtk.Label(label=f'peachOS Nectar {PEACHOS_VERSION}', css_classes=['title-1'], margin_top=12))

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)
        status_row.append(Gtk.Image.new_from_icon_name('emblem-ok-symbolic'))
        status_row.append(Gtk.Label(label='peachOS is up to date', css_classes=['heading']))
        self.append(status_row)

        self.append(Gtk.Label(
            label='There are no updates available.', css_classes=['dim-label'], margin_top=2,
        ))
