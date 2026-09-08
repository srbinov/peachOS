// News widget -- curated RSS headlines per topic, matched to the Apple News
// widget.
//
//   'square' -- one story, full-bleed image with the headline over a gradient.
//   'row'    -- topic header + two stories with thumbnails.
//   'grid'   -- topic header + four stories (2x2 footprint).
//
// Topic is per-widget, changed by the pencil in edit mode. Feeds +
// image cache: lib/providers/news.js. Font: SF Pro Display.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {topicName} from '../lib/providers/news.js';
import {FONT, fontStyle, Pango} from '../lib/fonts.js';

const ACCENT = {glass: '10,132,255', dark: '10,132,255', light: '0,96,223'};

export class NewsWidget {
    constructor(parent, ctx, size, variant) {
        this._ctx = ctx;
        this._variant = variant;                    // 'square' | 'row' | 'grid'
        this._topic = size.topic || 'top';
        this._cardMode = size.mode || 'glass';
        this._w = size.w;
        this._h = size.h;
        this._fg = size.fg || '255,255,255';
        this._accent = ACCENT[this._cardMode] || ACCENT.glass;

        this._root = new Clutter.Actor({
            width: size.w, height: size.h, clip_to_allocation: true,
        });
        parent.add_child(this._root);

        this._sub();
        this._midnight = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 1800, () => {
            this._render();
            return GLib.SOURCE_CONTINUE;
        });
    }

    setTopic(id) {
        if (id === this._topic)
            return;
        this._topic = id;
        this._unsub?.();
        this._sub();
    }

    _sub() {
        this._articles = this._ctx.news.get(this._topic);
        this._unsub = this._ctx.news.subscribe(this._topic, articles => {
            this._articles = articles;
            this._render();
        });
    }

    _render() {
        if (this._rendering)
            return;
        this._rendering = true;
        try {
            this._root.destroy_all_children();
            const arts = this._articles || [];
            if (this._variant === 'square')
                this._renderSquare(arts[0]);
            else
                this._renderList(arts, this._variant === 'grid' ? 4 : 2);
        } finally {
            this._rendering = false;
        }
    }

    _add(actor, x, y) {
        actor.set_position(Math.round(x), Math.round(y));
        this._root.add_child(actor);
        return actor;
    }

    _thumb(path, d, radius) {
        const w = new St.Widget({width: d, height: d});
        if (path) {
            w.style = `background-image: url("file://${path}"); background-size: cover; `
                + `border-radius: ${radius}px;`;
        } else {
            w.style = `background-color: rgba(${this._accent},0.25); border-radius: ${radius}px;`;
        }
        return w;
    }

    // ---- square -----------------------------------------------------

    _renderSquare(a) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * 0.08);

        const img = new St.Widget({width: w, height: h});
        img.style = a?.imagePath
            ? `background-image: url("file://${a.imagePath}"); background-size: cover;`
            : `background-color: rgba(${this._accent},0.35);`;
        this._add(img, 0, 0);

        const grad = new St.Widget({width: w, height: Math.round(h * 0.66)});
        grad.style = 'background-gradient-direction: vertical; '
            + 'background-gradient-start: rgba(0,0,0,0); '
            + 'background-gradient-end: rgba(0,0,0,0.9);';
        this._add(grad, 0, h - grad.height);

        if (!a) {
            this._add(new St.Label({
                text: `${topicName(this._topic)} — loading…`,
                style: fontStyle(FONT.display, Math.round(h * 0.07), 0.9, '255,255,255'),
            }), m, h - m - Math.round(h * 0.09));
            return;
        }

        const fs = Math.max(11, Math.round(h * 0.085));
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: w - 2 * m,
            style: `spacing: ${Math.round(fs * 0.2)}px;`,
        });
        box.add_child(new St.Label({
            text: a.source,
            style: fontStyle(FONT.display, Math.round(fs * 0.8), 0.8, '255,255,255'),
        }));
        const title = new St.Label({
            text: a.title,
            height: Math.round(fs * 1.25 * 3),
            style: fontStyle(FONT.display, fs, 1, '255,255,255') + ' font-weight: 700;',
        });
        title.clutter_text.line_wrap = true;
        title.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        box.add_child(title);

        const bh = Math.round(fs * 0.8 + fs * 1.25 * 3 + fs * 0.4);
        this._add(box, m, h - m - bh);
    }

    // ---- row / grid ----------------------------------------------

    _renderList(arts, n) {
        const w = this._w;
        const h = this._h;
        const m = Math.round(h * (this._variant === 'grid' ? 0.055 : 0.1));
        const fg = this._fg;

        // header
        const headFs = Math.max(12, Math.round(h * (this._variant === 'grid' ? 0.05 : 0.09)));
        const head = new St.BoxLayout({width: w - 2 * m});
        head.add_child(new St.Label({
            text: topicName(this._topic), x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style: fontStyle(FONT.display, headFs, 1, this._accent) + ' font-weight: 800;',
        }));
        const logo = new St.Label({
            text: 'N', y_align: Clutter.ActorAlign.CENTER,
            style: `font-family: "${FONT.display}"; font-size: ${Math.round(headFs * 0.95)}px; `
                + `font-weight: 800; color: rgba(${this._accent},1);`,
        });
        head.add_child(logo);
        this._add(head, m, m);

        const top = m + Math.round(headFs * 1.7);
        const rowH = (h - top - m) / n;
        const fs = Math.max(10, Math.round(rowH * (this._variant === 'grid' ? 0.24 : 0.2)));
        const lines = this._variant === 'grid' ? 3 : 2;

        for (let i = 0; i < n; i++) {
            const a = arts[i];
            const y = top + i * rowH;
            if (i > 0) {
                this._add(new St.Widget({
                    width: w - 2 * m, height: 1,
                    style: `background-color: rgba(${fg},0.10);`,
                }), m, y);
            }
            if (!a) {
                this._add(new St.Label({
                    text: 'Loading…',
                    style: fontStyle(FONT.display, fs, 0.4, fg),
                }), m, y + rowH * 0.4);
                continue;
            }

            const d = Math.round(rowH * 0.74);
            const thumbX = w - m - d;
            this._add(this._thumb(a.imagePath, d, Math.round(d * 0.16)),
                thumbX, y + (rowH - d) / 2);

            const textBox = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                width: thumbX - m - Math.round(fs * 0.6),
                y_align: Clutter.ActorAlign.CENTER,
                style: `spacing: ${Math.round(fs * 0.18)}px;`,
            });
            textBox.add_child(new St.Label({
                text: a.source.toUpperCase(),
                style: fontStyle(FONT.display, Math.round(fs * 0.72), 0.45, fg)
                    + ' font-weight: 700;',
            }));
            const t = new St.Label({
                text: a.title,
                height: Math.round(fs * 1.25 * lines),
                style: fontStyle(FONT.display, fs, 1, fg) + ' font-weight: 600;',
            });
            t.clutter_text.line_wrap = true;
            t.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            textBox.add_child(t);
            this._add(textBox, m, y + rowH * 0.12);
        }
    }

    destroy() {
        this._unsub?.();
        if (this._midnight)
            GLib.source_remove(this._midnight);
        this._midnight = 0;
        this._root.destroy();
    }
}
