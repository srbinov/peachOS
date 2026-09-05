"""Peach Intelligence: peachOS's built-in push-to-talk dictation (not an AI assistant --
literally just speech-to-text, Wispr-Flow-style). This page only ever configures things;
the actual hold-key/record/transcribe/paste behavior lives in
extensions/peachos-dictation@peachos (the global hotkey + paste injection, which have to run
inside gnome-shell's own process) and apps/dictation/peachos-dictation-daemon (recording,
whisper.cpp, the optional cleanup pass, the clipboard -- a per-user systemd service).

Dictation itself is fully offline (whisper.cpp) and never needs an API key. An API key here
only ever powers one optional thing: sending the raw transcript to Claude or OpenAI for a
punctuation/grammar/filler-word cleanup pass. Keys are stored in the login keyring via
libsecret -- this is the first thing in peachOS's own Settings app that stores a secret, so
this page is also where that convention gets established: never gsettings/plaintext.
"""
import os

import gi

gi.require_version('Secret', '1')
from gi.repository import Adw, Gio, GLib, Gtk, Secret

from widgets import DropdownRow, ToggleRow, make_hero_header
# Same recorder widget (and conflict scanner) peachySearch's own shortcut picker uses --
# reused directly rather than reimplemented, so "choose any shortcut you want" means the
# exact same capture UX/behavior in both places, not a lookalike with its own quirks.
from spotlight_page import ShortcutRow, accelerator_label, find_conflict, parse_accelerator

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

SETTINGS_SCHEMA_ID = 'org.gnome.shell.extensions.peachos-dictation'

CLEANUP_PROVIDERS = [('Claude (Anthropic)', 'anthropic'), ('OpenAI', 'openai')]

SECRET_SCHEMA = Secret.Schema.new(
    'org.peachos.dictation.ApiKey', Secret.SchemaFlags.NONE,
    {'provider': Secret.SchemaAttributeType.STRING},
)


def _optional_settings(schema_id: str):
    """Same guard appearance_page.py's own _optional_settings() uses -- Gio.Settings.new() on
    a schema that isn't in the global registry aborts the whole process instead of raising, so
    a machine that hasn't re-provisioned since this extension was added would otherwise take
    the entire Settings app down just for opening this one tab."""
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(schema_id, True) is None:
        return None
    return Gio.Settings.new(schema_id)


def _provider_label(provider_id: str) -> str:
    return next((label for label, pid in CLEANUP_PROVIDERS if pid == provider_id), provider_id)


class DictationPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = _optional_settings(SETTINGS_SCHEMA_ID)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'dictation.svg'), 'audio-input-microphone-symbolic',
            'Peach Intelligence',
            'Hold a key, speak, and let go -- your words are transcribed and pasted right '
            'where your cursor is. Runs fully offline; no account or API key required.',
        ))

        if self._settings is None:
            self.append(Gtk.Label(
                label="Peach Intelligence isn't installed on this system yet -- re-run "
                      'provision to add it.',
                wrap=True, css_classes=['dim-label'],
            ))
            return

        self._build_main_card()
        self._build_cleanup_card()

    # ---- Enable + hotkey ----------------------------------------------------

    def _build_main_card(self):
        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        enable_row = ToggleRow(
            'Enable Peach Intelligence',
            'Grabs the key below system-wide while it’s held down.',
        )
        self._settings.bind('dictation-enabled', enable_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(enable_row)

        self._hotkey_row = ShortcutRow('Push-to-Talk Key')
        self._hotkey_row.set_accelerator(self._current_hotkey())
        self._hotkey_row.connect_recorded(self._on_hotkey_recorded)
        card.append(self._hotkey_row)

        self.append(card)
        self.append(Gtk.Label(
            label='Hold the key (or key combo) anywhere -- even outside this app -- speak, '
                  'then let go. The transcript is pasted into whatever has focus.',
            xalign=0, wrap=True, css_classes=['caption', 'dim-label'],
        ))

    def _current_hotkey(self) -> str:
        values = self._settings.get_strv('hotkey')
        return values[0] if values else ''

    def _on_hotkey_recorded(self, accel_str):
        if accel_str is None:
            self._hotkey_row.set_accelerator(self._current_hotkey())  # cancelled -- redisplay the real value
            return
        if accel_str == self._current_hotkey():
            return  # re-recorded the exact same combo -- nothing to check or change

        ok, keyval, mods = parse_accelerator(accel_str)
        label, clear_fn = find_conflict(keyval, mods) if ok else (None, None)
        if label:
            self._show_conflict_dialog(label, clear_fn, accel_str)
        else:
            self._commit_hotkey(accel_str, keyval, mods)

    def _show_conflict_dialog(self, label, clear_fn, accel_str):
        self._hotkey_row.set_accelerator(self._current_hotkey())  # put the row back while the dialog is up
        ok, keyval, mods = parse_accelerator(accel_str)
        display = accelerator_label(keyval, mods) if ok else accel_str

        dialog = Adw.AlertDialog(
            heading='Shortcut Already in Use',
            body=f'“{display}” is already used by “{label}”. Replace it with Peach '
                 'Intelligence, or choose a different shortcut?',
        )
        dialog.add_response('cancel', 'Choose a Different Shortcut')
        dialog.add_response('replace', 'Replace')
        dialog.set_response_appearance('replace', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')

        def on_response(_dialog, response):
            if response == 'replace':
                clear_fn()
                self._commit_hotkey(accel_str, keyval, mods)
            else:
                self._hotkey_row.start_recording()

        dialog.connect('response', on_response)
        dialog.present(self.get_root())

    def _commit_hotkey(self, accel_str, keyval, mods):
        # hotkey-trigger-keyval/hotkey-modifier-mask are the pre-parsed form the extension
        # actually reads (it can't parse an arbitrary accelerator string itself -- see that
        # schema key's own description) -- always written together with 'hotkey', never left
        # to drift out of sync with it.
        self._settings.set_strv('hotkey', [accel_str])
        self._settings.set_int('hotkey-trigger-keyval', keyval)
        self._settings.set_int('hotkey-modifier-mask', int(mods))
        self._hotkey_row.set_accelerator(accel_str)

    # ---- Optional AI cleanup --------------------------------------------------

    def _build_cleanup_card(self):
        self.append(Gtk.Label(label='Cleanup', xalign=0, css_classes=['heading'], margin_top=6))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        cleanup_row = ToggleRow(
            'Clean up transcriptions with AI',
            'Sends the raw transcript to the provider below for punctuation, grammar, and '
            'filler-word cleanup before pasting. Off by default -- without this, the raw '
            'whisper.cpp transcript is pasted exactly as heard.',
        )
        self._settings.bind('cleanup-enabled', cleanup_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(cleanup_row)

        provider_row = DropdownRow('Provider', CLEANUP_PROVIDERS)
        provider_row.set_selected_value(self._settings.get_string('cleanup-provider'))
        card.append(provider_row)

        self.append(card)

        key_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        key_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'],
            margin_start=14, margin_end=14, margin_top=10, margin_bottom=10,
        )
        self._key_title = Gtk.Label(xalign=0, valign=Gtk.Align.CENTER)
        key_row.append(self._key_title)
        self._key_entry = Gtk.PasswordEntry(hexpand=True, show_peek_icon=True, valign=Gtk.Align.CENTER)
        key_row.append(self._key_entry)
        self._key_save_btn = Gtk.Button(label='Save', valign=Gtk.Align.CENTER, css_classes=['suggested-action'])
        self._key_save_btn.connect('clicked', lambda *_a: self._on_save_key())
        key_row.append(self._key_save_btn)
        self._key_remove_btn = Gtk.Button(label='Remove', valign=Gtk.Align.CENTER)
        self._key_remove_btn.connect('clicked', lambda *_a: self._on_remove_key())
        key_row.append(self._key_remove_btn)
        key_card.append(key_row)
        self.append(key_card)

        self._key_status = Gtk.Label(xalign=0, wrap=True, css_classes=['caption', 'dim-label'])
        self.append(self._key_status)

        def on_provider_changed(*_a):
            provider = provider_row.get_selected_value()
            self._settings.set_string('cleanup-provider', provider)
            self._refresh_key_ui(provider)
        provider_row.dropdown.connect('notify::selected', on_provider_changed)

        self._refresh_key_ui(provider_row.get_selected_value())

    def _refresh_key_ui(self, provider: str):
        self._key_title.set_label(f'{_provider_label(provider)} API Key')
        self._key_entry.set_text('')
        has_key = self._provider_has_key(provider)
        self._key_remove_btn.set_visible(has_key)
        self._key_status.set_label(
            f'A {_provider_label(provider)} key is saved in your login keyring.' if has_key
            else f'No {_provider_label(provider)} key saved yet -- cleanup falls back to the '
                 'raw transcript until one is added.'
        )

    def _provider_has_key(self, provider: str) -> bool:
        try:
            return bool(Secret.password_lookup_sync(SECRET_SCHEMA, {'provider': provider}, None))
        except GLib.Error:
            return False

    def _current_provider(self) -> str:
        return self._settings.get_string('cleanup-provider')

    def _on_save_key(self):
        key = self._key_entry.get_text().strip()
        if not key:
            return
        provider = self._current_provider()
        try:
            Secret.password_store_sync(
                SECRET_SCHEMA, {'provider': provider}, Secret.COLLECTION_DEFAULT,
                f'peachOS Peach Intelligence -- {_provider_label(provider)} API key',
                key, None,
            )
        except GLib.Error as e:
            self._key_status.set_label(f"Couldn't save that key: {e.message}")
            return
        self._refresh_key_ui(provider)

    def _on_remove_key(self):
        provider = self._current_provider()
        try:
            Secret.password_clear_sync(SECRET_SCHEMA, {'provider': provider}, None)
        except GLib.Error as e:
            self._key_status.set_label(f"Couldn't remove that key: {e.message}")
            return
        self._refresh_key_ui(provider)
