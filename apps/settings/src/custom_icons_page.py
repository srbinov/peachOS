"""Manage Custom Icons: per-app icon choice for the "Custom" icon-appearance style
(appearance_page.py's icon-style picker). Every installed app gets its own independent
Default / Dark / Custom(-uploaded file) choice here, written to CUSTOM_MANIFEST_PATH --
peachos-icon-appearance's apply_custom() is the only other thing that ever reads it.

This intentionally does NOT auto-generate an icon from anything (no "clear" algorithm, no
tinting) -- Default is the app's own icon untouched, Dark is real curated art (identical to
what the blanket Dark style uses, just opted into per-app), Custom is a real file the user
picked themselves. Same "only real curated art or a real user file, never synthesized" rule
peachos-icon-appearance's own module docstring states.
"""
import json
import os
import re
import shutil
import sys

import gi

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')
ICON_APPEARANCE_SCRIPT = '/usr/lib/peachos/iconmasker/peachos-icon-appearance'

DOCK_ORDER_GUARD_BUS_NAME = 'org.peachos.DockOrderGuard'
DOCK_ORDER_GUARD_OBJECT_PATH = '/org/peachos/DockOrderGuard'

# provision.sh installs the icon-masking tools to this system path; the repo's own
# apps/iconmasker/ is the fallback for running from a dev tree (same pattern avatar_picker.py
# uses for the emoji set).
_SYSTEM_ICONMASKER_DIR = '/usr/lib/peachos/iconmasker'
_DEV_ICONMASKER_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'iconmasker'))
_ICONMASKER_DIR = _SYSTEM_ICONMASKER_DIR if os.path.isdir(_SYSTEM_ICONMASKER_DIR) else _DEV_ICONMASKER_DIR
if _ICONMASKER_DIR not in sys.path:
    sys.path.insert(0, _ICONMASKER_DIR)

from peachos_icon_resolve import resolve_curated_dark, resolve_icon  # noqa: E402

CUSTOM_ICONS_DIR = os.path.expanduser('~/.local/share/peachos/custom-icons')
CUSTOM_MANIFEST_PATH = os.path.join(CUSTOM_ICONS_DIR, 'manifest.json')

PREVIEW_SIZE = 32
LIVE_APPLY_DEBOUNCE_MS = 400


def _load_manifest() -> dict:
    try:
        with open(CUSTOM_MANIFEST_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_manifest(manifest: dict):
    os.makedirs(CUSTOM_ICONS_DIR, exist_ok=True)
    tmp_path = f'{CUSTOM_MANIFEST_PATH}.tmp-{os.getpid()}'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp_path, CUSTOM_MANIFEST_PATH)  # atomic -- apply_custom() never reads a torn file


_SYSTEM_APPLICATIONS_DIR = '/usr/share/applications'
_ICON_LINE_RE = re.compile(r'^Icon=(.*)$')


def _read_icon_line(desktop_path: str):
    try:
        with open(desktop_path, encoding='utf-8', errors='replace') as f:
            in_entry = False
            for line in f:
                line = line.rstrip('\n')
                if line == '[Desktop Entry]':
                    in_entry = True
                    continue
                if line.startswith('[') and line != '[Desktop Entry]':
                    if in_entry:
                        break
                    continue
                if in_entry and (m := _ICON_LINE_RE.match(line)):
                    return m.group(1).strip()
    except OSError:
        pass
    return None


