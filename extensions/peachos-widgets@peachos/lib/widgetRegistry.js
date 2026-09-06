// The catalogue the picker reads and widgetLayer instantiates from.
//
// type -> { name, appIcon (themed icon name, resolves in the MacTahoe theme),
//           variants: { id -> { name, base:{w,h}, radiusRatio, make } } }
//
// Every placed widget also has a `scale` (sm | md | lg); the real pixel size is
// base * SCALE[scale], and each widget's layout is derived from those pixels
// (KDE-style), so one variant covers all three sizes.

import {DigitalClock, AnalogClock} from '../widgets/clock.js';
import {WeatherWidget} from '../widgets/weather.js';
import {CalendarWidget} from '../widgets/calendar.js';

// 15% smaller than the original 0.78 / 1.0 / 1.32
export const SCALES = {sm: 0.663, md: 0.85, lg: 1.122};
export const SCALE_ORDER = ['sm', 'md', 'lg'];

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
                name: 'Month', base: {w: 280, h: 280}, radiusRatio: 0.16,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'month'),
            },
            agenda: {
                name: 'Agenda', base: {w: 520, h: 280}, radiusRatio: 0.16,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'agenda'),
            },
        },
    },
};

export function variantDef(type, variant) {
    return REGISTRY[type]?.variants[variant] ?? null;
}

/** Real pixel geometry for a (type, variant, scale). */
export function sizeFor(type, variant, scale) {
    const def = variantDef(type, variant);
    if (!def)
        return null;
    const k = SCALES[scale] ?? 1;
    const w = Math.round(def.base.w * k);
    const h = Math.round(def.base.h * k);
    return {w, h, radius: Math.round(Math.min(w, h) * def.radiusRatio)};
}
