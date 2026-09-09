// lib/calendarAccounts.js
//
// Which calendar identity should a generic "Events and Tasks Reminders" notification
// (from evolution-alarm-notify, which fires for every connected calendar) be shown as?
//
// The notification itself carries no source-calendar id, so we answer it from the set
// of connected accounts instead: enumerate Evolution Data Server's [Calendar] sources,
// classify each by its auth host / backend, and:
//   - exactly one remote provider  -> that provider  ('google-calendar' / ...)
//   - zero, or more than one        -> 'calendar' (generic, opens GNOME Calendar)
//
// Same D-Bus enumeration + parent-walk as peachos-widgets'
// lib/providers/edsCalendar.js (_parseSources); kept standalone so this extension
// doesn't depend on the other.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const SOURCES_NAME = 'org.gnome.evolution.dataserver.Sources5';
const SOURCES_PATH = '/org/gnome/evolution/dataserver/SourceManager';
const SOURCE_IFACE = 'org.gnome.evolution.dataserver.Source';

const REFRESH_SECONDS = 120;

function classify(host, resource, backend) {
    const h = `${host} ${resource}`;
    if (/googleusercontent|(^|\.)google\.com(\s|$)|google\.com\//.test(h) || h.includes('google'))
        return 'google';
    if (/icloud\.com|(^|\.)me\.com|(^|\.)mac\.com/.test(h))
        return 'icloud';
    if (/outlook|office365|live\.com|microsoft|hotmail/.test(h))
        return 'microsoft';
    // no remote host, a local/on-device backend
    if (!host && ['local', 'contacts', 'weather', 'webcal'].includes(backend))
        return 'local';
    return host ? 'other' : 'local';
}

const PROVIDER_SLUG = {
    google: 'google-calendar',
    icloud: 'icloud-calendar',
    microsoft: 'outlook-calendar',
};

export class CalendarAccounts {
    constructor() {
        this._providers = new Set();   // 'google' | 'icloud' | 'microsoft' | 'local' | 'other'
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, REFRESH_SECONDS, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    /**
     * @returns {string} a WEB_APPS slug: 'google-calendar' | 'icloud-calendar' |
     *   'outlook-calendar' when exactly one remote provider is connected, else 'calendar'.
     */
    resolveSlug() {
        const remotes = [...this._providers].filter(p => p !== 'local' && p !== 'other');
        if (remotes.length === 1 && PROVIDER_SLUG[remotes[0]])
            return PROVIDER_SLUG[remotes[0]];
        return 'calendar';
    }

    refreshNow() {
        this._refresh();
    }

    _refresh() {
        Gio.DBus.session.call(
            SOURCES_NAME, SOURCES_PATH, 'org.freedesktop.DBus.ObjectManager',
            'GetManagedObjects', null, null, Gio.DBusCallFlags.NONE, 5000, null,
            (bus, res) => {
                let objects;
                try {
                    [objects] = bus.call_finish(res).recursiveUnpack();
                } catch (e) {
                    return; // EDS not up yet -- keep whatever we had
                }
                this._providers = this._parse(objects);
            });
    }

    _parse(objects) {
        const rows = [];
        for (const ifaces of Object.values(objects)) {
            const src = ifaces[SOURCE_IFACE];
            if (!src || typeof src.UID !== 'string' || typeof src.Data !== 'string')
                continue;
            const kf = new GLib.KeyFile();
            try {
                const bytes = new TextEncoder().encode(src.Data).length;
                if (!kf.load_from_data(src.Data, bytes, GLib.KeyFileFlags.NONE))
                    continue;
            } catch (e) {
                continue;
            }
            if (!kf.has_group('Calendar'))
                continue;
            const get = (grp, k) => {
                try {
                    return (kf.get_string(grp, k) || '').toLowerCase();
                } catch (e) {
                    return '';
                }
            };
            rows.push({
                uid: src.UID,
                parent: get('Data Source', 'Parent') || null,
                host: get('Authentication', 'Host'),
                backend: get('Calendar', 'BackendName'),
                resource: get('Resource', 'Identity') || get('WebDAV Backend', 'ResourcePath'),
            });
        }

        const byUid = new Map(rows.map(r => [r.uid, r]));
        const origin = r => {
            let cur = r;
            let host = '';
            let resource = '';
            for (let i = 0; cur && i < 6; i++) {
                host ||= cur.host;
                resource ||= cur.resource;
                cur = cur.parent ? byUid.get(cur.parent) : null;
            }
            return {host, resource};
        };

        const providers = new Set();
        for (const r of rows) {
            const {host, resource} = origin(r);
            providers.add(classify(host, resource, r.backend));
        }
        return providers;
    }

    destroy() {
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = 0;
        }
        this._providers.clear();
    }
}
