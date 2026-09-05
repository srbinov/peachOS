// lib/localSendWatcher.js
//
// LocalSend (the AirDrop-style app already installed via provision.sh) is a Flatpak with only
// `filesystems=xdg-download` access -- it can't write anywhere on the host except ~/Downloads.
// That's real, confirmed (`flatpak info --show-permissions org.localsend.localsend_app`), and
// it means a genuine "a file just arrived" signal is available without touching LocalSend's own
// code at all: watch ~/Downloads for a settled (fully-written) new file, and only treat it as a
// LocalSend receipt if the LocalSend flatpak is actually running at that moment. That second
// check is what keeps this from misfiring on an ordinary browser download; it's a coarse
// approximation (a browser download landing in the same instant LocalSend happens to be idly
// open in the background would still be misread), the same kind of known, accepted imprecision
// as dynamicIsland.js's own WM_CLASS media-focus guess -- there's no finer-grained "who wrote
// this file" signal available on Linux without patching LocalSend itself.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const LOCALSEND_FLATPAK_ID = 'org.localsend.localsend_app';
// Partial-download markers used by browsers and some transfer tools -- if a file with one of
// these suffixes ever settles (it shouldn't, they get renamed away), it's not a finished
// transfer worth announcing.
const IGNORED_SUFFIXES = ['.part', '.tmp', '.crdownload', '.download'];

export class LocalSendWatcher {
    constructor(onReceived) {
        this._onReceived = onReceived;
        this._monitor = null;
        this._changedId = 0;

        try {
            const downloadsPath = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD);
            if (!downloadsPath)
                return;
            const dir = Gio.File.new_for_path(downloadsPath);
            this._monitor = dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
            this._changedId = this._monitor.connect('changed', (_mon, file, _other, eventType) => {
                // CHANGES_DONE_HINT is GFileMonitor's own "writes to this file have settled"
                // signal -- waiting for it (instead of the earlier CREATED event) is what
                // avoids announcing a half-written file mid-transfer.
                if (eventType !== Gio.FileMonitorEvent.CHANGES_DONE_HINT &&
                    eventType !== Gio.FileMonitorEvent.RENAMED)
                    return;
                this._onFileSettled(file);
            });
        } catch (e) {
            logError(e, 'localSendWatcher: failed to watch Downloads');
        }
    }

    _onFileSettled(file) {
        const name = file.get_basename();
        if (!name || IGNORED_SUFFIXES.some(suffix => name.endsWith(suffix)))
            return;
        this._isLocalSendRunning(running => {
            if (running)
                this._onReceived(name);
        });
    }

    _isLocalSendRunning(callback) {
        try {
            const proc = Gio.Subprocess.new(
                ['flatpak', 'ps', '--columns=application'], Gio.SubprocessFlags.STDOUT_PIPE);
            proc.communicate_utf8_async(null, null, (source, result) => {
                try {
                    const [, stdout] = source.communicate_utf8_finish(result);
                    const running = stdout.split('\n').some(line => line.trim() === LOCALSEND_FLATPAK_ID);
                    callback(running);
                } catch (e) {
                    callback(false);
                }
            });
        } catch (e) {
            callback(false);
        }
    }

    destroy() {
        if (this._changedId && this._monitor)
            this._monitor.disconnect(this._changedId);
        this._changedId = 0;
        this._monitor = null;
    }
}
