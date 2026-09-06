// The widget card. Three modes, matching the KDE liquidglass widgets:
//
//   glass -- a blurred wallpaper crop (baked to a PNG, lib/wallpaperCrop.js)
//            as a CSS background-image, a translucent white tint on top, a
//            hairline rim. St clips background-image + children to the
//            border-radius.
//   dark  -- opaque #1c1c1e, white content.
//   light -- opaque #ffffff, dark content.
//
// Always full strength; not tied to the Settings "Liquid Glass" slider.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import Gio from 'gi://Gio';

import {buildBlurredCropFile} from './wallpaperCrop.js';

export const MARGIN = 0;
export const MODE_FG = {glass: '255,255,255', dark: '255,255,255', light: '26,27,30'};

let _cropSeq = 0;

export function makeLiquidGlass(opts) {
    const {innerW, innerH, x, y} = opts;
    const radius = opts.radius ?? 32;
    const mode = opts.mode ?? 'glass';
    const cropId = `${_cropSeq++}`;

    const widget = new St.Widget({
        width: innerW, height: innerH, x, y,
        reactive: false,
        layout_manager: new Clutter.BinLayout(),
    });

    const rim = mode === 'light'
        ? '1px solid rgba(0,0,0,0.10)'
        : mode === 'dark'
            ? '1px solid rgba(255,255,255,0.12)'
            : '1px solid rgba(255,255,255,0.5)';

    let tint = null;
    let applyCrop = () => {};
    let prevFile = null;
    let cropN = 0;

    if (mode === 'glass') {
        applyCrop = () => {
            // St caches background-image by URL, so each refresh needs a new
            // filename; drop the previous one.
            const file = buildBlurredCropFile(
                {x: widget.x, y: widget.y, w: innerW, h: innerH}, `${cropId}-${cropN++}`);
            widget.style = `border-radius: ${radius}px; border: ${rim};`
                + (file ? ` background-image: url("file://${file}"); background-size: cover;` : '');
            if (prevFile && prevFile !== file) {
                try {
                    Gio.File.new_for_path(prevFile).delete(null);
                } catch (e) {
                    // already gone
                }
            }
            prevFile = file;
        };
        applyCrop();

        tint = new St.Widget({
            x_expand: true, y_expand: true,
            style: `border-radius: ${radius}px;`
                + ' background-color: rgba(255,255,255,0.16);'
                + ' background-gradient-direction: vertical;'
                + ' background-gradient-start: rgba(255,255,255,0.28);'
                + ' background-gradient-end: rgba(255,255,255,0.06);',
        });
        widget.add_child(tint);
    } else {
        widget.style = `border-radius: ${radius}px; border: ${rim};`
            + (mode === 'dark' ? ' background-color: #1c1c1e;' : ' background-color: #ffffff;');
    }

    const content = new St.Widget({
        layout_manager: new Clutter.BinLayout(),
        x_expand: true, y_expand: true,
    });
    widget.add_child(content);

    return {
        widget,
        content,
        mode,
        fg: MODE_FG[mode],
        setInnerPos(nx, ny) {
            widget.set_position(Math.round(nx), Math.round(ny));
        },
        refresh() {
            applyCrop();
        },
    };
}
