// The catalogue the picker reads and widgetLayer instantiates from.
//
// Each type has a left-rail icon and one or more variants. A variant knows its
// inner (visible-glass) pixel size, corner radius, and a make(contentParent,
// ctx, size) that returns an object with a .destroy(). ctx = shared services
// { settings, weather, calendar, path }.
//
// Radius ratios mirror the KDE liquidglass screenshots: the clocks are
// near-circular iOS squircles, weather a touch less round, the calendar
// gently rounded.

import {DigitalClock, AnalogClock} from '../widgets/clock.js';
import {WeatherWidget} from '../widgets/weather.js';
import {CalendarWidget} from '../widgets/calendar.js';

export const REGISTRY = {
    clock: {
        name: 'Clock',
        icon: 'preferences-system-time-symbolic',
        variants: {
            digital: {
                name: 'Digital', w: 200, h: 200, radius: 92,
                make: (parent, ctx, size) => new DigitalClock(parent, size),
            },
            analog: {
                name: 'Analog', w: 200, h: 200, radius: 92,
                make: (parent, ctx, size) => new AnalogClock(parent, size),
            },
        },
    },
    weather: {
        name: 'Weather',
        icon: 'weather-few-clouds-symbolic',
        variants: {
            compact: {
                name: 'Now', w: 230, h: 230, radius: 68,
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'small'),
            },
            panel: {
                name: 'Forecast', w: 330, h: 330, radius: 84,
                make: (parent, ctx, size) => new WeatherWidget(parent, ctx, size, 'big'),
            },
        },
    },
    calendar: {
        name: 'Calendar',
        icon: 'x-office-calendar-symbolic',
        variants: {
            month: {
                name: 'Month', w: 300, h: 280, radius: 44,
                make: (parent, ctx, size) => new CalendarWidget(parent, ctx, size, 'month'),
            },
            agenda: {
                name: 'Agenda', w: 560, h: 280, radius: 44,
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
