// Calendar widget, matched to the KDE liquidglass repo (packages/calendar).
//
//  'month'  -- accent uppercase month header, S M T W T F S with weekend
//   dimming, a 6x7 grid filling the widget, today = a filled white circle with
//   the day number punched out (Cairo DEST_OUT) so the glass shows through.
//  'agenda' -- wide: the grid on the right, an events list on the left with
//   Events today / This week / Upcoming sections and colour-pilled cards.
//
// Events from lib/providers/calendar.js. Font: SF Pro Display.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import PangoCairo from 'gi://PangoCairo';
import St from 'gi://St';

import {formatEventTime} from '../lib/providers/calendar.js';
import {FONT, fontStyle, fontDesc, Pango} from '../lib/fonts.js';

const {cairo: Cairo} = imports;

const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY',
    'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// Today marker: a filled circle in the accent colour. Glass mode punches the
// day number out (Cairo DEST_OUT) so the backdrop shows through; solid modes
// draw a white number over the accent fill.
class TodayBadge {
    constructor(diameter, dayNumber, fontPx, cardMode, accent) {
        this.actor = new St.DrawingArea({width: diameter, height: diameter});
        this._day = dayNumber;
        this._fs = fontPx;
        this._punch = cardMode === 'glass';
        this._accent = accent; // [r,g,b]
        this.actor.connect('repaint', a => this._draw(a));
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            cr.setSourceRGBA(this._accent[0], this._accent[1], this._accent[2], 1);
            cr.arc(w / 2, h / 2, Math.min(w, h) / 2, 0, 2 * Math.PI);
            cr.fill();

            const layout = PangoCairo.create_layout(cr);
            layout.set_font_description(fontDesc(FONT.display, this._fs, true));
            layout.set_text(`${this._day}`, -1);
            const [lw, lh] = layout.get_pixel_size();
            if (this._punch) {
                cr.setOperator(Cairo.Operator.DEST_OUT);
            } else {
                cr.setOperator(Cairo.Operator.OVER);
                cr.setSourceRGBA(1, 1, 1, 1);
            }
            cr.moveTo((w - lw) / 2, (h - lh) / 2);
            PangoCairo.show_layout(cr, layout);
            cr.setOperator(Cairo.Operator.OVER);
        } finally {
            cr.$dispose();
        }
    }
}

