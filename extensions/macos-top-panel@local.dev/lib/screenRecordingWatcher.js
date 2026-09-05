// lib/screenRecordingWatcher.js
//
// Tracks whether GNOME Shell is currently recording the screen, via Main.screenshotUI's own
// `screencast-in-progress` property -- the exact same signal the shell's built-in red
// recording indicator uses. Real, first-party state (this extension runs inside gnome-shell,
// so it just reads it directly). Drives a persistent Dynamic Island pill for the whole
// recording, unlike the one-off toasts.
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export class ScreenRecordingWatcher {
    constructor(onChanged) {
        this._onChanged = onChanged;
        this._ui = Main.screenshotUI ?? null;
        this._notifyId = 0;

        if (this._ui) {
            this._notifyId = this._ui.connect('notify::screencast-in-progress',
                () => this._onChanged(this.isRecording));
        }
    }

    get isRecording() {
        return Boolean(this._ui?.screencast_in_progress);
    }

    destroy() {
        if (this._ui && this._notifyId)
            this._ui.disconnect(this._notifyId);
        this._notifyId = 0;
        this._ui = null;
    }
}
