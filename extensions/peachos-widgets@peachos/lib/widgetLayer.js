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

const EDIT_DIM = 40;      // scrim opacity (0-255) in edit mode
const GAP = 8;           // hard minimum gap between any two widgets
const SNAP = 13;         // distance within which a drag snaps to that gap / an edge
// Placeable area, from the two reference widgets the user positioned:
const TOP_MARGIN = 48;   // highest a widget can sit (clears the top bar)
const BOTTOM_MARGIN = 116; // lowest a widget's bottom edge can reach (clears the dock)
const EDGE = 8;          // left / right margin

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
        delete inst.scale;
        if (!inst.mode)
            inst.mode = 'glass';
        const frame = new WidgetFrame(inst, this._ctx, this._layer, {
            onMoved: f => this._onFrameMoved(f),
            onRemove: f => this.removeWidget(f),
            onResized: f => this._onFrameResized(f),
            onConfigured: () => this._persist(),
            snap: (id, x, y, w, hh) => this.snapPosition(id, x, y, w, hh),
        });
        this._frames.set(inst.id, frame);
        this._placeFrame(frame);
        frame.setEditing(this._editing);
        return frame;
    }

    _placeFrame(frame) {
        const inst = frame.instance;
        const size = sizeFor(inst.type, inst.variant);
        const monitors = Main.layoutManager.monitors;
        const m = monitors[inst.monitor] || Main.layoutManager.primaryMonitor;

        let x = m.x + inst.xRel * m.width;
        let y = m.y + inst.yRel * m.height;
        x = Math.max(m.x + EDGE, Math.min(m.x + m.width - size.w - EDGE, x));
        y = Math.max(m.y + TOP_MARGIN, Math.min(m.y + m.height - size.h - BOTTOM_MARGIN, y));
        frame.setInnerPos(Math.round(x), Math.round(y));
        frame.refreshBackdrop();
    }

    _onFrameResized(frame) {
        // The frame kept its top-left through the resize; clamp + push it out
        // of any collision at the new size, then persist.
        const inst = frame.instance;
        const r = frame.innerRect();
        const sn = this.snapPosition(inst.id, r.x, r.y, r.w, r.h);
        frame.setInnerPos(sn.x, sn.y);
        frame.refreshBackdrop();
        Object.assign(inst, this._locate(sn.x, sn.y));
        this._persist();
    }

    // Clamp to the work area (never above TOP_MARGIN) and snap a dragged
    // widget so it keeps a consistent GAP to -- or aligns an edge with -- any
    // other widget it overlaps on the perpendicular axis.
    snapPosition(exceptId, x, y, w, h) {
        const monitors = Main.layoutManager.monitors;
        const cx = x + w / 2;
        const cy = y + h / 2;
        const m = monitors.find(mm =>
            cx >= mm.x && cx < mm.x + mm.width && cy >= mm.y && cy < mm.y + mm.height)
            || Main.layoutManager.primaryMonitor;

        const clampX = v => Math.max(m.x + EDGE, Math.min(m.x + m.width - w - EDGE, v));
        const clampY = v => Math.max(m.y + TOP_MARGIN, Math.min(m.y + m.height - h - BOTTOM_MARGIN, v));
        x = clampX(x);
        y = clampY(y);

        const others = [...this._frames.values()]
            .filter(f => f.instance.id !== exceptId)
            .map(f => f.innerRect());

        let bestDX = SNAP + 1;
        let bestDY = SNAP + 1;
        let snapX = x;
        let snapY = y;
        for (const o of others) {
            const overlapY = y < o.y + o.h + GAP && y + h + GAP > o.y;
            const overlapX = x < o.x + o.w + GAP && x + w + GAP > o.x;
            if (overlapY) {
                for (const c of [o.x + o.w + GAP, o.x - GAP - w, o.x, o.x + o.w - w]) {
                    const d = Math.abs(c - x);
                    if (d < bestDX) {
                        bestDX = d;
                        snapX = c;
                    }
                }
            }
            if (overlapX) {
                for (const c of [o.y + o.h + GAP, o.y - GAP - h, o.y, o.y + o.h - h]) {
                    const d = Math.abs(c - y);
                    if (d < bestDY) {
                        bestDY = d;
                        snapY = c;
                    }
                }
            }
        }
        if (bestDX <= SNAP)
            x = snapX;
        if (bestDY <= SNAP)
            y = snapY;

        // Hard collision resolution: no two widgets may be closer than GAP.
        // Push the dragged widget out along its axis of least penetration.
        for (let iter = 0; iter < 12; iter++) {
            let moved = false;
            for (const o of others) {
                const ox1 = o.x - GAP;
                const oy1 = o.y - GAP;
                const ox2 = o.x + o.w + GAP;
                const oy2 = o.y + o.h + GAP;
                if (x < ox2 && x + w > ox1 && y < oy2 && y + h > oy1) {
                    const pushL = x + w - ox1;
                    const pushR = ox2 - x;
                    const pushU = y + h - oy1;
                    const pushD = oy2 - y;
                    const min = Math.min(pushL, pushR, pushU, pushD);
                    if (min === pushL)
                        x = clampX(x - pushL);
                    else if (min === pushR)
                        x = clampX(x + pushR);
                    else if (min === pushU)
                        y = clampY(y - pushU);
                    else
                        y = clampY(y + pushD);
                    moved = true;
                }
            }
            if (!moved)
                break;
        }

        return {x: Math.round(clampX(x)), y: Math.round(clampY(y))};
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

    addWidget(type, variant, stageX, stageY, mode = 'glass') {
        const size = sizeFor(type, variant);
        if (!size)
            return null;
        const id = `${type}-${variant}-${Date.now().toString(36)}`;
        const inst = {
            id, type, variant, mode,
            ...this._locate(stageX - size.w / 2, stageY - size.h / 2),
        };
        const frame = this._createFrame(inst);
        if (frame) {
            const r = frame.innerRect();
            const sn = this.snapPosition(inst.id, r.x, r.y, r.w, r.h);
            frame.setInnerPos(sn.x, sn.y);
            frame.refreshBackdrop();
            Object.assign(inst, this._locate(sn.x, sn.y));
            this._persist();
        }
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

    get ctx() {
        return this._ctx;
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
