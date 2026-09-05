// The widget picker: a bottom-left liquid-glass panel, ~1/3 x 1/3 of the
// primary monitor. Left rail = one icon per widget type; right = the variants
// for the selected type as cards you drag onto the desktop to place.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass, MARGIN} from './liquidGlass.js';
import {REGISTRY} from './widgetRegistry.js';

const INSET = 18;

export const WidgetPicker = GObject.registerClass(
class WidgetPicker extends St.Widget {
    _init(widgetLayer, callbacks) {
        super._init({name: 'peachos-widget-picker', reactive: false});
        this._widgetLayer = widgetLayer;
        this._callbacks = callbacks; // { onDone() }
        this._selectedType = Object.keys(REGISTRY)[0];

        const mon = Main.layoutManager.primaryMonitor;
        this._innerW = Math.round(mon.width / 3);
        this._innerH = Math.round(mon.height / 3);

        this._glass = makeLiquidGlass({
            innerW: this._innerW, innerH: this._innerH,
            x: mon.x + INSET,
            y: mon.y + mon.height - this._innerH - INSET,
            radius: 32, roundness: 7.0,
        });
        this._glass.widget.reactive = true;
        this._glass.content.reactive = true;
        this.add_child(this._glass.widget);
        this.add_child(this._glass.content);

        this._buildContents();
        this._selectType(this._selectedType);
    }

    _buildContents() {
        const row = new St.BoxLayout({
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-body',
        });
        this._glass.content.add_child(row);

        // Left rail --------------------------------------------------------
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
                child: new St.Icon({icon_name: def.icon, icon_size: 22}),
                can_focus: true,
            });
            btn.connect('clicked', () => this._selectType(type));
            this._rail.add_child(btn);
            this._railButtons.set(type, btn);
        }

        const spacer = new St.Widget({y_expand: true});
        this._rail.add_child(spacer);

        this._doneBtn = new St.Button({
            style_class: 'peachos-picker-done',
            child: new St.Icon({icon_name: 'object-select-symbolic', icon_size: 20}),
            can_focus: true,
        });
        this._doneBtn.connect('clicked', () => this._callbacks.onDone());
        this._rail.add_child(this._doneBtn);

        // Right side ------------------------------------------------------
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-main',
        });
        row.add_child(right);

        this._title = new St.Label({style_class: 'peachos-picker-title'});
        right.add_child(this._title);
        this._hint = new St.Label({
            text: 'Drag a widget onto the desktop',
            style_class: 'peachos-picker-hint',
        });
        right.add_child(this._hint);

        this._scroll = new St.ScrollView({
            x_expand: true, y_expand: true,
            style_class: 'peachos-picker-scroll',
        });
        this._scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this._grid = new St.BoxLayout({
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

        for (const [t, btn] of this._railButtons) {
            if (t === type)
                btn.add_style_class_name('selected');
            else
                btn.remove_style_class_name('selected');
        }

        this._grid.destroy_all_children();
        for (const [variant, vdef] of Object.entries(def.variants)) {
            const card = new St.Button({
                style_class: 'peachos-picker-card',
                can_focus: true,
            });
            const box = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_align: Clutter.ActorAlign.CENTER,
            });
            box.add_child(new St.Icon({
                icon_name: def.icon, icon_size: 30,
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'peachos-picker-card-icon',
            }));
            box.add_child(new St.Label({
                text: vdef.name,
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'peachos-picker-card-label',
            }));
            box.add_child(new St.Label({
                text: `${vdef.w}×${vdef.h}`,
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'peachos-picker-card-dim',
            }));
            card.set_child(box);
            card.connect('button-press-event', (_a, event) =>
                this._beginDrag(type, variant, vdef, event));
            this._grid.add_child(card);
        }
    }

    _panelStageRect() {
        return {
            x: this._glass.widget.x + MARGIN,
            y: this._glass.widget.y + MARGIN,
            w: this._innerW,
            h: this._innerH,
        };
    }

    _beginDrag(type, variant, vdef, event) {
        if (event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;

        const def = REGISTRY[type];
        const ghost = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-ghost',
            x_align: Clutter.ActorAlign.CENTER,
            width: Math.min(vdef.w, 180),
        });
        ghost.add_child(new St.Icon({
            icon_name: def.icon, icon_size: 28,
            x_align: Clutter.ActorAlign.CENTER,
        }));
        ghost.add_child(new St.Label({
            text: `${def.name} · ${vdef.name}`,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-ghost-label',
        }));
        this._widgetLayer.layer.add_child(ghost);

        const [px, py] = event.get_coords();
        const move = (x, y) => ghost.set_position(
            Math.round(x - ghost.width / 2), Math.round(y - 20));
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

                const p = this._panelStageRect();
                const onPanel = x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h;
                if (!onPanel)
                    this._widgetLayer.addWidget(type, variant, x, y);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        return Clutter.EVENT_STOP;
    }
});
