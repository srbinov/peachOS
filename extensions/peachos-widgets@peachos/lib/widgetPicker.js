// The widget picker: a bottom-left liquid-glass panel. Left rail = the app
// icon per widget type; right = the bare previews for the selected type
// (previews/<type>-<variant>.png, or the app icon if absent) -- no frame, no
// label -- laid out at their true relative footprint so a row preview reads
// twice as wide as a square one. Drag a preview onto the desktop to place it
// (as a dark widget; change the look with the widget's own edit-mode toggle).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass} from './liquidGlass.js';
import {REGISTRY} from './widgetRegistry.js';

const INSET = 20;
const PU = 94;       // preview size for a square widget (px)
const PGAP = 8;      // gap inside a preview footprint (matches the desktop grid)
const CARD_GAP = 16; // gap between previews in the picker
const PLACE_MODE = 'dark';

function previewDims(shape) {
    const wide = shape === 'row' || shape === 'grid';
    const tall = shape === 'grid';
    return {
        w: wide ? PU * 2 + PGAP : PU,
        h: tall ? PU * 2 + PGAP : PU,
    };
}

export const WidgetPicker = GObject.registerClass(
class WidgetPicker extends Clutter.Actor {
    _init(widgetLayer, callbacks) {
        super._init({name: 'peachos-widget-picker', reactive: false});
        this._widgetLayer = widgetLayer;
        this._ctx = widgetLayer.ctx;
        this._callbacks = callbacks;
        this._selectedType = Object.keys(REGISTRY)[0];

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
        this._selectType(this._selectedType);

        this._wxUnsub = this._ctx.weather?.subscribe(() => this._syncWeatherLoc());
        this.connect('destroy', () => this._wxUnsub?.());
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

        this._title = new St.Label({style_class: 'peachos-picker-title'});
        right.add_child(this._title);
        right.add_child(new St.Label({
            text: 'Drag a widget onto the desktop',
            style_class: 'peachos-picker-hint',
        }));

        this._weatherLoc = this._buildWeatherLoc();
        right.add_child(this._weatherLoc);

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

    // ---- weather location (Auto / Manual) -------------------------------

    _buildWeatherLoc() {
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-weatherloc',
            visible: false,
        });

        const head = new St.BoxLayout({style_class: 'peachos-picker-weatherloc-head'});
        head.add_child(new St.Label({
            text: 'Location', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-picker-weatherloc-label',
        }));
        const seg = new St.BoxLayout({style_class: 'peachos-picker-modeseg'});
        this._wxSeg = new Map();
        for (const [key, label] of [['auto', 'Auto'], ['manual', 'Manual']]) {
            const b = new St.Button({
                style_class: 'peachos-picker-modeseg-btn',
                child: new St.Label({text: label}),
            });
            b.connect('clicked', () => {
                this._ctx.weather?.setAutoLocation(key === 'auto');
                if (key === 'manual')
                    this._wxEntry.grab_key_focus();
                this._syncWeatherLoc();
            });
            seg.add_child(b);
            this._wxSeg.set(key, b);
        }
        head.add_child(seg);
        box.add_child(head);

        this._wxManual = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-wx-manual',
            visible: false,
        });
        this._wxEntry = new St.Entry({
            hint_text: 'Search for a city…',
            style_class: 'peachos-picker-wx-entry',
            x_expand: true, can_focus: true,
        });
        this._wxEntry.clutter_text.connect('activate', () => {
            const q = this._wxEntry.get_text();
            this._ctx.weather?.geocode(q, results => this._showWxResults(results));
        });
        this._wxManual.add_child(this._wxEntry);
        this._wxResults = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'peachos-picker-wx-results',
        });
        this._wxManual.add_child(this._wxResults);
        box.add_child(this._wxManual);

        this._wxCurrent = new St.Label({style_class: 'peachos-picker-wx-current'});
        box.add_child(this._wxCurrent);

        return box;
    }

    _showWxResults(results) {
        this._wxResults.destroy_all_children();
        if (!results.length) {
            this._wxResults.add_child(new St.Label({
                text: 'No matches', style_class: 'peachos-picker-wx-result',
            }));
            return;
        }
        for (const r of results) {
            const b = new St.Button({
                style_class: 'peachos-picker-wx-result',
                child: new St.Label({text: r.label}),
                x_expand: true,
            });
            b.connect('clicked', () => {
                this._ctx.weather?.setManualLocation(r.lat, r.lon, r.label);
                this._wxEntry.set_text('');
                this._wxResults.destroy_all_children();
                this._syncWeatherLoc();
            });
            this._wxResults.add_child(b);
        }
    }

    _syncWeatherLoc() {
        if (!this._weatherLoc)
            return;
        const wx = this._ctx.weather;
        const auto = wx ? wx.autoLocation : true;
        for (const [k, b] of this._wxSeg)
            b[(k === 'auto') === auto ? 'add_style_class_name' : 'remove_style_class_name']('selected');
        this._wxManual.visible = !auto;
        this._wxCurrent.text = wx
            ? (auto ? `Using your location · ${wx.locationName}` : `Showing · ${wx.locationName}`)
            : '';
    }

    _selectType(type) {
        this._selectedType = type;
        const def = REGISTRY[type];
        this._title.text = def.name;

        for (const [t, btn] of this._railButtons)
            btn[t === type ? 'add_style_class_name' : 'remove_style_class_name']('selected');

        this._weatherLoc.visible = type === 'weather';
        if (type === 'weather')
            this._syncWeatherLoc();

        this._grid.destroy_all_children();

        // Pack previews left-to-right at their true footprint, wrapping when a
        // row would overflow the content width.
        const maxRowW = Math.max(PU * 2 + PGAP, this._pw - 120);
        let rowBox = null;
        let rowW = 0;
        for (const [variant, vdef] of Object.entries(def.variants)) {
            const {w, h} = previewDims(vdef.shape);
            if (!rowBox || rowW + w > maxRowW) {
                rowBox = new St.BoxLayout({style_class: 'peachos-picker-grid-row'});
                this._grid.add_child(rowBox);
                rowW = 0;
            }
            rowBox.add_child(this._makeCard(type, variant, w, h));
            rowW += w + CARD_GAP;
        }
    }

    _previewPath(type, variant) {
        const p = GLib.build_filenamev(
            [this._ctx.path, 'previews', `${type}-${variant}.png`]);
        return GLib.file_test(p, GLib.FileTest.EXISTS) ? p : null;
    }

    _makeCard(type, variant, w, h) {
        const card = new St.Widget({
            width: w, height: h,
            reactive: true, track_hover: true,
            style_class: 'peachos-picker-preview',
            layout_manager: new Clutter.BinLayout(),
        });
        const path = this._previewPath(type, variant);
        if (path) {
            card.set_style(
                `background-image: url("file://${path}"); `
                + 'background-size: contain; background-position: center;');
        } else {
            card.add_child(new St.Icon({
                icon_name: REGISTRY[type].appIcon,
                icon_size: Math.min(56, Math.round(Math.min(w, h) * 0.5)),
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }
        card.connect('button-press-event', (_a, event) =>
            this._beginDrag(type, variant, event));
        return card;
    }

    _panelRect() {
        return {x: this._glass.widget.x, y: this._glass.widget.y, w: this._pw, h: this._ph};
    }

    _beginDrag(type, variant, event) {
        if (event.get_button() !== Clutter.BUTTON_PRIMARY)
            return Clutter.EVENT_PROPAGATE;

        const def = REGISTRY[type];
        const {w, h} = previewDims(def.variants[variant].shape);
        const path = this._previewPath(type, variant);
        const ghost = new St.Widget({
            width: w, height: h, opacity: 210,
            layout_manager: new Clutter.BinLayout(),
        });
        if (path) {
            ghost.set_style(
                `background-image: url("file://${path}"); `
                + 'background-size: contain; background-position: center;');
        } else {
            ghost.add_child(new St.Icon({
                icon_name: def.appIcon, icon_size: 32,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }
        this._widgetLayer.layer.add_child(ghost);

        const [px, py] = event.get_coords();
        const move = (x, y) => ghost.set_position(
            Math.round(x - w / 2), Math.round(y - h / 2));
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
                    this._widgetLayer.addWidget(type, variant, x, y, PLACE_MODE);
                    this.get_parent()?.set_child_above_sibling(this, null);
                }
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        return Clutter.EVENT_STOP;
    }
});
