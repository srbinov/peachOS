import Gio from 'gi://Gio';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// GNOME's own dash.js _redisplay() acknowledges in its own comment that its diffing
// algorithm "assumes only one item is moved at a given time" and that touching several
// items at once can make it "remove all the launchers and add them back in a new order" --
// exactly what peachos-icon-appearance's bulk icon swap does (many apps' resolved
// GDesktopAppInfo change within the same second). macos-dock-2026-peachos wraps that same
// stock dash.js, so it inherits the bug: switching icon appearance reshuffles every pinned
// app on the dock.
//
// There's no way to stop dash.js from doing this from outside GNOME Shell, so this snapshots
// the dock's actual on-screen app order before the change and forces it back after, at the
// Clutter actor level -- which has to happen here, inside the Shell process. Called over
// D-Bus by the Settings app's Appearance page (see appearance_page.py _run_icon_appearance).
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
    // macos-dock wraps stock dash.js: _box children are DashItemContainers whose .child is
    // the DashIcon/AppIcon. Cover both the direct .app and the ._delegate.app shapes.
    const inner = actor.child;
    return inner?.app ?? inner?._delegate?.app ?? actor._delegate?.app ?? null;
}

export class DockOrderGuard {
    constructor() {
        this._snapshot = null;
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            this._onBusAcquired.bind(this), null, null,
        );
    }

    _onBusAcquired(connection) {
        this._exportedObject = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._exportedObject.export(connection, OBJECT_PATH);
    }

    /** macos-dock's own dash box (NOT Main.overview.dash, which is a separate stock dash). */
    _dock() {
        return _findActorByName(Main.layoutManager.uiGroup, DOCK_ACTOR_NAME);
    }

    _dashBox(dock) {
        return dock?.dash?._box ?? null;
    }

    _appChildren(box) {
        return box.get_children().filter(actor => _appOfChild(actor) !== null);
    }

    Snapshot() {
        const box = this._dashBox(this._dock());
        this._snapshot = box
            ? this._appChildren(box).map(actor => _appOfChild(actor).get_id())
            : null;
    }

    Restore() {
        const dock = this._dock();
        const box = this._dashBox(dock);
        if (!box) {
            this._snapshot = null;
            return;
        }

        // Prefer the pre-change on-screen order; fall back to favorite-apps order (which the
        // Settings app restores byte-identical) if the snapshot was missed for any reason.
        let order = this._snapshot;
        if (!order || order.length === 0) {
            try {
                order = new Gio.Settings({schema_id: 'org.gnome.shell'})
                    .get_strv('favorite-apps');
            } catch (e) {
                order = [];
            }
        }
        this._snapshot = null;
        if (order.length === 0)
            return;

        const byId = new Map();
        for (const actor of this._appChildren(box))
            byId.set(_appOfChild(actor).get_id(), actor);

        let index = 0;
        for (const id of order) {
            const actor = byId.get(id);
            if (!actor)
                continue; // not in the dash any more (uninstalled/unpinned) -- skip
            box.set_child_at_index(actor, index);
            index++;
        }

        // macos-dock renders from its own this._icons cache, rebuilt only on
        // Shell.AppSystem/AppFavorites signals -- neither of which set_child_at_index()
        // fires. Invalidate it and redraw.
        if (dock && typeof dock._beginAnimation === 'function') {
            dock._icons = null;
            dock._beginAnimation();
        }
    }

    destroy() {
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
