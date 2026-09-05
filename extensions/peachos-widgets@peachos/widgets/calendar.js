// Calendar widget -- 'month' (a month grid, today highlighted, days with events
// dotted) and 'agenda' (month grid + a short list of upcoming events). Events
// from lib/providers/calendar.js (GNOME Shell's DBusEventSource).

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {formatEventTime} from '../lib/providers/calendar.js';

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() &&
        a.getDate() === b.getDate();
}

export class CalendarWidget {
    constructor(parent, ctx, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._root = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            y_expand: true,
            style_class: 'peachos-widget-calendar',
        });
        parent.add_child(this._root);

        this._unsub = ctx.calendar.subscribe(() => this._render());
        // Roll the grid over at midnight-ish.
        this._dayTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 1800, () => {
            this._render();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _render() {
        this._root.destroy_all_children();
        const today = new Date();

        // One events fetch for the whole visible month, then check days locally
        // (rather than one D-Bus round-trip per cell).
        const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
        const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 1);
        const monthEvents = this._ctx.calendar.getEvents(monthStart, monthEnd);
        const dayHasEvent = d => monthEvents.some(ev =>
            ev.date < new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1) &&
            ev.end > new Date(d.getFullYear(), d.getMonth(), d.getDate()));

        const header = new St.Label({
            text: today.toLocaleDateString(undefined, {month: 'long', year: 'numeric'}),
            style_class: 'peachos-widget-calendar-header',
        });
        this._root.add_child(header);

        const grid = new St.Widget({
            layout_manager: new Clutter.GridLayout(),
            style_class: 'peachos-widget-calendar-grid',
            x_expand: true,
        });
        const gl = grid.layout_manager;

        WEEKDAYS.forEach((d, i) => {
            gl.attach(new St.Label({
                text: d,
                style_class: 'peachos-widget-calendar-weekday',
                x_align: Clutter.ActorAlign.CENTER,
            }), i, 0, 1, 1);
        });

        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        const startCol = first.getDay();
        const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();

        let row = 1;
        for (let day = 1; day <= daysInMonth; day++) {
            const col = (startCol + day - 1) % 7;
            const cellDate = new Date(today.getFullYear(), today.getMonth(), day);
            const cell = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'peachos-widget-calendar-cell',
            });
            const num = new St.Label({
                text: `${day}`,
                x_align: Clutter.ActorAlign.CENTER,
                style_class: sameDay(cellDate, today)
                    ? 'peachos-widget-calendar-day peachos-widget-calendar-day--today'
                    : 'peachos-widget-calendar-day',
            });
            cell.add_child(num);
            const dot = new St.Widget({style_class: 'peachos-widget-calendar-dot'});
            dot.visible = dayHasEvent(cellDate);
            cell.add_child(dot);
            gl.attach(cell, col, row, 1, 1);
            if (col === 6)
                row++;
        }
        this._root.add_child(grid);

        if (this._mode === 'agenda') {
            const list = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                style_class: 'peachos-widget-calendar-agenda',
                x_expand: true,
            });
            const events = this._ctx.calendar.upcoming(4);
            if (!events.length) {
                list.add_child(new St.Label({
                    text: this._ctx.calendar.available ? 'No upcoming events' : 'No calendar connected',
                    style_class: 'peachos-widget-calendar-agenda-empty',
                }));
            } else {
                for (const ev of events) {
                    const rowBox = new St.BoxLayout({style_class: 'peachos-widget-calendar-agenda-row', x_expand: true});
                    rowBox.add_child(new St.Label({
                        text: ev.summary || '(untitled)',
                        style_class: 'peachos-widget-calendar-agenda-title',
                        x_expand: true,
                    }));
                    rowBox.add_child(new St.Label({
                        text: sameDay(ev.date, new Date())
                            ? formatEventTime(ev)
                            : ev.date.toLocaleDateString(undefined, {weekday: 'short'}),
                        style_class: 'peachos-widget-calendar-agenda-time',
                    }));
                    list.add_child(rowBox);
                }
            }
            this._root.add_child(list);
        }
    }

    destroy() {
        this._unsub?.();
        if (this._dayTimer)
            GLib.source_remove(this._dayTimer);
        this._dayTimer = 0;
        this._root.destroy();
    }
}
