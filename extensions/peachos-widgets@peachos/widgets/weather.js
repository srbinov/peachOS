// Weather widget, matched to the KDE liquidglass repo.
//
//  'small' -- city + pin, a very large thin temperature, the condition icon
//  top-right with H/L below it, and precipitation + wind bottom-left.
//  'big'   -- the same header plus an hourly strip and a 4-day forecast.
//
// Icons: the bundled KDE mono-light PNG set (icons/weather/*.png).
// Fonts: SF Pro Display (Regular / Thin).

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {wmoCondition, wmoIconName} from '../lib/providers/weather.js';

const FG = 'rgba(255,255,255,%A)';

function icon(ctxPath, name, size) {
    return new St.Icon({
        gicon: Gio.icon_new_for_string(
            GLib.build_filenamev([ctxPath, 'icons', 'weather', `${name}.png`])),
        icon_size: Math.round(size),
        style_class: 'peachos-weather-icon',
    });
}

function label(text, cls, sizePx, opacity = 1) {
    return new St.Label({
        text,
        style_class: cls,
        style: `font-size: ${Math.round(sizePx)}px;${opacity < 1 ? ` color: rgba(255,255,255,${opacity});` : ''}`,
    });
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
            const l = new St.Label({
                text: err ? 'Weather unavailable' : 'Loading…',
                style_class: 'peachos-weather-status',
            });
            l.set_position(
                Math.round((this._w - 120) / 2), Math.round(this._h / 2 - 10));
            this._root.add_child(l);
            return;
        }

        if (this._mode === 'big')
            this._renderBig(data);
        else
            this._renderSmall(data);
    }

    _renderSmall(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.09);
        const ls = Math.max(10, Math.round(Math.min(h, 350) * 0.065));
        const p = this._ctx.path;

        // City (top-left)
        const city = label(d.name, 'peachos-weather-city', ls * 1.1);
        city.set_position(m, m);
        this._root.add_child(city);

        // Big temperature
        const temp = label(`${d.temp}°`, 'peachos-weather-temp-big', ls * 4);
        temp.set_position(m - Math.round(ls * 0.1), m + Math.round(ls * 1.15));
        this._root.add_child(temp);

        // Condition icon (top-right) + H/L
        const iconSize = Math.round(ls * 3);
        const wIcon = icon(p, wmoIconName(d.code, d.isDay), iconSize);
        wIcon.set_position(w - m - iconSize, m - Math.round(ls * 0.4));
        this._root.add_child(wIcon);

        const hl = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.15)}px;`,
        });
        const hiRow = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.15)}px;`});
        hiRow.add_child(label('↑', 'peachos-weather-hl', ls));
        hiRow.add_child(label(`${d.hi}°`, 'peachos-weather-hl', ls));
        const loRow = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.15)}px;`});
        loRow.add_child(label('↓', 'peachos-weather-hl', ls, 0.7));
        loRow.add_child(label(`${d.lo}°`, 'peachos-weather-hl', ls, 0.7));
        hl.add_child(hiRow);
        hl.add_child(loRow);
        hl.set_position(w - m - Math.round(ls * 3.2), m + iconSize - Math.round(ls * 0.3));
        this._root.add_child(hl);

        // Precipitation + wind (bottom-left)
        const info = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        const infoSize = Math.round(ls * 0.86);
        info.add_child(label('Precipitation', 'peachos-weather-info-key', infoSize));
        info.add_child(label(
            d.precipProb != null ? `${d.precipProb}% chance` : `${d.precip} in`,
            'peachos-weather-info-val', infoSize, 0.55));
        info.add_child(new St.Widget({height: Math.round(ls * 0.35), width: 1}));
        info.add_child(label('Wind', 'peachos-weather-info-key', infoSize));
        info.add_child(label(`${d.wind} mph ${d.windDir}`, 'peachos-weather-info-val', infoSize, 0.55));
        info.set_position(m, h - m - Math.round(infoSize * 5.4));
        this._root.add_child(info);
    }

    _renderBig(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.06);
        const ls = Math.max(10, Math.round(Math.min(h, 350) * 0.062));
        const p = this._ctx.path;

        // Header: city + temp (left), icon + condition + H/L (right)
        const left = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL});
        left.add_child(label(d.name, 'peachos-weather-city', ls * 1.15));
        left.add_child(label(`${d.temp}°`, 'peachos-weather-temp-big', ls * 3.4));
        left.set_position(m, m);
        this._root.add_child(left);

        const iconSize = Math.round(ls * 2.6);
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.END,
        });
        const ri = icon(p, wmoIconName(d.code, d.isDay), iconSize);
        ri.x_align = Clutter.ActorAlign.END;
        right.add_child(ri);
        right.add_child(label(wmoCondition(d.code), 'peachos-weather-cond', ls));
        right.add_child(label(`H:${d.hi}°  L:${d.lo}°`, 'peachos-weather-hl', ls, 0.7));
        right.set_position(w - m - Math.round(ls * 6.5), m);
        this._root.add_child(right);

        // Separator
        let y = m + Math.round(ls * 4.4);
        this._root.add_child(this._sep(m, y, w - 2 * m));

        // Hourly strip
        y += Math.round(ls * 0.5);
        const hourly = new St.BoxLayout({width: w - 2 * m});
        for (const slot of d.hours.slice(0, 6)) {
            const col = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 3px;',
            });
            col.add_child(label(slot.hour, 'peachos-weather-hour', ls * 0.82, 0.7));
            col.add_child(icon(p, wmoIconName(slot.code, d.isDay), Math.round(ls * 1.5)));
            col.add_child(label(`${slot.temp}°`, 'peachos-weather-hour', ls * 0.9));
            hourly.add_child(col);
        }
        hourly.set_position(m, y);
        this._root.add_child(hourly);

        y += Math.round(ls * 4.2);
        this._root.add_child(this._sep(m, y, w - 2 * m));

        // 4-day forecast with range bars
        y += Math.round(ls * 0.5);
        const lows = d.days.map(x => x.lo);
        const highs = d.days.map(x => x.hi);
        const overallLo = Math.min(...lows);
        const overallHi = Math.max(...highs);
        const span = Math.max(1, overallHi - overallLo);
        const barW = Math.round(w * 0.28);

        d.days.slice(0, 4).forEach((day, i) => {
            const row = new St.BoxLayout({
                width: w - 2 * m,
                style: 'spacing: 8px;',
            });
            row.add_child(label(day.label, 'peachos-weather-day', ls, i === 0 ? 1 : 0.9));
            const di = icon(p, wmoIconName(day.code, true), Math.round(ls * 1.3));
            row.add_child(di);
            row.add_child(label(`${day.lo}°`, 'peachos-weather-day', ls, 0.6));

            const barH = Math.round(ls * 0.32);
            const track = new St.Widget({
                layout_manager: new Clutter.BinLayout(),
                width: barW, height: barH,
                y_align: Clutter.ActorAlign.CENTER,
                style: `background-color: rgba(255,255,255,0.12); border-radius: ${ls}px;`,
            });
            const fillX = Math.round(((day.lo - overallLo) / span) * barW);
            const fillW = Math.max(4, Math.round(((day.hi - day.lo) / span) * barW));
            const fill = new St.Widget({
                width: fillW, height: barH,
                x_align: Clutter.ActorAlign.START,
                style: `margin-left: ${fillX}px; background-color: rgba(255,255,255,0.5); border-radius: ${ls}px;`,
            });
            track.add_child(fill);
            row.add_child(track);
            row.add_child(label(`${day.hi}°`, 'peachos-weather-day', ls));
            row.set_position(m, y + i * Math.round(ls * 1.7));
            this._root.add_child(row);
        });
    }

    _sep(x, y, w) {
        const s = new St.Widget({
            x, y, width: w, height: 1,
            style: 'background-color: rgba(255,255,255,0.15);',
        });
        return s;
    }

    destroy() {
        this._unsub?.();
        this._root.destroy();
    }
}
