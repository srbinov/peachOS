// The desktop widget layer: an actor group pinned just above the wallpaper
// (inside Main.layoutManager._backgroundGroup, below every window -- the parent
// azclock uses), the placed WidgetFrames, JSON persistence, and the edit-mode
// dim scrim.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {WidgetFrame} from '../widgets/frame.js';
import {variantDef, sizeFor, UNIT, ROW_GAP} from './widgetRegistry.js';

const EDIT_DIM = 40;      // scrim opacity (0-255) in edit mode
const GAP = ROW_GAP;     // gap between any two widgets (also the grid gutter)
const CELL = UNIT + GAP; // one grid cell = a square widget + its gutter
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

        const x = m.x + inst.xRel * m.width;
        const y = m.y + inst.yRel * m.height;
        const sn = this.snapPosition(inst.id, x, y, size.w, size.h);
        frame.setInnerPos(sn.x, sn.y);
        frame.refreshBackdrop();
        Object.assign(inst, this._locate(sn.x, sn.y));
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

    // Snap a widget onto the invisible desktop grid: cells of CELL px, origin
    // at (EDGE, TOP_MARGIN) per monitor. A square widget is 1x1 cell, a row
    // widget 2x1. The dragged widget lands on the nearest free cell block to
    // where it was let go; if that block is taken, the closest free one.
    snapPosition(exceptId, x, y, w, h) {
        const monitors = Main.layoutManager.monitors;
        const cx = x + w / 2;
        const cy = y + h / 2;
        const m = monitors.find(mm =>
            cx >= mm.x && cx < mm.x + mm.width && cy >= mm.y && cy < mm.y + mm.height)
            || Main.layoutManager.primaryMonitor;

        const originX = m.x + EDGE;
        const originY = m.y + TOP_MARGIN;
        const cols = Math.max(1, Math.floor((m.width - 2 * EDGE + GAP) / CELL));
        const rows = Math.max(1, Math.floor(
            (m.height - TOP_MARGIN - BOTTOM_MARGIN + GAP) / CELL));

        const spanOf = px => Math.max(1, Math.round((px + GAP) / CELL));
        const cs = Math.min(cols, spanOf(w));
        const rs = Math.min(rows, spanOf(h));

        const cellOf = (v, origin) => Math.round((v - origin) / CELL);
        const clampCol = c => Math.max(0, Math.min(cols - cs, c));
        const clampRow = r => Math.max(0, Math.min(rows - rs, r));
        const wantCol = clampCol(cellOf(x, originX));
        const wantRow = clampRow(cellOf(y, originY));

        // Cells occupied by the other widgets on this monitor.
        const taken = new Set();
        for (const f of this._frames.values()) {
            if (f.instance.id === exceptId)
                continue;
            const r = f.innerRect();
            if (r.x + r.w / 2 < m.x || r.x + r.w / 2 >= m.x + m.width)
                continue;
            const oc = cellOf(r.x, originX);
            const or = cellOf(r.y, originY);
            const ocs = spanOf(r.w);
            const ors = spanOf(r.h);
            for (let i = 0; i < ocs; i++)
                for (let j = 0; j < ors; j++)
                    taken.add(`${oc + i},${or + j}`);
        }

        const fits = (c, r) => {
            for (let i = 0; i < cs; i++)
                for (let j = 0; j < rs; j++)
                    if (taken.has(`${c + i},${r + j}`))
                        return false;
            return true;
        };

        let col = wantCol;
        let row = wantRow;
        if (!fits(col, row)) {
            let best = null;
            let bestD = Infinity;
            for (let r = 0; r <= rows - rs; r++) {
                for (let c = 0; c <= cols - cs; c++) {
                    if (!fits(c, r))
                        continue;
                    const d = (c - wantCol) ** 2 + (r - wantRow) ** 2;
                    if (d < bestD) {
                        bestD = d;
                        best = [c, r];
                    }
                }
            }
            if (best)
                [col, row] = best;
        }

        return {
            x: Math.round(originX + col * CELL),
            y: Math.round(originY + row * CELL),
        };
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