export class CalendarWidget {
    constructor(parent, ctx, size, variant) {
        this._ctx = ctx;
        this._variant = variant;                 // 'month' | 'agenda'
        this._cardMode = size.mode || 'glass';   // 'glass' | 'dark' | 'light'
        this._w = size.w;
        this._h = size.h;
        this._fg = size.fg || '255,255,255';
        // KDE: month header + today badge use the accent -- white in glass,
        // red in solid (#FF3B30 dark / #D70015 light).
        this._accent = this._cardMode === 'glass' ? [1, 1, 1]
            : (this._cardMode === 'light' ? [0.843, 0, 0.082] : [1, 0.231, 0.188]);
        this._accentRgb = this._accent.map(v => Math.round(v * 255)).join(',');

        this._root = new Clutter.Actor({width: size.w, height: size.h});
        parent.add_child(this._root);

        this._unsub = ctx.calendar.subscribe(() => this._render());
        this._midnight = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 1800, () => {
            this._render();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _add(actor, x, y) {
        actor.set_position(Math.round(x), Math.round(y));
        this._root.add_child(actor);
        return actor;
    }

    _render() {
        this._root.destroy_all_children();
        const today = new Date();
        const ls = Math.max(11, Math.round(this._h * 0.058));

        const gridW = this._variant === 'agenda' ? Math.round(this._w * 0.5) : this._w;
        const gridX = this._variant === 'agenda' ? this._w - gridW : 0;
        this._renderGrid(gridX, gridW, ls, today);

        if (this._variant === 'agenda')
            this._renderAgenda(0, this._w - gridW, ls, today);
    }

    _renderGrid(originX, areaW, ls, today) {
        const padX = Math.round(this._w * 0.05);
        const padTop = Math.round(this._h * 0.11);
        const padBottom = Math.round(this._h * 0.07);
        const x0 = originX + (this._variant === 'agenda' ? Math.round(areaW * 0.04) : padX);
        const innerW = areaW - 2 * (this._variant === 'agenda' ? Math.round(areaW * 0.04) : padX);
        const colW = innerW / 7;
        let y = padTop;

        // Month header, left-edge roughly over the first weekday column.
        const header = new St.Label({
            text: MONTHS[today.getMonth()],
            style: fontStyle(FONT.display, ls, 1, this._accentRgb),
        });
        // left edge aligned with the "S" of the Sunday column
        this._add(header, x0 + colW / 2 - ls * 0.32, y);
        y += Math.round(ls * 1.6);

        // Weekday row
        for (let c = 0; c < 7; c++) {
            const weekend = c === 0 || c === 6;
            const wl = new St.Label({
                text: WEEKDAYS[c],
                style: fontStyle(FONT.display, ls, weekend ? 0.45 : 0.75, this._fg),
            });
            this._add(wl, x0 + c * colW + colW / 2 - ls * 0.32, y);
        }
        y += Math.round(ls * 1.55);

        // Day grid -- rows sized to the month's actual week count so it fills
        // the widget (months span 4-6 weeks).
        const gridH = this._h - padBottom - y;
        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        const offset = first.getDay();
        const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
        const numRows = Math.ceil((offset + daysInMonth) / 7);
        const rowH = gridH / numRows;

        const monthEvents = this._ctx.calendar.getEvents(
            new Date(today.getFullYear(), today.getMonth(), 1),
            new Date(today.getFullYear(), today.getMonth() + 1, 1));
        const hasEvent = day => monthEvents.some(ev =>
            ev.date < new Date(today.getFullYear(), today.getMonth(), day + 1) &&
            ev.end > new Date(today.getFullYear(), today.getMonth(), day));

        for (let day = 1; day <= daysInMonth; day++) {
            const slot = offset + day - 1;
            const col = slot % 7;
            const rowN = Math.floor(slot / 7);
            const cx = x0 + col * colW + colW / 2;
            const cy = y + rowN * rowH + rowH / 2;
            const weekend = col === 0 || col === 6;
            const isToday = sameDay(new Date(today.getFullYear(), today.getMonth(), day), today);

            if (isToday) {
                const dia = Math.round(Math.min(colW, rowH) * 0.95);
                const badge = new TodayBadge(dia, day, ls, this._cardMode, this._accent);
                this._add(badge.actor, cx - dia / 2, cy - dia / 2);
            } else {
                const dl = new St.Label({
                    text: `${day}`,
                    style: fontStyle(FONT.display, ls, weekend ? 0.45 : 1, this._fg),
                });
                this._add(dl, cx - ls * 0.32, cy - ls * 0.62);
                if (hasEvent(day)) {
                    this._add(new St.Widget({
                        width: 4, height: 4,
                        style: `background-color: rgba(${this._fg},0.85); border-radius: 2px;`,
                    }), cx - 2, cy + ls * 0.55);
                }
            }
        }
    }

    _renderAgenda(originX, areaW, ls, today) {
        const m = Math.round(this._h * 0.09);
        const list = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: areaW - 2 * m,
            style: `spacing: ${Math.round(this._h * 0.022)}px;`,
        });
        this._add(list, originX + m, m);

        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const weekEnd = new Date(start);
        weekEnd.setDate(weekEnd.getDate() + (7 - start.getDay()));
        const end = new Date(start);
        end.setDate(end.getDate() + 30);

        const events = this._ctx.calendar.getEvents(now, end);
        if (!events.length) {
            const l = new St.Label({
                text: this._ctx.calendar.available ? 'No upcoming events' : 'No calendar connected',
                style: fontStyle(FONT.display, ls, 0.45, this._fg),
            });
            list.add_child(l);
            return;
        }

        const buckets = {today: [], week: [], later: []};
        for (const ev of events.slice(0, 10)) {
            if (sameDay(ev.date, now))
                buckets.today.push(ev);
            else if (ev.date < weekEnd)
                buckets.week.push(ev);
            else
                buckets.later.push(ev);
        }

        const section = (title, evs, fmt) => {
            if (!evs.length)
                return;
            const hl = new St.Label({
                text: title,
                style: fontStyle(FONT.display, ls, 0.55, this._fg) + ' padding-top: 4px;',
            });
            list.add_child(hl);
            for (const ev of evs)
                list.add_child(this._eventCard(ev, fmt(ev), ls));
        };

        section('Events today', buckets.today, ev => formatEventTime(ev));
        section('This week', buckets.week,
            ev => ev.date.toLocaleDateString(undefined, {weekday: 'short', day: 'numeric'}));
        section('Upcoming', buckets.later,
            ev => ev.date.toLocaleDateString(undefined, {month: 'short', day: 'numeric'}));
    }

    _eventCard(ev, timeText, ls) {
        const rowH = Math.round(ls * 2.3);
        const card = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            x_expand: true, height: rowH,
            style: `background-color: rgba(255,255,255,0.10); border-radius: ${Math.round(ls * 0.55)}px;`,
        });
        const inner = new St.BoxLayout({
            x_expand: true,
            style: `padding: 0 ${Math.round(ls * 0.55)}px; spacing: ${Math.round(ls * 0.45)}px;`,
        });
        inner.add_child(new St.Widget({
            width: 3, height: Math.round(rowH * 0.55),
            y_align: Clutter.ActorAlign.CENTER,
            style: `background-color: ${ev.allDay ? '#FF9500' : '#4B9EFF'}; border-radius: 2px;`,
        }));
        const title = new St.Label({
            text: ev.summary || '(untitled)', x_expand: true,
            style: fontStyle(FONT.display, Math.round(ls * 0.92), 1, this._fg),
        });
        title.y_align = Clutter.ActorAlign.CENTER;
        title.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        inner.add_child(title);
        const time = new St.Label({
            text: timeText,
            style: fontStyle(FONT.display, Math.round(ls * 0.78), 0.6, this._fg),
        });
        time.y_align = Clutter.ActorAlign.CENTER;
        inner.add_child(time);
        card.add_child(inner);
        return card;
    }

    destroy() {
        this._unsub?.();
        if (this._midnight)
            GLib.source_remove(this._midnight);
        this._midnight = 0;
        this._root.destroy();
    }
}
