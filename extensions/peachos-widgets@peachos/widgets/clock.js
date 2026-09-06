// Clock widgets, ported from the KDE liquidglass repo.
//
//  DigitalClock -- packages/clock-digital: a tick ring between two inset
//  squircle frames (TickRing.qml), a subtle moving highlight, and a centred
//  H:MM in Barlow Condensed that auto-shrinks to fit, with a two-dot colon.
//
//  AnalogClock -- packages/clock-analog: translucent disc, 60 pill ticks,
//  SF Pro Rounded hour numbers, pill hands, an orange (#F6A029) second hand.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {squircleRayHit} from '../lib/squircle.js';
import {FONT, fontStyle} from '../lib/fonts.js';

const {cairo: Cairo} = imports;

const SECOND_ORANGE = [0.965, 0.627, 0.161]; // #F6A029

class Ticker {
    constructor(intervalMs, onTick) {
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
        this._w = size.w;
        this._h = size.h;
        this._radius = size.radius;
        this._roundness = size.roundness ?? 7.5;
        this._fg = size.fg || '255,255,255';
        // glass keeps the readout translucent; solid modes want it opaque
        this._digitOpacity = this._fg.startsWith('255') ? 0.55 : 0.9;
        this._ringBase = this._fg.startsWith('255') ? 0.20 : 0.35;

        this._root = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: size.w, height: size.h,
        });
        parent.add_child(this._root);

        this._ring = new St.DrawingArea({x_expand: true, y_expand: true});
        this._ring.connect('repaint', a => this._drawRing(a));
        this._root.add_child(this._ring);

        this._row = new St.BoxLayout({
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._hour = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        this._min = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        this._colon = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._dots = [new St.Widget(), new St.Widget()];
        this._dots.forEach(d => this._colon.add_child(d));
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
        const h = `${((now.get_hour() + 11) % 12) + 1}`;
        const m = now.format('%M');

        // KDE: target 0.60*minSide, shrink to fit the interior (edge inset
        // + tick + pad = ~15% each side).
        const minSide = Math.min(this._w, this._h);
        const availW = this._w - 2 * minSide * 0.15;
        let px = minSide * 0.6;
        const estW = (h.length + m.length) * 0.46 * px + 0.55 * px;
        if (estW > availW)
            px *= availW / estW;
        px = Math.round(px);

        this._hour.text = h;
        this._min.text = m;
        this._hour.style = fontStyle(FONT.clock, px, this._digitOpacity, this._fg);
        this._min.style = fontStyle(FONT.clock, px, this._digitOpacity, this._fg);

        const dot = Math.max(3, Math.round(px * 0.10));
        this._colon.style = `spacing: ${Math.round(dot * 1.35)}px; `
            + `margin: 0 ${Math.round(px * 0.12)}px;`;
        this._dots.forEach(d => {
            d.set_size(dot, dot);
            d.style = `background-color: rgba(${this._fg},${this._digitOpacity}); `
                + `border-radius: ${dot}px;`;
        });
    }

    // Ported from TickRing.qml _rebuild(): two inset squircle frames, corner
    // ticks pulled slightly outward.
    _drawRing(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const cx = w / 2;
            const cy = h / 2;
            const minSide = Math.min(w, h);
            const n = Math.max(this._roundness, 2.0);

            const outerInsetPx = 0.05 * minSide;
            const innerPad = (0.05 + 0.026) * minSide;
            const cornerExtPx = 0.012 * minSide;

            const secAngle = (Date.now() % 60000) / 60000 * 360;

            cr.setLineCap(Cairo.LineCap.ROUND);
            cr.setLineWidth(2.2);

            for (let i = 0; i < 60; i++) {
                const rad = i * 6 * Math.PI / 180;
                const dx = Math.sin(rad);
                const dy = -Math.cos(rad);
                const cornerBlend = 1 - Math.abs(Math.abs(dx) - Math.abs(dy));
                const tickOuterInset = Math.max(0, outerInsetPx - cornerExtPx * cornerBlend);

                const [ox, oy] = squircleRayHit(dx, dy,
                    Math.max(1, w / 2 - tickOuterInset),
                    Math.max(1, h / 2 - tickOuterInset),
                    Math.max(0, this._radius - tickOuterInset), n);
                const [ix, iy] = squircleRayHit(dx, dy,
                    Math.max(1, w / 2 - innerPad),
                    Math.max(1, h / 2 - innerPad),
                    Math.max(0, this._radius - innerPad), n);

                let off = (secAngle - i * 6 + 360) % 360;
                if (off > 180)
                    off -= 360;
                const near = Math.max(0, 1 - Math.abs(off) / 46);
                const op = this._ringBase + (1 - this._ringBase) * near * near * 0.4;

                cr.setSourceRGBA(...this._rgb(), op);
                cr.moveTo(cx + ix, cy + iy);
                cr.lineTo(cx + ox, cy + oy);
                cr.stroke();
            }
        } finally {
            cr.$dispose();
        }
    }

    _rgb() {
        return this._fg.split(',').map(v => parseInt(v, 10) / 255);
    }

    destroy() {
        this._tick.destroy();
        this._root.destroy();
    }
}

