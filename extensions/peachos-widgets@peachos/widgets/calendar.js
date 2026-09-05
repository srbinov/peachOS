// Calendar widget, matched to the KDE liquidglass repo.
//
//  'month'  -- accent month header, S M T W T F S, a 6x7 grid with weekend
//   days dimmed and today drawn as a filled circle with the number punched out
//   (transparent, so the glass shows through).
//  'agenda' -- wide: the same grid on the right, an events list on the left
//   with "Events today / This week / Upcoming" sections and colour-pilled cards.
//
// Events from lib/providers/calendar.js. Font: SF Pro Display Regular.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {formatEventTime} from '../lib/providers/calendar.js';

const {cairo: Cairo} = imports;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// A filled circle with the day number punched out via DEST_OUT compositing.
class TodayBadge {
    constructor(diameter, dayNumber, fontPx) {
        this.actor = new St.DrawingArea({width: diameter, height: diameter});
        this._d = diameter;
        this._day = dayNumber;
        this._fs = fontPx;
        this.actor.connect('repaint', a => this._draw(a));
    }

    _draw(area) {
        const [w, h] = area.get_surface_size();
        const cr = area.get_context();
        try {
            const r = Math.min(w, h) / 2;
            cr.setSourceRGBA(1, 1, 1, 1);
            cr.arc(w / 2, h / 2, r, 0, 2 * Math.PI);
            cr.fill();

            cr.selectFontFace('SF Pro Display', Cairo.FontSlant.NORMAL, Cairo.FontWeight.NORMAL);
            cr.setFontSize(this._fs);
            const txt = `${this._day}`;
            const ext = cr.textExtents(txt);
            cr.setOperator(Cairo.Operator.DEST_OUT);
            cr.moveTo(w / 2 - ext.width / 2 - ext.xBearing, h / 2 - ext.height / 2 - ext.yBearing);
            cr.showText(txt);
            cr.setOperator(Cairo.Operator.OVER);
        } finally {
            cr.$dispose();
        }
    }
}

