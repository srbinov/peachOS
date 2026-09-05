// Weather widget -- 'compact' (temp + condition) and 'panel' (adds a 4-day
// strip). Data from lib/providers/weather.js (Open-Meteo).

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import {wmoInfo} from '../lib/providers/weather.js';

export class WeatherWidget {
    constructor(parent, ctx, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._root = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            y_expand: true,
            style_class: 'peachos-widget-weather',
        });
        parent.add_child(this._root);
        this._unsub = ctx.weather.subscribe((data, err) => this._render(data, err));
    }

    _render(data, err) {
        this._root.destroy_all_children();

        if (!data) {
            const l = new St.Label({
                text: err ? 'Weather unavailable' : 'Loading weather…',
                style_class: 'peachos-widget-weather-status',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
                y_expand: true,
            });
            this._root.add_child(l);
            return;
        }

        const [label, icon] = wmoInfo(data.code, data.isDay);

        const top = new St.BoxLayout({style_class: 'peachos-widget-weather-top', x_expand: true});
        top.add_child(new St.Icon({
            icon_name: icon,
            style_class: 'peachos-widget-weather-icon',
            y_align: Clutter.ActorAlign.CENTER,
        }));

        const textCol = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
        });
        textCol.add_child(new St.Label({
            text: `${data.temp}°`,
            style_class: 'peachos-widget-weather-temp',
        }));
        textCol.add_child(new St.Label({
            text: data.name,
            style_class: 'peachos-widget-weather-place',
        }));
        top.add_child(textCol);
        this._root.add_child(top);

        this._root.add_child(new St.Label({
            text: `${label} · Feels ${data.feels}°`,
            style_class: 'peachos-widget-weather-cond',
        }));

        if (this._mode === 'panel' && data.days.length) {
            const strip = new St.BoxLayout({
                style_class: 'peachos-widget-weather-strip',
                x_expand: true,
            });
            for (const day of data.days.slice(0, 4)) {
                const [, dIcon] = wmoInfo(day.code, true);
                const col = new St.BoxLayout({
                    orientation: Clutter.Orientation.VERTICAL,
                    x_expand: true,
                    style_class: 'peachos-widget-weather-day',
                });
                col.add_child(new St.Label({
                    text: day.label,
                    style_class: 'peachos-widget-weather-day-label',
                    x_align: Clutter.ActorAlign.CENTER,
                }));
                col.add_child(new St.Icon({
                    icon_name: dIcon,
                    style_class: 'peachos-widget-weather-day-icon',
                    x_align: Clutter.ActorAlign.CENTER,
                }));
                col.add_child(new St.Label({
                    text: `${day.hi}° ${day.lo}°`,
                    style_class: 'peachos-widget-weather-day-temp',
                    x_align: Clutter.ActorAlign.CENTER,
                }));
                strip.add_child(col);
            }
            this._root.add_child(strip);
        }
    }

    destroy() {
        this._unsub?.();
        this._root.destroy();
    }
}
