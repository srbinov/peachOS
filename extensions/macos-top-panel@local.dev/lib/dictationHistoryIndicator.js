// lib/dictationHistoryIndicator.js
//
// Top-bar dropdown for Peach Intelligence's last few transcriptions, with a one-click copy
// per entry. peachos-dictation-daemon (a separate Python process) is the one that actually
// writes HISTORY_PATH, appending the final (post-cleanup, if enabled) text of every
// successful transcription -- this only ever reads it, re-read on every menu open (same
// "refresh when the dropdown opens" pattern bluetoothIndicator.js already uses for its own
// device list) rather than a live file-watcher, since a small JSON read on an explicit user
// action is cheap and simple.
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const HISTORY_PATH = GLib.build_filenamev([GLib.get_home_dir(), '.local/share/peachos/dictation-history.json']);
const MAX_SHOWN = 3;
const PREVIEW_MAX_CHARS = 72;

function readHistory() {
    try {
        const file = Gio.File.new_for_path(HISTORY_PATH);
        const [ok, contents] = file.load_contents(null);
        if (!ok)
            return [];
        const parsed = JSON.parse(new TextDecoder().decode(contents));
        return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        return []; // no history yet (ENOENT is normal before the first transcription) or a
                   // malformed file -- either way, an empty list is the safe fallback.
    }
}

function preview(text) {
    const oneLine = text.replace(/\s+/g, ' ').trim();
    return oneLine.length > PREVIEW_MAX_CHARS ? `${oneLine.slice(0, PREVIEW_MAX_CHARS - 1)}…` : oneLine;
}

export const DictationHistoryIndicator = GObject.registerClass(
class DictationHistoryIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.5, 'Peach Intelligence');

        this._icon = new St.Icon({icon_name: 'peachos-dictation-topbar', icon_size: 18});
        this.add_child(this._icon);

        this._emptyItem = new PopupMenu.PopupMenuItem('No transcriptions yet', {reactive: false});
        this.menu.addMenuItem(this._emptyItem);

        this._entriesBox = new St.BoxLayout({vertical: true, x_expand: true});
        this._entriesItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        this._entriesItem.add_child(this._entriesBox);
        this.menu.addMenuItem(this._entriesItem);

        this.menu.connect('open-state-changed', (_menu, isOpen) => {
            if (isOpen)
                this._refresh();
        });
    }

    _refresh() {
        this._entriesBox.destroy_all_children();
        const entries = readHistory().slice(0, MAX_SHOWN);

        this._emptyItem.visible = entries.length === 0;
        this._entriesItem.visible = entries.length > 0;

        for (const entry of entries) {
            const text = typeof entry?.text === 'string' ? entry.text : '';
            if (!text)
                continue;
            this._entriesBox.add_child(this._buildRow(text));
        }
    }

    _buildRow(text) {
        const row = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});

        const label = new St.Label({
            text: preview(text), x_expand: true, y_align: Clutter.ActorAlign.CENTER,
            style_class: 'dictation-history-label',
        });
        label.clutter_text.line_wrap = true;
        row.add_child(label);

        const copyButton = new St.Button({
            style_class: 'dictation-history-copy button flat', can_focus: true, track_hover: true,
        });
        copyButton.set_child(new St.Icon({icon_name: 'edit-copy-symbolic', icon_size: 15}));
        copyButton.connect('clicked', () => {
            St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
            this.menu.close();
        });
        row.add_child(copyButton);

        return row;
    }
});
