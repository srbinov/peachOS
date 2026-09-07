// Google Calendar events -- the same DBusEventSource the regular calendar
// widget uses (Evolution Data Server / GNOME Online Accounts), but filtered to
// the calendars that belong to a Google account.
//
// `connected` gates an empty state whose button opens peachOS Settings ->
// Internet Accounts, where the native Google sign-in lives. Once the account
// is added, EDS syncs the events and GOA refreshes the tokens.
//
// Same requestRange discipline as lib/providers/calendar.js: reload only from
// _refreshRange(), never from getEvents().

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Calendar from 'resource:///org/gnome/shell/ui/calendar.js';

const SOURCES_NAME = 'org.gnome.evolution.dataserver.Sources5';
const SOURCES_PATH = '/org/gnome/evolution/dataserver/SourceManager';
const SOURCE_IFACE = 'org.gnome.evolution.dataserver.Source';

export class GoogleCalendarSource {
    constructor() {
        this._listeners = new Set();
        this._emitId = 0;
        this._emitting = false;
        this._rangeKey = '';
        this._googleUids = null;   // Set<uid> of Google calendar sources, or null
        this._connected = false;   // a Google account with a calendar exists

        try {
            this._source = new Calendar.DBusEventSource();
            this._source.connectObject('changed', () => this._scheduleEmit(), this);
        } catch (e) {
            logError(e, '[peachos-widgets] google calendar source unavailable');
            this._source = null;
        }

        this._detect();
        this._refreshRange();
        this._rangeTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 6 * 3600, () => {
            this._refreshRange();
            return GLib.SOURCE_CONTINUE;
        });
        // an account can be added while we're running
        this._detectTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 90, () => {
            this._detect();
            return GLib.SOURCE_CONTINUE;
        });
        // pull fresh CalDAV data more often than EDS's own ~30-min cadence
        this._syncTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 5 * 60, () => {
            this._refreshCalDav();
            return GLib.SOURCE_CONTINUE;
        });
    }

    // Ask EDS to fetch each Google calendar from the server now.
    _refreshCalDav() {
        for (const uid of this._googleUids ?? []) {
            Gio.DBus.session.call(
                'org.gnome.evolution.dataserver.Calendar8',
                '/org/gnome/evolution/dataserver/CalendarFactory',
                'org.gnome.evolution.dataserver.CalendarFactory', 'OpenCalendar',
                new GLib.Variant('(s)', [uid]), null,
                Gio.DBusCallFlags.NONE, 15000, null,
                (bus, res) => {
                    try {
                        const [path, name] = bus.call_finish(res).deepUnpack();
                        bus.call(name, path,
                            'org.gnome.evolution.dataserver.Calendar', 'Refresh',
                            null, null, Gio.DBusCallFlags.NONE, 15000, null, null);
                    } catch (e) {
                        // backend busy / offline -- next tick
                    }
                });
        }
    }

    get connected() {
        return this._connected;
    }

    subscribe(fn) {
        this._listeners.add(fn);
        fn();
        return () => this._listeners.delete(fn);
    }

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

    // --- which calendars are Google ---------------------------------------

    async _detect() {
        let googleAccountIds = new Set();
        try {
            googleAccountIds = await this._googleAccounts();
        } catch (e) {
            // GOA unavailable -- fall through with an empty set
        }

        let uids = null;
        try {
            uids = await this._googleSourceUids(googleAccountIds);
        } catch (e) {
            logError(e, '[peachos-widgets] EDS source enumeration failed');
        }

        const before = this._googleUids ? [...this._googleUids].sort().join() : '';
        this._googleUids = uids && uids.size ? uids : null;
        this._connected = (this._googleUids !== null) || googleAccountIds.size > 0;
        const after = this._googleUids ? [...this._googleUids].sort().join() : '';
        if (this._googleUids && after !== before)
            this._refreshCalDav();          // new/changed account -> fetch now
        this._scheduleEmit();
    }

    async _googleAccounts() {
        const {default: Goa} = await import('gi://Goa');
        const client = await new Promise((resolve, reject) => {
            Goa.Client.new(null, (_o, res) => {
                try {
                    resolve(Goa.Client.new_finish(res));
                } catch (e) {
                    reject(e);
                }
            });
        });
        const ids = new Set();
        for (const obj of client.get_accounts()) {
            const acc = obj.get_account();
            if (!acc || acc.provider_type !== 'google')
                continue;
            if (acc.calendar_disabled || !obj.get_calendar())
                continue;
            ids.add(acc.id);
        }
        return ids;
    }

    _googleSourceUids(googleAccountIds) {
        return new Promise((resolve, reject) => {
            Gio.DBus.session.call(
                SOURCES_NAME, SOURCES_PATH,
                'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects',
                null, null, Gio.DBusCallFlags.NONE, 5000, null,
                (bus, res) => {
                    try {
                        const [objects] = bus.call_finish(res).recursiveUnpack();
                        resolve(this._parseSources(objects, googleAccountIds));
                    } catch (e) {
                        reject(e);
                    }
                });
        });
    }

    _parseSources(objects, googleAccountIds) {
        // First pass: index every source's keyfile.
        const rows = [];
        for (const ifaces of Object.values(objects)) {
            const src = ifaces[SOURCE_IFACE];
            if (!src)
                continue;
            const uid = src.UID;
            const data = src.Data;
            if (typeof uid !== 'string' || typeof data !== 'string')
                continue;
            const kf = new GLib.KeyFile();
            let ok = false;
            try {
                ok = kf.load_from_data(data, data.length, GLib.KeyFileFlags.NONE);
            } catch (e) {
                ok = false;
            }
            if (!ok)
                continue;
            const get = (grp, k) => {
                try {
                    return kf.has_group(grp) && kf.has_key(grp, k)
                        ? kf.get_string(grp, k) : null;
                } catch (e) {
                    return null;
                }
            };
            rows.push({
                uid,
                parent: get('Data Source', 'Parent'),
                account: get('GNOME Online Accounts', 'AccountId'),
                isCalendar: kf.has_group('Calendar'),
                isCollection: kf.has_group('Collection'),
            });
        }

        const byUid = new Map(rows.map(r => [r.uid, r]));
        const isGoogleChain = r => {
            let cur = r;
            for (let i = 0; cur && i < 6; i++) {
                if (cur.account && googleAccountIds.has(cur.account))
                    return true;
                cur = cur.parent ? byUid.get(cur.parent) : null;
            }
            return false;
        };

        const uids = new Set();
        for (const r of rows) {
            if (r.isCalendar && isGoogleChain(r))
                uids.add(r.uid);
        }
        return uids;
    }

    // --- events ---------------------------------------------------------

    /** Cached Google events overlapping [begin, end]. */
    getEvents(begin, end) {
        if (!this._source)
            return [];
        let events = this._source.getEvents(begin, end) ?? [];
        if (this._googleUids) {
            events = events.filter(ev =>
                this._googleUids.has(String(ev.id).split('\n')[0]));
        }
        return events.map(ev => {
            const span = ev.end.getTime() - ev.date.getTime();
            const allDay = ev.date.getHours() === 0 && ev.date.getMinutes() === 0 &&
                span % (24 * 3600 * 1000) === 0 && span >= 24 * 3600 * 1000;
            return {summary: ev.summary, date: ev.date, end: ev.end, allDay};
        });
    }

    destroy() {
        this._listeners.clear();
        for (const t of ['_emitId', '_rangeTimer', '_detectTimer', '_syncTimer']) {
            if (this[t]) {
                GLib.source_remove(this[t]);
                this[t] = 0;
            }
        }
        if (this._source) {
            this._source.disconnectObject(this);
            this._source.destroy?.();
            this._source = null;
        }
    }
}

/** Open peachOS Settings -> Internet Accounts to connect Google. */
export function openAccountSettings() {
    for (const argv of [
        ['peachos-settings', 'internetaccounts'],
        ['gnome-control-center', 'online-accounts'],
    ]) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
            return;
        } catch (e) {
            // try the next
        }
    }
}
