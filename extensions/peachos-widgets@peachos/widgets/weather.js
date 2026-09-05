// Weather widget, matched to the KDE liquidglass repo (packages/weather).
//
//  'small' -- city, a very large thin temperature, condition icon top-right
//   with H/L below it, precipitation + wind bottom-left.
//  'big'   -- header + an hourly strip + a 4-day forecast with range bars.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {wmoCondition, wmoIconName} from '../lib/providers/weather.js';
import {FONT, fontStyle} from '../lib/fonts.js';

function wIcon(ctxPath, name, size) {
    return new St.Icon({
        gicon: Gio.icon_new_for_string(
            GLib.build_filenamev([ctxPath, 'icons', 'weather', `${name}.png`])),
        icon_size: Math.round(size),
    });
}

function txt(text, family, px, opacity = 1) {
    return new St.Label({text, style: fontStyle(family, px, opacity)});
}

export class WeatherWidget {
    constructor(parent, ctx, size, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._w = size.w;
        this._h = size.h;

        this._root = new Clutter.Actor({width: size.w, height: size.h});
        parent.add_child(this._root);

        this._unsub = ctx.weather.subscribe((data, err) => this._render(data, err));
    }

    _render(data, err) {
        this._root.destroy_all_children();
        if (!data) {
            this._add(txt(err ? 'Weather unavailable' : 'Loading…', FONT.display, 13, 0.8),
                this._w * 0.1, this._h / 2 - 10);
            return;
        }
        if (this._mode === 'big')
            this._renderBig(data);
        else
            this._renderSmall(data);
    }

    _add(actor, x, y) {
        actor.set_position(Math.round(x), Math.round(y));
        this._root.add_child(actor);
        return actor;
    }

    _renderSmall(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.09);
        const ls = Math.max(11, Math.round(Math.min(h, 350) * 0.066));
        const p = this._ctx.path;

        this._add(txt(d.name, FONT.display, ls * 1.15), m, m);
        this._add(txt(`${d.temp}°`, FONT.displayThin, ls * 4),
            m - Math.round(ls * 0.06), m + Math.round(ls * 1.3));

        const iconSize = Math.round(ls * 3);
        this._add(wIcon(p, wmoIconName(d.code, d.isDay), iconSize),
            w - m - iconSize, m - Math.round(ls * 0.35));

        const hl = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.18)}px;`,
        });
        const mkRow = (arrow, val, op) => {
            const r = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.12)}px;`});
            r.add_child(txt(arrow, FONT.display, ls, op));
            r.add_child(txt(val, FONT.display, ls, op));
            return r;
        };
        hl.add_child(mkRow('↑', `${d.hi}°`, 1));
        hl.add_child(mkRow('↓', `${d.lo}°`, 0.7));
        this._add(hl, w - m - Math.round(ls * 3.2), m + iconSize + Math.round(ls * 0.1));

        const info = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        const is = Math.round(ls * 0.88);
        info.add_child(txt('Precipitation', FONT.display, is));
        info.add_child(txt(
            d.precipProb != null ? `${d.precipProb}% chance` : `${d.precip}"`,
            FONT.display, is, 0.55));
        info.add_child(new St.Widget({height: Math.round(ls * 0.4), width: 1}));
        info.add_child(txt('Wind', FONT.display, is));
        info.add_child(txt(`${d.wind} mph ${d.windDir}`, FONT.display, is, 0.55));
        const infoH = Math.round(is * 4.6 + ls * 0.4);
        this._add(info, m, h - m - infoH);
    }

    _renderBig(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.06);
        const ls = Math.max(11, Math.round(Math.min(h, 350) * 0.062));
        const p = this._ctx.path;

        const left = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        left.add_child(txt(d.name, FONT.display, ls * 1.15));
        left.add_child(txt(`${d.temp}°`, FONT.displayThin, ls * 3.3));
        this._add(left, m, m);

        const iconSize = Math.round(ls * 2.6);
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.15)}px;`,
        });
        const rAlign = a => {
            a.x_align = Clutter.ActorAlign.END;
            return a;
        };
        right.add_child(rAlign(wIcon(p, wmoIconName(d.code, d.isDay), iconSize)));
        right.add_child(rAlign(txt(wmoCondition(d.code), FONT.display, ls)));
        right.add_child(rAlign(txt(`H:${d.hi}°  L:${d.lo}°`, FONT.display, ls, 0.7)));
        this._add(right, w - m - Math.round(ls * 7), m);

        let y = m + Math.round(ls * 4.2);
        this._add(this._sep(w - 2 * m), m, y);

        y += Math.round(ls * 0.55);
        const hourly = new St.BoxLayout({width: w - 2 * m});
        for (const slot of d.hours.slice(0, 6)) {
            const col = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 4px;',
            });
            const cAlign = a => {
                a.x_align = Clutter.ActorAlign.CENTER;
                return a;
            };
            col.add_child(cAlign(txt(slot.hour, FONT.display, ls * 0.8, 0.7)));
            col.add_child(cAlign(wIcon(p, wmoIconName(slot.code, d.isDay), Math.round(ls * 1.6))));
            col.add_child(cAlign(txt(`${slot.temp}°`, FONT.display, ls * 0.92)));
            hourly.add_child(col);
        }
        this._add(hourly, m, y);

        y += Math.round(ls * 4.4);
        this._add(this._sep(w - 2 * m), m, y);

        y += Math.round(ls * 0.55);
        const lows = d.days.map(x => x.lo);
        const highs = d.days.map(x => x.hi);
        const oLo = Math.min(...lows);
        const oHi = Math.max(...highs);
        const span = Math.max(1, oHi - oLo);
        const barW = Math.round(w * 0.30);
        const rowStep = Math.round(ls * 1.85);

        d.days.slice(0, 4).forEach((day, i) => {
            const row = new St.BoxLayout({width: w - 2 * m, style: 'spacing: 10px;'});
            const vc = a => {
                a.y_align = Clutter.ActorAlign.CENTER;
                return a;
            };
            row.add_child(vc(txt(day.label, FONT.display, ls, i === 0 ? 1 : 0.9)));
            row.add_child(vc(wIcon(p, wmoIconName(day.code, true), Math.round(ls * 1.35))));
            row.add_child(vc(txt(`${day.lo}°`, FONT.display, ls, 0.6)));

            const barH = Math.round(ls * 0.34);
            const track = new St.Widget({
                layout_manager: new Clutter.BinLayout(),
                width: barW, height: barH,
                y_align: Clutter.ActorAlign.CENTER,
                style: `background-color: rgba(255,255,255,0.12); border-radius: ${ls}px;`,
            });
            const fx = Math.round(((day.lo - oLo) / span) * barW);
            const fw = Math.max(5, Math.round(((day.hi - day.lo) / span) * barW));
            track.add_child(new St.Widget({
                width: fw, height: barH,
                x_align: Clutter.ActorAlign.START,
                style: `margin-left: ${fx}px; background-color: rgba(255,255,255,0.55); border-radius: ${ls}px;`,
            }));
            row.add_child(track);
            row.add_child(vc(txt(`${day.hi}°`, FONT.display, ls)));
            this._add(row, m, y + i * rowStep);
        });
    }

    _sep(width) {
        return new St.Widget({
            width, height: 1,
            style: 'background-color: rgba(255,255,255,0.15);',
        });
    }

    destroy() {
        this._unsub?.();
        this._root.destroy();
    }
}
