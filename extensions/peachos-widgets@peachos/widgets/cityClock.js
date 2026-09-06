// City clock -- 2x2 world clock (KDE packages/city-2). Four minimal analog
// faces, each showing a city's local time; the face flips white (day) / dark
// (night) per city, with the city code inside. Configured via the pencil
// button in edit mode (lib/cityPicker.js).

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import PangoCairo from 'gi://PangoCairo';
import St from 'gi://St';

import {computeCity} from '../lib/worldClock.js';
import {FONT, fontDesc} from '../lib/fonts.js';

const {cairo: Cairo} = imports;

const ORANGE = [0.965, 0.627, 0.161];
export const DEFAULT_CITY_CLOCKS =
    ['America/Los_Angeles', 'Europe/London', 'Asia/Tokyo', 'Australia/Sydney'];

function drawFace(cr, cx, cy, r, city) {
    const day = city.isDay;
    const disc = day ? [1, 1, 1] : [0.204, 0.204, 0.212];   // #fff / #343436
    const mark = day ? [0.102, 0.106, 0.118] : [1, 1, 1];   // #1A1B1E / #fff
    const M = a => [mark[0], mark[1], mark[2], a];

    cr.setSourceRGBA(disc[0], disc[1], disc[2], 1);
    cr.arc(cx, cy, r, 0, 2 * Math.PI);
    cr.fill();

    const tickW = r * 0.020;
    const outerR = r - tickW * 2;
    const innerR = outerR - r * 0.09;
    const minuteLen = (outerR + innerR) / 2;
    const hourLen = minuteLen * 0.65;

    // 12 pill hour lines
    const lineW = r * 0.0336 * 0.9 * 1.15 * 1.35;
    const lineLen = hourLen * 0.4 * 0.9 * 1.1;
    cr.setLineCap(Cairo.LineCap.ROUND);
    cr.setLineWidth(lineW);
    cr.setSourceRGBA(...M(0.75));
    for (let i = 0; i < 12; i++) {
        const a = i * 30 * Math.PI / 180;
        const s = Math.sin(a);
        const c = -Math.cos(a);
        cr.moveTo(cx + s * outerR, cy + c * outerR);
        cr.lineTo(cx + s * (outerR - lineLen), cy + c * (outerR - lineLen));
        cr.stroke();
    }

    const hand = M(0.92);
    const pill = (turns, len) => {
        cr.save();
        cr.translate(cx, cy);
        cr.rotate(turns * 2 * Math.PI);
        cr.setSourceRGBA(...hand);
        cr.rectangle(-(r * 0.0336) / 2, -(r * 0.15), r * 0.0336, r * 0.15);
        cr.fill();
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setLineWidth(r * 0.065);
        cr.moveTo(0, -(r * 0.15));
        cr.lineTo(0, -len);
        cr.stroke();
        cr.restore();
    };
    pill(city.hourAngle / 360, hourLen);
    pill(city.minuteAngle / 360, minuteLen);

    // pivot
    cr.setSourceRGBA(...hand);
    cr.arc(cx, cy, r * 0.05, 0, 2 * Math.PI);
    cr.fill();

    // second hand (orange, 2x thick for the small grid faces)
    cr.save();
    cr.translate(cx, cy);
    cr.rotate((city.secondAngle / 360) * 2 * Math.PI);
    cr.setSourceRGBA(...ORANGE, 1);
    const shw = r * 0.007 * 1.3 * 2;
    cr.rectangle(-shw, -outerR, shw * 2, outerR + r * 0.15);
    cr.fill();
    cr.restore();
    cr.setSourceRGBA(...ORANGE, 1);
    cr.arc(cx, cy, r * 0.04, 0, 2 * Math.PI);
    cr.fill();

    // city code, toward the top
    const layout = PangoCairo.create_layout(cr);
    layout.set_font_description(fontDesc(FONT.rounded, Math.max(7, r * 0.26)));
    layout.set_text(city.code || '', -1);
    const [lw, lh] = layout.get_pixel_size();
    cr.setSourceRGBA(...M(0.55));
    cr.moveTo(cx - lw / 2, cy - r * 0.4 - lh / 2);
    PangoCairo.show_layout(cr, layout);
}

export class CityClock {
    constructor(parent, ctx, size) {
        this._logicalW = size.w;
        this._clocks = (size.clocks && size.clocks.length ? size.clocks : DEFAULT_CITY_CLOCKS).slice(0, 4);

        this._root = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: size.w, height: size.h,
        });
        parent.add_child(this._root);

        this._area = new St.DrawingArea({x_expand: true, y_expand: true});
        this._area.connect('repaint', a => this._draw(a));
        this._root.add_child(this._area);

        this._tick = size.preview
            ? {destroy() {}}
            : {
                _id: GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
                    this._area.queue_repaint();
                    return GLib.SOURCE_CONTINUE;
                }),
                destroy() {
                    if (this._id)
                        GLib.source_remove(this._id);
                    this._id = 0;
                },
            };
    }

    setClocks(arr) {
        this._clocks = (arr && arr.length ? arr : DEFAULT_CITY_CLOCKS).slice(0, 4);
        this._area.queue_repaint();
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const scale = w / Math.max(1, this._logicalW);
            const margin = Math.round(Math.min(w, h) * 0.06);
            const gap = Math.round(margin * 0.4);
            const cellW = (w - 2 * margin - gap) / 2;
            const cellH = (h - 2 * margin - gap) / 2;
            const faceR = (Math.min(cellW, cellH) - 10 * scale) / 2;
            const now = new Date();

            for (let i = 0; i < 4; i++) {
                const tz = this._clocks[i] || DEFAULT_CITY_CLOCKS[i];
                const col = i % 2;
                const row = Math.floor(i / 2);
                const cx = margin + col * (cellW + gap) + cellW / 2;
                const cy = margin + row * (cellH + gap) + cellH / 2;
                drawFace(cr, cx, cy, faceR, computeCity(tz, now));
            }
        } finally {
            cr.$dispose();
        }
    }

    destroy() {
        this._tick.destroy();
        this._root.destroy();
    }
}
