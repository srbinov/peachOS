import os
import re

from gi.repository import Adw, Gio, Gtk

from widgets import make_hero_header, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

NOTIFICATIONS_SCHEMA = 'org.gnome.desktop.notifications'
PER_APP_SCHEMA = 'org.gnome.desktop.notifications.application'
PER_APP_PATH_ROOT = '/org/gnome/desktop/notifications/application/'


def _canonicalize_app_id(desktop_id: str) -> str:
    """Same algorithm gnome-shell's own NotificationApplicationPolicy uses
    (messageTray.js's _canonicalizeId) to turn a .desktop id into the path
    segment its per-app notification settings live under -- has to match
    exactly, or these toggles would write to a schema path the real
    notification daemon never reads. Strip the .desktop suffix first (the
    daemon does this via Shell.App.get_id().replace(/\\.desktop$/, '')
    before canonicalizing, not after)."""
    base = re.sub(r'\.desktop$', '', desktop_id)
    canonical = re.sub(r'[^a-z0-9-]', '-', base.lower())
    return re.sub(r'-+', '-', canonical)


def _app_settings(desktop_id: str) -> Gio.Settings:
    canonical = _canonicalize_app_id(desktop_id)
    return Gio.Settings.new_with_path(PER_APP_SCHEMA, f'{PER_APP_PATH_ROOT}{canonical}/')


def _register_app(master_settings: Gio.Settings, desktop_id: str):
    """Mirrors NotificationApplicationPolicy.store(): records the app's real
    id on its per-app settings object and lists it in the master schema's
    application-children, so a real notification from this app (and gnome-
    control-center's own Notifications panel, if the user ever opens it)
    resolves to the exact same settings this toggle controls."""
    canonical = _canonicalize_app_id(desktop_id)
    app_settings = _app_settings(desktop_id)
    if app_settings.get_string('application-id') != desktop_id:
        app_settings.set_string('application-id', desktop_id)

    children = master_settings.get_strv('application-children')
    if canonical not in children:
        master_settings.set_strv('application-children', children + [canonical])

    return app_settings


class _AppNotificationRow(Gtk.Box):
    def __init__(self, master_settings: Gio.Settings, app_info: Gio.AppInfo):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        icon = Gtk.Image(gicon=app_info.get_icon())
        icon.set_pixel_size(28)
        self.append(icon)

        self.append(Gtk.Label(label=app_info.get_name(), xalign=0, hexpand=True, valign=Gtk.Align.CENTER))

        self._settings = _register_app(master_settings, app_info.get_id())
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._settings.bind('enable', switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.append(switch)


class NotificationsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(NOTIFICATIONS_SCHEMA)
        self._app_monitor = Gio.AppInfoMonitor.get()
        self._app_monitor_id = self._app_monitor.connect('changed', lambda *_a: self._rebuild_app_list())

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'notifications.svg'), 'preferences-system-notifications-symbolic',
            'Notifications', "Customize when and how notifications appear, and which apps can send them.",
        ))

        top_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        banners_row = ToggleRow('Show notification banners')
        self._settings.bind('show-banners', banners_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        top_card.append(banners_row)

        lock_row = ToggleRow('Show notifications when screen is locked')
        self._settings.bind('show-in-lock-screen', lock_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        top_card.append(lock_row)

        self.append(top_card)

        self.append(Gtk.Label(label='Application Notifications', xalign=0, css_classes=['heading']))

        self._app_list_box = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._app_list_box)

        self.connect('destroy', self._on_destroy)
        self._rebuild_app_list()

    def _rebuild_app_list(self):
        child = self._app_list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._app_list_box.remove(child)
            child = next_child

        apps = sorted(
            (a for a in Gio.AppInfo.get_all() if a.should_show()),
            key=lambda a: a.get_name().lower(),
        )
        for app_info in apps:
            self._app_list_box.append(_AppNotificationRow(self._settings, app_info))

    def _on_destroy(self, _widget):
        if self._app_monitor_id:
            self._app_monitor.disconnect(self._app_monitor_id)
            self._app_monitor_id = 0
