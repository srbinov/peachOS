/*
 * Owns the menu-bar background AND the menu-bar text colour.
 *
 *   menu-bar-blur = false  ->  panel fully transparent (wallpaper shows straight through)
 *   menu-bar-blur = true   ->  a frosted software blur of the wallpaper slice behind it
 *
 * In both cases the panel foreground (black vs white text/icons) is chosen from the
 * luminance of that same wallpaper slice, so it stays legible -- computed by the same
 * helper, no Shell.Screenshot.pick_color (unreliable on the GPUs peachOS targets).
 *
 * GNOME 50's Panel.vfunc_allocate only lays out its own left/center/right boxes, so a
 * child added straight to Main.panel is never allocated. The backdrop therefore lives in
 * Main.layoutManager.panelBox as an absolutely-positioned actor inside a zero-size holder
 * (so the vertical box gives it no space), painted below Main.panel.
 */
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const HELPER = '/usr/lib/peachos/menubar/peachos-menubar-blur';
const REGEN_DEBOUNCE_MS = 350;
const CACHE_DIR = GLib.build_filenamev([GLib.get_user_cache_dir(), 'peachos-menubar']);

export class PanelBackground {
    /**
     * @param {Gio.Settings} panelSettings
     * @param {(fg: 'black'|'white') => void} onForeground
     */
    constructor(panelSettings, onForeground) {
        this._panelSettings = panelSettings;
        this._onForeground = onForeground ?? (() => {});
        this._holder = null;
        this._actor = null;
        this._bgSettings = null;
        this._ifaceSettings = null;
        this._signalIds = [];
        this._regenId = 0;
        this._regenInFlight = false;
        this._nonce = 0;
        this._currentPath = null;
        this._destroyed = false;
    }

    enable() {
        this._destroyed = false;

        this._holder = new Clutter.Actor({width: 0, height: 0});
        this._actor = new St.Widget({
            style_class: 'macos-panel-backdrop',
            reactive: false,
            can_focus: false,
        });
        this._actor.set_content_gravity(Clutter.ContentGravity.RESIZE_FILL);
        this._actor.hide();
        this._holder.add_child(this._actor);
        Main.layoutManager.panelBox.insert_child_below(this._holder, Main.panel);
        this._syncGeometry();

        this._connect(Main.panel, 'notify::allocation', () => this._syncGeometry());
        this._connect(Main.layoutManager, 'monitors-changed', () => {
            this._syncGeometry();
            this._scheduleRegen();
        });
        try {
            this._bgSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
            this._ifaceSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
            this._connect(this._bgSettings, 'changed::picture-uri', () => this._scheduleRegen());
            this._connect(this._bgSettings, 'changed::picture-uri-dark', () => this._scheduleRegen());
            this._connect(this._ifaceSettings, 'changed::color-scheme', () => this._scheduleRegen());
        } catch (e) {
            logError(e, '[macos-top-panel] menu-bar blur: could not watch wallpaper settings');
        }
        this._connect(this._panelSettings, 'changed::menu-bar-blur', () => this._apply());
        this._connect(this._panelSettings, 'changed::panel-height', () => {
            this._syncGeometry();
            this._scheduleRegen();
        });

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
        if (this._holder) {
            this._holder.destroy();  // also destroys _actor
            this._holder = null;
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

    _syncGeometry() {
        if (!this._actor)
            return;
        // panelBox coordinate space; Main.panel is normally at its origin.
        this._actor.set_position(Main.panel.x, Main.panel.y);
        this._actor.set_size(
            Main.panel.width || Main.layoutManager.primaryMonitor?.width || 0,
            Main.panel.height || 40);
    }

    _apply() {
        if (!this._actor)
            return;
        if (!this.isBlurOn()) {
            this._actor.set_content(null);
            this._actor.hide();
        }
        // Always regenerate: even blur-off needs the luminance verdict for text colour,
        // since the wallpaper shows straight through a transparent panel.
        this._scheduleRegen(true);
    }

    _scheduleRegen(immediate = false) {
        if (this._regenId)
            GLib.source_remove(this._regenId);
        this._regenId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, immediate ? 1 : REGEN_DEBOUNCE_MS, () => {
                this._regenId = 0;
                this._regenAndApply();
                return GLib.SOURCE_REMOVE;
            });
    }

    _regenAndApply() {
        if (this._destroyed || !this._actor || this._regenInFlight)
            return;
        const mon = Main.layoutManager.primaryMonitor;
        if (!mon)
            return;
        this._regenInFlight = true;

        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const w = Math.round(mon.width * scale);
        const h = Math.round(mon.height * scale);
        let ph = this._panelSettings.get_int('panel-height');
        if (ph <= 0)
            ph = Main.panel.height || 40;
        ph = Math.round(ph * scale);

        this._nonce += 1;
        const prevPath = this._currentPath;
        const outPath = GLib.build_filenamev([CACHE_DIR, `panel-blur-${this._nonce}.png`]);

        let proc;
        try {
            proc = Gio.Subprocess.new(
                [HELPER, String(w), String(h), String(ph), outPath],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (e) {
            this._regenInFlight = false;
            logError(e, '[macos-top-panel] menu-bar blur: could not run helper');
            return;
        }
        proc.communicate_utf8_async(null, null, (p, res) => {
            this._regenInFlight = false;
            if (this._destroyed || !this._actor)
                return;
            let ok, stdout;
            try {
                [ok, stdout] = p.communicate_utf8_finish(res);
            } catch (e) {
                return;
            }
            const [pngPath = '', verdict = ''] = (stdout || '').trim().split('\n');

            // Text colour: contrast against whatever's behind the (transparent) panel.
            this._onForeground(verdict.trim() === 'light' ? 'black' : 'white');

            if (!this.isBlurOn()) {
                this._actor.set_content(null);
                this._actor.hide();
                return;
            }
            if (!ok || !pngPath || !GLib.file_test(pngPath, GLib.FileTest.EXISTS)) {
                this._actor.set_content(null);
                this._actor.hide();
                return;
            }
            this._setImage(pngPath);
            this._currentPath = pngPath;
            if (prevPath && prevPath !== pngPath) {
                Gio.File.new_for_path(prevPath).delete_async(
                    GLib.PRIORITY_LOW, null, (f, r) => {
                        try {
                            f.delete_finish(r);
                        } catch (e) {
                            // stale cache file already gone -- harmless
                        }
                    });
            }
        });
    }

    _setImage(path) {
        let pixbuf;
        try {
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path);
        } catch (e) {
            logError(e, '[macos-top-panel] menu-bar blur: could not load strip');
            this._actor.hide();
            return;
        }
        // Clutter.Image was removed in GNOME 50 -- use St.ImageContent + Cogl bytes.
        const coglContext = global.stage.context.get_backend().get_cogl_context();
        const content = St.ImageContent.new_with_preferred_size(
            pixbuf.get_width(), pixbuf.get_height());
        content.set_bytes(
            coglContext,
            pixbuf.read_pixel_bytes(),
            pixbuf.get_has_alpha() ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
            pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_rowstride());
        this._actor.set_content(content);
        this._actor.show();
    }
}
