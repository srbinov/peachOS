// Bridge between apps/settings' Appearance page (peachos-icon-appearance) and the live
// dock: hide the dock while a Default/Dark/Custom icon-style switch rewrites a burst of
// .desktop files, and pin the dock's on-screen order through it.
//
// WHY THIS EXISTS
// ----------------
// GNOME's own dash.js _redisplay() admits in its own source comment that its diffing
// algorithm "assumes only one item is moved at a given time" -- touching several apps'
// GDesktopAppInfo at once (exactly what peachos-icon-appearance's bulk Icon= rewrite does)
// can make it "remove all the launchers and add them back in a new order". This dock wraps
// that same stock dash.js and rebuilds itself from dash._box's child order whenever
// installed-changed fires, so it inherits the scramble: switching icon appearance used to
// reshuffle every pinned + running app in the dock.
//
// org.gnome.shell favorite-apps is not a complete order either: a running-but-unpinned app
// sits in the dock with no entry in that list, so restoring only favorites drops it and it
// lands wherever dash._box happens to enumerate it next.
//
// lib/dockOrderGuard.js (macos-top-panel) is the OLDER fix for this: it freezes dash.js's
// _queueRedisplay for the duration of the swap over D-Bus. It's still exported and still
// works as an in-process freeze of last resort, but Settings no longer drives it directly --
// Restore()'s re-armed _queueRedisplay() schedules dash.js's real _redisplay() asynchronously
// (Meta.later_add), which still recomputes its own target order from AppFavorites + running-
// app enumeration and can reorder non-favorite running apps on the way out. Fixing the order
// AFTER that redisplay runs leaves a visible flicker (see POST_REDISPLAY_REAPPLY_MS's own
// comment in that file).
//
// This bridge instead HIDES the dock for the whole swap and never lets it repaint until the
// new icons are confirmed on screen:
//   begin()  -- freeze + snapshot the on-screen order, slide the dock fully off-screen, and
//               suppress its own slideIn (autohide/hover would otherwise fight the hidden
//               state while .desktop files are still mid-rewrite).
//   finish() -- poll until every checked icon's live gicon actually matches its .desktop
//               file's CURRENT Icon= value, apply the snapshotted order, THEN slide back in.
//   abort()  -- peachos-icon-appearance itself failed: put the order back and reveal
//               immediately, no icon-matching wait (nothing changed).
//
// All three write a one-word status to $XDG_RUNTIME_DIR/peachos-ia-dock so the Settings
// process (a separate process; msg-to-ext is fire-and-forget, no return channel) can poll
// for completion instead of guessing a fixed delay.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Fav from 'resource:///org/gnome/shell/ui/appFavorites.js';

// Don't start rewriting .desktop files until the dock has actually finished sliding off --
// otherwise the first few icon updates land while it's still partway visible.
const SLIDE_OUT_MS = 420;
// How often finish() re-checks whether the live icons match their .desktop files yet.
const MATCH_POLL_MS = 120;
// Require this many CONSECUTIVE matching polls before trusting it -- avoids showing the
// dock on one lucky frame where a stale gicon momentarily looks equal to the new one.
const MATCH_STREAK_NEEDED = 8;
// ...but also never trust it before this many polls have happened at all, even if every
// one matched (some apps' icons never change between styles -- an all-match streak on
// poll #1 doesn't mean the ones that DO change have caught up yet).
const MATCH_MIN_TRIES = 18;
// Absolute giveup: reveal anyway rather than hang the Settings UI forever.
const MATCH_MAX_TRIES = 70; // * 120ms ~= 8.4s
// Re-apply the pinned order for a while after reveal -- peachos-icon-watcherd and GNOME's
// own installed-changed debounce can still trickle in a few more updates right after.
const KEEP_PINNED_BEATS = 12;
const KEEP_PINNED_INTERVAL_MS = 350;
// Stop re-pinning (unwrap _redisplay) after this long even if keepPinned's own beats
// somehow didn't run to completion -- never leave the dock permanently frozen.
const DISARM_PIN_MS = 20000;

function _runtimeStatusPath() {
    const dir = GLib.getenv('XDG_RUNTIME_DIR') || '/tmp';
    return GLib.build_filenamev([dir, 'peachos-ia-dock']);
}

