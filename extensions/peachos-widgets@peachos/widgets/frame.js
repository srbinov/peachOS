// A single placed widget: a liquid-glass squircle (shader) with a crisp content
// overlay on top, a drag-to-move handler and a remove button -- the last two
// only active in edit mode.
//
// This is a plain controller, not an actor subclass: its three actors (glass,
// content overlay, remove button) go straight into widgetLayer's layer -- a
// Clutter.Actor with the default fixed layout, which is what actually allocates
// fixed-positioned children at their preferred size (an St.Widget wrapper does
// not). Drag is done by hand rather than dnd.js, whose reparent-during-drag
// mangles the ShaderEffect + painted wallpaper content.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import {makeLiquidGlass, MARGIN} from '../lib/liquidGlass.js';
import {variantDef} from '../lib/widgetRegistry.js';

const GRID = 8;

export class WidgetFrame {
    constructor(instance, ctx, layer, callbacks) {
        this.instance = instance;
        this._ctx = ctx;
        this._layer = layer;
        this._callbacks = callbacks; // { onMoved(frame), onRemove(frame) }
        this._editing = false;
        this._capturedId = 0;

        const def = variantDef(instance.type, instance.variant);
        this._innerW = def.w;
        this._innerH = def.h;

        this._glass = makeLiquidGlass({
            innerW: def.w, innerH: def.h, x: 0, y: 0,
            radius: def.radius, roundness: 7.0,
        });

        this._removeBtn = new St.Button({
            style_class: 'peachos-widget-remove',
            child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 14}),
            visible: false,
        });
        this._removeBtn.connect('clicked', () => this._callbacks.onRemove(this));

        // glass (shader) first, crisp content overlay on top, then chrome.
        layer.add_child(this._glass.widget);
        layer.add_child(this._glass.content);
        layer.add_child(this._removeBtn);

        try {
            this._content = def.make(this._glass.content, ctx,
                {w: def.w, h: def.h, radius: def.radius, roundness: 7.0});
        } catch (e) {
            logError(e, `[peachos-widgets] failed to build ${instance.type}/${instance.variant}`);
        }

        this._pressId = this._glass.widget.connect('button-press-event',
            (_a, event) => this._onPress(event));
    }

    /** The visible-glass rect in stage coords (excludes the invisible MARGIN). */
    innerRect() {
        return {
            x: this._glass.widget.x + MARGIN,
            y: this._glass.widget.y + MARGIN,
            w: this._innerW,
            h: this._innerH,
        };
    }

    setInnerPos(x, y) {
        this._glass.setInnerPos(x, y);
        this._removeBtn.set_position(x - 10, y - 10);
    }

    refreshBackdrop() {
        this._glass.refresh();
    }

    raise() {
        const parent = this._glass.widget.get_parent();
        if (!parent)
            return;
        parent.set_child_above_sibling(this._glass.widget, null);
        parent.set_child_above_sibling(this._glass.content, null);
        parent.set_child_above_sibling(this._removeBtn, null);
    }

    setEditing(editing) {
        this._editing = editing;
        this._glass.widget.reactive = editing;
        this._removeBtn.visible = editing;
        if (editing)
            this._glass.content.add_style_class_name('peachos-widget--editing');
        else
            this._glass.content.remove_style_class_name('peachos-widget--editing');
    }

    _onPress(event) {
        if (!this._editing || event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;

        const [px, py] = event.get_coords();
        const r = this.innerRect();
        this._drag = {px, py, ax: r.x, ay: r.y};
        this._capturedId = global.stage.connect('captured-event',
            (_s, ev) => this._onDragEvent(ev));
        this._glass.content.add_style_class_name('peachos-widget--dragging');
        return Clutter.EVENT_STOP;
    }

    _onDragEvent(ev) {
        const type = ev.type();
        if (type === Clutter.EventType.MOTION) {
            const [x, y] = ev.get_coords();
            this.setInnerPos(
                Math.round(this._drag.ax + (x - this._drag.px)),
                Math.round(this._drag.ay + (y - this._drag.py)));
            return Clutter.EVENT_STOP;
        }
        if (type === Clutter.EventType.BUTTON_RELEASE) {
            this._endDrag();
            this._snapAndCommit();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _endDrag() {
        if (this._capturedId) {
            global.stage.disconnect(this._capturedId);
            this._capturedId = 0;
        }
        this._glass.content.remove_style_class_name('peachos-widget--dragging');
    }

    _snapAndCommit() {
        const r = this.innerRect();
        this.setInnerPos(
            Math.round(r.x / GRID) * GRID,
            Math.round(r.y / GRID) * GRID);
        this.refreshBackdrop();
        this._callbacks.onMoved(this);
    }

    destroy() {
        this._endDrag();
        if (this._pressId) {
            this._glass.widget.disconnect(this._pressId);
            this._pressId = 0;
        }
        try {
            this._content?.destroy?.();
        } catch (e) {
            logError(e, '[peachos-widgets] content destroy failed');
        }
        this._content = null;
        this._glass.content.destroy();
        this._glass.widget.destroy();
        this._removeBtn.destroy();
        this._glass = null;
    }
}
