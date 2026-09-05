// lib/powerStatus.js
//
// Watches UPower's DisplayDevice (the same system-wide "the battery" aggregate GNOME's own
// battery indicator reads) for the transition into the Charging state, so the Dynamic Island
// can flash a brief "Charging -- Xh Ym to full" toast the instant a charger is plugged in.
// Real, live D-Bus data (org.freedesktop.UPower on the system bus) -- not a stub.
import Gio from 'gi://Gio';

const UPOWER_BUS_NAME = 'org.freedesktop.UPower';
const DISPLAY_DEVICE_PATH = '/org/freedesktop/UPower/devices/DisplayDevice';
const DEVICE_IFACE = 'org.freedesktop.UPower.Device';

// See UPower's own enums-device-state -- 1 is the only value that means "actively charging".
const STATE_CHARGING = 1;

export function formatTimeToFull(seconds) {
    if (!seconds || seconds <= 0)
        return null;
    const totalMinutes = Math.round(seconds / 60);
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    if (h > 0)
        return m > 0 ? `${h}h ${m}m to full` : `${h}h to full`;
    return `${m}m to full`;
}

export class PowerStatusWatcher {
    constructor(onChargingStarted) {
        this._onChargingStarted = onChargingStarted;
        this._lastState = null;
        this._proxy = null;
        this._signalId = 0;

        try {
            this._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, null,
                UPOWER_BUS_NAME, DISPLAY_DEVICE_PATH, DEVICE_IFACE, null);
            this._lastState = this._proxy.get_cached_property('State')?.unpack() ?? null;
            this._signalId = this._proxy.connect('g-properties-changed', (_proxy, changed) => {
                const dict = changed.deep_unpack();
                if (!('State' in dict))
                    return;
                const newState = dict.State.unpack();
                const wasCharging = this._lastState === STATE_CHARGING;
                this._lastState = newState;
                // Only the *edge* into charging matters -- a toast on every property tick
                // (percentage ticks up every minute or so while already charging) would be
                // exactly the "annoying, always there" pill the user explicitly didn't want.
                if (newState === STATE_CHARGING && !wasCharging) {
                    const timeToFull = this._proxy.get_cached_property('TimeToFull')?.unpack() ?? 0;
                    this._onChargingStarted(timeToFull);
                }
            });
        } catch (e) {
            // No battery (desktop machine) or UPower unavailable -- just means this toast
            // never fires, not worth surfacing as an error.
            logError(e, 'powerStatus: failed to connect to UPower');
        }
    }

    destroy() {
        if (this._signalId && this._proxy)
            this._proxy.disconnect(this._signalId);
        this._signalId = 0;
        this._proxy = null;
    }
}
