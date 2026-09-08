// Branded calendar sources, both on the shell's DBusEventSource (Evolution
// Data Server / GNOME Online Accounts) but each scoped to one account family:
//
//   ICloudCalendarSource -- iCloud + on-device calendars (everything that is
//                           NOT another branded account, i.e. not Google).
//   GoogleCalendarSource -- calendars that chain up to a Google GOA account.
//
// Filtering is by the event id prefix (= the ESource UID); the ESources are
// enumerated over the EDS Sources bus and matched against GOA accounts.
//
// requestRange discipline (see lib/providers/calendar.js): reload only from
// _refreshRange(), never from getEvents().

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Calendar from 'resource:///org/gnome/shell/ui/calendar.js';

const SOURCES_NAME = 'org.gnome.evolution.dataserver.Sources5';
const SOURCES_PATH = '/org/gnome/evolution/dataserver/SourceManager';
const SOURCE_IFACE = 'org.gnome.evolution.dataserver.Source';

class FilteredCalendarSource {
    // cfg: {
    //   collectAccounts(acc) -> bool   -- GOA accounts whose calendars we want
    //   excludeAccounts(acc) -> bool   -- GOA accounts to exclude even so
    //   matchSourceData(dataStr) -> bool   -- extra include by raw keyfile
    //   alwaysConnected: bool
    // }
    constructor(cfg) {
        this._cfg = cfg;
        this._listeners = new Set();
        this._emitId = 0;
        this._emitting = false;
        this._rangeKey = '';
        this._uids = null;         // Set<uid> to keep, or null == keep all
        this._connected = !!cfg.alwaysConnected;

        try {
            this._source = new Calendar.DBusEventSource();
            this._source.connectObject('changed', () => this._scheduleEmit(), this);
        } catch (e) {
            logError(e, '[peachos-widgets] calendar source unavailable');
            this._source = null;
        }

        this._detect();
        this._refreshRange();
        this._rangeTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 6 * 3600, () => {
            this._refreshRange();
            return GLib.SOURCE_CONTINUE;
        });
        this._detectTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 90, () => {
            this._detect();
            return GLib.SOURCE_CONTINUE;
        });
        this._syncTimer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 3 * 60, () => {
            this._refreshCalDav();
            return GLib.SOURCE_CONTINUE;
        });
    }

    get connected() {
        return this._connected;
    }

    /** Pull from the server right now (e.g. the user just opened edit mode). */
    refreshNow() {
        this._detect();
        this._refreshCalDav();
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

    // Ask EDS to fetch each kept calendar from the server now.
    _refreshCalDav() {
        for (const uid of this._uids ?? []) {
            Gio.DBus.session.call(
                'org.gnome.evolution.dataserver.Calendar8',
                '/org/gnome/evolution/dataserver/CalendarFactory', 'OpenCalendar',
                new GLib.Variant('(s)', [uid]), null,
                Gio.DBusCallFlags.NONE, 15000, null,
                (bus, res) => {
                    try {
                        const [path, name] = bus.call_finish(res).recursiveUnpack();
                        bus.call(name, path,
                            'org.gnome.evolution.dataserver.Calendar', 'Refresh',
                            null, null, Gio.DBusCallFlags.NONE, 15000, null, null);
                    } catch (e) {
                        // backend busy / offline -- next tick
                    }
                });
        }
    }

    // --- which calendars to keep -----------------------------------------

    async _detect() {
        let collect = new Set();
        let exclude = new Set();
        try {
            ({collect, exclude} = await this._goaAccounts());
        } catch (e) {
            // GOA unavailable
        }

        let uids = null;
        try {
            uids = await this._sourceUids(collect, exclude);
        } catch (e) {
            logError(e, '[peachos-widgets] EDS source enumeration failed');
        }

        const before = this._uids ? [...this._uids].sort().join() : '';
        this._uids = uids;                       // null == keep all
        const after = this._uids ? [...this._uids].sort().join() : '';
        this._connected = this._cfg.alwaysConnected ||
            (!!this._uids && this._uids.size > 0) || collect.size > 0;
        if (this._uids && after !== before)
            this._refreshCalDav();
        this._scheduleEmit();
    }

    async _goaAccounts() {
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
        const collect = new Set();
        const exclude = new Set();
        for (const obj of client.get_accounts()) {
            const acc = obj.get_account();
            if (!acc)
                continue;
            if (this._cfg.excludeAccounts?.(acc))
                exclude.add(acc.id);
            if (this._cfg.collectAccounts?.(acc) && !acc.calendar_disabled && obj.get_calendar())
                collect.add(acc.id);
        }
        return {collect, exclude};
    }

    _sourceUids(collect, exclude) {
        return new Promise((resolve, reject) => {
            Gio.DBus.session.call(
                SOURCES_NAME, SOURCES_PATH,
                'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects',
                null, null, Gio.DBusCallFlags.NONE, 5000, null,
                (bus, res) => {
                    try {
                        const [objects] = bus.call_finish(res).recursiveUnpack();
                        resolve(this._parseSources(objects, collect, exclude));
                    } catch (e) {
                        reject(e);
                    }
                });
        });
    }

    _parseSources(objects, collect, exclude) {
        const rows = [];
        for (const ifaces of Object.values(objects)) {
            const src = ifaces[SOURCE_IFACE];
            if (!src || typeof src.UID !== 'string' || typeof src.Data !== 'string')
                continue;
            const kf = new GLib.KeyFile();
            try {
                // length must be the UTF-8 byte count, not the JS string length
                const bytes = new TextEncoder().encode(src.Data).length;
                if (!kf.load_from_data(src.Data, bytes, GLib.KeyFileFlags.NONE))
                    continue;
            } catch (e) {
                continue;
            }
            const get = (grp, k) => {
                try {
                    return kf.has_group(grp) && kf.has_key(grp, k)
                        ? kf.get_string(grp, k) : null;
                } catch (e) {
                    return null;
                }
            };
            rows.push({
                uid: src.UID,
                data: src.Data,
                parent: get('Data Source', 'Parent'),
                account: get('GNOME Online Accounts', 'AccountId'),
                isCalendar: kf.has_group('Calendar'),
            });
        }

        const byUid = new Map(rows.map(r => [r.uid, r]));
        const chainAccount = r => {
            let cur = r;
            for (let i = 0; cur && i < 6; i++) {
                if (cur.account)
                    return cur.account;
                cur = cur.parent ? byUid.get(cur.parent) : null;
            }
            return null;
        };

        const uids = new Set();
        for (const r of rows) {
            if (!r.isCalendar)
                continue;
            const acc = chainAccount(r);
            if (acc && exclude.has(acc))
                continue;
            const keep =
                (acc && collect.has(acc)) ||
                (this._cfg.matchSourceData?.(r.data) ?? false) ||
                (this._cfg.keepUnbranded && !acc);
            if (keep)
                uids.add(r.uid);
        }
        return uids;
    }

    // --- events --------------------------------------------------------

    getEvents(begin, end) {
        if (!this._source)
            return [];
        let events = this._source.getEvents(begin, end) ?? [];
        if (this._uids)
            events = events.filter(ev => this._uids.has(String(ev.id).split('\n')[0]));
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

const ICLOUD_RE = /(^|[.@/])icloud\.com|@me\.com|@mac\.com/i;

export class ICloudCalendarSource extends FilteredCalendarSource {
    constructor() {
        super({
            // keep on-device + iCloud + any CalDAV; just not the Google tab's
            excludeAccounts: acc => acc.provider_type === 'google',
            matchSourceData: data => ICLOUD_RE.test(data),
            keepUnbranded: true,
            alwaysConnected: true,   // there is always a local calendar
        });
    }

    get hasICloud() {
        return !!this._uids && [...this._uids].length > 0 &&
            this._connected;
    }
}

export class GoogleCalendarSource extends FilteredCalendarSource {
    constructor() {
        super({
            collectAccounts: acc => acc.provider_type === 'google',
            alwaysConnected: false,
        });
    }
}

/** Open peachOS Settings -> Internet Accounts to connect an account. */
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
