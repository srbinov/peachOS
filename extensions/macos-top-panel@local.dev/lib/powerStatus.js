// lib/powerStatus.js
//
// Watches UPower's DisplayDevice (the same system-wide "the battery" aggregate GNOME's own
// battery indicator reads) for three edges worth a brief Dynamic Island toast:
//   - a charger was just plugged in        -> "Charging -- Xh Ym to full"
//   - the battery dropped to a low level   -> "Low Battery -- N%"
//   - the battery finished charging        -> "Fully Charged"
// Real, live D-Bus data (org.freedesktop.UPower on the system bus) -- not a stub.
import Gio from 'gi://Gio';

const UPOWER_BUS_NAME = 'org.freedesktop.UPower';
const DISPLAY_DEVICE_PATH = '/org/freedesktop/UPower/devices/DisplayDevice';
const DEVICE_IFACE = 'org.freedesktop.UPower.Device';

// UPower enums-device-state.
const STATE_CHARGING = 1;
const STATE_FULLY_CHARGED = 4;
// UPower enums-device-warning-level: 3 = Low, 4 = Critical, 5 = Action.
const WARNING_LEVEL_LOW = 3;

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
    // callbacks: { onChargingStarted(timeToFullSeconds), onLowBattery(percent), onFullyCharged() }
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._lastState = null;
        this._lastWarningLevel = null;
        this._proxy = null;
        this._signalId = 0;

        try {
            this._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, null,
                UPOWER_BUS_NAME, DISPLAY_DEVICE_PATH, DEVICE_IFACE, null);
            this._lastState = this._proxy.get_cached_property('State')?.unpack() ?? null;
            this._lastWarningLevel = this._proxy.get_cached_property('WarningLevel')?.unpack() ?? null;
            this._signalId = this._proxy.connect('g-properties-changed', (_proxy, changed) =>
                this._onPropsChanged(changed.deep_unpack()));
        } catch (e) {
            // No battery (desktop machine) or UPower unavailable -- these toasts just never
            // fire, not worth surfacing as an error.
            logError(e, 'powerStatus: failed to connect to UPower');
        }
    }

    _percent() {
        return Math.round(this._proxy.get_cached_property('Percentage')?.unpack() ?? 0);
    }

    _onPropsChanged(dict) {
        if ('State' in dict) {
            const newState = dict.State.unpack();
            const wasCharging = this._lastState === STATE_CHARGING;
            const wasFull = this._lastState === STATE_FULLY_CHARGED;
            this._lastState = newState;

            // Only the *edge* into each state matters -- a toast on every property tick
            // (percentage updates roughly once a minute) would be exactly the "annoying,
            // always there" pill the user explicitly didn't want.
            if (newState === STATE_CHARGING && !wasCharging) {
                const timeToFull = this._proxy.get_cached_property('TimeToFull')?.unpack() ?? 0;
                this._cb.onChargingStarted?.(timeToFull);
            } else if (newState === STATE_FULLY_CHARGED && !wasFull) {
                this._cb.onFullyCharged?.();
            }
        }

        if ('WarningLevel' in dict) {
            const level = dict.WarningLevel.unpack();
            const wasLowOrWorse = this._lastWarningLevel >= WARNING_LEVEL_LOW;
            this._lastWarningLevel = level;
            // Fire once, on the way down past the "low" threshold -- not repeatedly as it
            // keeps dropping through critical/action.
            if (level === WARNING_LEVEL_LOW && !wasLowOrWorse)
                this._cb.onLowBattery?.(this._percent());
        }
    }

    destroy() {
        if (this._signalId && this._proxy)
            this._proxy.disconnect(this._signalId);
        this._signalId = 0;
        this._proxy = null;
    }
}
