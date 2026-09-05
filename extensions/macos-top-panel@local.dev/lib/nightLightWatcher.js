// lib/nightLightWatcher.js
//
// Watches gnome-settings-daemon's NightLightActive (org.gnome.SettingsDaemon.Color, session
// bus) -- true exactly when the screen is actually being warmed, whether that's from a manual
// toggle or the schedule kicking in. Real, live. Fires only on a change, so Night Light
// turning on or off gets a brief Dynamic Island toast.
import Gio from 'gi://Gio';

const BUS_NAME = 'org.gnome.SettingsDaemon.Color';
const OBJECT_PATH = '/org/gnome/SettingsDaemon/Color';
const IFACE = 'org.gnome.SettingsDaemon.Color';

export class NightLightWatcher {
    constructor(onChanged) {
        this._onChanged = onChanged;
        this._active = null;
        this._proxy = null;
        this._signalId = 0;

        try {
            this._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, null,
                BUS_NAME, OBJECT_PATH, IFACE, null);
            this._active = Boolean(this._proxy.get_cached_property('NightLightActive')?.unpack());
            this._signalId = this._proxy.connect('g-properties-changed', (_proxy, changed) => {
                const dict = changed.deep_unpack();
                if (!('NightLightActive' in dict))
                    return;
                const next = Boolean(dict.NightLightActive.unpack());
                if (next === this._active)
                    return;
                this._active = next;
                this._onChanged(next);
            });
        } catch (e) {
            logError(e, 'nightLightWatcher: failed to connect to gnome-settings-daemon Color');
        }
    }

    destroy() {
        if (this._signalId && this._proxy)
            this._proxy.disconnect(this._signalId);
        this._signalId = 0;
        this._proxy = null;
    }
}
