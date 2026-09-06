// A single placed widget: the glass card + its content, plus edit-mode chrome
// (remove button, S/M/L size cycle) and hand-rolled drag-to-move.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import {makeLiquidGlass, MODE_FG} from '../lib/liquidGlass.js';
import {variantDef, sizeFor, SCALE_ORDER} from '../lib/widgetRegistry.js';
import {CityPicker} from '../lib/cityPicker.js';

const GRID = 8;
const MODE_ORDER = ['glass', 'dark', 'light'];
const MODE_LABEL = {glass: 'GLASS', dark: 'DARK', light: 'LIGHT'};

export class WidgetFrame {
    constructor(instance, ctx, layer, callbacks) {
        this.instance = instance;
        this._ctx = ctx;
        this._layer = layer;
        this._callbacks = callbacks; // { onMoved(frame), onRemove(frame), onResized(frame) }
        this._editing = false;
        this._capturedId = 0;

        this._buildGlass();
    }

    _buildGlass() {
        const inst = this.instance;
        const mode = inst.mode || 'glass';
        this._size = sizeFor(inst.type, inst.variant, inst.scale || 'md');

        this._glass = makeLiquidGlass({
            innerW: this._size.w, innerH: this._size.h, x: 0, y: 0,
            radius: this._size.radius, mode,
        });
        this._layer.add_child(this._glass.widget);

        const def = variantDef(inst.type, inst.variant);
        this._configurable = !!def.configurable;
        try {
            this._content = def.make(this._glass.content, this._ctx, {
                w: this._size.w, h: this._size.h,
                radius: this._size.radius, roundness: 7.5,
                mode, fg: MODE_FG[mode],
                clocks: inst.clocks,
            });
        } catch (e) {
            logError(e, `[peachos-widgets] failed to build ${inst.type}/${inst.variant}`);
        }

        this._buildChrome();

        this._pressId = this._glass.widget.connect('button-press-event',
            (_a, event) => this._onPress(event));
    }

    _buildChrome() {
        // On the layer (a sibling of the glass), not a child of it -- the glass
        // uses a BinLayout for its content overlay, which would ignore a fixed
        // position.
        this._chrome = new St.BoxLayout({
            style_class: 'peachos-widget-chrome',
            visible: this._editing,
        });

        const modeCycle = new St.Button({
            style_class: 'peachos-widget-chrome-btn',
            child: new St.Label({text: MODE_LABEL[this.instance.mode || 'glass']}),
        });
        modeCycle.connect('clicked', () => this._cycle('mode', MODE_ORDER));
        this._chrome.add_child(modeCycle);

        const sizeCycle = new St.Button({
            style_class: 'peachos-widget-chrome-btn',
            child: new St.Label({text: (this.instance.scale || 'md').toUpperCase()}),
        });
        sizeCycle.connect('clicked', () => this._cycle('scale', SCALE_ORDER));
        this._chrome.add_child(sizeCycle);

        if (this._configurable) {
            const cfg = new St.Button({
                style_class: 'peachos-widget-chrome-btn',
                child: new St.Icon({icon_name: 'document-edit-symbolic', icon_size: 13}),
            });
            cfg.connect('clicked', () => this._openConfig());
            this._chrome.add_child(cfg);
        }

        const removeBtn = new St.Button({
            style_class: 'peachos-widget-chrome-btn peachos-widget-chrome-remove',
            child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 13}),
        });
        removeBtn.connect('clicked', () => this._callbacks.onRemove(this));
        this._chrome.add_child(removeBtn);

        this._layer.add_child(this._chrome);
        this._syncChrome();
    }

    _syncChrome() {
        const r = this.innerRect();
        const [, cw] = this._chrome.get_preferred_width(-1);
        this._chrome.set_position(
            Math.round(r.x + r.w - Math.max(cw, 34) + 6), Math.round(r.y - 12));
        this._layer.set_child_above_sibling(this._chrome, null);
    }

    innerRect() {
        return {x: this._glass.widget.x, y: this._glass.widget.y, w: this._size.w, h: this._size.h};
    }

    setInnerPos(x, y) {
        this._glass.setInnerPos(x, y);
        this._syncChrome();
    }

    refreshBackdrop() {
        this._glass?.refresh();
    }

    setEditing(editing) {
        this._editing = editing;
        this._glass.widget.reactive = editing;
        this._chrome.visible = editing;
        if (!editing && this._cityPicker) {
            this._cityPicker.destroy();
            this._cityPicker = null;
        }
        if (editing)
            this._glass.widget.add_style_class_name('peachos-widget--editing');
        else
            this._glass.widget.remove_style_class_name('peachos-widget--editing');
    }

    _openConfig() {
        if (this._cityPicker)
            return;
        this._cityPicker = new CityPicker(this.instance.clocks || [], {
            onChange: clocks => {
                this.instance.clocks = clocks;
                this._content?.setClocks?.(clocks);
                this._callbacks.onConfigured?.(this);
            },
            onDone: () => {
                this._cityPicker?.destroy();
                this._cityPicker = null;
            },
        });
        this._layer.add_child(this._cityPicker);
        this._layer.set_child_above_sibling(this._cityPicker, null);
    }

    _cycle(key, order) {
        const cur = this.instance[key] || order[0];
        this.instance[key] = order[(order.indexOf(cur) + 1) % order.length];

        const anchor = this.innerRect();
        this._teardownContent();
        this._chrome.destroy();
        this._glass.widget.destroy();

        this._buildGlass();
        this.setEditing(true);
        // keep the top-left anchored, then let the layer clamp + persist
        this.setInnerPos(anchor.x, anchor.y);
        this._callbacks.onResized(this);
    }

    _onPress(event) {
        if (!this._editing || event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;
        const [px, py] = event.get_coords();
        const r = this.innerRect();
        this._drag = {px, py, ax: r.x, ay: r.y};
        this._capturedId = global.stage.connect('captured-event', (_s, ev) => this._onDragEvent(ev));
        this._glass.widget.add_style_class_name('peachos-widget--dragging');
        return Clutter.EVENT_STOP;
    }

    _onDragEvent(ev) {
        const t = ev.type();
        if (t === Clutter.EventType.MOTION) {
            const [x, y] = ev.get_coords();
            const rawX = this._drag.ax + (x - this._drag.px);
            const rawY = this._drag.ay + (y - this._drag.py);
            const sn = this._callbacks.snap(
                this.instance.id, rawX, rawY, this._size.w, this._size.h);
            this.setInnerPos(sn.x, sn.y);
            return Clutter.EVENT_STOP;
        }
        if (t === Clutter.EventType.BUTTON_RELEASE) {
            this._endDrag();
            this.refreshBackdrop();
            this._callbacks.onMoved(this);
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _endDrag() {
        if (this._capturedId) {
            global.stage.disconnect(this._capturedId);
            this._capturedId = 0;
        }
        this._glass.widget.remove_style_class_name('peachos-widget--dragging');
    }

    _teardownContent() {
        try {
            this._content?.destroy?.();
        } catch (e) {
            logError(e, '[peachos-widgets] content destroy failed');
        }
        this._content = null;
    }

    destroy() {
        this._endDrag();
        this._pressId = 0;
        this._cityPicker?.destroy();
        this._cityPicker = null;
        this._teardownContent();
        this._chrome?.destroy();
        this._chrome = null;
        this._glass.widget.destroy();
        this._glass = null;
    }
}
