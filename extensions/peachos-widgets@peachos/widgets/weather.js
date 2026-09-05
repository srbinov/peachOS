// Weather widget, ported from the KDE liquidglass repo (packages/weather).
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

export class WeatherWidget {
    constructor(parent, ctx, size, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._w = size.w;
        this._h = size.h;
        this._fg = size.fg || '255,255,255';
        // light-mode wants coloured icons; glass/dark want the mono set
        this._iconSet = this._fg.startsWith('26,') ? 'weather-color' : 'weather-mono';

        this._root = new Clutter.Actor({width: size.w, height: size.h});
        parent.add_child(this._root);

        this._unsub = ctx.weather.subscribe((data, err) => this._render(data, err));
    }

    _icon(name, size) {
        return new St.Icon({
            gicon: Gio.icon_new_for_string(GLib.build_filenamev(
                [this._ctx.path, 'icons', this._iconSet, `${name}.png`])),
            icon_size: Math.round(size),
        });
    }

    _txt(text, family, px, opacity = 1) {
        return new St.Label({text, style: fontStyle(family, px, opacity, this._fg)});
    }

    _render(data, err) {
        this._root.destroy_all_children();
        if (!data) {
            this._add(this._txt(err ? 'Weather unavailable' : 'Loading…', FONT.display, 13, 0.8),
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
        const ls = Math.max(11, Math.round(Math.min(h, 350) * 0.068));

        this._add(this._txt(d.name, FONT.display, ls * 1.15), m, m);
        this._add(this._txt(`${d.temp}°`, FONT.displayThin, ls * 4),
            m - Math.round(ls * 0.06), m + Math.round(ls * 1.25));

        const iconSize = Math.round(ls * 3);
        this._add(this._icon(wmoIconName(d.code, d.isDay), iconSize),
            w - m - iconSize, m - Math.round(ls * 0.35));

        const hl = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.18)}px;`,
        });
        const mkRow = (arrow, val, op) => {
            const r = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.12)}px;`});
            r.add_child(this._txt(arrow, FONT.display, ls, op));
            r.add_child(this._txt(val, FONT.display, ls, op));
            return r;
        };
        hl.add_child(mkRow('↑', `${d.hi}°`, 1));
        hl.add_child(mkRow('↓', `${d.lo}°`, 0.7));
        this._add(hl, w - m - Math.round(ls * 3.2), m + iconSize + Math.round(ls * 0.05));

        const info = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        const is = Math.round(ls * 0.9);
        info.add_child(this._txt('Precipitation', FONT.display, is));
        info.add_child(this._txt(
            d.precipProb != null ? `${d.precipProb}% chance` : `${d.precip}"`,
            FONT.display, is, 0.6));
        info.add_child(new St.Widget({height: Math.round(ls * 0.35), width: 1}));
        info.add_child(this._txt('Wind', FONT.display, is));
        info.add_child(this._txt(`${d.wind} mph ${d.windDir}`, FONT.display, is, 0.6));
        const infoH = Math.round(is * 4.5 + ls * 0.35);
        this._add(info, m, h - m - infoH);
    }

    _renderBig(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.055);
        const ls = Math.max(11, Math.round(Math.min(h, 360) * 0.06));

        const left = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        left.add_child(this._txt(d.name, FONT.display, ls * 1.1));
        left.add_child(this._txt(`${d.temp}°`, FONT.displayThin, ls * 3.2));
        this._add(left, m, m);

        const iconSize = Math.round(ls * 2.4);
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.12)}px;`,
        });
        const rAlign = a => {
            a.x_align = Clutter.ActorAlign.END;
            return a;
        };
        right.add_child(rAlign(this._icon(wmoIconName(d.code, d.isDay), iconSize)));
        right.add_child(rAlign(this._txt(wmoCondition(d.code), FONT.display, ls)));
        right.add_child(rAlign(this._txt(`H:${d.hi}°  L:${d.lo}°`, FONT.display, ls, 0.7)));
        this._add(right, w - m - Math.round(ls * 6.8), m);

        let y = m + Math.round(ls * 3.9);
        this._add(this._sep(w - 2 * m), m, y);

        y += Math.round(ls * 0.5);
        const hourly = new St.BoxLayout({width: w - 2 * m});
        for (const slot of d.hours.slice(0, 6)) {
            const col = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 3px;',
            });
            const cAlign = a => {
                a.x_align = Clutter.ActorAlign.CENTER;
                return a;
            };
            col.add_child(cAlign(this._txt(slot.hour, FONT.display, ls * 0.78, 0.7)));
            col.add_child(cAlign(this._icon(wmoIconName(slot.code, d.isDay), Math.round(ls * 1.5))));
            col.add_child(cAlign(this._txt(`${slot.temp}°`, FONT.display, ls * 0.9)));
            hourly.add_child(col);
        }
        this._add(hourly, m, y);

        y += Math.round(ls * 4.1);
        this._add(this._sep(w - 2 * m), m, y);

        y += Math.round(ls * 0.5);
        const lows = d.days.map(x => x.lo);
        const highs = d.days.map(x => x.hi);
        const oLo = Math.min(...lows);
        const oHi = Math.max(...highs);
        const span = Math.max(1, oHi - oLo);
        const barW = Math.round(w * 0.28);
        const rowStep = Math.round(ls * 1.8);

        d.days.slice(0, 4).forEach((day, i) => {
            const row = new St.BoxLayout({width: w - 2 * m, style: 'spacing: 9px;'});
            const vc = a => {
                a.y_align = Clutter.ActorAlign.CENTER;
                return a;
            };
            row.add_child(vc(this._txt(day.label, FONT.display, ls, i === 0 ? 1 : 0.9)));
            row.add_child(vc(this._icon(wmoIconName(day.code, true), Math.round(ls * 1.3))));
            row.add_child(vc(this._txt(`${day.lo}°`, FONT.display, ls, 0.6)));

            const barH = Math.round(ls * 0.32);
            const track = new St.Widget({
                layout_manager: new Clutter.BinLayout(),
                width: barW, height: barH,
                y_align: Clutter.ActorAlign.CENTER,
                style: `background-color: rgba(${this._fg},0.12); border-radius: ${ls}px;`,
            });
            const fx = Math.round(((day.lo - oLo) / span) * barW);
            const fw = Math.max(5, Math.round(((day.hi - day.lo) / span) * barW));
            track.add_child(new St.Widget({
                width: fw, height: barH,
                x_align: Clutter.ActorAlign.START,
                style: `margin-left: ${fx}px; background-color: rgba(${this._fg},0.5); border-radius: ${ls}px;`,
            }));
            row.add_child(track);
            row.add_child(vc(this._txt(`${day.hi}°`, FONT.display, ls)));
            this._add(row, m, y + i * rowStep);
        });
    }

    _sep(width) {
        return new St.Widget({
            width, height: 1,
            style: `background-color: rgba(${this._fg},0.16);`,
        });
    }

    destroy() {
        this._unsub?.();
        this._root.destroy();
    }
}
