// lib/screenshotWatcher.js
//
// Watches the Screenshots folder (XDG Pictures dir + /Screenshots, where GNOME Shell saves
// captures) for a new settled file. Real -- it's just a directory monitor, same technique as
// localSendWatcher.js. A screenshot or a finished screen recording landing there gets a brief
// Dynamic Island toast.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const VIDEO_SUFFIXES = ['.webm', '.mp4', '.mkv', '.ogv'];

export class ScreenshotWatcher {
    // callbacks: { onCaptured(kind) } where kind is 'screenshot' | 'recording'
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._monitor = null;
        this._changedId = 0;

        try {
            const pics = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES);
            if (!pics)
                return;
            const dir = Gio.File.new_for_path(GLib.build_filenamev([pics, 'Screenshots']));
            // GNOME creates the folder the first time it saves there; monitor it even if it
            // doesn't exist yet -- Gio.FileMonitor on a not-yet-existing dir starts reporting
            // once it appears.
            this._monitor = dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._changedId = this._monitor.connect('changed', (_mon, file, _other, eventType) => {
                if (eventType !== Gio.FileMonitorEvent.CHANGES_DONE_HINT &&
                    eventType !== Gio.FileMonitorEvent.RENAMED)
                    return;
                const name = file.get_basename() || '';
                if (name.startsWith('.'))
                    return;
                const isVideo = VIDEO_SUFFIXES.some(s => name.toLowerCase().endsWith(s));
                this._cb.onCaptured?.(isVideo ? 'recording' : 'screenshot');
            });
        } catch (e) {
            logError(e, 'screenshotWatcher: failed to watch the Screenshots folder');
        }
    }

    destroy() {
        if (this._monitor && this._changedId)
            this._monitor.disconnect(this._changedId);
        this._changedId = 0;
        this._monitor = null;
    }
}
