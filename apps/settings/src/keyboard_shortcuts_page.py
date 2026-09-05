import os

from gi.repository import Gio, GLib, Gtk

from spotlight_page import (ShortcutRow, accelerator_label, find_conflict, parse_accelerator)
from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

MEDIA_KEYS_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys'
CUSTOM_KEYBINDING_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
CUSTOM_PATH_ROOT = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/'
# peachySearch owns this one (spotlight_page.py) -- never touch it here.
RESERVED_CUSTOM_PATH = f'{CUSTOM_PATH_ROOT}ulauncher/'

# (label, schema_id, key). Every key is an 'as' array; this editor writes a
# single-element list and "Reset" reverts to the schema default.
SHORTCUT_CATEGORIES = [
    ('Launchers', [
        ('Settings', MEDIA_KEYS_SCHEMA, 'control-center'),
        ('Home Folder', MEDIA_KEYS_SCHEMA, 'home'),
        ('Web Browser', MEDIA_KEYS_SCHEMA, 'www'),
        ('Email', MEDIA_KEYS_SCHEMA, 'email'),
        ('Terminal', MEDIA_KEYS_SCHEMA, 'terminal'),
        ('Calculator', MEDIA_KEYS_SCHEMA, 'calculator'),
    ]),
    ('Navigation', [
        ('Switch Applications', 'org.gnome.desktop.wm.keybindings', 'switch-applications'),
        ('Switch Windows', 'org.gnome.desktop.wm.keybindings', 'switch-windows'),
        ('Show All Applications', 'org.gnome.shell.keybindings', 'toggle-application-view'),
        ('Show the Overview', 'org.gnome.shell.keybindings', 'toggle-overview'),
        ('Show the Desktop', 'org.gnome.desktop.wm.keybindings', 'show-desktop'),
        ('Quick Settings', 'org.gnome.shell.keybindings', 'toggle-quick-settings'),
        ('Move to Workspace on the Left', 'org.gnome.desktop.wm.keybindings', 'switch-to-workspace-left'),
        ('Move to Workspace on the Right', 'org.gnome.desktop.wm.keybindings', 'switch-to-workspace-right'),
        ('Move Window One Workspace Left', 'org.gnome.desktop.wm.keybindings', 'move-to-workspace-left'),
        ('Move Window One Workspace Right', 'org.gnome.desktop.wm.keybindings', 'move-to-workspace-right'),
    ]),
    ('Windows', [
        ('Close Window', 'org.gnome.desktop.wm.keybindings', 'close'),
        ('Toggle Fullscreen', 'org.gnome.desktop.wm.keybindings', 'toggle-fullscreen'),
        ('Toggle Maximized', 'org.gnome.desktop.wm.keybindings', 'toggle-maximized'),
        ('Minimize Window', 'org.gnome.desktop.wm.keybindings', 'minimize'),
        ('Tile Window Left', 'org.gnome.mutter.keybindings', 'toggle-tiled-left'),
        ('Tile Window Right', 'org.gnome.mutter.keybindings', 'toggle-tiled-right'),
        ('Move Window', 'org.gnome.desktop.wm.keybindings', 'begin-move'),
        ('Resize Window', 'org.gnome.desktop.wm.keybindings', 'begin-resize'),
    ]),
    ('Screenshots', [
        ('Take Interactive Screenshot', 'org.gnome.shell.keybindings', 'show-screenshot-ui'),
        ('Screenshot the Whole Screen', 'org.gnome.shell.keybindings', 'screenshot'),
        ('Screenshot a Window', 'org.gnome.shell.keybindings', 'screenshot-window'),
        ('Record the Screen', 'org.gnome.shell.keybindings', 'show-screen-recording-ui'),
    ]),
    ('System', [
        ('Lock Screen', MEDIA_KEYS_SCHEMA, 'screensaver'),
        ('Log Out', MEDIA_KEYS_SCHEMA, 'logout'),
        ('Volume Up', MEDIA_KEYS_SCHEMA, 'volume-up'),
        ('Volume Down', MEDIA_KEYS_SCHEMA, 'volume-down'),
        ('Mute', MEDIA_KEYS_SCHEMA, 'volume-mute'),
        ('Play / Pause', MEDIA_KEYS_SCHEMA, 'play'),
        ('Next Track', MEDIA_KEYS_SCHEMA, 'next'),
        ('Previous Track', MEDIA_KEYS_SCHEMA, 'previous'),
    ]),
    ('Typing', [
        ('Switch to Next Input Source', 'org.gnome.desktop.wm.keybindings', 'switch-input-source'),
        ('Switch to Previous Input Source', 'org.gnome.desktop.wm.keybindings', 'switch-input-source-backward'),
    ]),
    ('Accessibility', [
        ('Turn Screen Reader On or Off', MEDIA_KEYS_SCHEMA, 'screenreader'),
        ('Turn Zoom On or Off', MEDIA_KEYS_SCHEMA, 'magnifier'),
        ('Zoom In', MEDIA_KEYS_SCHEMA, 'magnifier-zoom-in'),
        ('Zoom Out', MEDIA_KEYS_SCHEMA, 'magnifier-zoom-out'),
        ('Turn On-Screen Keyboard On or Off', MEDIA_KEYS_SCHEMA, 'on-screen-keyboard'),
    ]),
]