function _writeStatus(word) {
    try {
        GLib.file_set_contents(_runtimeStatusPath(), word);
    } catch (e) {
        // best-effort -- Settings' own 10s poll timeout covers a missed write
    }
}

function _appOf(c) {
    return c._appwell?.app ?? null;
}

/** Fresh Gio.Icon for an app id, preferring the exact user-local override path
 * peachos-icon-appearance just wrote (guaranteed current) over the generic XDG lookup
 * (which would also find it, but only after update-desktop-database / cache settle). */
function _freshIconForApp(appId) {
    if (!appId)
        return null;
    try {
        const overridePath = GLib.build_filenamev(
            [GLib.get_home_dir(), '.local/share/applications', appId]);
        let info = GLib.file_test(overridePath, GLib.FileTest.EXISTS)
            ? Gio.DesktopAppInfo.new_from_filename(overridePath)
            : null;
        if (!info)
            info = Gio.DesktopAppInfo.new(appId);
        return info ? info.get_icon() : null;
    } catch (e) {
        return null;
    }
}

function _giconsEqual(a, b) {
    if (!a || !b)
        return false;
    try {
        if (a.equal && a.equal(b))
            return true;
    } catch (e) {
        // fall through to path comparison
    }
    try {
        const ap = a.get_file ? a.get_file()?.get_path() : (a.file?.get_path?.() ?? null);
        const bp = b.get_file ? b.get_file()?.get_path() : (b.file?.get_path?.() ?? null);
        return ap != null && ap === bp;
    } catch (e) {
        return false;
    }
}

function _appActors(d) {
    const box = d?.dash?._box;
    if (!box)
        return [];
    return box.get_children().filter(c => _appOf(c) !== null);
}

/** Record the dock's current on-screen order (every app, pinned or not) and each app's
 * running-window count (animator falls back to this for the running dots while
 * AppSystem is mid-rescan -- see refreshIcons()'s own note). */
function snapshot(d) {
    d._peachOrder = _appActors(d).map(c => _appOf(c).get_id());
    d._peachRunning = {};
    for (const c of _appActors(d)) {
        const app = _appOf(c);
        try {
            d._peachRunning[app.get_id()] = app.get_windows ? app.get_windows().length : 0;
        } catch (e) {
            // app object gone mid-scan -- leave it unset, animator falls back to 0
        }
    }
}

/** Suppress dash.js's own redisplay-triggered reordering for the duration of the swap by
 * wrapping _redisplay (not just _queueRedisplay -- see this file's top comment for why
 * a queue-only freeze still lets one real scramble through on the way out). Re-entrant
 * safe: a second freeze() while already frozen is a no-op. */
function freeze(d) {
    const dash = d?.dash;
    if (!dash || d._peachOrigRedisplay)
        return;
    d._peachPinActive = true;
    d._peachOrigQueueRedisplay = dash._queueRedisplay;
    dash._queueRedisplay = () => {};
    d._peachOrigRedisplay = dash._redisplay.bind(dash);
    dash._redisplay = (...args) => {
        d._peachOrigRedisplay(...args);
        if (d._peachPinActive)
            pinOrder(d);
    };
}

/** One real _queueRedisplay(), while still hidden and still pinned -- lets dash.js
 * rematch apps that started/stopped running during the swap (freeze() alone leaves them
 * stuck on stale actors / missing from the running section). Because _redisplay is still
 * wrapped, the one real rebuild this triggers re-applies pinOrder() in the same turn, so
 * it never paints as a visible shuffle. */
function thawOnce(d) {
    if (d?._peachOrigQueueRedisplay)
        d._peachOrigQueueRedisplay.call(d.dash);
}

function pinOrder(d) {
    applyOrder(d);
    refreshIcons(d);
    if (typeof d._beginAnimation === 'function')
        d._beginAnimation();
}

/** Put dash._box back into the snapshotted order. Never touches _extraIcons (Trash/
 * Downloads/mounts) as if it were an app slot -- it has no app id, so the reorder loop
 * below naturally skips it, but a prior bug here treated any id-less child as a "ghost"
 * (width/opacity forced to 0), which collapsed the extras tray to a sliver after a swap.
 * Explicitly re-asserts it's visible/full-size/last every call as a guard against that
 * class of bug recurring. */
