// Calendar events via GNOME Shell's own DBusEventSource (talks to
// org.gnome.Shell.CalendarServer, which is backed by Evolution Data Server /
// GNOME Online Accounts). Reusing it means no extra gir dependency and the same
// accounts the top-bar calendar already shows.

import GLib from 'gi://GLib';

import * as Calendar from 'resource:///org/gnome/shell/ui/calendar.js';

function startOfDay(d) {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
}

export class CalendarSource {
    constructor() {
        this._listeners = new Set();
        try {
            this._source = new Calendar.DBusEventSource();
            this._source.connectObject('changed', () => this._emit(), this);
        } catch (e) {
            logError(e, '[peachos-widgets] calendar source unavailable');
            this._source = null;
        }
        this._requestUpcomingRange();
    }

    get available() {
        return this._source !== null;
    }

    subscribe(fn) {
        this._listeners.add(fn);
        fn();
        return () => this._listeners.delete(fn);
    }

    _emit() {
        for (const fn of this._listeners)
            fn();
    }

    _requestUpcomingRange() {
        if (!this._source)
            return;
        const begin = startOfDay(new Date());
        const end = new Date(begin);
        end.setDate(end.getDate() + 14);
        this._source.requestRange(begin, end);
    }

    /** Events between two JS Dates, each { summary, date, end, allDay }. */
    getEvents(begin, end) {
        if (!this._source)
            return [];
        this._source.requestRange(startOfDay(begin), end);
        const events = this._source.getEvents(begin, end) ?? [];
        return events.map(ev => {
            const span = ev.end.getTime() - ev.date.getTime();
            const allDay = ev.date.getHours() === 0 && ev.date.getMinutes() === 0 &&
                span % (24 * 3600 * 1000) === 0 && span >= 24 * 3600 * 1000;
            return {summary: ev.summary, date: ev.date, end: ev.end, allDay};
        });
    }

    /** The next `count` upcoming events from now. */
    upcoming(count = 5) {
        const now = new Date();
        const end = new Date(now);
        end.setDate(end.getDate() + 14);
        return this.getEvents(now, end).slice(0, count);
    }

    /** True if any event touches the given day (JS Date). */
    hasEventsOn(day) {
        const b = startOfDay(day);
        const e = new Date(b);
        e.setDate(e.getDate() + 1);
        return this.getEvents(b, e).length > 0;
    }

    destroy() {
        this._listeners.clear();
        if (this._source) {
            this._source.disconnectObject(this);
            this._source.destroy?.();
            this._source = null;
        }
    }
}

export function formatEventTime(ev) {
    if (ev.allDay)
        return 'All day';
    const t = GLib.DateTime.new_from_unix_local(Math.floor(ev.date.getTime() / 1000));
    return t.format('%-I:%M %p');
}
