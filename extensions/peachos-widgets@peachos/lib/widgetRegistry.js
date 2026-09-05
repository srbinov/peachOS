// The catalogue the picker reads and widgetLayer instantiates from.
//
// Each type has a left-rail icon and one or more variants. A variant knows its
// inner (visible-glass) pixel size, corner radius, and a make(contentParent,
// ctx, size) that returns an object with a .destroy(). ctx = shared services
// { settings, weather, calendar }. Sizes/radii mirror the KDE liquidglass
// widgets (cornerRadius ~= 0.46 * min side -> nearly circular corners).

import {DigitalClock, AnalogClock} from '../widgets/clock.js';
import {WeatherWidget} from '../widgets/weather.js';
import {CalendarWidget} from '../widgets/calendar.js';

const rad = (w, h) => Math.round(Math.min(w, h) * 0.46);

export const REGISTRY = {
    clock: {
        name: 'Clock',
        icon: 'preferences-system-time-symbolic',
        variants: {
            digital: {
                name: 'Digital', w: 200, h: 200, radius: rad(200, 200),
                make: (parent, ctx, size) => new DigitalClock(parent, size),
            },
            analog: {
                name: 'Analog', w: 200, h: 200, radius: rad(200, 200),
                make: (parent, ctx, size) => new AnalogClock(parent, size),
            },
        },
    },
    weather: {
        name: 'Weather',
        icon: 'weather-few-clouds-symbolic',
        variants: {
            compact: {
                name: 'Now', w: 240, h: 240, radius: rad(240, 240),
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'small'),
            },
            panel: {
                name: 'Forecast', w: 320, h: 320, radius: rad(320, 320),
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'big'),
            },
        },
    },
    calendar: {
        name: 'Calendar',
        icon: 'x-office-calendar-symbolic',
        variants: {
            month: {
                name: 'Month', w: 260, h: 260, radius: rad(260, 260),
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'month'),
            },
            agenda: {
                name: 'Agenda', w: 470, h: 235, radius: 64,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'agenda'),
            },
        },
    },
};

export function variantDef(type, variant) {
    const t = REGISTRY[type];
    if (!t)
        return null;
    return t.variants[variant] ?? null;
}