export class CalendarWidget {
    constructor(parent, ctx, size, mode) {
        this._ctx = ctx;
        this._mode = mode;
        this._w = size.w;
        this._h = size.h;

        this._root = new Clutter.Actor({width: size.w, height: size.h});
        parent.add_child(this._root);

        this._unsub = ctx.calendar.subscribe(() => this._render());
        this._midnight = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 1800, () => {
            this._render();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _render() {
        this._root.destroy_all_children();
        const today = new Date();
        const ls = Math.max(10, Math.round(this._h * 0.058));

        const gridW = this._mode === 'agenda' ? this._h : this._w;
        const gridX = this._mode === 'agenda' ? this._w - gridW : 0;
        this._renderGrid(gridX, gridW, ls, today);

        if (this._mode === 'agenda')
            this._renderAgenda(0, this._w - gridW, ls, today);
    }

    _renderGrid(originX, areaW, ls, today) {
        const pad = Math.round(this._h * 0.09);
        const topPad = Math.round(this._h * 0.14);
        const x0 = originX + pad;
        const innerW = areaW - 2 * pad;
        let y = topPad;

        // Month header, aligned to the centre of the first column.
        const colW = innerW / 7;
        const header = new St.Label({
            text: MONTHS[today.getMonth()].toUpperCase(),
            style_class: 'peachos-cal-month',
            style: `font-size: ${ls}px;`,
        });
        // Left-aligned to roughly the first weekday column's letter (matches KDE).
        header.set_position(Math.round(x0 + colW / 2 - ls * 0.3), Math.round(y));
        this._root.add_child(header);
        y += Math.round(ls * 1.5);

        // Weekday row
        for (let c = 0; c < 7; c++) {
            const weekend = c === 0 || c === 6;
            const wl = new St.Label({
                text: WEEKDAYS[c],
                style_class: 'peachos-cal-weekday',
                style: `font-size: ${ls}px; color: rgba(255,255,255,${weekend ? 0.45 : 0.75});`,
            });
            wl.set_position(Math.round(x0 + c * colW + colW / 2 - ls * 0.3), Math.round(y));
            this._root.add_child(wl);
        }
        y += Math.round(ls * 1.5);

        // Day grid
        const gridH = this._h - pad - y;
        const rowH = gridH / 6;
        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        const offset = first.getDay(); // Sunday-first
        const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();

        // one events fetch for the whole month
        const monthEvents = this._ctx.calendar.getEvents(
            new Date(today.getFullYear(), today.getMonth(), 1),
            new Date(today.getFullYear(), today.getMonth() + 1, 1));
        const hasEvent = day => monthEvents.some(ev =>
            ev.date < new Date(today.getFullYear(), today.getMonth(), day + 1) &&
            ev.end > new Date(today.getFullYear(), today.getMonth(), day));

        for (let day = 1; day <= daysInMonth; day++) {
            const slot = offset + day - 1;
            const col = slot % 7;
            const row = Math.floor(slot / 7);
            const cx = x0 + col * colW + colW / 2;
            const cy = y + row * rowH + rowH / 2;
            const weekend = col === 0 || col === 6;
            const isToday = sameDay(new Date(today.getFullYear(), today.getMonth(), day), today);

            if (isToday) {
                const dia = Math.round(Math.min(colW, rowH) * 1.05);
                const badge = new TodayBadge(dia, day, ls);
                badge.actor.set_position(Math.round(cx - dia / 2), Math.round(cy - dia / 2));
                this._root.add_child(badge.actor);
            } else {
                const dl = new St.Label({
                    text: `${day}`,
                    style_class: 'peachos-cal-day',
                    style: `font-size: ${ls}px; color: rgba(255,255,255,${weekend ? 0.45 : 1});`,
                });
                dl.set_position(Math.round(cx - ls * 0.32), Math.round(cy - ls * 0.62));
                this._root.add_child(dl);
            }

            if (hasEvent(day) && !isToday) {
                const dot = new St.Widget({
                    width: 4, height: 4,
                    style: 'background-color: rgba(255,255,255,0.9); border-radius: 2px;',
                });
                dot.set_position(Math.round(cx - 2), Math.round(cy + ls * 0.5));
                this._root.add_child(dot);
            }
        }
    }

    _renderAgenda(originX, areaW, ls, today) {
        const m = Math.round(this._h * 0.09);
        const list = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: areaW - 2 * m,
            style: `spacing: ${Math.round(this._h * 0.02)}px;`,
        });
        list.set_position(originX + m, m);
        this._root.add_child(list);

        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const weekEnd = new Date(start);
        weekEnd.setDate(weekEnd.getDate() + (7 - start.getDay()));
        const end = new Date(start);
        end.setDate(end.getDate() + 30);

        const events = this._ctx.calendar.getEvents(now, end);
        if (!events.length) {
            list.add_child(new St.Label({
                text: this._ctx.calendar.available ? 'No upcoming events' : 'No calendar connected',
                style_class: 'peachos-cal-empty',
                style: `font-size: ${ls}px;`,
            }));
            return;
        }

        const buckets = {today: [], week: [], later: []};
        for (const ev of events.slice(0, 12)) {
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
            list.add_child(new St.Label({
                text: title,
                style_class: 'peachos-cal-section',
                style: `font-size: ${ls}px;`,
            }));
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
        const rowH = Math.round(ls * 2.4);
        const card = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            style_class: 'peachos-cal-card',
            style: `border-radius: ${Math.round(ls * 0.7)}px;`,
            x_expand: true,
            height: rowH,
        });

        const inner = new St.BoxLayout({x_expand: true, style: `padding: 0 ${Math.round(ls * 0.5)}px; spacing: ${Math.round(ls * 0.4)}px;`});
        const pill = new St.Widget({
            width: 3, height: Math.round(rowH * 0.55),
            y_align: Clutter.ActorAlign.CENTER,
            style: `background-color: ${this._pillColor(ev)}; border-radius: 2px;`,
        });
        inner.add_child(pill);
        const titleL = new St.Label({
            text: ev.summary || '(untitled)',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-cal-card-title',
            style: `font-size: ${Math.round(ls * 0.92)}px;`,
        });
        titleL.clutter_text.ellipsize = 3; // PANGO_ELLIPSIZE_END
        inner.add_child(titleL);
        inner.add_child(new St.Label({
            text: timeText,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'peachos-cal-card-time',
            style: `font-size: ${Math.round(ls * 0.78)}px;`,
        }));
        card.add_child(inner);
        return card;
    }

    _pillColor(ev) {
        return ev.allDay ? '#FF9500' : '#4B9EFF';
    }

    destroy() {
        this._unsub?.();
        if (this._midnight)
            GLib.source_remove(this._midnight);
        this._midnight = 0;
        this._root.destroy();
    }
}
