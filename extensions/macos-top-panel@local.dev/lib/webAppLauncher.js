// lib/webAppLauncher.js
//
// "Open this website in the best thing that's actually installed" -- a resolution
// hierarchy shared by anything in peachOS that represents a web service (right now:
// the Notification Center re-attributing calendar-reminder notifications; later:
// widgets, other notification sources).
//
// Order, first hit wins:
//   1. a real native app for the service            (Shell.App by desktop id)
//   2. a peachOS web-app wrapper for it             (.desktop with X-PeachOS-WebApp=<slug>)
//   3. a Chrome / Chromium PWA for it               (.desktop whose Exec has --app=<origin>)
//   4. fall back to the URL in the default browser  (Gio.AppInfo.launch_default_for_uri)
//
// THE CONVENTION for step 2: every peachOS web-app wrapper (Electron, WebKitGTK, ...)
// ships a .desktop file with a single extra line
//     X-PeachOS-WebApp=<slug>
// where <slug> is a key in WEB_APPS below. That line is all a new wrapper needs to be
// picked up here -- no code change. provision.sh already stamps it onto
// icloud-for-linux_calendar.desktop.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

// slug -> service. `icon` is resolved lazily (see iconFor) so importing this module
// doesn't touch the filesystem. `nativeIds` are tried as-is via Shell.AppSystem.
export const WEB_APPS = {
    'google-calendar': {
        name: 'Google Calendar',
        url: 'https://calendar.google.com/',
        iconFile: 'assets/webapp/google-calendar.png',
        nativeIds: [],
    },
    'icloud-calendar': {
        name: 'iCloud Calendar',
        url: 'https://www.icloud.com/calendar/',
        iconFile: 'assets/webapp/icloud-calendar.svg',
        // the WebKitGTK wrapper provision.sh installs -- also carries X-PeachOS-WebApp,
        // so step 2 would catch it too; listing it here just makes it step 1.
        nativeIds: ['icloud-for-linux_calendar.desktop'],
    },
    'outlook-calendar': {
        name: 'Outlook Calendar',
        url: 'https://outlook.live.com/calendar/',
        iconFile: 'assets/webapp/outlook-calendar.svg',
        nativeIds: [],
    },
    // Zero or several remote calendar accounts -> don't pretend it's one brand.
    'calendar': {
        name: 'Calendar',
        url: null,
        iconName: 'org.gnome.Calendar',
        nativeIds: ['org.gnome.Calendar.desktop'],
    },
};

/**
 * A Gio.Icon for a WEB_APPS entry. `extensionPath` is the extension's own dir
 * (Extension.path / metadata dir).
 * @param {string} slug
 * @param {string} extensionPath
 * @returns {Gio.Icon|null}
 */
export function iconFor(slug, extensionPath) {
    const site = WEB_APPS[slug];
    if (!site)
        return null;
    if (site.iconName)
        return new Gio.ThemedIcon({name: site.iconName});
    if (site.iconFile)
        return Gio.FileIcon.new(Gio.File.new_for_path(
            GLib.build_filenamev([extensionPath, site.iconFile])));
    return null;
}

function launchContext() {
    try {
        return global.create_app_launch_context(0, -1);
    } catch (e) {
        return null;
    }
}

function originHost(url) {
    try {
        return GLib.Uri.parse(url, GLib.UriFlags.NONE).get_host() || '';
    } catch (e) {
        return '';
    }
}

/**
 * Open the given service (a WEB_APPS slug) the best way available. Never throws.
 * @param {string} slug
 * @returns {boolean} whether something was launched
 */
export function openWebApp(slug) {
    const site = WEB_APPS[slug] ?? WEB_APPS['calendar'];
    const ctx = launchContext();

    // 1. native app
    const appSystem = Shell.AppSystem.get_default();
    for (const id of site.nativeIds ?? []) {
        try {
            const app = appSystem.lookup_app(id);
            if (app) {
                app.activate();
                return true;
            }
        } catch (e) {
            logError(e, `[macos-top-panel] webAppLauncher: native ${id} failed`);
        }
    }

    const all = Gio.AppInfo.get_all();

    // 2. peachOS web-app wrapper: .desktop with X-PeachOS-WebApp=<slug>
    for (const info of all) {
        try {
            if (info.get_string?.('X-PeachOS-WebApp') === slug) {
                info.launch([], ctx);
                return true;
            }
        } catch (e) {
            // not a DesktopAppInfo / key absent -- ignore
        }
    }

    // 3. Chrome / Chromium PWA: Exec carries --app=<url> for this origin
    if (site.url) {
        const host = originHost(site.url);
        if (host) {
            for (const info of all) {
                try {
                    const exec = info.get_commandline?.() ?? '';
                    if (exec.includes('--app=') && exec.includes(host)) {
                        info.launch([], ctx);
                        return true;
                    }
                } catch (e) {
                    // ignore
                }
            }
        }
    }

    // 4. fall back to the URL in the default browser
    if (site.url) {
        try {
            Gio.AppInfo.launch_default_for_uri(site.url, ctx);
            return true;
        } catch (e) {
            logError(e, `[macos-top-panel] webAppLauncher: launch_default_for_uri ${site.url} failed`);
        }
        return false;
    }

    // no URL (the generic 'calendar' entry) -- last resort, GNOME Calendar
    try {
        appSystem.lookup_app('org.gnome.Calendar.desktop')?.activate();
        return true;
    } catch (e) {
        return false;
    }
}
