// Clock widgets, matched to the KDE liquidglass repo.
//
//  DigitalClock -- a tick ring following the glass squircle with a subtle
//  comet-trail second indicator, and a centred H:MM in Barlow Condensed with
//  a two-dot colon (KDE clock-digital + TickRing.qml + DigitalTime.qml).
//
//  AnalogClock -- translucent disc, 60 pill ticks, SF Pro Rounded hour
//  numbers, pill hour/minute hands, an orange (#F6A029) second hand + hinge
//  (KDE clock-analog/main.qml).

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {squircleRayHit} from '../lib/squircle.js';
import {applyFont, FAMILIES, Pango} from '../lib/fonts.js';

const {cairo: Cairo} = imports;

const FG = [1, 1, 1];
const SECOND_ORANGE = [0.965, 0.627, 0.161]; // #F6A029
const DIGIT_OPACITY = 0.55;                   // glass mode
const RING_BASE_OPACITY = 0.22;               // glass mode

class Ticker {
    constructor(intervalMs, onTick) {
        this._onTick = onTick;
        onTick();
        this._id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, intervalMs, () => {
            onTick();
            return GLib.SOURCE_CONTINUE;
        });
    }

    destroy() {
        if (this._id)
            GLib.source_remove(this._id);
        this._id = 0;
    }
}

// ---------------------------------------------------------------------------
// Digital
// ---------------------------------------------------------------------------

