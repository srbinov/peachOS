// The widget picker: a bottom-left liquid-glass panel. Left rail = the app
// icon for each widget type (Clock / Weather / Calendar); right = a card per
// (variant x size) that you drag onto the desktop to place.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass} from './liquidGlass.js';
import {REGISTRY, SCALE_ORDER} from './widgetRegistry.js';

const INSET = 20;
const SIZE_LABEL = {sm: 'Small', md: 'Medium', lg: 'Large'};
const MODES = [['glass', 'Glass'], ['dark', 'Dark'], ['light', 'Light']];
const CARDS_PER_ROW = 3;

export const WidgetPicker = GObject.registerClass(
class WidgetPicker extends Clutter.Actor {
    _init(widgetLayer, callbacks) {
        super._init({name: 'peachos-widget-picker', reactive: false});
        this._widgetLayer = widgetLayer;
        this._callbacks = callbacks;
        this._selectedType = Object.keys(REGISTRY)[0];
        this._mode = 'glass';

        const mon = Main.layoutManager.primaryMonitor;
        this._pw = Math.round(mon.width / 3);
        this._ph = Math.round(mon.height * 0.4);
        this._px = mon.x + INSET;
        this._py = mon.y + mon.height - this._ph - INSET;

        this._glass = makeLiquidGlass({
            innerW: this._pw, innerH: this._ph,
            x: this._px, y: this._py, radius: 34,
        });
        this._glass.widget.reactive = true;
        this.add_child(this._glass.widget);

        this._buildContents();
        this._setMode('glass');
        this._selectType(this._selectedType);
    }

    _setMode(mode) {
        this._mode = mode;
        for (const [id, b] of this._modeButtons)
            b[id === mode ? 'add_style_class_name' : 'remove_style_class_name']('selected');
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

        this._grid.destroy_all_children();

        const cards = [];
        for (const [variant, vdef] of Object.entries(def.variants)) {
            for (const scale of SCALE_ORDER)
                cards.push({type, variant, vdef, scale});
        }

        let rowBox = null;
        cards.forEach((c, i) => {
            if (i % CARDS_PER_ROW === 0) {
                rowBox = new St.BoxLayout({style_class: 'peachos-picker-grid-row'});
                this._grid.add_child(rowBox);
            }
            rowBox.add_child(this._makeCard(c));
        });
    }

    _makeCard({type, variant, vdef, scale}) {
        const def = REGISTRY[type];
        const card = new St.Button({style_class: 'peachos-picker-card', can_focus: true});
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
        });
        box.add_child(new St.Icon({
            icon_name: def.appIcon, icon_size: 34,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-card-icon',
        }));
        box.add_child(new St.Label({
            text: vdef.name,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-card-label',
        }));
        box.add_child(new St.Label({
            text: SIZE_LABEL[scale],
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-card-dim',
        }));
        card.set_child(box);
        card.connect('button-press-event', (_a, event) =>
            this._beginDrag(type, variant, scale, event));
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
