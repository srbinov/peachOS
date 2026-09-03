import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// If Restore() never arrives (Settings app died mid-swap), un-freeze anyway after this.
const SAFETY_UNFREEZE_MS = 15000;

// GNOME's own dash.js _redisplay() acknowledges in its own comment that its diffing
// algorithm "assumes only one item is moved at a given time" and that touching several
// items at once can make it "remove all the launchers and add them back in a new order" --
// exactly what peachos-icon-appearance's bulk .desktop rewrite does (every app re-resolves
// its GDesktopAppInfo within the same second). macos-dock-2026-peachos wraps that same
// stock dash.js and rebuilds itself from dash._box's child order on installed-changed, so
// it inherits the scramble: switching icon appearance reshuffles every pinned app.
//
// Fixing the order AFTER the fact leaves a visible 1-3s flicker. Instead this SUPPRESSES
// dash.js's redisplay for the duration of the swap (Snapshot -> Restore, driven over D-Bus
// by the Settings app's Appearance page). dash._box is never reordered, so macos-dock's own
// installed-changed handler -- which still fires, and refreshes the icons -- reads _box in
// its original order and the dock never moves. Restore re-enables redisplay and syncs once.
const BUS_NAME = 'org.peachos.DockOrderGuard';
const OBJECT_PATH = '/org/peachos/DockOrderGuard';
const IFACE_XML = `
<node>
  <interface name="${BUS_NAME}">
    <method name="Snapshot" />
    <method name="Restore" />
  </interface>
</node>`;

// macos-dock's Dock actor sets this as its own name (dock.js _init: name: 'dashtodockContainer').
const DOCK_ACTOR_NAME = 'dashtodockContainer';

function _findActorByName(actor, name) {
    if (actor.name === name)
        return actor;
    for (const child of actor.get_children()) {
        const found = _findActorByName(child, name);
        if (found)
            return found;
    }
    return null;
}

function _appOfChild(actor) {
    const inner = actor.child;
    return inner?.app ?? inner?._delegate?.app ?? actor._delegate?.app ?? null;
}

export class DockOrderGuard {
    constructor() {
        this._dash = null;
        this._origQueueRedisplay = null;
        this._snapshot = null;
        this._safetyId = 0;
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            this._onBusAcquired.bind(this), null, null,
        );
    }

    _onBusAcquired(connection) {
        this._exportedObject = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._exportedObject.export(connection, OBJECT_PATH);
    }

    /** macos-dock's own Dock actor (NOT Main.overview.dash, a separate stock dash). */
    _dock() {
        return _findActorByName(Main.layoutManager.uiGroup, DOCK_ACTOR_NAME);
    }

    _appChildren(box) {
        return box.get_children().filter(actor => _appOfChild(actor) !== null);
    }

    Snapshot() {
        if (this._origQueueRedisplay)
            return; // already guarding (Restore missed) -- keep the first patch

        const dock = this._dock();
        const dash = dock?.dash ?? null;
        if (!dash?._box || typeof dash._queueRedisplay !== 'function')
            return;

        this._dash = dash;
        this._snapshot = this._appChildren(dash._box)
            .map(actor => _appOfChild(actor).get_id());

        // Freeze dash.js's redisplay. installed-changed / AppFavorites 'changed' /
        // app-state-changed all route through _queueRedisplay(); a no-op here means the
        // diff that would scramble _box simply never runs.
        this._origQueueRedisplay = dash._queueRedisplay;
        dash._queueRedisplay = () => {};

        this._safetyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SAFETY_UNFREEZE_MS, () => {
            this._safetyId = 0;
            this._unfreeze();
            return GLib.SOURCE_REMOVE;
        });
    }

    _unfreeze() {
        if (this._dash && this._origQueueRedisplay) {
            try {
                this._dash._queueRedisplay = this._origQueueRedisplay;
            } catch (e) {
                // dash gone
            }
        }
        this._dash = null;
        this._origQueueRedisplay = null;
    }

    Restore() {
        if (this._safetyId) {
            GLib.source_remove(this._safetyId);
            this._safetyId = 0;
        }
        this._unfreeze();

        const dock = this._dock();
        const box = dock?.dash?._box ?? null;
        if (!box) {
            this._snapshot = null;
            return;
        }

        // Belt-and-suspenders: _box should still be in order (redisplay was frozen), but if
        // anything slipped a reorder through, put it back. Prefer the pre-swap order, fall
        // back to favorite-apps (which the Settings app restores byte-identical).
        let order = this._snapshot;
        this._snapshot = null;
        if (!order || order.length === 0) {
            try {
                order = new Gio.Settings({schema_id: 'org.gnome.shell'})
                    .get_strv('favorite-apps');
            } catch (e) {
                order = [];
            }
        }
        if (order.length) {
            const byId = new Map();
            for (const actor of this._appChildren(box))
                byId.set(_appOfChild(actor).get_id(), actor);
            let index = 0;
            for (const id of order) {
                const actor = byId.get(id);
                if (!actor)
                    continue;
                box.set_child_at_index(actor, index);
                index++;
            }
        }

        // Re-sync dash.js now that redisplay is live again (no scramble: _box already
        // matches the favorites order), then make macos-dock re-read icons + order.
        if (dock?.dash && typeof dock.dash._queueRedisplay === 'function')
            dock.dash._queueRedisplay();
        if (dock && typeof dock._beginAnimation === 'function') {
            dock._icons = null;
            dock._beginAnimation();
        }
    }

    destroy() {
        if (this._safetyId) {
            GLib.source_remove(this._safetyId);
            this._safetyId = 0;
        }
        this._unfreeze();
        this._snapshot = null;
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._exportedObject) {
            this._exportedObject.flush();
            this._exportedObject.unexport();
            this._exportedObject = null;
        }
    }
}