export class DigitalClock {
    constructor(parent, size) {
        this._radius = size.radius;
        this._roundness = size.roundness ?? 7.0;
        const minSide = Math.min(size.w, size.h);

        this._root = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: size.w, height: size.h,
        });
        parent.add_child(this._root);

        this._ring = new St.DrawingArea({x_expand: true, y_expand: true});
        this._ring.connect('repaint', a => this._drawRing(a));
        this._root.add_child(this._ring);

        // H : MM  ---------------------------------------------------------
        const px = Math.round(minSide * 0.44);
        this._row = new St.BoxLayout({
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._hour = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        this._min = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        for (const l of [this._hour, this._min]) {
            applyFont(l, FAMILIES.barlow, px, Pango.Weight.MEDIUM);
            l.style = `color: rgba(255,255,255,${DIGIT_OPACITY});`;
        }

        const dot = Math.max(3, Math.round(px * 0.11));
        this._colon = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            y_align: Clutter.ActorAlign.CENTER,
            style: `spacing: ${Math.round(dot * 1.35)}px; margin: 0 ${Math.round(px * 0.11)}px;`,
        });
        for (let i = 0; i < 2; i++) {
            this._colon.add_child(new St.Widget({
                width: dot, height: dot,
                style: `background-color: rgba(255,255,255,${DIGIT_OPACITY}); border-radius: ${dot}px;`,
            }));
        }
        this._row.add_child(this._hour);
        this._row.add_child(this._colon);
        this._row.add_child(this._min);
        this._root.add_child(this._row);

        this._tick = new Ticker(1000, () => {
            this._updateTime();
            this._ring.queue_repaint();
        });
    }

    _updateTime() {
        const now = GLib.DateTime.new_now_local();
        this._hour.text = `${((now.get_hour() + 11) % 12) + 1}`;
        this._min.text = now.format('%M');
    }

    _drawRing(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const minSide = Math.min(w, h);
            const cx = w / 2;
            const cy = h / 2;
            const n = Math.max(this._roundness, 2.0);

            const outerInset = 0.05 * minSide;
            const tickLen = 0.05 * minSide;
            const cornerExt = 0.012 * minSide;
            const innerPad = outerInset + tickLen;

            const secPos = (Date.now() % 60000) / 1000;
            const curIdx = Math.floor(secPos) % 60;
            const prevIdx = (curIdx - 1 + 60) % 60;
            const fadeT = secPos - Math.floor(secPos);
            const sHead = fadeT * fadeT * (3 - 2 * fadeT);
            const trailDeg = 250;

            cr.setLineCap(Cairo.LineCap.ROUND);
            cr.setLineWidth(2.4);

            for (let i = 0; i < 60; i++) {
                const rad = i * 6 * Math.PI / 180;
                const dx = Math.sin(rad);
                const dy = -Math.cos(rad);
                const cornerBlend = 1 - Math.abs(Math.abs(dx) - Math.abs(dy));
                const oInset = Math.max(0, outerInset - cornerExt * cornerBlend);

                const [ox, oy] = squircleRayHit(dx, dy,
                    Math.max(1, w / 2 - oInset), Math.max(1, h / 2 - oInset),
                    Math.max(0, this._radius - oInset), n);
                const [ix, iy] = squircleRayHit(dx, dy,
                    Math.max(1, w / 2 - innerPad), Math.max(1, h / 2 - innerPad),
                    Math.max(0, this._radius - innerPad), n);

                let s = 0;
                if (i === curIdx) {
                    s = sHead;
                } else {
                    const off = ((prevIdx * 6) - (i * 6) + 360) % 360;
                    if (off <= trailDeg)
                        s = Math.pow(1 - off / trailDeg, 0.7) * 0.9;
                }
                const op = RING_BASE_OPACITY + (1 - RING_BASE_OPACITY) * s;

                cr.setSourceRGBA(FG[0], FG[1], FG[2], op);
                cr.moveTo(cx + ix, cy + iy);
                cr.lineTo(cx + ox, cy + oy);
                cr.stroke();
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

// ---------------------------------------------------------------------------
// Analog
// ---------------------------------------------------------------------------

export class AnalogClock {
    constructor(parent, size) {
        this._root = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: size.w, height: size.h,
        });
        parent.add_child(this._root);

        this._face = new St.DrawingArea({x_expand: true, y_expand: true});
        this._face.connect('repaint', a => this._draw(a));
        this._root.add_child(this._face);

        this._numbers = new Clutter.Actor({width: size.w, height: size.h});
        this._root.add_child(this._numbers);
        this._layoutNumbers(size.w, size.h);

        this._tick = new Ticker(1000, () => this._face.queue_repaint());
    }

    _layoutNumbers(w, h) {
        const cx = w / 2;
        const cy = h / 2;
        const faceR = Math.min(w, h) / 2 - Math.min(w, h) * 0.08;
        const dist = faceR * 0.72;
        const fs = Math.max(9, Math.round(faceR * 0.17));
        for (let i = 1; i <= 12; i++) {
            const a = (i / 12) * 2 * Math.PI;
            const l = new St.Label({text: `${i}`});
            applyFont(l, FAMILIES.rounded, fs, Pango.Weight.MEDIUM);
            l.style = 'color: rgba(255,255,255,0.85);';
            const nw = fs * (i < 10 ? 0.52 : 0.98);
            const nh = fs * 1.15;
            l.set_position(
                Math.round(cx + Math.sin(a) * dist - nw / 2),
                Math.round(cy - Math.cos(a) * dist - nh / 2));
            this._numbers.add_child(l);
        }
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const cx = w / 2;
            const cy = h / 2;
            const r = Math.min(w, h) / 2 - Math.min(w, h) * 0.08;

            cr.setSourceRGBA(1, 1, 1, 0.20);
            cr.arc(cx, cy, r, 0, 2 * Math.PI);
            cr.fill();

            const tickW = r * 0.020;
            const tickLen = r * 0.09;
            const outerR = r - tickW * 2;
            const innerR = outerR - tickLen;
            cr.setLineCap(Cairo.LineCap.ROUND);
            cr.setLineWidth(tickW);
            for (let i = 0; i < 60; i++) {
                cr.setSourceRGBA(FG[0], FG[1], FG[2], i % 5 === 0 ? 0.75 : 0.30);
                const a = i * 6 * Math.PI / 180;
                const s = Math.sin(a);
                const c = Math.cos(a);
                cr.moveTo(cx + s * innerR, cy - c * innerR);
                cr.lineTo(cx + s * outerR, cy - c * outerR);
                cr.stroke();
            }

            const now = GLib.DateTime.new_now_local();
            const sec = now.get_second();
            const min = now.get_minute() + sec / 60;
            const hr = (now.get_hour() % 12) + min / 60;

            const minuteLen = (outerR + innerR) / 2;
            const hourLen = minuteLen * 0.65;

            const pill = (turns, len, stemEnd, stemW, pillW, rgba) => {
                cr.save();
                cr.translate(cx, cy);
                cr.rotate(turns * 2 * Math.PI);
                cr.setSourceRGBA(...rgba);
                cr.rectangle(-stemW / 2, -stemEnd, stemW, stemEnd);
                cr.fill();
                cr.setLineCap(Cairo.LineCap.ROUND);
                cr.setLineWidth(pillW);
                cr.moveTo(0, -stemEnd);
                cr.lineTo(0, -len);
                cr.stroke();
                cr.restore();
            };

            const hand = [1, 1, 1, 0.92];
            pill(hr / 12, hourLen, r * 0.15, r * 0.034, r * 0.065, hand);
            pill(min / 60, minuteLen, r * 0.15, r * 0.034, r * 0.065, hand);

            cr.save();
            cr.translate(cx, cy);
            cr.rotate((sec / 60) * 2 * Math.PI);
            cr.setSourceRGBA(...SECOND_ORANGE, 1);
            const shw = r * 0.009;
            cr.rectangle(-shw, -(r - tickW * 2), shw * 2, (r - tickW * 2) + r * 0.15);
            cr.fill();
            cr.restore();

            cr.setSourceRGBA(...hand);
            cr.arc(cx, cy, r * 0.05, 0, 2 * Math.PI);
            cr.fill();
            cr.setSourceRGBA(...SECOND_ORANGE, 1);
            cr.arc(cx, cy, r * 0.035, 0, 2 * Math.PI);
            cr.fill();
        } finally {
            cr.$dispose();
        }
    }

    destroy() {
        this._tick.destroy();
        this._root.destroy();
    }
}
