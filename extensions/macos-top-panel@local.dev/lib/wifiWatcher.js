// lib/wifiWatcher.js
//
// Watches NetworkManager's active connections (org.freedesktop.NetworkManager, system bus)
// for a Wi-Fi connection ("802-11-wireless") coming up or going away, and reports the
// network name. Same live source GNOME's own Wi-Fi menu reflects; a connect/disconnect
// gets a brief Dynamic Island toast ("Connected to <ssid>" / "Disconnected from <ssid>").
//
// Modelled on vpnWatcher.js -- and, like it, every proxy is DO_NOT_AUTO_START so a missing
// NetworkManager fails fast instead of blocking the shell main loop on service activation
// (see the BT-less freeze lesson in peachos-iso-build).
import Gio from 'gi://Gio';

const NM_NAME = 'org.freedesktop.NetworkManager';
const NM_PATH = '/org/freedesktop/NetworkManager';
const NM_IFACE = 'org.freedesktop.NetworkManager';
const ACTIVE_IFACE = 'org.freedesktop.NetworkManager.Connection.Active';

const WIFI_TYPE = '802-11-wireless';

export class WifiWatcher {
    // callbacks: { onConnected(ssid), onDisconnected(ssid) }
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._proxy = null;
        this._signalId = 0;
        // path -> connection Id, for the Wi-Fi connections currently active.
        this._active = new Map();

        try {
            this._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_AUTO_START, null,
                NM_NAME, NM_PATH, NM_IFACE, null);
            this._refresh(true);
            this._signalId = this._proxy.connect('g-properties-changed', (_proxy, changed) => {
                if ('ActiveConnections' in changed.deep_unpack())
                    this._refresh(false);
            });
        } catch (e) {
            logError(e, 'wifiWatcher: failed to connect to NetworkManager');
        }
    }

    _activeConnectionPaths() {
        return this._proxy.get_cached_property('ActiveConnections')?.deep_unpack() ?? [];
    }

    _connProxy(path) {
        return Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_AUTO_START, null,
            NM_NAME, path, ACTIVE_IFACE, null);
    }

    _refresh(silent) {
        const seen = new Map();
        for (const path of this._activeConnectionPaths()) {
            try {
                const conn = this._connProxy(path);
                const type = conn.get_cached_property('Type')?.unpack() ?? '';
                if (type !== WIFI_TYPE)
                    continue;
                seen.set(path, conn.get_cached_property('Id')?.unpack() || 'Wi-Fi');
            } catch (e) {
                // Connection vanished between listing and querying -- ignore.
            }
        }

        if (!silent) {
            for (const [path, name] of seen)
                if (!this._active.has(path))
                    this._cb.onConnected?.(name);
            for (const [path, name] of this._active)
                if (!seen.has(path))
                    this._cb.onDisconnected?.(name);
        }
        this._active = seen;
    }

    destroy() {
        if (this._signalId && this._proxy)
            this._proxy.disconnect(this._signalId);
        this._signalId = 0;
        this._proxy = null;
        this._active.clear();
    }
}
