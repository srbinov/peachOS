import os

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from widgets import make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

MEDIA_KEYS_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys'
KEYBINDING_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
KEYBINDING_PATH = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/ulauncher/'
KEYBINDING_NAME = 'Show peachySearch'
KEYBINDING_COMMAND = '/usr/bin/ulauncher toggle'
DEFAULT_BINDING = '<Primary>space'

# Every GNOME schema that holds real, live keybindings as a plain array-of-strings key
# (as opposed to custom-keybindings, which is relocatable -- handled separately below).
# Scanned generically by key *type* (== 'as'), not by hardcoding key names, so this
# doesn't need updating if GNOME adds/renames keybinding keys in a future version.
FIXED_KEYBINDING_SCHEMAS = [
    'org.gnome.desktop.wm.keybindings',
    'org.gnome.shell.keybindings',
    'org.gnome.mutter.keybindings',
    'org.gnome.mutter.wayland.keybindings',
    'org.gnome.settings-daemon.plugins.media-keys',
]

# Modifier bits that make it into the saved accelerator -- NumLock/CapsLock etc. also
# show up in the raw event state and would otherwise produce a binding that silently
# never matches once the user's lock-key state differs.
_RELEVANT_MODS = (
    Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK
)

# A *global* shortcut needs a real anchor modifier -- Gtk.accelerator_valid() alone
# isn't enough of a check here: it happily accepts a bare key with no modifier at all
# (e.g. plain Space, plain F1) or Shift-only combos, since it's meant for validating
# in-app menu accelerators, not something that hijacks a key everywhere on the system.
# Without this, recording could bind bare Space -- meaning every future press of the
# spacebar toggles peachySearch instead of typing a space, anywhere, in any app.
_REQUIRED_ANCHOR_MODS = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK


def _is_usable_global_accel(keyval, mods):
    return bool(mods & _REQUIRED_ANCHOR_MODS) and Gtk.accelerator_valid(keyval, mods)

# (glyph, mask, the L/R keyvals that hold it down) -- macOS's canonical modifier order
# and glyphs (Control, Option, Shift, Command), matching peachOS's styling elsewhere.
_MOD_GROUPS = [
    ('⌃', Gdk.ModifierType.CONTROL_MASK, {Gdk.KEY_Control_L, Gdk.KEY_Control_R}),
    ('⌥', Gdk.ModifierType.ALT_MASK, {Gdk.KEY_Alt_L, Gdk.KEY_Alt_R}),
    ('⇧', Gdk.ModifierType.SHIFT_MASK, {Gdk.KEY_Shift_L, Gdk.KEY_Shift_R}),
    ('⌘', Gdk.ModifierType.SUPER_MASK, {Gdk.KEY_Super_L, Gdk.KEY_Super_R}),
]
_ALL_MODIFIER_KEYVALS = {kv for _glyph, _mask, keyvals in _MOD_GROUPS for kv in keyvals}

_CHIP_CSS = b"""
.shortcut-chip {
  background-color: alpha(currentColor, 0.14);
  border-radius: 6px;
  padding: 2px 9px;
  margin-top: -4px;
  margin-left: 2px;
  margin-right: 2px;
  font-weight: 600;
  opacity: 0;
}
.shortcut-chip.shown {
  margin-top: 0px;
  opacity: 1;
  transition: opacity 140ms ease-out, margin-top 140ms ease-out;
}
button.shortcut-button.recording {
  background-color: alpha(#0A84FF, 0.14);
  transition: background-color 140ms ease-out;
}
"""


def _accel_matches(binding_str, keyval, mods):
    if not binding_str:
        return False
    ok, b_keyval, b_mods = Gtk.accelerator_parse(binding_str)
    return ok and b_keyval == keyval and b_mods == mods


def find_conflict(keyval, mods):
    """Scan every real keybinding on the system for one that already matches
    (keyval, mods). Returns (human_readable_label, clear_fn) if something else
    already uses it, or (None, None) if it's free. clear_fn(), if called,
    unbinds that other shortcut."""
    schema_source = Gio.SettingsSchemaSource.get_default()

    for schema_id in FIXED_KEYBINDING_SCHEMAS:
        schema = schema_source.lookup(schema_id, True)
        if not schema:
            continue
        settings = Gio.Settings.new(schema_id)
        for key_name in schema.list_keys():
            key_info = schema.get_key(key_name)
            if key_info.get_value_type().dup_string() != 'as':
                continue
            for binding in settings.get_strv(key_name):
                if _accel_matches(binding, keyval, mods):
                    label = key_info.get_summary() or key_name

                    def clear(settings=settings, key_name=key_name, binding=binding):
                        settings.set_strv(key_name, [b for b in settings.get_strv(key_name) if b != binding])

                    return label, clear

    media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
    for path in media_keys.get_strv('custom-keybindings'):
        if path == KEYBINDING_PATH:
            continue  # that's peachySearch's own binding
        custom = Gio.Settings.new_with_path(KEYBINDING_SCHEMA, path)
        if _accel_matches(custom.get_string('binding'), keyval, mods):
            label = custom.get_string('name') or 'a custom shortcut'

            def clear(custom=custom):
                custom.set_string('binding', '')

            return label, clear

    return None, None


