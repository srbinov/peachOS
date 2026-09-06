// The widget card, drawn in Cairo as a proper quintic squircle (n = 5, the
// Apple app-icon superellipse) -- not a border-radius rounded rect.
//
//   glass -- a blurred wallpaper crop (lib/wallpaperCrop.js, baked to a PNG)
//            + a translucent white tint/gradient + a hairline rim.
//   dark  -- opaque #1c1c1e, white content.
//   light -- opaque #ffffff, dark content.
//
// Always full strength; not tied to the Settings "Liquid Glass" slider.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import St from 'gi://St';

import {squirclePath} from './squircle.js';
import {buildBlurredCropFile} from './wallpaperCrop.js';

const {cairo: Cairo} = imports;

export const MARGIN = 0;
export const MODE_FG = {glass: '255,255,255', dark: '255,255,255', light: '26,27,30'};

const SQUIRCLE_N = 5;
let _cropSeq = 0;

function traceSquircle(cr, w, h, r) {
    // centred, inset 1px so a 1px stroke sits inside the bounds
    squirclePath(cr, w / 2, h / 2, w / 2 - 1, h / 2 - 1, Math.max(1, r - 1), SQUIRCLE_N, 128);
}

function paintCard(cr, w, h, radiusPx, mode, cropPath) {
    cr.save();
    traceSquircle(cr, w, h, radiusPx);
    cr.clip();

    if (mode === 'glass') {
        if (cropPath) {
            try {
                const png = Cairo.ImageSurface.createFromPNG(cropPath);
                const pw = png.getWidth();
                const ph = png.getHeight();
                if (pw > 0 && ph > 0) {
                    cr.save();
                    cr.scale(w / pw, h / ph);
                    cr.setSourceSurface(png, 0, 0);
                    cr.getSource().setExtend(Cairo.Extend.PAD);
                    cr.paint();
                    cr.restore();
                }
            } catch (e) {
                // no crop yet
            }
        }
        const g = new Cairo.LinearGradient(0, 0, 0, h);
        g.addColorStopRGBA(0, 1, 1, 1, 0.26);
        g.addColorStopRGBA(1, 1, 1, 1, 0.05);
        cr.setSource(g);
        cr.paint();
        cr.setSourceRGBA(1, 1, 1, 0.08);
        cr.paint();
    } else if (mode === 'light') {
        cr.setSourceRGBA(1, 1, 1, 1);
        cr.paint();
    } else {
        cr.setSourceRGBA(0.109, 0.109, 0.118, 1); // #1c1c1e
        cr.paint();
    }
    cr.restore();

    // rim
    traceSquircle(cr, w, h, radiusPx);
    cr.setLineWidth(mode === 'glass' ? 1.3 : 1.0);
    if (mode === 'light')
        cr.setSourceRGBA(0, 0, 0, 0.1);
    else if (mode === 'dark')
        cr.setSourceRGBA(1, 1, 1, 0.12);
    else
        cr.setSourceRGBA(1, 1, 1, 0.5);
    cr.stroke();
}

export function makeLiquidGlass(opts) {
    const {innerW, innerH, x, y} = opts;
    const radius = opts.radius ?? 32;
    const mode = opts.mode ?? 'glass';
    const cropId = _cropSeq++;

    const widget = new St.Widget({
        width: innerW, height: innerH, x, y,
        reactive: false,
        layout_manager: new Clutter.BinLayout(),
    });

    let cropPath = null;
    let prevPath = null;
    let cropN = 0;

    const card = new St.DrawingArea({x_expand: true, y_expand: true});
    card.connect('repaint', area => {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const scale = w / Math.max(1, innerW);
            paintCard(cr, w, h, radius * scale, mode, cropPath);
        } finally {
            cr.$dispose();
        }
    });
    widget.add_child(card);

    const applyCrop = () => {
        if (mode === 'glass') {
            const p = buildBlurredCropFile(
                {x: widget.x, y: widget.y, w: innerW, h: innerH}, `${cropId}-${cropN++}`);
            if (p) {
                cropPath = p;
                if (prevPath && prevPath !== p) {
                    try {
                        Gio.File.new_for_path(prevPath).delete(null);
                    } catch (e) {
                        // gone
                    }
                }
                prevPath = p;
            }
        }
        card.queue_repaint();
    };
    applyCrop();

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