// ---------------------------------------------------------------------------
// Analog -- ported from packages/clock-analog-2 (the minimal one: 12 pill
// hour-lines, no numbers, no minute ring).
// ---------------------------------------------------------------------------

export class AnalogClock {
    constructor(parent, size) {
        this._fg = size.fg || '255,255,255';
        this._mode = size.mode || 'glass';

        this._root = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: size.w, height: size.h,
        });
        parent.add_child(this._root);

        this._face = new St.DrawingArea({x_expand: true, y_expand: true});
        this._face.connect('repaint', a => this._draw(a));
        this._root.add_child(this._face);

        this._tick = new Ticker(1000, () => this._face.queue_repaint());
    }

    _rgb(a = 1) {
        const [r, g, b] = this._fg.split(',').map(v => parseInt(v, 10) / 255);
        return [r, g, b, a];
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const cx = w / 2;
            const cy = h / 2;
            // face inset from the card edge, then r = radius of that face
            const inset = Math.min(w, h) * 0.08;
            const r = Math.min(w, h) / 2 - inset;

            // --- clock plate (circle) ---
            if (this._mode === 'glass')
                cr.setSourceRGBA(...this._rgb(0.20));
            else if (this._mode === 'light')
                cr.setSourceRGBA(1, 1, 1, 1);
            else
                cr.setSourceRGBA(0.204, 0.204, 0.212, 1); // #343436
            cr.arc(cx, cy, r, 0, 2 * Math.PI);
            cr.fill();

            const tickW = r * 0.020;
            const outerR = r - tickW * 2;              // 0.96 r
            const innerR = outerR - r * 0.09;          // 0.87 r
            const minuteLen = (outerR + innerR) / 2;   // 0.915 r
            const hourLen = minuteLen * 0.65;          // 0.595 r

            // --- 12 pill-shaped hour lines ---
            const lineW = r * 0.0336 * 0.9 * 1.15 * 1.35;
            const lineLen = hourLen * 0.40 * 0.90 * 1.10;
            cr.setLineCap(Cairo.LineCap.ROUND);
            cr.setLineWidth(lineW);
            cr.setSourceRGBA(...this._rgb(0.75));
            for (let i = 0; i < 12; i++) {
                const a = i * 30 * Math.PI / 180;
                const s = Math.sin(a);
                const c = -Math.cos(a);
                cr.moveTo(cx + s * outerR, cy + c * outerR);
                cr.lineTo(cx + s * (outerR - lineLen), cy + c * (outerR - lineLen));
                cr.stroke();
            }

            const now = GLib.DateTime.new_now_local();
            const sec = now.get_second();
            const min = now.get_minute() + sec / 60;
            const hr = (now.get_hour() % 12) + min / 60;

            const hand = this._rgb(this._mode === 'glass' ? 0.92 : 1.0);

            // pill hand: thin stem (rect) + capsule (thick round-capped stroke)
            const drawHand = (turns, totalLen) => {
                cr.save();
                cr.translate(cx, cy);
                cr.rotate(turns * 2 * Math.PI);
                cr.setSourceRGBA(...hand);
                const stemEnd = r * 0.15;
                const stemW = r * 0.0336;
                cr.rectangle(-stemW / 2, -stemEnd, stemW, stemEnd);
                cr.fill();
                cr.setLineCap(Cairo.LineCap.ROUND);
                cr.setLineWidth(r * 0.065);
                cr.moveTo(0, -stemEnd);
                cr.lineTo(0, -totalLen);
                cr.stroke();
                cr.restore();
            };
            drawHand(hr / 12, hourLen);
            drawHand(min / 60, minuteLen);

            // pivot
            cr.setSourceRGBA(...hand);
            cr.arc(cx, cy, r * 0.05, 0, 2 * Math.PI);
            cr.fill();

            // second hand (orange, with counterweight tail)
            cr.save();
            cr.translate(cx, cy);
            cr.rotate((sec / 60) * 2 * Math.PI);
            cr.setSourceRGBA(...SECOND_ORANGE, 1);
            const shw = r * 0.007 * 1.3;
            cr.rectangle(-shw, -outerR, shw * 2, outerR + r * 0.15);
            cr.fill();
            cr.restore();

            // hinge dot (orange, on top)
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