function applyOrder(d) {
    const box = d?.dash?._box;
    const order = d._peachOrder;
    if (!box || !order || !order.length)
        return;

    const byId = new Map();
    for (const c of _appActors(d))
        byId.set(_appOf(c).get_id(), c);

    let index = 0;
    for (const id of order) {
        const c = byId.get(id);
        if (!c)
            continue; // app quit mid-swap -- just drop it from the order
        box.set_child_at_index(c, index);
        index++;
    }

    // Favorites|running separator: park it right after the last pinned app when there's
    // an unpinned running app after it (so it reads as a real divider), hide it otherwise.
    // Only ever touch a separator dash._box directly parents -- see dock.js's own
    // _findIcons() note on why the extras tray's separator must never be confused with it.
    let favIds;
    try {
        favIds = new Set(Fav.getAppFavorites().getFavoriteIds());
    } catch (e) {
        favIds = new Set();
    }
    const hasUnpinnedRunning = order.some(id => !favIds.has(id));
    const sep = box.get_children().find(
        c => c._cls === 'dash-separator' && c.get_parent() === box);
    if (sep) {
        if (hasUnpinnedRunning) {
            let lastFavIndex = -1;
            box.get_children().forEach((c, i) => {
                const app = _appOf(c);
                if (app && favIds.has(app.get_id()))
                    lastFavIndex = i;
            });
            if (lastFavIndex >= 0) {
                box.set_child_at_index(sep, lastFavIndex + 1);
                sep.visible = true;
            }
        } else {
            sep.visible = false;
        }
    }

    if (d._extraIcons) {
        d._extraIcons.visible = true;
        d._extraIcons.width = -1;
        d._extraIcons.height = -1;
        box.set_child_at_index(d._extraIcons, box.get_children().length - 1);
    }

    d._icons = null; // force _findIcons()/animator to re-scan on next paint
}

/** Push each app's CURRENT .desktop icon onto its existing actor -- never destroy/recreate
 * the actor (that's what would visibly reshuffle/flicker). Every property animator.js
 * reads a gicon from: the St.Icon itself, the BaseIcon wrapper, the cached renderer, and
 * (older GNOME) child.icon. */
function refreshIcons(d) {
    for (const c of _appActors(d)) {
        const app = _appOf(c);
        const gicon = _freshIconForApp(app.get_id());
        if (!gicon)
            continue;
        if (c._icon)
            c._icon.gicon = gicon;
        if (c._grid?.icon)
            c._grid.icon.gicon = gicon;
        if (c._renderer)
            c._renderer.gicon = gicon;
        if (c.child?.icon)
            c.child.icon.gicon = gicon;
    }
}

/** True once at least MATCH_MIN_CHECKED real apps' live gicons match what their .desktop
 * file currently points at. Requires checking a few, not just one, so a coincidental early
 * match (an app whose icon didn't change between styles) can't short-circuit the wait for
 * the ones that did. */
const MATCH_MIN_CHECKED = 4;
function iconsMatch(d) {
    let checked = 0;
    for (const c of _appActors(d)) {
        const app = _appOf(c);
        const wanted = _freshIconForApp(app.get_id());
        const current = c._icon?.gicon;
        if (!wanted || !current)
            continue;
        checked++;
        if (!_giconsEqual(wanted, current))
            return false;
    }
    return checked >= MATCH_MIN_CHECKED;
}

/** Re-arm the real dash.js redisplay/queueRedisplay (apps that started/stopped running
 * during the swap can rematch again), but leave _redisplay WRAPPED so pinOrder() keeps
 * firing in the same turn as any redisplay for a while longer -- see keepPinned(). */
function armPin(d) {
    const dash = d?.dash;
    if (dash && d._peachOrigQueueRedisplay) {
        dash._queueRedisplay = d._peachOrigQueueRedisplay;
        d._peachOrigQueueRedisplay = null;
    }
    d._peachPinActive = true;
    keepPinned(d, KEEP_PINNED_BEATS);
    if (d._peachDisarmId)
        GLib.source_remove(d._peachDisarmId);
    d._peachDisarmId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, DISARM_PIN_MS, () => {
        d._peachDisarmId = 0;
        disarmPin(d);
        return GLib.SOURCE_REMOVE;
    });
}

