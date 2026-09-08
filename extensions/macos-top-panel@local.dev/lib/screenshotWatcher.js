// lib/screenshotWatcher.js
//
// Watches the Screenshots folder (XDG Pictures dir + /Screenshots, where GNOME Shell saves
// captures) for a new file. Real -- it's just a directory monitor, same technique as
// localSendWatcher.js. A screenshot or a finished screen recording landing there gets a
// brief Dynamic Island toast.
//
// A screenshot PNG is written in one shot, so we fire on CREATED/RENAMED immediately --
// waiting for CHANGES_DONE_HINT (GLib's settle timer) added a visible 1-2s lag after the
// capture. A screen recording grows over its whole duration, so for videos we still wait
// for CHANGES_DONE_HINT (which fires once the file stops changing == recording stopped).
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const VIDEO_SUFFIXES = ['.webm', '.mp4', '.mkv', '.ogv'];
const DEDUPE_MS = 2000;

export class ScreenshotWatcher {
    // callbacks: { onCaptured(kind) } where kind is 'screenshot' | 'recording'
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._monitor = null;
        this._changedId = 0;
        this._recent = new Map();   // basename -> dedupe timeout id

        try {
            const pics = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES);
            if (!pics)
                return;
            const dir = Gio.File.new_for_path(GLib.build_filenamev([pics, 'Screenshots']));
            // GNOME creates the folder the first time it saves there; monitor it even if it
            // doesn't exist yet -- Gio.FileMonitor on a not-yet-existing dir starts reporting
            // once it appears.
            this._monitor = dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._changedId = this._monitor.connect(
                'changed', (_mon, file, other, eventType) => this._onChanged(file, other, eventType));
        } catch (e) {
            logError(e, 'screenshotWatcher: failed to watch the Screenshots folder');
        }
    }

    _onChanged(file, other, eventType) {
        const E = Gio.FileMonitorEvent;
        // RENAMED can carry the interesting name in either arg depending on GLib version;
        // the temp file GIO renames from is a dotfile, so skip those.
        const name = [file?.get_basename(), other?.get_basename()]
            .find(n => n && !n.startsWith('.')) || '';
        if (!name)
            return;

        const isVideo = VIDEO_SUFFIXES.some(s => name.toLowerCase().endsWith(s));
        const fire = isVideo
            ? eventType === E.CHANGES_DONE_HINT || eventType === E.RENAMED
            : eventType === E.CREATED || eventType === E.RENAMED || eventType === E.MOVED_IN;
        if (!fire)
            return;

        // One atomic save can surface as CREATED then RENAMED (or a burst of CHANGED);
        // collapse everything for the same file within DEDUPE_MS to one toast.
        if (this._recent.has(name))
            return;
        this._recent.set(name, GLib.timeout_add(GLib.PRIORITY_DEFAULT, DEDUPE_MS, () => {
            this._recent.delete(name);
            return GLib.SOURCE_REMOVE;
        }));

        this._cb.onCaptured?.(isVideo ? 'recording' : 'screenshot');
    }

    destroy() {
        if (this._monitor && this._changedId)
            this._monitor.disconnect(this._changedId);
        this._changedId = 0;
        this._monitor = null;
        for (const id of this._recent.values())
            GLib.source_remove(id);
        this._recent.clear();
    }
}
