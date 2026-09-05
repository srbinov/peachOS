// lib/bluetoothWatcher.js
//
// Watches BlueZ (org.bluez, system bus) for a device's Connected property flipping, via the
// standard ObjectManager on "/". Real, live data -- the same interface GNOME's own Bluetooth
// menu uses. A paired device connecting or disconnecting gets a brief Dynamic Island toast
// ("<name> connected").
import Gio from 'gi://Gio';

const BLUEZ_NAME = 'org.bluez';
const DEVICE_IFACE = 'org.bluez.Device1';

export class BluetoothWatcher {
    // callbacks: { onConnected(name), onDisconnected(name) }
    constructor(callbacks) {
        this._cb = callbacks || {};
        this._manager = null;
        this._propsId = 0;
        // Track last-known Connected per object path so a properties-changed that merely
        // re-asserts the current value (BlueZ is chatty) doesn't double-fire.
        this._connected = new Map();

        try {
            this._manager = Gio.DBusObjectManagerClient.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusObjectManagerClientFlags.NONE,
                BLUEZ_NAME, '/', null, null);

            for (const obj of this._manager.get_objects()) {
                const iface = obj.get_interface(DEVICE_IFACE);
                if (iface)
                    this._connected.set(obj.get_object_path(), this._isConnected(iface));
            }

            this._propsId = this._manager.connect('interface-proxy-properties-changed',
                (_mgr, _obj, iface, changed) => {
                    if (iface.get_interface_name() !== DEVICE_IFACE)
                        return;
                    const dict = changed.deep_unpack();
                    if (!('Connected' in dict))
                        return;
                    const path = iface.get_object_path();
                    const nowConnected = dict.Connected.unpack();
                    if (this._connected.get(path) === nowConnected)
                        return;
                    this._connected.set(path, nowConnected);
                    const name = this._deviceName(iface);
                    if (nowConnected)
                        this._cb.onConnected?.(name);
                    else
                        this._cb.onDisconnected?.(name);
                });
        } catch (e) {
            // No adapter / BlueZ not running -- toasts just never fire.
            logError(e, 'bluetoothWatcher: failed to connect to BlueZ');
        }
    }

    _isConnected(iface) {
        return Boolean(iface.get_cached_property('Connected')?.unpack());
    }

    _deviceName(iface) {
        return iface.get_cached_property('Alias')?.unpack()
            || iface.get_cached_property('Name')?.unpack()
            || 'Bluetooth device';
    }

    destroy() {
        if (this._manager && this._propsId)
            this._manager.disconnect(this._propsId);
        this._propsId = 0;
        this._manager = null;
        this._connected.clear();
    }
}
