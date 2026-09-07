// Weather widget, ported from the KDE liquidglass repo (packages/weather).
//
//  'small' -- city, a very large thin temperature, condition icon top-right
//   with H/L below it, precipitation + wind bottom-left.
//  'big'   -- header + an hourly strip + a 4-day forecast with range bars.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {wmoCondition, wmoIconName, skyGradient} from '../lib/providers/weather.js';
import {FONT, fontStyle, Pango} from '../lib/fonts.js';

export class WeatherWidget {
    constructor(parent, ctx, size, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._w = size.w;
        this._h = size.h;
        this._cardMode = size.mode || 'glass';
        this._baseFg = size.fg || '255,255,255';
        this._setTint = size.setTint;
        this._fg = this._baseFg;
        this._iconSet = 'weather-mono';

        this._root = new Clutter.Actor({width: size.w, height: size.h});
        parent.add_child(this._root);

        this._unsub = ctx.weather.subscribe((data, err) => this._render(data, err));
    }

    // In "light" mode the card is painted as the sky: blue for clear, grey for
    // cloud, dusky blue-black at night. Text + icons flip to suit its
    // brightness. Glass/dark modes keep the plain foreground.
    _applySky(d) {
        if (this._cardMode !== 'light' || !d) {
            this._fg = this._baseFg;
            this._iconSet = this._baseFg.startsWith('26,') ? 'weather-color' : 'weather-mono';
            this._setTint?.(null);
            return;
        }
        const sky = skyGradient(d.code, d.isDay);
        this._setTint?.(sky);
        this._fg = sky.dark ? '255,255,255' : '26,27,30';
        this._iconSet = sky.dark ? 'weather-mono' : 'weather-color';
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
        this._applySky(data);
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
        const m = Math.round(h * 0.10);
        const ls = Math.max(11, Math.round(h * 0.072));

        // Header: city name (ellipsised) + the current-location arrow.
        const arrowW = Math.round(ls * 1.3);
        const name = this._txt(d.name, FONT.display, ls * 1.12);
        name.width = w - 2 * m - arrowW;
        name.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this._add(name, m, m);
        const arrow = this._txt('➤', FONT.display, ls * 0.66, 0.9);
        arrow.set_pivot_point(0.5, 0.5);
        arrow.rotation_angle_z = -45;
        this._add(arrow, m + (w - 2 * m - arrowW) + Math.round(ls * 0.2),
            m + Math.round(ls * 0.24));

        // Condition icon, top-right, roughly header-aligned.
        const iconSize = Math.round(ls * 2.85);
        this._add(this._icon(wmoIconName(d.code, d.isDay), iconSize),
            w - m - iconSize, m - Math.round(ls * 0.35));

        // Big temperature.
        this._add(this._txt(`${d.temp}°`, FONT.displayThin, ls * 3.6),
            m - Math.round(ls * 0.05), m + Math.round(ls * 1.05));

        // High / low, stacked under the icon.
        const hl = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style: `spacing: ${Math.round(ls * 0.12)}px;`,
        });
        const mkRow = (glyph, val, op) => {
            const r = new St.BoxLayout({style: `spacing: ${Math.round(ls * 0.14)}px;`});
            r.add_child(this._txt(glyph, FONT.display, ls * 0.86, op));
            r.add_child(this._txt(val, FONT.display, ls * 1.0, op));
            return r;
        };
        hl.add_child(mkRow('↑', `${d.hi}°`, 0.95));
        hl.add_child(mkRow('↓', `${d.lo}°`, 0.6));
        this._add(hl, w - m - Math.round(ls * 3.0),
            m + iconSize + Math.round(ls * 0.05));

        // Precipitation / Wind block.
        const info = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: w - 2 * m,
        });
        const is = Math.round(ls * 0.9);
        const sub = text => {
            const l = this._txt(text, FONT.display, is, 0.55);
            l.clutter_text.line_wrap = true;
            l.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
            return l;
        };
        info.add_child(this._txt('Precipitation', FONT.display, is));
        info.add_child(sub(d.precipText));
        info.add_child(new St.Widget({height: Math.round(ls * 0.3), width: 1}));
        info.add_child(this._txt('Wind', FONT.display, is));
        info.add_child(sub(`${d.wind} ${d.windUnit} ${d.windDir}`));
        this._add(info, m, Math.round(h * 0.55));
    }

    // Row shape (two squares wide): header block + an hourly strip, like the
    // Apple Weather medium widget.
    _renderBig(d) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.12);
        const ls = Math.max(11, Math.round(h * 0.076));

        // Header left: city + big temperature.
        this._add(this._txt(d.name, FONT.display, ls * 1.05), m, m);
        this._add(this._txt(`${d.temp}°`, FONT.displayThin, ls * 3.3),
            m - Math.round(ls * 0.05), m + Math.round(ls * 1.0));

        // Header right: icon, condition, H/L -- right-aligned.
        const iconSize = Math.round(ls * 2.5);
        const right = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: Math.round(ls * 8.5),
            style: `spacing: ${Math.round(ls * 0.14)}px;`,
        });
        const rAlign = a => {
            a.x_align = Clutter.ActorAlign.END;
            return a;
        };
        right.add_child(rAlign(this._icon(wmoIconName(d.code, d.isDay), iconSize)));
        right.add_child(rAlign(this._txt(wmoCondition(d.code), FONT.display, ls)));
        right.add_child(rAlign(this._txt(`H:${d.hi}°  L:${d.lo}°`, FONT.display, ls * 0.95, 0.7)));
        this._add(right, w - m - Math.round(ls * 8.5), m - Math.round(ls * 0.2));

        // Hourly strip along the bottom.
        const strip = new St.BoxLayout({width: w - 2 * m});
        for (const slot of d.hours.slice(0, 6)) {
            const col = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                style: `spacing: ${Math.round(ls * 0.28)}px;`,
            });
            const cAlign = a => {
                a.x_align = Clutter.ActorAlign.CENTER;
                return a;
            };
            col.add_child(cAlign(this._txt(slot.hour, FONT.display, ls * 0.82, 0.7)));
            col.add_child(cAlign(this._icon(wmoIconName(slot.code, d.isDay), Math.round(ls * 1.7))));
            col.add_child(cAlign(this._txt(`${slot.temp}°`, FONT.display, ls * 0.95)));
            strip.add_child(col);
        }
        this._add(strip, m, h - m - Math.round(ls * 4.3));
    }

    destroy() {
        this._unsub?.();
        this._root.destroy();
    }
}
