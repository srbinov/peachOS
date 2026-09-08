// lib/spriteAnimation.js
//
// Plays a grid sprite-sheet PNG as a looping frame animation on an St.Widget.
// The sheet is sliced once (lazily, on first play) into St.ImageContent
// textures which are then swapped on a GLib timer -- no per-frame decode or
// upload once warmed.
//
// Used for the Peach Intelligence voice waveform in the Dynamic Island, baked
// from a Lottie file by tools/lottie-bake/. The companion <sheet>.json holds
// { frames, cols, rows, cellW, cellH, durationMs }.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GdkPixbuf from 'gi://GdkPixbuf';
import St from 'gi://St';

export function loadSpriteMeta(jsonPath) {
    const [ok, bytes] = Gio.File.new_for_path(jsonPath).load_contents(null);
    if (!ok)
        throw new Error(`could not read ${jsonPath}`);
    return JSON.parse(new TextDecoder().decode(bytes));
}

export class SpriteAnimation {
    // meta: { frames, cols, rows, cellW, cellH, durationMs }
    // opts.loop       -- true: restart at 0 forever; false: stop on the last frame
    // opts.durationMs  -- override the loop length from meta (e.g. play it faster)
    constructor(sheetPath, meta, {width, height, loop = true, durationMs = null}) {
        this._sheetPath = sheetPath;
        this._meta = meta;
        this._loop = loop;
        this._durationMs = durationMs ?? meta.durationMs;
        this._frames = null;
        this._timerId = 0;
        this._i = 0;

        this.actor = new St.Widget({
            width, height, opacity: 255,
            y_align: Clutter.ActorAlign.CENTER, y_expand: false,
        });
        this.actor.set_content_gravity(Clutter.ContentGravity.RESIZE_FILL);
        this.actor.set_pivot_point(0.5, 0.5);
    }

    _ensureFrames() {
        if (this._frames)
            return true;
        try {
            const sheet = GdkPixbuf.Pixbuf.new_from_file(this._sheetPath);
            const coglContext = global.stage.context.get_backend().get_cogl_context();
            const {frames, cols, cellW, cellH} = this._meta;
            this._frames = [];
            for (let n = 0; n < frames; n++) {
                const sx = (n % cols) * cellW;
                const sy = Math.floor(n / cols) * cellH;
                // copy_area into a fresh pixbuf -- new_subpixbuf (even .copy()'d) keeps the
                // sheet's full rowstride, which bloats every frame's buffer ~8x.
                const cell = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, true, 8, cellW, cellH);
                sheet.copy_area(sx, sy, cellW, cellH, cell, 0, 0);
                const content = St.ImageContent.new_with_preferred_size(cellW, cellH);
                content.set_bytes(
                    coglContext, cell.read_pixel_bytes(),
                    cell.get_has_alpha() ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
                    cellW, cellH, cell.get_rowstride());
                this._frames.push(content);
            }
            return true;
        } catch (e) {
            logError(e, '[macos-top-panel] sprite sheet load failed');
            this._frames = null;
            return false;
        }
    }

    get isPlaying() {
        return this._timerId !== 0;
    }

    // Slice + upload the frames now (idle time) so the first play() doesn't.
    warm() {
        this._ensureFrames();
    }

    play() {
        if (this._timerId || !this._ensureFrames())
            return;
        const {frames} = this._meta;
        const interval = Math.max(16, Math.round(this._durationMs / frames));
        this._i = 0;
        this._show(0);
        this._timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, interval, () => {
            this._i++;
            if (this._i >= frames) {
                if (!this._loop) {
                    this._i = frames - 1;
                    this._show(this._i);
                    this._timerId = 0;
                    return GLib.SOURCE_REMOVE;
                }
                this._i = 0;
            }
            this._show(this._i);
            return GLib.SOURCE_CONTINUE;
        });
    }

    stop() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        this._i = 0;
        this.actor.remove_all_transitions();
        this.actor.scale_y = 1;
    }

    _show(i) {
        if (this._frames?.[i])
            this.actor.set_content(this._frames[i]);
    }

    // Subtle vertical pulse from a live 0..1 signal (real mic level). Keeps the
    // baked art but lets the animation still visibly react to the voice.
    setLevel(level) {
        const target = 0.62 + Math.min(1, Math.max(0, level)) * 0.6;
        this.actor.ease({
            scale_y: target, duration: 110,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });
    }

    destroy() {
        this.stop();
        this.actor.set_content(null);
        this._frames = null;
        this.actor.destroy();
    }
}
