// lib/powerProfileWatcher.js
//
// Watches power-profiles-daemon's ActiveProfile (power-saver / balanced / performance) --
// the same daemon and property GNOME's own Quick Settings power toggle drives. Real, live
// D-Bus (net.hadess.PowerProfiles on the system bus). Fires only on a change, never on the
// initial value, so switching profiles gets a brief Dynamic Island toast.
import Gio from 'gi://Gio';

const BUS_NAME = 'net.hadess.PowerProfiles';
const OBJECT_PATH = '/net/hadess/PowerProfiles';
const IFACE = 'net.hadess.PowerProfiles';

const PROFILE_LABELS = {
    'power-saver': 'Power Saver',
    'balanced': 'Balanced',
    'performance': 'Performance',
};

export function powerProfileLabel(id) {
    return PROFILE_LABELS[id] ?? id;
}

export function powerProfileIcon(id) {
    return `power-profile-${id}-symbolic`;
}

export class PowerProfileWatcher {
    constructor(onProfileChanged) {
        this._onProfileChanged = onProfileChanged;
        this._current = null;
        this._proxy = null;
        this._signalId = 0;
        this._destroyed = false;

        // Async + DO_NOT_AUTO_START: power-profiles-daemon is frequently absent (server
        // installs, TLP setups, some laptops). A sync proxy with auto-start there blocks
        // the shell's main loop for the full 25s D-Bus activation timeout -- a hard
        // freeze on first boot. Async means we never block; DO_NOT_AUTO_START means the
        // proxy just reports "no owner" instantly instead of trying to launch it.
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_AUTO_START, null,
            BUS_NAME, OBJECT_PATH, IFACE, null,
            (_src, res) => {
                if (this._destroyed)
                    return;
                let proxy;
                try {
                    proxy = Gio.DBusProxy.new_for_bus_finish(res);
                } catch (e) {
                    logError(e, 'powerProfileWatcher: failed to connect to power-profiles-daemon');
                    return;
                }
                if (!proxy.get_name_owner())
                    return; // p-p-d not running -- toast just never fires
                this._proxy = proxy;
                this._current = proxy.get_cached_property('ActiveProfile')?.unpack() ?? null;
                this._signalId = proxy.connect('g-properties-changed', (_proxy, changed) => {
                    const dict = changed.deep_unpack();
                    if (!('ActiveProfile' in dict))
                        return;
                    const next = dict.ActiveProfile.unpack();
                    if (next === this._current)
                        return;
                    this._current = next;
                    this._onProfileChanged(next);
                });
            });
    }

    destroy() {
        this._destroyed = true;
        if (this._signalId && this._proxy)
            this._proxy.disconnect(this._signalId);
        this._signalId = 0;
        this._proxy = null;
    }
}
