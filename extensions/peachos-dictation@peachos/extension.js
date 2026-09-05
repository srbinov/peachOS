/* Peach Intelligence: hold the configured key, speak, let go -- peachos-dictation-daemon
 * records + transcribes (whisper.cpp, offline) + optionally cleans up with an LLM, sets the
 * clipboard, then calls back into this extension's Paste() to inject the paste keystroke.
 *
 * This side owns everything that has to live inside gnome-shell's own process: the global
 * hotkey (press via Main.wm.addKeybinding, release via a modal grab + key-release-event --
 * see _onHotkeyPressed()'s own comment for why a plain keybinding grab alone can't detect
 * release) and the synthetic Ctrl+V paste (Clutter.VirtualInputDevice, only available
 * in-process -- an ordinary Wayland client can't inject input at all; confirmed live on this
 * machine, `wtype` fails with "Compositor does not support the virtual keyboard protocol").
 *
 * The actual recording/transcribing indicator now lives in macos-top-panel@local.dev's
 * Dynamic Island (lib/dynamicIsland.js) instead of a pill of this extension's own -- this
 * extension just publishes 'recording-state' on its own gsettings and the Dynamic Island
 * watches it. Deliberately gsettings, not a direct cross-extension actor/method reference:
 * these are two independent extensions (each individually enable/disable/reloadable), and a
 * shared, well-typed schema key is a far more decoupled seam than one reaching into the
 * other's live JS objects.
 */
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

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

// How long 'error' stays visible in the Dynamic Island before this settles back to 'idle' on
// its own -- same 1.5s the old floating pill used for the same purpose.
const ERROR_DISPLAY_MS = 1500;

