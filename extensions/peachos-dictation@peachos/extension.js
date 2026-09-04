/* Peach Intelligence: hold the configured key, speak, let go -- peachos-dictation-daemon
 * records + transcribes (whisper.cpp, offline) + optionally cleans up with an LLM, sets the
 * clipboard, then calls back into this extension's Paste() to inject the paste keystroke.
 *
 * This side owns everything that has to live inside gnome-shell's own process: the global
 * hotkey (press via Main.wm.addKeybinding, release via a modal grab + key-release-event --
 * see _onHotkeyPressed()'s own comment for why a plain keybinding grab alone can't detect
 * release), the small recording/transcribing indicator, and the synthetic Ctrl+V paste
 * (Clutter.VirtualInputDevice, only available in-process -- an ordinary Wayland client can't
 * inject input at all; confirmed live on this machine, `wtype` fails with "Compositor does
 * not support the virtual keyboard protocol").
 */
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Keysym name -> Clutter.KEY_* value, for the fixed set of bare push-to-talk keys the
// Settings app's hotkey picker ever writes to the 'hotkey' gsetting (see that schema key's
// own description for why only a single bare key makes sense here). A real accelerator
// parser (Gtk.accelerator_parse / Gdk.keyval_from_name) would work too, but Gdk is never
// imported by any OTHER extension's actual extension.js in this repo -- only their prefs.js
// (a separate, ordinary GTK process) -- gnome-shell's own process isn't a GTK application
// context, so pulling Gdk in here risks it simply not being available. A tiny fixed lookup
// table needs neither.
const KEYSYM_TABLE = {
    Alt_L: 65513, Alt_R: 65514,
    Control_L: 65507, Control_R: 65508,
    Super_L: 65515, Super_R: 65516,
    Caps_Lock: 65509,
};

const DAEMON_BUS_NAME = 'org.peachos.DictationDaemon';
const DAEMON_OBJECT_PATH = '/org/peachos/DictationDaemon';

const SELF_BUS_NAME = 'org.peachos.Dictation';
const SELF_OBJECT_PATH = '/org/peachos/Dictation';
const SELF_IFACE_XML = `
<node>
  <interface name="${SELF_BUS_NAME}">
    <method name="Paste" />
    <method name="Failed">
      <arg type="s" name="message" direction="in" />
    </method>
  </interface>
</node>`;

// Safety backstop, same spirit as dockOrderGuard.js's SAFETY_UNFREEZE_MS: if a release event
// is ever missed (focus stolen mid-hold, a compositor hiccup, ...) this forces the modal grab
// and recording to end instead of leaving the shell stuck refusing every other shortcut.
const MAX_RECORDING_MS = 60000;

