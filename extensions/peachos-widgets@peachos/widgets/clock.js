// Clock widgets -- digital (two St.Labels) and analog (St.DrawingArea + Cairo,
// the same pattern as macos-top-panel/lib/batteryCanvas.js).

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

const {cairo: Cairo} = imports;

class ClockTimer {
    constructor(onTick) {
        this._onTick = onTick;
        onTick();
        // Re-align to the top of each second, then tick once a second.
        const now = GLib.DateTime.new_now_local();
        const delayMs = 1000 - Math.floor(now.get_microsecond() / 1000);
        this._syncId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delayMs, () => {
            this._syncId = 0;
            this._onTick();
            this._tickId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
                this._onTick();
                return GLib.SOURCE_CONTINUE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        if (this._syncId)
            GLib.source_remove(this._syncId);
        if (this._tickId)
            GLib.source_remove(this._tickId);
        this._syncId = 0;
        this._tickId = 0;
    }
}

export class DigitalClock {
    constructor(parent) {
        this._box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
            y_expand: true,
            style_class: 'peachos-widget-clock',
        });
        this._time = new St.Label({
            style_class: 'peachos-widget-clock-time',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._date = new St.Label({
            style_class: 'peachos-widget-clock-date',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._box.add_child(this._time);
        this._box.add_child(this._date);
        parent.add_child(this._box);

        this._timer = new ClockTimer(() => this._tick());
    }

    _tick() {
        const now = GLib.DateTime.new_now_local();
        this._time.text = now.format('%-I:%M');
        this._date.text = now.format('%A, %B %-e');
    }

    destroy() {
        this._timer.destroy();
        this._box.destroy();
    }
}

export class AnalogClock {
    constructor(parent) {
        this._area = new St.DrawingArea({x_expand: true, y_expand: true});
        this._area.connect('repaint', area => this._draw(area));
        parent.add_child(this._area);

        this._timer = new ClockTimer(() => this._area.queue_repaint());
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const cx = w / 2;
            const cy = h / 2;
            const r = Math.min(w, h) / 2 - 6;

            // Face
            cr.setSourceRGBA(1, 1, 1, 0.10);
            cr.arc(cx, cy, r, 0, 2 * Math.PI);
            cr.fill();
            cr.setLineWidth(1.5);
            cr.setSourceRGBA(1, 1, 1, 0.55);
            cr.arc(cx, cy, r, 0, 2 * Math.PI);
            cr.stroke();

            // Hour ticks
            cr.setSourceRGBA(1, 1, 1, 0.65);
            for (let i = 0; i < 12; i++) {
                const a = (i / 12) * 2 * Math.PI;
                const outer = r - 3;
                const inner = i % 3 === 0 ? r - 10 : r - 6;
                cr.setLineWidth(i % 3 === 0 ? 2.2 : 1.2);
                cr.moveTo(cx + Math.sin(a) * inner, cy - Math.cos(a) * inner);
                cr.lineTo(cx + Math.sin(a) * outer, cy - Math.cos(a) * outer);
                cr.stroke();
            }

            const now = GLib.DateTime.new_now_local();
            const s = now.get_second();
            const m = now.get_minute() + s / 60;
            const hr = (now.get_hour() % 12) + m / 60;

            const hand = (angleTurns, length, width, alpha) => {
                const a = angleTurns * 2 * Math.PI;
                cr.setLineWidth(width);
                cr.setSourceRGBA(1, 1, 1, alpha);
                cr.moveTo(cx, cy);
                cr.lineTo(cx + Math.sin(a) * length, cy - Math.cos(a) * length);
                cr.stroke();
            };

            hand(hr / 12, r * 0.5, 3.5, 0.95);
            hand(m / 60, r * 0.75, 2.5, 0.95);
            hand(s / 60, r * 0.82, 1.2, 0.8);

            cr.setSourceRGBA(1, 1, 1, 0.95);
            cr.arc(cx, cy, 3, 0, 2 * Math.PI);
            cr.fill();
        } finally {
            cr.$dispose();
        }
    }

    destroy() {
        this._timer.destroy();
        this._area.destroy();
    }
}