export default class PeachIntelligenceExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._bound = false;
        this._recording = false;
        this._grab = null;
        this._releaseHandlerId = 0;
        this._safetyId = 0;
        this._errorTimeoutId = 0;
        this._grabAnchor = null;
        this._targetWindow = null;

        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, SELF_BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            (connection) => {
                this._exportedObject = Gio.DBusExportedObject.wrapJSObject(SELF_IFACE_XML, this);
                this._exportedObject.export(connection, SELF_OBJECT_PATH);
            }, null, null,
        );

        this._buildGrabAnchor();
        this._setRecordingState('idle');
        this._syncKeybinding();
        this._enabledChangedId = this._settings.connect('changed::dictation-enabled', () => this._syncKeybinding());
    }

    disable() {
        if (this._enabledChangedId) {
            this._settings.disconnect(this._enabledChangedId);
            this._enabledChangedId = 0;
        }
        if (this._errorTimeoutId) {
            GLib.source_remove(this._errorTimeoutId);
            this._errorTimeoutId = 0;
        }
        if (this._recording)
            this._endRecording(false);
        if (this._bound) {
            Main.wm.removeKeybinding('hotkey');
            this._bound = false;
        }
        this._setRecordingState('idle');
        this._grabAnchor?.destroy();
        this._grabAnchor = null;

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

    // Main.wm.addKeybinding only ever fires on PRESS (like any GNOME accelerator/media key --
    // Mutter doesn't deliver a matching release through that API at all). Getting the RELEASE
    // needs the same technique CoverflowAltTab's own switcher.js uses for Alt-Tab's "hold Alt,
    // release to confirm" gesture: take a modal grab on a real, mapped, reactive actor and
    // listen for key-release-event directly on it. The Dynamic Island now owns the VISUAL
    // side of this, so _grabAnchor is invisible -- it exists purely to satisfy pushModal()'s
    // "needs a real actor" requirement.
    _onHotkeyPressed() {
        if (this._recording)
            return;
        this._recording = true;
        this._setRecordingState('listening');

        // The window the user was actually typing into, captured BEFORE anything below
        // touches focus -- see _endRecording()'s own comment for why this is what actually
        // fixes the paste, not just clearing Clutter's stage-level key focus.
        this._targetWindow = global.display.get_focus_window();
        console.log(`peachos-dictation: recording started, target window = ${this._focusedWindowLabel()}`);

        this._grab = Main.pushModal(this._grabAnchor, {actionMode: Shell.ActionMode.NONE});
        global.stage.set_key_focus(this._grabAnchor);
        this._releaseHandlerId = this._grabAnchor.connect('key-release-event', this._onKeyReleaseEvent.bind(this));

        this._safetyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MAX_RECORDING_MS, () => {
            this._safetyId = 0;
            this._endRecording(true);
            return GLib.SOURCE_REMOVE;
        });

        this._callDaemon('StartRecording');
    }

    // The hotkey can be any real accelerator now (Peach Intelligence's own Settings tab uses
    // the exact same ShortcutRow widget peachySearch's shortcut picker does -- a bare
    // modifier, or a full Ctrl/Alt/Super chord), not a fixed list of bare keys, so "released"
    // has two ways to fire: the combo's own base/trigger key comes back up (release D from
    // Ctrl+Alt+D), or -- for a chord -- one of its held modifiers does (release Alt from
    // Ctrl+Alt+D, without D itself ever having been pressed again). The second check reads
    // LIVE modifier state (global.get_pointer(), same call switcher.js uses for Alt-Tab's own
    // release detection) rather than trying to match the released key's own symbol against a
    // specific modifier keyval, since a chord's modifiers were never individually recorded --
    // only their combined Gdk.ModifierType bitmask (hotkey-modifier-mask) was.
    _onKeyReleaseEvent(_actor, event) {
        const triggerKeyval = this._settings.get_int('hotkey-trigger-keyval');
        if (event.get_key_symbol() === triggerKeyval) {
            this._endRecording(true);
            return Clutter.EVENT_STOP;
        }

        const modMask = this._settings.get_int('hotkey-modifier-mask');
        if (modMask !== 0) {
            const [, , mods] = global.get_pointer();
            if ((mods & modMask) !== modMask) {
                this._endRecording(true);
                return Clutter.EVENT_STOP;
            }
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _endRecording(tellDaemon) {
        this._recording = false;
        if (this._safetyId) {
            GLib.source_remove(this._safetyId);
            this._safetyId = 0;
        }
        if (this._releaseHandlerId) {
            this._grabAnchor.disconnect(this._releaseHandlerId);
            this._releaseHandlerId = 0;
        }
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        // global.stage.set_key_focus(null) alone (an earlier fix here) turned out not to be
        // enough -- it only clears Clutter's own stage-level actor focus, a separate thing
        // from Mutter's real window-manager focus (which surface actually receives input at
        // the Wayland level). Nothing here was verified to actually move Mutter's own
        // focused-window state away from the target in the first place, so clearing Clutter's
        // side alone didn't reliably restore where the synthetic Ctrl+V would land.
        //
        // window.focus() directly, NOT Main.activateWindow()/window.activate(): those are the
        // same high-level "the user just switched to this app" call the dock/dash use to
        // decide when to show their own "just activated" feedback -- real bug this caused, an
        // app icon flashing in the dock on every single paste. The target window was already
        // focused, on the current workspace, already raised, right up until this code grabbed
        // focus away from it; it only needs its keyboard focus back, not a full re-activation
        // with every side effect that implies.
        global.stage.set_key_focus(null);
        try {
            this._targetWindow?.focus(global.get_current_time());
        } catch (e) {
            // Window may have closed while recording -- nothing to focus back to, not an error.
        }
        this._targetWindow = null;
        this._setRecordingState('transcribing');
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
        this._setRecordingState('idle');
        // Diagnostic, deliberately left in rather than stripped after debugging -- this fires
        // once per dictation (not a hot path), and confirming which window a paste actually
        // targeted is the fastest way to tell a genuinely-fixed run from a regression here.
        console.log(`peachos-dictation: pasting into ${this._focusedWindowLabel()}`);
        this._injectPaste();
    }

    _focusedWindowLabel() {
        const win = global.display.get_focus_window();
        return win ? (win.get_wm_class() ?? '(no wm_class)') : '(no focused window)';
    }

    Failed(message) {
        logError(new Error(message), 'peachos-dictation daemon');
        this._setRecordingState('error');
        if (this._errorTimeoutId)
            GLib.source_remove(this._errorTimeoutId);
        this._errorTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ERROR_DISPLAY_MS, () => {
            this._errorTimeoutId = 0;
            this._setRecordingState('idle');
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

    _setRecordingState(state) {
        if (this._settings.get_string('recording-state') !== state)
            this._settings.set_string('recording-state', state);
    }

    // ---- Modal-grab anchor (invisible -- see this class's own header comment) --------------

    _buildGrabAnchor() {
        this._grabAnchor = new St.Widget({reactive: true, can_focus: true, opacity: 0});
        Main.layoutManager.addChrome(this._grabAnchor, {affectsStruts: false, trackFullscreen: false});
    }
}
