// The desktop widget layer: an actor group pinned just above the wallpaper
// (inside Main.layoutManager._backgroundGroup, below every window -- the parent
// azclock uses), the placed WidgetFrames, JSON persistence, and the edit-mode
// dim scrim.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {WidgetFrame} from '../widgets/frame.js';
import {variantDef, sizeFor} from './widgetRegistry.js';

const EDIT_DIM = 40; // scrim opacity (0-255) in edit mode

export class WidgetLayer {
    constructor(settings, ctx) {
        this._settings = settings;
        this._ctx = ctx;
        this._frames = new Map();
        this._editing = false;
        this._lastWritten = null;
        this._raiseId = 0;

        this._layer = new Clutter.Actor({name: 'peachos-widget-layer', reactive: false});
        Main.layoutManager._backgroundGroup.add_child(this._layer);
        this._raise();

        this._dim = new St.Widget({
            style: 'background-color: black;',
            opacity: 0,
            reactive: false,
            visible: false,
        });
        this._layer.add_child(this._dim);
        this._sizeDim();

        Main.layoutManager.connectObject(
            'monitors-changed', () => this._onMonitorsChanged(), this);
        settings.connectObject(
            'changed::widgets', () => {
                // Skip our own writes (Gio.Settings::changed fires async, so a
                // simple in-flight flag would already be cleared).
                if (this._settings.get_string('widgets') !== this._lastWritten)
                    this._reload();
            }, this);

        this._loadFromSettings();
    }

    // --- stacking -----------------------------------------------------------

    _raise() {
        const parent = this._layer.get_parent();
        if (parent)
            parent.set_child_above_sibling(this._layer, null);
    }

    raise() {
        this._raise();
    }

    refreshBackdrops() {
        for (const frame of this._frames.values())
            frame.refreshBackdrop();
    }

    raiseLater() {
        if (this._raiseId)
            return;
        this._raiseId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._raiseId = 0;
            this._raise();
            return GLib.SOURCE_REMOVE;
        });
    }

    _sizeDim() {
        const monitors = Main.layoutManager.monitors;
        let x0 = 0, y0 = 0, x1 = 0, y1 = 0;
        for (const m of monitors) {
            x0 = Math.min(x0, m.x);
            y0 = Math.min(y0, m.y);
            x1 = Math.max(x1, m.x + m.width);
            y1 = Math.max(y1, m.y + m.height);
        }
        this._dim.set_position(x0, y0);
        this._dim.set_size(x1 - x0, y1 - y0);
        this._layer.set_child_below_sibling(this._dim, null);
    }

    // --- persistence ------------------------------------------------------

    _loadFromSettings() {
        let list = [];
        try {
            list = JSON.parse(this._settings.get_string('widgets'));
        } catch (e) {
            logError(e, '[peachos-widgets] bad widgets JSON, starting empty');
        }
        for (const inst of list)
            this._createFrame(inst);
    }

    _reload() {
        for (const frame of this._frames.values())
            frame.destroy();
        this._frames.clear();
        this._loadFromSettings();
        for (const frame of this._frames.values())
            frame.setEditing(this._editing);
    }

    _persist() {
        const list = [...this._frames.values()].map(f => f.instance);
        this._lastWritten = JSON.stringify(list);
        this._settings.set_string('widgets', this._lastWritten);
    }

    // --- placement -------------------------------------------------------

    _createFrame(inst) {
        if (!variantDef(inst.type, inst.variant)) {
            log(`[peachos-widgets] unknown widget ${inst.type}/${inst.variant}, skipping`);
            return null;
        }
        if (!inst.scale)
            inst.scale = 'md';
        if (!inst.mode)
            inst.mode = 'glass';
        const frame = new WidgetFrame(inst, this._ctx, this._layer, {
            onMoved: f => this._onFrameMoved(f),
            onRemove: f => this.removeWidget(f),
            onResized: f => this._onFrameResized(f),
        });
        this._frames.set(inst.id, frame);
        this._placeFrame(frame);
        frame.setEditing(this._editing);
        return frame;
    }

    _placeFrame(frame) {
        const inst = frame.instance;
        const size = sizeFor(inst.type, inst.variant, inst.scale);
        const monitors = Main.layoutManager.monitors;
        const m = monitors[inst.monitor] || Main.layoutManager.primaryMonitor;

        let x = m.x + inst.xRel * m.width;
        let y = m.y + inst.yRel * m.height;
        x = Math.max(m.x + 8, Math.min(m.x + m.width - size.w - 8, x));
        y = Math.max(m.y + 8, Math.min(m.y + m.height - size.h - 8, y));
        frame.setInnerPos(Math.round(x), Math.round(y));
        frame.refreshBackdrop();
    }

    _onFrameResized(frame) {
        this._placeFrame(frame);
        this._onFrameMoved(frame);
    }

    _locate(innerX, innerY) {
        const monitors = Main.layoutManager.monitors;
        let idx = monitors.findIndex(m =>
            innerX >= m.x && innerX < m.x + m.width &&
            innerY >= m.y && innerY < m.y + m.height);
        if (idx < 0)
            idx = Main.layoutManager.primaryIndex;
        const m = monitors[idx];
        return {
            monitor: idx,
            xRel: (innerX - m.x) / m.width,
            yRel: (innerY - m.y) / m.height,
        };
    }

    _onFrameMoved(frame) {
        const r = frame.innerRect();
        Object.assign(frame.instance, this._locate(r.x, r.y));
        this._persist();
    }

    _onMonitorsChanged() {
        this._sizeDim();
        for (const frame of this._frames.values())
            this._placeFrame(frame);
        this.raiseLater();
    }

    // --- public API -----------------------------------------------------

    addWidget(type, variant, stageX, stageY, scale = 'md', mode = 'glass') {
        const size = sizeFor(type, variant, scale);
        if (!size)
            return null;
        const id = `${type}-${variant}-${Date.now().toString(36)}`;
        const inst = {
            id, type, variant, scale, mode,
            ...this._locate(stageX - size.w / 2, stageY - size.h / 2),
        };
        const frame = this._createFrame(inst);
        if (frame)
            this._persist();
        return frame;
    }

    removeWidget(frame) {
        this._frames.delete(frame.instance.id);
        frame.destroy();
        this._persist();
    }

    get layer() {
        return this._layer;
    }

    get count() {
        return this._frames.size;
    }

    setEditing(editing) {
        if (this._editing === editing)
            return;
        this._editing = editing;

        this._dim.remove_all_transitions();
        if (editing) {
            this._sizeDim();
            this._dim.visible = true;
            this._dim.reactive = true;
            this._dim.ease({opacity: EDIT_DIM, duration: 250, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        } else {
            this._dim.reactive = false;
            this._dim.ease({
                opacity: 0, duration: 200, mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onStopped: () => {
                    this._dim.visible = false;
                },
            });
        }

        for (const frame of this._frames.values())
            frame.setEditing(editing);
    }

    destroy() {
        if (this._raiseId) {
            GLib.source_remove(this._raiseId);
            this._raiseId = 0;
        }
        Main.layoutManager.disconnectObject(this);
        this._settings.disconnectObject(this);
        for (const frame of this._frames.values())
            frame.destroy();
        this._frames.clear();
        this._layer.destroy();
        this._layer = null;
    }
}