function keepPinned(d, beatsLeft) {
    if (beatsLeft <= 0 || !d._peachPinActive)
        return;
    pinOrder(d);
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, KEEP_PINNED_INTERVAL_MS, () => {
        keepPinned(d, beatsLeft - 1);
        return GLib.SOURCE_REMOVE;
    });
}

/** Unwrap _redisplay entirely -- the dock goes back to driving its own order from
 * dash._box exactly as it does outside a swap. Deliberately does NOT clear _peachRunning:
 * Shell.AppSystem briefly reports 0 windows for an app right after a .desktop-file burst
 * (it's mid-rescan), and animator.js falls back to _peachRunning for the running dots --
 * nulling it here would blank every dot for that window, which reads as a broken dock. */
function disarmPin(d) {
    d._peachPinActive = false;
    if (d._peachDisarmId) {
        GLib.source_remove(d._peachDisarmId);
        d._peachDisarmId = 0;
    }
    const dash = d?.dash;
    if (dash && d._peachOrigRedisplay) {
        dash._redisplay = d._peachOrigRedisplay;
        d._peachOrigRedisplay = null;
    }
}

function _forEachDock(ext, fn) {
    for (const d of ext.docks || [])
        fn(d);
}

/** Called (via msg-to-ext) right before peachos-icon-appearance runs. */
export function begin(ext) {
    _writeStatus('pending');
    ext.icon_map_cache = {};
    ext.app_map_cache = {};
    _forEachDock(ext, (d) => {
        if (!d?.dash?._box)
            return;
        d.autohider?.disable();
        freeze(d);
        snapshot(d);
        d._peachOrigSlideIn = d.slideIn.bind(d);
        // GNOME's own autohide/hover logic can call slideIn() while the swap is still in
        // flight (e.g. the pointer happens to be near the dock's edge) -- no-op it until
        // finish()/abort() explicitly restores the real one, or the dock would slide back
        // in showing stale/half-updated icons.
        d.slideIn = () => {};
        d.slideOut();
    });
}

/** Called (via msg-to-ext) after peachos-icon-appearance exits 0. Polls internally --
 * writes 'ready' to the status file once every dock is confirmed showing current icons
 * and has slid back in. Safe to call even if begin() was never seen (e.g. extension
 * reloaded mid-swap): reveals immediately with whatever order is currently on screen. */
export function finish(ext) {
    const docks = (ext.docks || []).filter(d => d?.dash?._box);
    if (!docks.length) {
        _writeStatus('ready');
        return;
    }
    for (const d of docks)
        thawOnce(d);

    let streak = 0;
    let tries = 0;
    const tick = () => {
        tries++;
        const allMatch = docks.every(d => iconsMatch(d));
        streak = allMatch ? streak + 1 : 0;
        const settled = (streak >= MATCH_STREAK_NEEDED && tries >= MATCH_MIN_TRIES)
            || tries >= MATCH_MAX_TRIES;
        if (!settled)
            return GLib.SOURCE_CONTINUE;

        for (const d of docks) {
            applyOrder(d);
            refreshIcons(d);
            d._icons = null;
            if (d._peachOrigSlideIn) {
                d.slideIn = d._peachOrigSlideIn;
                d._peachOrigSlideIn = null;
            }
            d.slideIn();
            armPin(d);
            d.autohider?.enable();
        }
        _writeStatus('ready');
        return GLib.SOURCE_REMOVE;
    };
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, MATCH_POLL_MS, tick);
}

/** Called (via msg-to-ext) if peachos-icon-appearance itself failed -- nothing on disk
 * actually changed, so just put the snapshotted order back and reveal immediately. */
export function abort(ext) {
    _forEachDock(ext, (d) => {
        if (!d?.dash?._box)
            return;
        applyOrder(d);
        d._icons = null;
        if (d._peachOrigSlideIn) {
            d.slideIn = d._peachOrigSlideIn;
            d._peachOrigSlideIn = null;
        }
        d.slideIn();
        disarmPin(d);
        d.autohider?.enable();
        if (typeof d._beginAnimation === 'function')
            d._beginAnimation();
    });
    _writeStatus('ready');
}
