// A single placed widget: a liquid-glass squircle (shader) with a crisp content
// overlay on top, a drag-to-move handler and a remove button -- the last two
// only active in edit mode.
//
// Drag is done by hand (button-press -> global.stage 'captured-event' motion ->
// button-release) rather than dnd.js: the glass actor carries a ShaderEffect and
// painted wallpaper content, which dnd.js's reparent-during-drag mangles.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {makeLiquidGlass, MARGIN} from '../lib/liquidGlass.js';
import {variantDef} from '../lib/widgetRegistry.js';

const GRID = 8;

export const WidgetFrame = GObject.registerClass(
class WidgetFrame extends St.Widget {
    _init(instance, ctx, callbacks) {
        super._init({name: `peachos-widget-${instance.id}`});
        this.instance = instance;
        this._ctx = ctx;
        this._callbacks = callbacks; // { onMoved(frame), onRemove(frame) }
        this._editing = false;

        const def = variantDef(instance.type, instance.variant);
        this._innerW = def.w;
        this._innerH = def.h;

        this._glass = makeLiquidGlass({
            innerW: def.w, innerH: def.h, x: 0, y: 0,
            radius: def.radius, roundness: 7.0,
        });
        // Order matters: glass (shader) first, crisp content overlay on top.
        this.add_child(this._glass.widget);
        this.add_child(this._glass.content);

        try {
            this._content = def.make(this._glass.content, ctx);
        } catch (e) {
            logError(e, `[peachos-widgets] failed to build ${instance.type}/${instance.variant}`);
        }

        this._removeBtn = new St.Button({
            style_class: 'peachos-widget-remove',
            child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 14}),
            visible: false,
        });
        this._removeBtn.connect('clicked', () => this._callbacks.onRemove(this));
        this.add_child(this._removeBtn);

        // The glass actor sits under the content; a press that falls through the
        // (non-reactive) content lands here.
        this._pressId = this._glass.widget.connect('button-press-event',
            (_a, event) => this._onPress(event));

        this.connect('destroy', () => this._onDestroy());
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
            if (this._capturedId) {
                global.stage.disconnect(this._capturedId);
                this._capturedId = 0;
            }
            this._glass.content.remove_style_class_name('peachos-widget--dragging');
            this._snapAndCommit();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _snapAndCommit() {
        const r = this.innerRect();
        this.setInnerPos(
            Math.round(r.x / GRID) * GRID,
            Math.round(r.y / GRID) * GRID);
        this.refreshBackdrop();
        this._callbacks.onMoved(this);
    }

    _onDestroy() {
        if (this._capturedId) {
            global.stage.disconnect(this._capturedId);
            this._capturedId = 0;
        }
        this._pressId = 0;
        try {
            this._content?.destroy?.();
        } catch (e) {
            logError(e, '[peachos-widgets] content destroy failed');
        }
        this._content = null;
    }
});