class ShortcutRow(Gtk.Box):
    """A title + a button that either shows the current accelerator, or --
    while recording -- a live, animated row of chips for every key currently
    held down. Escape cancels; losing focus (e.g. clicking away) cancels too."""

    def __init__(self, title: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))

        self._recording = False
        self._held_mod_keyvals = set()
        self._on_recorded = None

        self._idle_label = Gtk.Label()
        self._chip_box = Gtk.Box(spacing=0, halign=Gtk.Align.CENTER)

        self.button = Gtk.Button(css_classes=['flat', 'shortcut-button'], valign=Gtk.Align.CENTER, child=self._idle_label)
        self.button.connect('clicked', self.start_recording)
        self.append(self.button)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CHIP_CSS)
        self.button.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        key_controller = Gtk.EventControllerKey()
        # CAPTURE, not the default phase: while recording, this needs first look at every
        # key event, before GTK's own accelerator/mnemonic handling gets a chance to
        # consume it. Alt+<letter> in particular is otherwise intercepted before it ever
        # reaches a bubble-phase handler. (Keys GNOME Shell/Mutter itself grabs globally --
        # Super alone, Alt+Tab, etc. -- never reach any application window at all,
        # regardless of phase; that's a Wayland compositor boundary, not fixable here.)
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect('key-pressed', self._on_key_pressed)
        key_controller.connect('key-released', self._on_key_released)
        self.button.add_controller(key_controller)

        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect('leave', self._on_focus_leave)
        self.button.add_controller(focus_controller)

    def set_accelerator(self, accel_str: str):
        self._recording = False
        self._held_mod_keyvals.clear()
        self.button.remove_css_class('recording')
        self.button.set_child(self._idle_label)
        if accel_str:
            ok, keyval, mods = Gtk.accelerator_parse(accel_str)
            self._idle_label.set_label(Gtk.accelerator_get_label(keyval, mods) if ok else accel_str)
        else:
            self._idle_label.set_label('None')

    def connect_recorded(self, callback):
        """callback(accel_str_or_None) fires once a key combo is recorded, or
        with None if recording was cancelled -- caller should just redisplay
        the real current value in that case, not clear it."""
        self._on_recorded = callback

    def start_recording(self, *_args):
        self._recording = True
        self._held_mod_keyvals.clear()
        self.button.add_css_class('recording')
        self.button.set_child(self._chip_box)
        self._render_chips()
        self.button.grab_focus()

    def _on_focus_leave(self, *_args):
        if self._recording:
            self._cancel_recording()

    def _cancel_recording(self):
        self._recording = False
        self._held_mod_keyvals.clear()
        if self._on_recorded:
            self._on_recorded(None)

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if not self._recording:
            return False
        if keyval == Gdk.KEY_Escape:
            self._cancel_recording()
            return True
        if keyval in _ALL_MODIFIER_KEYVALS:
            self._held_mod_keyvals.add(keyval)
            self._render_chips()
            return True
        mods = state & _RELEVANT_MODS
        if not _is_usable_global_accel(keyval, mods):
            self._flash_hint()
            return True  # missing a real modifier, or not a valid accelerator -- keep listening
        self._finish_recording(keyval, mods)
        return True

    def _on_key_released(self, _controller, keyval, _keycode, _state):
        if self._recording and keyval in self._held_mod_keyvals:
            self._held_mod_keyvals.discard(keyval)
            self._render_chips()
        return False

    def _flash_hint(self):
        """A key was pressed that isn't usable on its own (no Ctrl/Alt/Super held --
        e.g. bare Space, which would otherwise silently swallow every future press of
        the spacebar system-wide). Briefly explain why instead of just ignoring it."""
        self._render_chips(final_label='needs ⌃ ⌥ or ⌘')
        GLib.timeout_add(700, self._clear_hint)

    def _clear_hint(self):
        if self._recording:
            self._render_chips()
        return GLib.SOURCE_REMOVE

    def _finish_recording(self, keyval, mods):
        self._recording = False
        self._render_chips(final_label=Gtk.accelerator_get_label(keyval, 0))
        accel_str = Gtk.accelerator_name(keyval, mods)
        # Hold the fully-assembled combo on screen for a beat before handing off --
        # otherwise it flashes straight to whatever happens next (a saved shortcut, or
        # a conflict dialog) and the animation nobody gets to see it land.
        GLib.timeout_add(220, self._deliver_recorded, accel_str)

    def _deliver_recorded(self, accel_str):
        if self._on_recorded:
            self._on_recorded(accel_str)
        return GLib.SOURCE_REMOVE

    def _add_chip(self, text):
        chip = Gtk.Label(label=text, css_classes=['shortcut-chip'])
        self._chip_box.append(chip)
        GLib.idle_add(chip.add_css_class, 'shown')

    def _render_chips(self, final_label=None):
        child = self._chip_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._chip_box.remove(child)
            child = next_child
        for glyph, _mask, keyvals in _MOD_GROUPS:
            if self._held_mod_keyvals & keyvals:
                self._add_chip(glyph)
        if final_label:
            self._add_chip(final_label)
        elif not self._held_mod_keyvals:
            self._add_chip('Press a key…')


class SpotlightPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
        self._keybinding = Gio.Settings.new_with_path(KEYBINDING_SCHEMA, KEYBINDING_PATH)

        self._build_ui()
        self._ensure_registered()
        self._connect_settings()

    def _build_ui(self):
        # Same file the sidebar row itself uses (main.py's make_sidebar_icon auto-detects
        # data/icons/spotlight.svg by row_id) -- was pointing at the icon-theme name
        # "peachysearch" instead, which resolves to the installed app icon
        # (applications-mode.svg, from the Applications mode-dot), not this file.
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'spotlight.svg'), 'system-search-symbolic', 'peachySearch',
            "peachOS's Spotlight-style app, file, and clipboard launcher.",
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._shortcut_row = ShortcutRow('Keyboard Shortcut')
        self._shortcut_row.connect_recorded(self._on_shortcut_recorded)
        card.append(self._shortcut_row)
        self.append(card)

    def _ensure_registered(self):
        """A fresh/blank system has the custom-keybinding schema instance
        available but nothing pointing GNOME's media-keys daemon at it --
        make sure the path is actually in the enabled list, the command is
        the real toggle invocation (not whatever ulauncher's own first-run
        hotkey setup or an older provisioning pass left behind), and there's
        a sane default binding if the user hasn't set one yet.

        Also self-heals an unsafe binding (bare key, no Ctrl/Alt/Super --
        e.g. plain Space, which swallows every future press of the spacebar
        system-wide) back to the default. The recorder itself can't produce
        one of these any more, but this key is still just a plain GSettings
        string -- anything can write to it directly (gsettings/dconf CLI,
        dconf-editor, a future bug elsewhere), and it should never be
        possible to get stuck with an unusable spacebar just because
        *something* set a bad value outside this page."""
        paths = self._media_keys.get_strv('custom-keybindings')
        if KEYBINDING_PATH not in paths:
            self._media_keys.set_strv('custom-keybindings', [*paths, KEYBINDING_PATH])
        self._keybinding.set_string('command', KEYBINDING_COMMAND)
        self._keybinding.set_string('name', KEYBINDING_NAME)

        if not self._binding_is_safe(self._keybinding.get_string('binding')):
            self._keybinding.set_string('binding', DEFAULT_BINDING)

    @staticmethod
    def _binding_is_safe(binding):
        if not binding:
            return False
        ok, keyval, mods = Gtk.accelerator_parse(binding)
        return ok and _is_usable_global_accel(keyval, mods)

    def _connect_settings(self):
        self._keybinding.connect('changed::binding', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        # Self-heals at any point, not just startup -- the binding is still just a plain
        # GSettings string underneath, writable by anything (gsettings/dconf CLI,
        # dconf-editor, ...), not only this page's own recorder.
        binding = self._keybinding.get_string('binding')
        if not self._binding_is_safe(binding):
            self._keybinding.set_string('binding', DEFAULT_BINDING)  # re-fires changed::binding, safely
            return
        self._shortcut_row.set_accelerator(binding)

    def _on_shortcut_recorded(self, accel_str):
        if accel_str is None:
            self._refresh()  # cancelled -- redisplay the real current value
            return

        ok, keyval, mods = Gtk.accelerator_parse(accel_str)
        label, clear_fn = find_conflict(keyval, mods) if ok else (None, None)
        if label:
            self._show_conflict_dialog(label, clear_fn, accel_str)
        else:
            self._keybinding.set_string('binding', accel_str)

    def _show_conflict_dialog(self, label, clear_fn, accel_str):
        self._refresh()  # put the button back to its real (old) value while the dialog is up
        ok, keyval, mods = Gtk.accelerator_parse(accel_str)
        display = Gtk.accelerator_get_label(keyval, mods) if ok else accel_str

        dialog = Adw.AlertDialog(
            heading='Shortcut Already in Use',
            body=f'“{display}” is already used by “{label}”. Replace it with peachySearch, '
                 'or choose a different shortcut?',
        )
        dialog.add_response('cancel', 'Choose a Different Shortcut')
        dialog.add_response('replace', 'Replace')
        dialog.set_response_appearance('replace', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')

        def on_response(_dialog, response):
            if response == 'replace':
                clear_fn()
                self._keybinding.set_string('binding', accel_str)
            else:
                self._shortcut_row.start_recording()

        dialog.connect('response', on_response)
        dialog.present(self.get_root())