def _icon_value_for(app_info: Gio.AppInfo):
    """The raw Icon= value peachos_icon_resolve.resolve_icon() expects -- an absolute path or
    a themed icon name. Prefers peachOS's own /usr/share/applications/<id>.desktop Icon= (read
    directly) over Gio.AppInfo.get_icon() when that file exists: for a Flatpak app peachOS
    rebrands with a permanent curated override (Calendar, Weather, ...), Gio.AppInfo can
    resolve to the FLATPAK'S OWN shadow .desktop instead -- confirmed on this machine, real
    $XDG_DATA_DIRS lists /var/lib/flatpak/exports/share ahead of /usr/share -- which still
    declares the app's stock themed icon, not peachOS's rebrand. This is exactly the same
    highest-priority-file resolution peachos-icon-appearance's own apply_dark()/apply_custom()
    already use (their SYSTEM_DIRS glob order), so Dark availability here matches what
    actually happens once Custom style is applied. Real bug this fixes: Calendar showed no
    Dark option here despite having curated dark art, because Gio.AppInfo resolved it to the
    Flatpak's own 'org.gnome.Calendar' themed icon instead of the curated override path."""
    desktop_id = app_info.get_id()
    if desktop_id:
        override_path = os.path.join(_SYSTEM_APPLICATIONS_DIR, desktop_id)
        if os.path.isfile(override_path):
            icon_value = _read_icon_line(override_path)
            if icon_value:
                return icon_value

    gicon = app_info.get_icon()
    if gicon is None:
        return None
    if isinstance(gicon, Gio.FileIcon):
        gfile = gicon.get_file()
        return gfile.get_path() if gfile else None
    if isinstance(gicon, Gio.ThemedIcon):
        names = gicon.get_names()
        return names[0] if names else None
    return None


def _load_texture(path: str, size: int):
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
        return Gdk.Texture.new_for_pixbuf(pixbuf)
    except GLib.Error:
        return None


def _call_dock_order_guard(method_name: str):
    """Same fire-and-forget D-Bus call appearance_page.py makes -- duplicated rather than
    imported, these are two separate page modules with independent lifecycles (matching this
    app's own established pattern, see wallpaper_page.py's _current_path() docstring)."""
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            DOCK_ORDER_GUARD_BUS_NAME, DOCK_ORDER_GUARD_OBJECT_PATH, DOCK_ORDER_GUARD_BUS_NAME, None,
        )
        proxy.call_sync(method_name, None, Gio.DBusCallFlags.NONE, 500, None)
    except GLib.Error:
        pass