export default class PeachIntelligenceExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._bound = false;
        this._recording = false;
        this._grab = null;
        this._releaseHandlerId = 0;
        this._safetyId = 0;
        this._indicator = null;

        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, SELF_BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            (connection) => {
                this._exportedObject = Gio.DBusExportedObject.wrapJSObject(SELF_IFACE_XML, this);
                this._exportedObject.export(connection, SELF_OBJECT_PATH);
            }, null, null,
        );

        this._buildIndicator();
        this._syncKeybinding();
        this._enabledChangedId = this._settings.connect('changed::dictation-enabled', () => this._syncKeybinding());
    }

    disable() {
        if (this._enabledChangedId) {
            this._settings.disconnect(this._enabledChangedId);
            this._enabledChangedId = 0;
        }
        if (this._recording)
            this._endRecording(false);
        if (this._bound) {
            Main.wm.removeKeybinding('hotkey');
            this._bound = false;
        }
        this._indicator?.destroy();
        this._indicator = null;

        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._exportedObject) {
            this._exportedObject.flush();
            this._exportedObject.unexport();
            this._exportedObject = null;
        }
        this._settings = null;
    }

    // ---- Hotkey lifecycle -------------------------------------------------

    _syncKeybinding() {
        const enabled = this._settings.get_boolean('dictation-enabled');
        if (enabled && !this._bound) {
            Main.wm.addKeybinding(
                'hotkey', this._settings,
                Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, Shell.ActionMode.NORMAL,
                () => this._onHotkeyPressed(),
            );
            this._bound = true;
        } else if (!enabled && this._bound) {
            if (this._recording)
                this._endRecording(false);
            Main.wm.removeKeybinding('hotkey');
            this._bound = false;
        }
    }

    _triggerKeyval() {
        const [accel] = this._settings.get_strv('hotkey');
        return KEYSYM_TABLE[accel] ?? 0;
    }

    // Main.wm.addKeybinding only ever fires on PRESS (like any GNOME accelerator/media key --
    // Mutter doesn't deliver a matching release through that API at all). Getting the RELEASE
    // needs the same technique CoverflowAltTab's own switcher.js uses for Alt-Tab's "hold Alt,
    // release to confirm" gesture: take a modal grab on a real, mapped, reactive actor (here,
    // the recording indicator itself -- no throwaway invisible actor needed) and listen for
    // key-release-event directly on it.
    _onHotkeyPressed() {
        if (this._recording)
            return;
        this._recording = true;
        this._showIndicator('listening');

        this._grab = Main.pushModal(this._indicator, {actionMode: Shell.ActionMode.NONE});
        global.stage.set_key_focus(this._indicator);
        this._releaseHandlerId = this._indicator.connect('key-release-event', this._onKeyReleaseEvent.bind(this));

        this._safetyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MAX_RECORDING_MS, () => {
            this._safetyId = 0;
            this._endRecording(true);
            return GLib.SOURCE_REMOVE;
        });

        this._callDaemon('StartRecording');
    }

    _onKeyReleaseEvent(_actor, event) {
        if (event.get_key_symbol() !== this._triggerKeyval())
            return Clutter.EVENT_PROPAGATE;
        this._endRecording(true);
        return Clutter.EVENT_STOP;
    }

    _endRecording(tellDaemon) {
        this._recording = false;
        if (this._safetyId) {
            GLib.source_remove(this._safetyId);
            this._safetyId = 0;
        }
        if (this._releaseHandlerId) {
            this._indicator.disconnect(this._releaseHandlerId);
            this._releaseHandlerId = 0;
        }
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        this._showIndicator('transcribing');
        if (tellDaemon)
            this._callDaemon('StopRecording');
    }

    _callDaemon(method) {
        try {
            const proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, null,
                DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, DAEMON_BUS_NAME, null,
            );
            proxy.call_sync(method, null, Gio.DBusCallFlags.NONE, 2000, null);
        } catch (e) {
            logError(e, `peachos-dictation: ${method} failed`);
            this.Failed(`Couldn't reach the dictation daemon (${e.message})`);
        }
    }

    // ---- Called by peachos-dictation-daemon over D-Bus ---------------------

    Paste() {
        this._hideIndicator();
        this._injectPaste();
    }

    Failed(message) {
        logError(new Error(message), 'peachos-dictation daemon');
        this._showIndicator('error');
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
            this._hideIndicator();
            return GLib.SOURCE_REMOVE;
        });
    }

    _injectPaste() {
        const seat = Clutter.get_default_backend().get_default_seat();
        const virtualDevice = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        virtualDevice.notify_keyval(Clutter.CURRENT_TIME, Clutter.KEY_Control_L, Clutter.KeyState.PRESSED);
        virtualDevice.notify_keyval(Clutter.CURRENT_TIME, Clutter.KEY_v, Clutter.KeyState.PRESSED);
        virtualDevice.notify_keyval(Clutter.CURRENT_TIME, Clutter.KEY_v, Clutter.KeyState.RELEASED);
        virtualDevice.notify_keyval(Clutter.CURRENT_TIME, Clutter.KEY_Control_L, Clutter.KeyState.RELEASED);
    }

    // ---- Indicator ----------------------------------------------------------

    _buildIndicator() {
        this._indicator = new St.BoxLayout({
            style_class: 'peachos-dictation-pill',
            reactive: true,
            can_focus: true,
            visible: false,
            vertical: false,
        });
        this._indicatorIcon = new St.Icon({icon_name: 'audio-input-microphone-symbolic', icon_size: 16});
        this._indicatorLabel = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        this._indicator.add_child(this._indicatorIcon);
        this._indicator.add_child(this._indicatorLabel);
        Main.layoutManager.addChrome(this._indicator, {affectsStruts: false, trackFullscreen: false});
    }

    _showIndicator(state) {
        const label = {listening: 'Listening…', transcribing: 'Transcribing…', error: "Couldn't transcribe"}[state];
        this._indicator.remove_style_class_name('peachos-dictation-pill--listening');
        this._indicator.remove_style_class_name('peachos-dictation-pill--transcribing');
        this._indicator.remove_style_class_name('peachos-dictation-pill--error');
        this._indicator.add_style_class_name(`peachos-dictation-pill--${state}`);
        this._indicatorLabel.set_text(label);
        this._indicator.visible = true;
        this._positionIndicator();
    }

    _hideIndicator() {
        this._indicator.visible = false;
    }

    _positionIndicator() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const [, natHeight] = this._indicator.get_preferred_height(-1);
        const [, natWidth] = this._indicator.get_preferred_width(natHeight);
        this._indicator.set_position(
            monitor.x + Math.round((monitor.width - natWidth) / 2),
            monitor.y + Main.panel.height + 8,
        );
    }
}
