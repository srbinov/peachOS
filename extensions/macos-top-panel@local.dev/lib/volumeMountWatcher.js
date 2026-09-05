// lib/volumeMountWatcher.js
//
// Gio.VolumeMonitor's mount-added / mount-removed signals -- the same GVfs monitor Files and
// the shell's own removable-media menu use. Real, live. A USB stick / SD card / external
// drive appearing or being ejected gets a brief Dynamic Island toast.
import Gio from 'gi://Gio';

export class VolumeMountWatcher {
    // callbacks: { onMounted(name), onUnmounted(name) }
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._monitor = Gio.VolumeMonitor.get();
        this._addedId = this._monitor.connect('mount-added', (_m, mount) => {
            // Skip pseudo-mounts that aren't a physical volume (e.g. GVfs network shares
            // mounting at login) -- only announce something the user can actually hold.
            if (!mount.get_volume())
                return;
            this._cb.onMounted?.(mount.get_name());
        });
        this._removedId = this._monitor.connect('mount-removed', (_m, mount) => {
            this._cb.onUnmounted?.(mount.get_name());
        });
    }

    destroy() {
        if (this._monitor) {
            if (this._addedId)
                this._monitor.disconnect(this._addedId);
            if (this._removedId)
                this._monitor.disconnect(this._removedId);
        }
        this._addedId = 0;
        this._removedId = 0;
        this._monitor = null;
    }
}
