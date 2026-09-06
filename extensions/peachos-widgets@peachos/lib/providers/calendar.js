// Calendar events via GNOME Shell's own DBusEventSource (talks to
// org.gnome.Shell.CalendarServer, backed by Evolution Data Server / GNOME
// Online Accounts) -- the same accounts the top-bar calendar shows.
//
// CRITICAL: requestRange() must be called ONLY from _refreshRange(), never
// from getEvents(). A requestRange whose window differs from the last one
// makes DBusEventSource reload and re-emit 'changed'; if that happens inside
// the 'changed' -> subscribers -> render -> getEvents chain it recurses
// forever and takes the shell down. getEvents() is a pure read of the cache.

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
        this._emitId = 0;
        this._emitting = false;
        this._rangeKey = '';

        try {
            this._source = new Calendar.DBusEventSource();
            this._source.connectObject('changed', () => this._scheduleEmit(), this);
        } catch (e) {
            logError(e, '[peachos-widgets] calendar source unavailable');
            this._source = null;
        }

        this._refreshRange();
        // Roll the loaded window forward roughly daily.
        this._rangeTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 6 * 3600, () => {
            this._refreshRange();
            return GLib.SOURCE_CONTINUE;
        });
    }

    get available() {
        return this._source !== null;
    }

    subscribe(fn) {
        this._listeners.add(fn);
        fn();
        return () => this._listeners.delete(fn);
    }

    // Coalesce 'changed' bursts onto an idle so a reload triggered mid-render
    // can't recurse synchronously.
    _scheduleEmit() {
        if (this._emitId)
            return;
        this._emitId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._emitId = 0;
            if (this._emitting)
                return GLib.SOURCE_REMOVE;
            this._emitting = true;
            try {
                for (const fn of this._listeners)
                    fn();
            } finally {
                this._emitting = false;
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    // The ONLY place requestRange() is called. One wide window (start of this
    // month -> +60 days) covers every widget's needs.
    _refreshRange() {
        if (!this._source)
            return;
        const now = new Date();
        const begin = new Date(now.getFullYear(), now.getMonth(), 1);
        const end = new Date(begin);
        end.setDate(end.getDate() + 62);
        const key = `${begin.getTime()}-${end.getTime()}`;
        if (key === this._rangeKey)
            return;
        this._rangeKey = key;
        this._source.requestRange(begin, end);
    }

    /** Cached events overlapping [begin, end], each { summary, date, end, allDay }. */
    getEvents(begin, end) {
        if (!this._source)
            return [];
        const events = this._source.getEvents(begin, end) ?? [];
        return events.map(ev => {
            const span = ev.end.getTime() - ev.date.getTime();
            const allDay = ev.date.getHours() === 0 && ev.date.getMinutes() === 0 &&
                span % (24 * 3600 * 1000) === 0 && span >= 24 * 3600 * 1000;
            return {summary: ev.summary, date: ev.date, end: ev.end, allDay};
        });
    }

    upcoming(count = 5) {
        const now = new Date();
        const end = new Date(now);
        end.setDate(end.getDate() + 45);
        return this.getEvents(now, end).slice(0, count);
    }

    hasEventsOn(day) {
        const b = startOfDay(day);
        const e = new Date(b);
        e.setDate(e.getDate() + 1);
        return this.getEvents(b, e).length > 0;
    }

    destroy() {
        this._listeners.clear();
        if (this._emitId) {
            GLib.source_remove(this._emitId);
            this._emitId = 0;
        }
        if (this._rangeTimer) {
            GLib.source_remove(this._rangeTimer);
            this._rangeTimer = 0;
        }
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