class _CustomIconRow(Gtk.Box):
    """One installed app: a live icon preview, its name, a Default/Dark/Custom picker, and
    (only once Custom is picked) a button to pick a different file. on_change(desktop_id,
    mode, file_name) fires on every committed choice -- reverted (cancelled file dialog,
    unreadable image) never fires it, so the page's manifest only ever gets real choices."""

    def __init__(self, app_info: Gio.AppInfo, choice: dict, on_change):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        self.app_info = app_info
        self.desktop_id = app_info.get_id()
        self._on_change = on_change

        # Resolved once here and reused for both Dark-availability and the Default preview
        # below -- same source peachos-icon-appearance's own apply_dark()/apply_custom() would
        # resolve for this exact app (see _icon_value_for()'s own docstring for why that's not
        # just Gio.AppInfo.get_icon()).
        icon_value = _icon_value_for(app_info)
        self._source_path, _category = resolve_icon(icon_value) if icon_value else (None, None)
        self._dark_source = resolve_curated_dark(self._source_path) if self._source_path else None

        self._mode = choice.get('mode', 'default') if choice else 'default'
        if self._mode == 'dark' and self._dark_source is None:
            self._mode = 'default'  # art was removed/renamed since this was chosen
        self._file_name = choice.get('file') if choice else None
        if self._mode == 'upload' and not (self._file_name and os.path.isfile(
                os.path.join(CUSTOM_ICONS_DIR, self._file_name))):
            self._mode, self._file_name = 'default', None  # uploaded file went missing
        self._suppress = False

        self._icon_wrap = Gtk.Box(
            css_classes=['scheme-photo'], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self._icon_wrap.set_size_request(PREVIEW_SIZE, PREVIEW_SIZE)
        self._icon_wrap.set_overflow(Gtk.Overflow.HIDDEN)
        self.append(self._icon_wrap)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER, spacing=2)
        info_box.append(Gtk.Label(label=app_info.get_name(), xalign=0))
        self._status_label = Gtk.Label(label='', xalign=0, css_classes=['caption', 'dim-label'])
        info_box.append(self._status_label)
        self.append(info_box)

        toggles = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=0, valign=Gtk.Align.CENTER, css_classes=['linked'])
        self._default_btn = Gtk.ToggleButton(label='Default')
        self._dark_btn = Gtk.ToggleButton(label='Dark', sensitive=self._dark_source is not None)
        self._custom_btn = Gtk.ToggleButton(label='Custom')
        self._dark_btn.set_group(self._default_btn)
        self._custom_btn.set_group(self._default_btn)
        toggles.append(self._default_btn)
        toggles.append(self._dark_btn)
        toggles.append(self._custom_btn)
        self.append(toggles)

        self._choose_btn = Gtk.Button(
            icon_name='document-open-symbolic', valign=Gtk.Align.CENTER, css_classes=['flat'],
            tooltip_text='Choose a different file', visible=self._mode == 'upload')
        self._choose_btn.connect('clicked', lambda *_a: self._pick_file())
        self.append(self._choose_btn)

        {'default': self._default_btn, 'dark': self._dark_btn, 'upload': self._custom_btn}[self._mode].set_active(True)
        self._default_btn.connect('toggled', self._on_toggle, 'default')
        self._dark_btn.connect('toggled', self._on_toggle, 'dark')
        # 'clicked', not 'toggled' -- re-clicking an already-selected Custom must still open
        # the file dialog (to change the file), which a 'toggled' handler would never see
        # since GTK doesn't re-fire toggled for a no-op reselect of the same radio button.
        self._custom_btn.connect('clicked', self._on_custom_clicked)

        self._refresh_preview()
        self._refresh_status()

    def _on_toggle(self, btn, mode):
        if self._suppress or not btn.get_active():
            return
        self._commit(mode, self._file_name if mode == 'upload' else None)

    def _on_custom_clicked(self, _btn):
        if self._suppress:
            return
        self._pick_file()

    def _pick_file(self):
        prior_mode = self._mode
        dialog = Gtk.FileDialog(title=f'Choose an Icon for {self.app_info.get_name()}')
        image_filter = Gtk.FileFilter(name='Images')
        image_filter.add_mime_type('image/png')
        image_filter.add_mime_type('image/svg+xml')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, lambda d, r: self._on_file_chosen(d, r, prior_mode))

    def _on_file_chosen(self, dialog, result, prior_mode):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            gfile = None
        if gfile is None:
            self._revert_toggle(prior_mode)
            return  # cancelled -- leave the previous choice exactly as it was
        src_path = gfile.get_path()
        ext = os.path.splitext(src_path or '')[1].lower()
        if not src_path or ext not in ('.png', '.svg'):
            self._revert_toggle(prior_mode)
            return

        os.makedirs(CUSTOM_ICONS_DIR, exist_ok=True)
        # desktop_id is already a plain, filesystem-safe .desktop filename -- no slug-hashing
        # needed the way peachos-icon-appearance's own generated PNGs use, this file is
        # user-facing (they might go looking for it) and there's exactly one per app.
        file_name = f'{self.desktop_id}{ext}'
        dest_path = os.path.join(CUSTOM_ICONS_DIR, file_name)
        try:
            shutil.copyfile(src_path, dest_path)
        except OSError:
            self._revert_toggle(prior_mode)
            return

        self._commit('upload', file_name)

    def _revert_toggle(self, mode):
        self._suppress = True
        {'default': self._default_btn, 'dark': self._dark_btn, 'upload': self._custom_btn}[mode].set_active(True)
        self._suppress = False

    def _commit(self, mode, file_name):
        self._mode = mode
        self._file_name = file_name
        self._choose_btn.set_visible(mode == 'upload')
        self._refresh_preview()
        self._refresh_status()
        self._on_change(self.desktop_id, mode, file_name)

    def _refresh_preview(self):
        child = self._icon_wrap.get_first_child()
        if child is not None:
            self._icon_wrap.remove(child)

        texture = None
        if self._mode == 'upload' and self._file_name:
            texture = _load_texture(os.path.join(CUSTOM_ICONS_DIR, self._file_name), PREVIEW_SIZE)
        elif self._mode == 'dark' and self._dark_source is not None:
            texture = _load_texture(str(self._dark_source), PREVIEW_SIZE)
        elif self._source_path is not None:
            texture = _load_texture(str(self._source_path), PREVIEW_SIZE)

        if texture is not None:
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_size_request(PREVIEW_SIZE, PREVIEW_SIZE)
        else:
            picture = Gtk.Image(gicon=self.app_info.get_icon())
            picture.set_pixel_size(PREVIEW_SIZE - 4)
        self._icon_wrap.append(picture)

    def _refresh_status(self):
        if self._mode == 'dark':
            self._status_label.set_label('Dark icon')
        elif self._mode == 'upload':
            self._status_label.set_label('Custom icon')
        elif self._dark_source is None:
            self._status_label.set_label('Default icon · no dark art available')
        else:
            self._status_label.set_label('Default icon')


class CustomIconsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._appearance_settings = Gio.Settings.new('org.peachos.appearance')
        self._manifest = _load_manifest()
        self._app_monitor = Gio.AppInfoMonitor.get()
        self._app_monitor_id = self._app_monitor.connect('changed', lambda *_a: self._rebuild_app_list())
        self._apply_source = 0

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'appearance.svg'), 'applications-graphics-symbolic',
            'Custom Icons',
            'Choose the default, dark, or your own icon for each app. '
            'Switch Icon & Widget Style to Custom on the Appearance tab to see it.',
        ))

        self._search_entry = Gtk.SearchEntry(placeholder_text='Search Apps')
        self._search_entry.connect('search-changed', lambda *_a: self._app_list_box.invalidate_filter())
        self.append(self._search_entry)

        self._app_list_box = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._app_list_box.set_filter_func(self._filter_row)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(self._app_list_box)
        self.append(scroller)

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
        seen_ids = set()
        for app_info in apps:
            desktop_id = app_info.get_id()
            if not desktop_id or desktop_id in seen_ids:
                continue
            seen_ids.add(desktop_id)
            row = _CustomIconRow(app_info, self._manifest.get(desktop_id, {}), self._on_row_changed)
            self._app_list_box.append(row)

    def _filter_row(self, listbox_row):
        query = self._search_entry.get_text().strip().lower()
        if not query:
            return True
        return query in listbox_row.get_child().app_info.get_name().lower()

    def _on_row_changed(self, desktop_id, mode, file_name):
        if mode == 'default':
            self._manifest.pop(desktop_id, None)
        elif mode == 'dark':
            self._manifest[desktop_id] = {'mode': 'dark'}
        elif mode == 'upload':
            self._manifest[desktop_id] = {'mode': 'upload', 'file': file_name}
        _save_manifest(self._manifest)
        self._maybe_live_apply()

    def _maybe_live_apply(self):
        # Only bother re-running the apply script if Custom is actually the active style --
        # otherwise this just quietly stages the manifest for whenever the user switches to
        # it (same "configure ahead of time" idea as appearance_page.py's own row here).
        if self._appearance_settings.get_string('icon-style') != 'custom':
            return
        if self._apply_source:
            GLib.source_remove(self._apply_source)
        # Debounced -- rendering is cache-backed and cheap now (see peachos-icon-appearance's
        # own _cached_render docstring), but a user flipping through several apps in a row
        # shouldn't fire a subprocess + dock-guard round trip on every single click.
        self._apply_source = GLib.timeout_add(LIVE_APPLY_DEBOUNCE_MS, self._flush_live_apply)

    def _flush_live_apply(self):
        self._apply_source = 0
        _call_dock_order_guard('Snapshot')
        proc = Gio.Subprocess.new(
            [ICON_APPEARANCE_SCRIPT, 'custom'],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
        )

        def on_done(source, result):
            try:
                source.communicate_utf8_finish(result)
            except GLib.Error:
                pass
            # Same belt-and-suspenders two-shot Restore() appearance_page.py's own icon-style
            # switch uses -- see dockOrderGuard.js for why one shot right after isn't enough.
            for delay in (1800, 3500):
                GLib.timeout_add(delay, lambda: _call_dock_order_guard('Restore') or GLib.SOURCE_REMOVE)

        proc.communicate_utf8_async(None, None, on_done)
        return GLib.SOURCE_REMOVE

    def _on_destroy(self, _widget):
        if self._app_monitor_id:
            self._app_monitor.disconnect(self._app_monitor_id)
            self._app_monitor_id = 0
        if self._apply_source:
            GLib.source_remove(self._apply_source)
            self._apply_source = 0
