// The catalogue the picker reads and widgetLayer instantiates from.
//
// Each type has a left-rail icon and one or more variants. A variant knows its
// inner (visible-glass) pixel size, corner radius, and a make(contentParent,
// ctx) that returns an object with a .destroy(). ctx = shared services
// { settings, weather, calendar }.

import {DigitalClock, AnalogClock} from '../widgets/clock.js';
import {WeatherWidget} from '../widgets/weather.js';
import {CalendarWidget} from '../widgets/calendar.js';

export const REGISTRY = {
    clock: {
        name: 'Clock',
        icon: 'preferences-system-time-symbolic',
        variants: {
            digital: {
                name: 'Digital', w: 260, h: 118, radius: 28,
                make: parent => new DigitalClock(parent),
            },
            analog: {
                name: 'Analog', w: 168, h: 168, radius: 22,
                make: parent => new AnalogClock(parent),
            },
        },
    },
    weather: {
        name: 'Weather',
        icon: 'weather-few-clouds-symbolic',
        variants: {
            compact: {
                name: 'Compact', w: 210, h: 132, radius: 28,
                make: (parent, ctx) => new WeatherWidget(parent, ctx, 'compact'),
            },
            panel: {
                name: 'Forecast', w: 320, h: 176, radius: 30,
                make: (parent, ctx) => new WeatherWidget(parent, ctx, 'panel'),
            },
        },
    },
    calendar: {
        name: 'Calendar',
        icon: 'x-office-calendar-symbolic',
        variants: {
            month: {
                name: 'Month', w: 248, h: 236, radius: 26,
                make: (parent, ctx) => new CalendarWidget(parent, ctx, 'month'),
            },
            agenda: {
                name: 'Agenda', w: 300, h: 300, radius: 28,
                make: (parent, ctx) => new CalendarWidget(parent, ctx, 'agenda'),
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
