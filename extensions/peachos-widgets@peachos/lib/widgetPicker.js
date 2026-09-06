// The widget picker: a bottom-left liquid-glass panel. Left rail = the app
// icon for each widget type (Clock / Weather / Calendar); right = a card per
// (variant x size) that you drag onto the desktop to place.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass, MODE_FG} from './liquidGlass.js';
import {REGISTRY, SCALE_ORDER, variantDef} from './widgetRegistry.js';

const INSET = 20;
const SIZE_CHIP = {sm: 'S', md: 'M', lg: 'L'};
const SIZE_LABEL = {sm: 'Small', md: 'Medium', lg: 'Large'};
const MODES = [['glass', 'Glass'], ['dark', 'Dark'], ['light', 'Light']];
const CARDS_PER_ROW = 3;
const PREVIEW_MAX = 104;

export const WidgetPicker = GObject.registerClass(
class WidgetPicker extends Clutter.Actor {
    _init(widgetLayer, callbacks) {
        super._init({name: 'peachos-widget-picker', reactive: false});
        this._widgetLayer = widgetLayer;
        this._ctx = widgetLayer.ctx;
        this._callbacks = callbacks;
        this._selectedType = Object.keys(REGISTRY)[0];
        this._mode = 'glass';
        this._previews = [];
        this._previewGlass = [];
        this.connect('destroy', () => this._destroyPreviews());

        const mon = Main.layoutManager.primaryMonitor;
        this._pw = Math.round(Math.min(720, Math.max(560, mon.width * 0.38)));
        this._ph = Math.round(Math.min(560, Math.max(420, mon.height * 0.46)));
        this._px = mon.x + INSET;
        this._py = mon.y + mon.height - this._ph - INSET;

        this._glass = makeLiquidGlass({
            innerW: this._pw, innerH: this._ph,
            x: this._px, y: this._py, radius: 46,
        });
        this._glass.widget.reactive = true;
        this.add_child(this._glass.widget);

        this._buildContents();
        this._setMode('glass'); // also builds the card grid
    }

    _destroyPreviews() {
        for (const p of this._previews) {
            try {
                p.destroy?.();
            } catch (e) {
                // ignore
            }
        }
        this._previews = [];
        this._previewGlass = [];
    }

    _setMode(mode) {
        this._mode = mode;
        for (const [id, b] of this._modeButtons)
            b[id === mode ? 'add_style_class_name' : 'remove_style_class_name']('selected');
        // re-render the previews in the new mode (skipped during initial build)
        if (this._grid)
            this._selectType(this._selectedType);
    }

    _buildContents() {
        const row = new St.BoxLayout({
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-body',
        });
        this._glass.content.add_child(row);

        this._rail = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-rail',
            y_expand: true,
        });
        row.add_child(this._rail);

        this._railButtons = new Map();
        for (const [type, def] of Object.entries(REGISTRY)) {
            const btn = new St.Button({
                style_class: 'peachos-picker-rail-btn',
                child: new St.Icon({icon_name: def.appIcon, icon_size: 30}),
                can_focus: true,
            });
            btn.connect('clicked', () => this._selectType(type));
            this._rail.add_child(btn);
            this._railButtons.set(type, btn);
        }

        this._rail.add_child(new St.Widget({y_expand: true}));

        const done = new St.Button({
            style_class: 'peachos-picker-done',
            child: new St.Icon({icon_name: 'object-select-symbolic', icon_size: 20}),
            can_focus: true,
        });
        done.connect('clicked', () => this._callbacks.onDone());
        this._rail.add_child(done);

        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-main',
        });
        row.add_child(right);

        const titleRow = new St.BoxLayout({x_expand: true});
        this._title = new St.Label({style_class: 'peachos-picker-title', x_expand: true});
        titleRow.add_child(this._title);

        this._modeSeg = new St.BoxLayout({style_class: 'peachos-picker-modeseg'});
        this._modeButtons = new Map();
        for (const [id, label] of MODES) {
            const b = new St.Button({
                style_class: 'peachos-picker-modeseg-btn',
                child: new St.Label({text: label}),
                can_focus: true,
            });
            b.connect('clicked', () => this._setMode(id));
            this._modeSeg.add_child(b);
            this._modeButtons.set(id, b);
        }
        titleRow.add_child(this._modeSeg);
        right.add_child(titleRow);

        right.add_child(new St.Label({
            text: 'Drag a widget onto the desktop',
            style_class: 'peachos-picker-hint',
        }));

        this._scroll = new St.ScrollView({
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-scroll',
        });
        this._scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this._grid = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-grid',
            x_expand: true,
        });
        this._scroll.set_child(this._grid);
        right.add_child(this._scroll);
    }

    _selectType(type) {
        this._selectedType = type;
        const def = REGISTRY[type];
        this._title.text = def.name;

        for (const [t, btn] of this._railButtons)
            btn[t === type ? 'add_style_class_name' : 'remove_style_class_name']('selected');

        this._destroyPreviews();
        this._grid.destroy_all_children();
        this._cardScale = new Map(); // variant -> selected size

        const variants = Object.entries(def.variants);
        let rowBox = null;
        variants.forEach(([variant, vdef], i) => {
            if (i % CARDS_PER_ROW === 0) {
                rowBox = new St.BoxLayout({style_class: 'peachos-picker-grid-row'});
                this._grid.add_child(rowBox);
            }
            rowBox.add_child(this._makeCard(type, variant, vdef));
        });
    }

    // A card = a live miniature of the widget (rendered exactly as placed) +
    // its name + an S/M/L size selector. Dragging it places at the chosen size.
    _makeCard(type, variant, vdef) {
        this._cardScale.set(variant, 'md');

        const card = new St.Button({style_class: 'peachos-picker-card', can_focus: true});
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
        });

        // preview -----------------------------------------------------------
        const s = PREVIEW_MAX / Math.max(vdef.base.w, vdef.base.h);
        const pw = Math.round(vdef.base.w * s);
        const ph = Math.round(vdef.base.h * s);
        const radius = Math.round(Math.min(pw, ph) * vdef.radiusRatio);
        const mode = this._mode;

        const previewBin = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: PREVIEW_MAX, height: PREVIEW_MAX,
            style_class: 'peachos-picker-card-preview',
        });
        const glass = makeLiquidGlass({
            innerW: pw, innerH: ph, x: 0, y: 0, radius, mode, noCrop: true,
        });
        glass.widget.x_align = Clutter.ActorAlign.CENTER;
        glass.widget.y_align = Clutter.ActorAlign.CENTER;
        try {
            const inst = vdef.make(glass.content, this._ctx, {
                w: pw, h: ph, radius, roundness: 7.5,
                mode, fg: MODE_FG[mode], preview: true,
            });
            this._previews.push(inst);
        } catch (e) {
            logError(e, `[peachos-widgets] preview build failed for ${type}/${variant}`);
        }
        this._previewGlass.push(glass);
        previewBin.add_child(glass.widget);
        box.add_child(previewBin);

        box.add_child(new St.Label({
            text: vdef.name,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-card-label',
        }));

        // size selector ---------------------------------------------------
        const seg = new St.BoxLayout({
            style_class: 'peachos-picker-sizeseg',
            x_align: Clutter.ActorAlign.CENTER,
        });
        const btns = new Map();
        for (const sc of SCALE_ORDER) {
            const b = new St.Button({
                style_class: 'peachos-picker-sizeseg-btn' + (sc === 'md' ? ' selected' : ''),
                child: new St.Label({text: SIZE_CHIP[sc]}),
            });
            b.connect('clicked', () => {
                this._cardScale.set(variant, sc);
                for (const [k, bb] of btns)
                    bb[k === sc ? 'add_style_class_name' : 'remove_style_class_name']('selected');
            });
            seg.add_child(b);
            btns.set(sc, b);
        }
        box.add_child(seg);

        card.set_child(box);
        card.connect('button-press-event', (_a, event) =>
            this._beginDrag(type, variant, this._cardScale.get(variant), event));
        return card;
    }

    _panelRect() {
        return {x: this._glass.widget.x, y: this._glass.widget.y, w: this._pw, h: this._ph};
    }

    _beginDrag(type, variant, scale, event) {
        if (event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;

        const def = REGISTRY[type];
        const ghost = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-ghost',
            x_align: Clutter.ActorAlign.CENTER,
        });
        ghost.add_child(new St.Icon({
            icon_name: def.appIcon, icon_size: 30,
            x_align: Clutter.ActorAlign.CENTER,
        }));
        ghost.add_child(new St.Label({
            text: `${def.variants[variant].name} · ${SIZE_LABEL[scale]}`,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-ghost-label',
        }));
        this._widgetLayer.layer.add_child(ghost);

        const [px, py] = event.get_coords();
        const move = (x, y) => ghost.set_position(Math.round(x - 60), Math.round(y - 24));
        move(px, py);

        const capturedId = global.stage.connect('captured-event', (_s, ev) => {
            const t = ev.type();
            if (t === Clutter.EventType.MOTION) {
                const [x, y] = ev.get_coords();
                move(x, y);
                return Clutter.EVENT_STOP;
            }
            if (t === Clutter.EventType.BUTTON_RELEASE) {
                global.stage.disconnect(capturedId);
                const [x, y] = ev.get_coords();
                ghost.destroy();
                const p = this._panelRect();
                const onPanel = x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h;
                if (!onPanel) {
                    this._widgetLayer.addWidget(type, variant, x, y, scale, this._mode);
                    this.get_parent()?.set_child_above_sibling(this, null);
                }
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        return Clutter.EVENT_STOP;
    }
});
