// Weather widget, matched to the KDE liquidglass repo (packages/weather).
//
//  'small' -- city, a very large thin temperature, the condition icon
//   top-right with H/L below it, precipitation + wind bottom-left.
//  'big'   -- header + an hourly strip + a 4-day forecast with range bars.
//
// Icons: bundled KDE mono-light PNGs. Fonts: SF Pro Display (Thin for the
// temperature, Regular elsewhere).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {wmoCondition, wmoIconName} from '../lib/providers/weather.js';
import {applyFont, FAMILIES, Pango} from '../lib/fonts.js';

function wIcon(ctxPath, name, size) {
    return new St.Icon({
        gicon: Gio.icon_new_for_string(
            GLib.build_filenamev([ctxPath, 'icons', 'weather', `${name}.png`])),
        icon_size: Math.round(size),
    });
}

function txt(text, px, weight = Pango.Weight.NORMAL, opacity = 1) {
    const l = new St.Label({text});
    applyFont(l, FAMILIES.display, px, weight);
    l.style = `color: rgba(255,255,255,${opacity});`;
    return l;
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
            const l = txt(err ? 'Weather unavailable' : 'Loading…', 13, Pango.Weight.NORMAL, 0.8);
            l.set_position(Math.round(this._w * 0.1), Math.round(this._h / 2 - 10));
            this._root.add_child(l);
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
        const ls = Math.max(10, Math.round(Math.min(h, 350) * 0.065));
        const p = this._ctx.path;

        this._add(txt(d.name, ls * 1.1, Pango.Weight.MEDIUM), m, m);

        const temp = txt(`${d.temp}°`, ls * 4, Pango.Weight.THIN);
        this._add(temp, m - Math.round(ls * 0.06), m + Math.round(ls * 1.35));

        const iconSize = Math.round(ls * 3);
        this._add(wIcon(p, wmoIconName(d.code, d.isDay), iconSize),
            w - m - iconSize, m - Math.round(ls * 0.3));

        // H / L, right-aligned, below the icon
        const hl = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.END,
            style: `spacing: ${Math.round(ls * 0.15)}px;`,
        });
        const mkRow = (arrow, val, op) => {
            const r = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.15)}px;`});
            r.add_child(txt(arrow, ls, Pango.Weight.NORMAL, op));
            r.add_child(txt(val, ls, Pango.Weight.NORMAL, op));
            return r;
        };
        hl.add_child(mkRow('↑', `${d.hi}°`, 1));
        hl.add_child(mkRow('↓', `${d.lo}°`, 0.7));
        this._add(hl, w - m - Math.round(ls * 3.4), m + iconSize + Math.round(ls * 0.1));

        // Precipitation + wind, pinned bottom-left
        const info = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        const is = Math.round(ls * 0.86);
        info.add_child(txt('Precipitation', is, Pango.Weight.MEDIUM));
        info.add_child(txt(
            d.precipProb != null ? `${d.precipProb}% chance` : `${d.precip}"`,
            is, Pango.Weight.NORMAL, 0.55));
        info.add_child(new St.Widget({height: Math.round(ls * 0.4), width: 1}));
        info.add_child(txt('Wind', is, Pango.Weight.MEDIUM));
        info.add_child(txt(`${d.wind} mph ${d.windDir}`, is, Pango.Weight.NORMAL, 0.55));
        const infoH = Math.round(is * 4 * 1.35 + ls * 0.4);
        this._add(info, m, h - m - infoH);
    }

    _renderBig(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.06);
        const ls = Math.max(10, Math.round(Math.min(h, 350) * 0.062));
        const p = this._ctx.path;

        // Header: city + temp left, icon + condition + H/L right
        const left = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        left.add_child(txt(d.name, ls * 1.15, Pango.Weight.MEDIUM));
        left.add_child(txt(`${d.temp}°`, ls * 3.3, Pango.Weight.THIN));
        this._add(left, m, m);

        const iconSize = Math.round(ls * 2.6);
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.END,
            style: `spacing: ${Math.round(ls * 0.15)}px;`,
        });
        const ri = wIcon(p, wmoIconName(d.code, d.isDay), iconSize);
        ri.x_align = Clutter.ActorAlign.END;
        right.add_child(ri);
        const cond = txt(wmoCondition(d.code), ls, Pango.Weight.MEDIUM);
        cond.x_align = Clutter.ActorAlign.END;
        right.add_child(cond);
        const hlL = txt(`H:${d.hi}°  L:${d.lo}°`, ls, Pango.Weight.MEDIUM, 0.7);
        hlL.x_align = Clutter.ActorAlign.END;
        right.add_child(hlL);
        this._add(right, w - m - Math.round(ls * 7), m);

        let y = m + Math.round(ls * 4.2);
        this._add(this._sep(w - 2 * m), m, y);

        // Hourly strip
        y += Math.round(ls * 0.55);
        const hourly = new St.BoxLayout({width: w - 2 * m});
        for (const slot of d.hours.slice(0, 6)) {
            const col = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 4px;',
            });
            const hl = txt(slot.hour, ls * 0.8, Pango.Weight.NORMAL, 0.7);
            hl.x_align = Clutter.ActorAlign.CENTER;
            col.add_child(hl);
            const ic = wIcon(p, wmoIconName(slot.code, d.isDay), Math.round(ls * 1.6));
            ic.x_align = Clutter.ActorAlign.CENTER;
            col.add_child(ic);
            const tl = txt(`${slot.temp}°`, ls * 0.92);
            tl.x_align = Clutter.ActorAlign.CENTER;
            col.add_child(tl);
            hourly.add_child(col);
        }
        this._add(hourly, m, y);

        y += Math.round(ls * 4.4);
        this._add(this._sep(w - 2 * m), m, y);

        // 4-day forecast with range bars
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
            const dl = txt(day.label, ls, Pango.Weight.MEDIUM, i === 0 ? 1 : 0.9);
            dl.y_align = Clutter.ActorAlign.CENTER;
            row.add_child(dl);
            const di = wIcon(p, wmoIconName(day.code, true), Math.round(ls * 1.35));
            di.y_align = Clutter.ActorAlign.CENTER;
            row.add_child(di);
            const loL = txt(`${day.lo}°`, ls, Pango.Weight.NORMAL, 0.6);
            loL.y_align = Clutter.ActorAlign.CENTER;
            row.add_child(loL);

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
            const hiL = txt(`${day.hi}°`, ls);
            hiL.y_align = Clutter.ActorAlign.CENTER;
            row.add_child(hiL);
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
