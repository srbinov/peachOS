import os

from gi.repository import Gio, GLib, Gtk

from widgets import DropdownRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

# (row title, the content-type mimeapps.list actually keys the default on,
# other content-types that should get set together with it). Matches
# gnome-control-center's own "Default Applications" categories -- gap found
# comparing against the stock Settings app (peachOS's custom one never had
# this at all).
CATEGORIES = [
    ('Web Browser', 'text/html', ['x-scheme-handler/http', 'x-scheme-handler/https']),
    ('Email', 'x-scheme-handler/mailto', []),
    ('Calendar', 'text/calendar', []),
    ('Music', 'audio/mpeg', []),
    ('Video', 'video/mp4', []),
    ('Photos', 'image/jpeg', []),
]


class GeneralDefaultAppsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'general.svg'), 'preferences-desktop-default-applications-symbolic',
            'Default Apps', 'Choose which app opens each kind of file or link by default.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        any_rows = False
        for title, content_type, extra_types in CATEGORIES:
            row = self._build_row(title, content_type, extra_types)
            if row is not None:
                card.append(row)
                any_rows = True
        self.append(card)

        if not any_rows:
            self.append(Gtk.Label(
                label='No apps are registered as handlers for these file/link types yet.',
                css_classes=['dim-label'],
            ))

    def _build_row(self, title: str, content_type: str, extra_types: list):
        # get_all_for_type() -- every installed app that's registered a
        # handler for this content type, same source gnome-control-center's
        # own panel and `xdg-mime query default` read from.
        apps = Gio.AppInfo.get_all_for_type(content_type)
        options = []
        seen_ids = set()
        for app in apps:
            app_id = app.get_id()
            if not app_id or app_id in seen_ids:
                continue
            seen_ids.add(app_id)
            options.append((app.get_display_name() or app.get_name(), app_id))
        if not options:
            return None  # nothing installed handles this type -- no point showing an empty picker

        row = DropdownRow(title, options)
        current = Gio.AppInfo.get_default_for_type(content_type, False)
        if current is not None:
            row.set_selected_value(current.get_id())

        def on_changed(dropdown, _pspec, content_type=content_type, extra_types=extra_types):
            app_id = row.get_selected_value()
            app_info = Gio.DesktopAppInfo.new(app_id)
            if app_info is None:
                return
            for ct in [content_type] + extra_types:
                try:
                    app_info.set_as_default_for_type(ct)
                except GLib.Error:
                    pass

        row.dropdown.connect('notify::selected', on_changed)
        return row