def _schema_has_key(schema_id, key):
    src = Gio.SettingsSchemaSource.get_default()
    schema = src.lookup(schema_id, True)
    return bool(schema and key in schema.list_keys())


class _EditableShortcutRow(Gtk.Box):
    """One curated shortcut: label, its current accelerator (recordable via the
    shared ShortcutRow), and a reset button back to the schema default."""

    def __init__(self, label, schema_id, key, on_changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, css_classes=['network-row'])
        self._settings = Gio.Settings.new(schema_id)
        self._key = key
        self._on_changed = on_changed

        self._recorder = ShortcutRow(label)
        self._recorder.set_hexpand(True)
        self._recorder.connect_recorded(self._on_recorded)
        self.append(self._recorder)

        self._reset_btn = Gtk.Button(icon_name='edit-clear-symbolic', css_classes=['flat'],
                                     valign=Gtk.Align.CENTER, tooltip_text='Reset to default')
        self._reset_btn.connect('clicked', self._on_reset)
        self.append(self._reset_btn)

        self._settings.connect(f'changed::{key}', lambda *_a: self._refresh())
        self._refresh()

    def _current(self):
        values = self._settings.get_strv(self._key)
        return values[0] if values else ''

    def _refresh(self):
        self._recorder.set_accelerator(self._current())
        self._reset_btn.set_sensitive(
            self._settings.get_user_value(self._key) is not None)

    def _on_recorded(self, accel_str):
        if not accel_str:
            self._refresh()
            return
        ok, keyval, mods = parse_accelerator(accel_str)
        label, clear_fn = find_conflict(keyval, mods) if ok else (None, None)
        if label:
            self._prompt_conflict(accel_str, label, clear_fn)
        else:
            self._commit(accel_str)

    def _commit(self, accel_str):
        self._settings.set_strv(self._key, [accel_str])
        self._refresh()
        self._on_changed()

    def _prompt_conflict(self, accel_str, other_label, clear_fn):
        ok, keyval, mods = parse_accelerator(accel_str)
        combo = accelerator_label(keyval, mods) if ok else accel_str
        dialog = Gtk.AlertDialog()
        dialog.set_modal(True)
        dialog.set_message(f'“{combo}” is already used for “{other_label}”')
        dialog.set_detail('Reassign it to this shortcut instead?')
        dialog.set_buttons(['Cancel', 'Reassign'])
        dialog.set_cancel_button(0)
        dialog.set_default_button(1)

        def done(dlg, res):
            try:
                choice = dlg.choose_finish(res)
            except GLib.Error:
                choice = 0
            if choice == 1:
                if clear_fn:
                    clear_fn()
                self._commit(accel_str)
            else:
                self._refresh()

        root = self.get_root()
        dialog.choose(root if isinstance(root, Gtk.Window) else None, None, done)

    def _on_reset(self, _btn):
        self._settings.reset(self._key)
        self._refresh()
        self._on_changed()


class _CustomShortcutDialog(Gtk.Window):
    def __init__(self, parent, on_saved, existing=None):
        super().__init__(title='Custom Shortcut' if existing else 'Add Custom Shortcut',
                         transient_for=parent, modal=True, default_width=400, resizable=False)
        self._on_saved = on_saved
        self._existing = existing

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        self.set_child(box)

        box.append(Gtk.Label(label='Name', xalign=0))
        self._name_entry = Gtk.Entry(placeholder_text='e.g. Open Notes')
        box.append(self._name_entry)

        box.append(Gtk.Label(label='Command', xalign=0))
        self._command_entry = Gtk.Entry(placeholder_text='e.g. gnome-text-editor')
        box.append(self._command_entry)

        self._shortcut_row = ShortcutRow('Shortcut')
        self._shortcut_row.add_css_class('wifi-card')
        self._recorded_accel = ''
        self._shortcut_row.connect_recorded(self._on_recorded)
        box.append(self._shortcut_row)

        if existing:
            self._name_entry.set_text(existing.get_string('name'))
            self._command_entry.set_text(existing.get_string('command'))
            self._recorded_accel = existing.get_string('binding')
            self._shortcut_row.set_accelerator(self._recorded_accel)

        self._error = Gtk.Label(xalign=0, wrap=True, css_classes=['error'], visible=False)
        box.append(self._error)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_a: self.close())
        save = Gtk.Button(label='Save', css_classes=['suggested-action'])
        save.connect('clicked', self._on_save)
        buttons.append(cancel)
        buttons.append(save)
        box.append(buttons)

    def _on_recorded(self, accel_str):
        if accel_str:
            self._recorded_accel = accel_str
        self._shortcut_row.set_accelerator(self._recorded_accel)

    def _on_save(self, _btn):
        name = self._name_entry.get_text().strip()
        command = self._command_entry.get_text().strip()
        if not name or not command or not self._recorded_accel:
            self._error.set_label('Fill in a name, a command, and a shortcut.')
            self._error.set_visible(True)
            return
        self._on_saved(name, command, self._recorded_accel, self._existing)
        self.close()


class KeyboardShortcutsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'keyboard.svg'), 'input-keyboard-symbolic',
            'Keyboard Shortcuts', 'View and change the shortcuts for common actions, and add your own.',
        ))

        for title, shortcuts in SHORTCUT_CATEGORIES:
            rows = [(label, schema, key) for label, schema, key in shortcuts
                    if _schema_has_key(schema, key)]
            if not rows:
                continue
            self.append(Gtk.Label(label=title, xalign=0, css_classes=['heading'], margin_start=4))
            card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
            for label, schema, key in rows:
                card.append(_EditableShortcutRow(label, schema, key, self._noop))
            self.append(card)

        # ---- Custom shortcuts ----
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.append(Gtk.Label(label='Custom Shortcuts', xalign=0, hexpand=True,
                                css_classes=['heading'], margin_start=4))
        add_btn = Gtk.Button(icon_name='list-add-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)
        add_btn.connect('clicked', lambda *_a: self._open_custom_dialog(None))
        header.append(add_btn)
        self.append(header)

        self._custom_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._custom_card)
        self._custom_empty = Gtk.Label(
            label='No custom shortcuts yet.', xalign=0, css_classes=['dim-label', 'caption'], margin_start=4)
        self.append(self._custom_empty)

        self._rebuild_custom_list()

    def _noop(self):
        pass

    # ---- custom shortcuts -------------------------------------------

    def _custom_paths(self):
        return [p for p in self._media_keys.get_strv('custom-keybindings') if p != RESERVED_CUSTOM_PATH]

    def _rebuild_custom_list(self):
        child = self._custom_card.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._custom_card.remove(child)
            child = nxt

        paths = self._custom_paths()
        self._custom_card.set_visible(bool(paths))
        self._custom_empty.set_visible(not paths)

        for path in paths:
            settings = Gio.Settings.new_with_path(CUSTOM_KEYBINDING_SCHEMA, path)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
            row.set_margin_start(14)
            row.set_margin_end(8)
            row.set_margin_top(8)
            row.set_margin_bottom(8)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
            text.append(Gtk.Label(label=settings.get_string('name') or 'Untitled', xalign=0))
            text.append(Gtk.Label(label=settings.get_string('command'), xalign=0,
                                  css_classes=['caption', 'dim-label']))
            row.append(text)

            binding = settings.get_string('binding')
            ok, keyval, mods = parse_accelerator(binding)
            row.append(Gtk.Label(label=accelerator_label(keyval, mods) if ok and binding else 'Disabled',
                                 css_classes=['dim-label']))

            edit_btn = Gtk.Button(icon_name='document-edit-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)
            edit_btn.connect('clicked', lambda _b, s=settings: self._open_custom_dialog(s))
            row.append(edit_btn)
            del_btn = Gtk.Button(icon_name='user-trash-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)
            del_btn.connect('clicked', lambda _b, p=path: self._delete_custom(p))
            row.append(del_btn)

            self._custom_card.append(row)

    def _open_custom_dialog(self, existing):
        root = self.get_root()
        dialog = _CustomShortcutDialog(root if isinstance(root, Gtk.Window) else None,
                                       self._save_custom, existing)
        dialog.present()

    def _save_custom(self, name, command, binding, existing):
        if existing is not None:
            existing.set_string('name', name)
            existing.set_string('command', command)
            existing.set_string('binding', binding)
            self._rebuild_custom_list()
            return
        paths = self._media_keys.get_strv('custom-keybindings')
        index = 0
        while f'{CUSTOM_PATH_ROOT}custom{index}/' in paths:
            index += 1
        new_path = f'{CUSTOM_PATH_ROOT}custom{index}/'
        settings = Gio.Settings.new_with_path(CUSTOM_KEYBINDING_SCHEMA, new_path)
        settings.set_string('name', name)
        settings.set_string('command', command)
        settings.set_string('binding', binding)
        self._media_keys.set_strv('custom-keybindings', paths + [new_path])
        self._rebuild_custom_list()

    def _delete_custom(self, path):
        settings = Gio.Settings.new_with_path(CUSTOM_KEYBINDING_SCHEMA, path)
        for key in ('name', 'command', 'binding'):
            settings.reset(key)
        self._media_keys.set_strv(
            'custom-keybindings', [p for p in self._media_keys.get_strv('custom-keybindings') if p != path])
        self._rebuild_custom_list()
