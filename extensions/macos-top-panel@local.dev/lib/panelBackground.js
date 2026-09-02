/*
 * Owns the menu-bar background.
 *
 *   menu-bar-blur = false  ->  fully transparent (wallpaper shows straight through)
 *   menu-bar-blur = true   ->  a soft frosted blur of the wallpaper slice behind the panel
 *
 * A dedicated backdrop actor is inserted as Main.panel's first child rather than styling
 * #panel via CSS: the shell theme's own transparent #panel rule has intermittently lost to
 * a stock opaque-black default (HANDOFF "Top bar background bug, parked"), and a child actor
 * is painted after the panel's own background but before every panel widget, so it wins
 * regardless. The blur itself is a one-shot software render (peachos-menubar-blur, PIL) --
 * no Shell.BlurEffect, which is a real freeze risk on the GPUs peachOS still targets.
 */
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const HELPER = '/usr/lib/peachos/menubar/peachos-menubar-blur';
const REGEN_DEBOUNCE_MS = 350;
const CACHE_DIR = GLib.build_filenamev([GLib.get_user_cache_dir(), 'peachos-menubar']);

export class PanelBackground {
    /** @param {Gio.Settings} panelSettings */
    constructor(panelSettings) {
        this._panelSettings = panelSettings;
        this._actor = null;
        this._bgSettings = null;
        this._ifaceSettings = null;
        this._signalIds = [];
        this._regenId = 0;
        this._nonce = 0;
        this._destroyed = false;
    }

    enable() {
        this._destroyed = false;
        this._actor = new St.Widget({
            style_class: 'macos-panel-backdrop',
            reactive: false,
            can_focus: false,
            track_hover: false,
        });
        this._actor.add_constraint(new Clutter.BindConstraint({
            source: Main.panel,
            coordinate: Clutter.BindCoordinate.SIZE,
        }));
        Main.panel.insert_child_at_index(this._actor, 0);

        try {
            this._bgSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
            this._ifaceSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
            this._connect(this._bgSettings, 'changed::picture-uri', () => this._scheduleRegen());
            this._connect(this._bgSettings, 'changed::picture-uri-dark', () => this._scheduleRegen());
            this._connect(this._ifaceSettings, 'changed::color-scheme', () => this._scheduleRegen());
        } catch (e) {
            logError(e, '[macos-top-panel] menu-bar blur: could not watch wallpaper settings');
        }
        this._connect(Main.layoutManager, 'monitors-changed', () => this._scheduleRegen());
        this._connect(this._panelSettings, 'changed::menu-bar-blur', () => this._apply());
        this._connect(this._panelSettings, 'changed::panel-height', () => this._scheduleRegen());

        this._apply();
    }

    disable() {
        this._destroyed = true;
        if (this._regenId) {
            GLib.source_remove(this._regenId);
            this._regenId = 0;
        }
        for (const [obj, id] of this._signalIds)
            obj.disconnect(id);
        this._signalIds = [];
        this._bgSettings = null;
        this._ifaceSettings = null;
        if (this._actor) {
            this._actor.destroy();
            this._actor = null;
        }
    }

    /** True while this module is painting a (non-transparent) panel background. */
    isBlurOn() {
        return this._panelSettings.get_boolean('menu-bar-blur');
    }

    _connect(obj, signal, cb) {
        this._signalIds.push([obj, obj.connect(signal, cb)]);
    }

    _apply() {
        if (!this._actor)
            return;
        if (this.isBlurOn()) {
            this._regenAndShow();
        } else {
            this._actor.style = 'background-color: transparent;';
            this._actor.hide();
        }
    }

    _scheduleRegen() {
        if (!this.isBlurOn())
            return;
        if (this._regenId)
            GLib.source_remove(this._regenId);
        this._regenId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, REGEN_DEBOUNCE_MS, () => {
            this._regenId = 0;
            this._regenAndShow();
            return GLib.SOURCE_REMOVE;
        });
    }

    _regenAndShow() {
        if (this._destroyed || !this._actor || !this.isBlurOn() || this._regenInFlight)
            return;
        this._regenInFlight = true;

        const mon = Main.layoutManager.primaryMonitor;
        if (!mon) {
            this._regenInFlight = false;
            return;
        }
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const w = Math.round(mon.width * scale);
        const h = Math.round(mon.height * scale);
        let ph = this._panelSettings.get_int('panel-height');
        if (ph <= 0)
            ph = Main.panel.height || 40;
        ph = Math.round(ph * scale);

        // Fresh filename each render so St's texture cache (keyed by path) actually
        // reloads it; last render's file is removed once the new one is in place.
        this._nonce += 1;
        const prevPath = this._currentPath;
        const outPath = GLib.build_filenamev([CACHE_DIR, `panel-blur-${this._nonce}.png`]);

        let proc;
        try {
            proc = Gio.Subprocess.new(
                [HELPER, String(w), String(h), String(ph), outPath],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            );
        } catch (e) {
            this._regenInFlight = false;
            logError(e, '[macos-top-panel] menu-bar blur: could not run helper');
            return;
        }
        proc.communicate_utf8_async(null, null, (p, res) => {
            this._regenInFlight = false;
            if (this._destroyed || !this._actor || !this.isBlurOn())
                return;
            let ok, stdout;
            try {
                [ok, stdout] = p.communicate_utf8_finish(res);
            } catch (e) {
                return;
            }
            const path = (stdout || '').trim();
            if (!ok || !path || !GLib.file_test(path, GLib.FileTest.EXISTS)) {
                // Wallpaper unreadable / helper failed -- leave the panel transparent
                // rather than showing a broken tile.
                this._actor.style = 'background-color: transparent;';
                this._actor.show();
                return;
            }
            this._actor.style =
                `background-image: url("file://${path}"); ` +
                'background-size: cover; background-position: center;';
            this._actor.show();
            this._currentPath = path;
            if (prevPath && prevPath !== path) {
                try {
                    Gio.File.new_for_path(prevPath).delete_async(GLib.PRIORITY_LOW, null, null);
                } catch (e) {
                    // harmless -- a stale cache file, cleaned up next boot at worst
                }
            }
        });
    }
}
