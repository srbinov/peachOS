// The catalogue the picker reads and widgetLayer instantiates from.
//
// type -> { name, appIcon (themed icon name, resolves in the MacTahoe theme),
//           variants: { id -> { name, base:{w,h}, radiusRatio, make } } }
//
// Every widget renders at one fixed size -- base * SIZE_K. There is no
// per-widget size option; the layout is derived from those pixels (KDE-style).

import {DigitalClock, AnalogClock} from '../widgets/clock.js';
import {CityClock} from '../widgets/cityClock.js';
import {WeatherWidget} from '../widgets/weather.js';
import {CalendarWidget} from '../widgets/calendar.js';

// The single size everything renders at (15% smaller than the original 1.0).
export const SIZE_K = 0.85;

export const REGISTRY = {
    clock: {
        name: 'Clock',
        appIcon: 'org.gnome.Clocks',
        variants: {
            digital: {
                name: 'Digital', base: {w: 200, h: 200}, radiusRatio: 0.24,
                make: (parent, ctx, size) => new DigitalClock(parent, size),
            },
            analog: {
                name: 'Analog', base: {w: 200, h: 200}, radiusRatio: 0.24,
                make: (parent, ctx, size) => new AnalogClock(parent, size, 'minimal'),
            },
            classic: {
                name: 'Classic', base: {w: 200, h: 200}, radiusRatio: 0.24,
                make: (parent, ctx, size) => new AnalogClock(parent, size, 'classic'),
            },
            dial: {
                name: 'Dial', base: {w: 200, h: 200}, radiusRatio: 0.24,
                make: (parent, ctx, size) => new AnalogClock(parent, size, 'fullface'),
            },
            world: {
                // same footprint as a normal clock (2x2 minimal faces inside).
                name: 'World', base: {w: 200, h: 200}, radiusRatio: 0.24,
                configurable: true,
                make: (parent, ctx, size) => new CityClock(parent, ctx, {...size, layout: 'grid'}),
            },
            worldRow: {
                // ~= two square clocks side by side (+ their gap); same height
                // and same corner curvature as a normal clock.
                name: 'World Row', base: {w: 408, h: 200}, radiusRatio: 0.24,
                configurable: true,
                make: (parent, ctx, size) => new CityClock(parent, ctx, {...size, layout: 'row'}),
            },
        },
    },
    weather: {
        name: 'Weather',
        appIcon: 'org.gnome.Weather',
        variants: {
            conditions: {
                name: 'Conditions', base: {w: 230, h: 230}, radiusRatio: 0.30,
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'small'),
            },
            forecast: {
                name: 'Forecast', base: {w: 250, h: 300}, radiusRatio: 0.20,
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'big'),
            },
        },
    },
    calendar: {
        name: 'Calendar',
        appIcon: 'org.gnome.Calendar',
        variants: {
            month: {
                name: 'Month', base: {w: 280, h: 280}, radiusRatio: 0.22,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'month'),
            },
            agenda: {
                name: 'Agenda', base: {w: 540, h: 270}, radiusRatio: 0.2,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'agenda'),
            },
        },
    },
};

export function variantDef(type, variant) {
    return REGISTRY[type]?.variants[variant] ?? null;
}

/** Real pixel geometry for a (type, variant) -- one fixed size. */
export function sizeFor(type, variant) {
    const def = variantDef(type, variant);
    if (!def)
        return null;
    const w = Math.round(def.base.w * SIZE_K);
    const h = Math.round(def.base.h * SIZE_K);
    return {w, h, radius: Math.round(Math.min(w, h) * def.radiusRatio)};
}
