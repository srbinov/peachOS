// Photos widget -- a random picture from your iCloud Photo Library, rotated
// through the day. The image fills the squircle (painted by the glass card,
// same as the News "story"); a small date sits over the base gradient.
//
// Sign-in + the local photo cache: lib/providers/icloudPhotos.js (backed by the
// peachos-icloud-photos Python helper). When there's nothing cached yet the
// widget shows a short "set up in Settings" note instead.
//
//   'square' / 'grid' -- one photo at the footprint's size.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {FONT, fontStyle} from '../lib/fonts.js';

// Open peachOS Settings on the Internet Accounts page (where the iCloud sign-in
// lives). Same subprocess spawn edsCalendar.openAccountSettings uses.
function openICloudSettings() {
    for (const argv of [
        ['peachos-settings', 'internetaccounts'],
        ['gnome-control-center', 'online-accounts'],
    ]) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
            return;
        } catch (e) {
            // try the next
        }
    }
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];

// "June 14, 2019" -> with a "N years ago today" tail when it's this calendar day
function prettyDate(iso) {
    if (!iso)
        return '';
    const [y, m, d] = iso.split('-').map(n => parseInt(n, 10));
    if (!y || !m || !d)
        return '';
    let s = `${MONTHS[m - 1]} ${d}, ${y}`;
    const now = new Date();
    if (now.getMonth() + 1 === m && now.getDate() === d) {
        const yrs = now.getFullYear() - y;
        if (yrs === 1)
            s = 'One year ago today';
        else if (yrs > 1)
            s = `${yrs} years ago today`;
    }
    return s;
}

export class PhotosWidget {
    constructor(parent, ctx, size, variant) {
        this._ctx = ctx;
        this._variant = variant;
        this._w = size.w;
        this._h = size.h;
        this._setImage = size.setImage;

        this._root = new Clutter.Actor({
            width: size.w, height: size.h, clip_to_allocation: true,
        });
        parent.add_child(this._root);

        this._unsub = ctx.icloudPhotos?.subscribe(() => this._render());
    }

    _render() {
        if (this._rendering)
            return;
        this._rendering = true;
        try {
            this._root.destroy_all_children();

            const cur = this._ctx.icloudPhotos?.get();
            const st = this._ctx.icloudPhotos?.status ?? {};
            const fs = Math.max(10, Math.round(this._h * 0.075));

            if (cur && GLib.file_test(cur.path, GLib.FileTest.EXISTS)) {
                this._setImage?.(cur.path);
                const date = prettyDate(cur.date);
                if (date) {
                    const m = Math.round(this._h * 0.09);
                    const lbl = new St.Label({
                        text: date,
                        style: fontStyle(FONT.display, fs, 0.95, '255,255,255')
                            + ' font-weight: 600;',
                    });
                    lbl.set_position(m, Math.round(this._h - m - fs * 1.3));
                    this._root.add_child(lbl);
                }
                return;
            }

            // nothing to show -- the "set it up" placeholder
            this._setImage?.(null);
            this._renderPlaceholder(st);
        } finally {
            this._rendering = false;
        }
    }

    _renderPlaceholder(st) {
        const w = this._w;
        const h = this._h;
        const compact = h < 210;
        const pad = Math.round(Math.min(w, h) * 0.09);
        const fg = '255,255,255'; // photos card is always a dark image card
        const titlePx = Math.max(13, Math.round(h * (compact ? 0.11 : 0.085)));
        const subPx = Math.round(titlePx * 0.72);

        const icoPath = n =>
            GLib.build_filenamev([this._ctx.path, 'icons', 'app', n]);

        const col = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            width: w, height: h,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            style: `spacing: ${Math.round(titlePx * (compact ? 0.5 : 0.75))}px; `
                + `padding: ${pad}px;`,
        });

        // Apple Photos icon
        col.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(icoPath('icloud-photos.svg')),
            icon_size: Math.round(Math.min(w, h) * (compact ? 0.34 : 0.26)),
            x_align: Clutter.ActorAlign.CENTER,
        }));

        // Apple logo + "iCloud Photos" lockup
        const titleRow = new St.BoxLayout({
            x_align: Clutter.ActorAlign.CENTER,
            style: `spacing: ${Math.round(titlePx * 0.32)}px;`,
        });
        titleRow.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(icoPath('apple-logo-white.svg')),
            icon_size: Math.round(titlePx * 1.15),
            y_align: Clutter.ActorAlign.CENTER,
        }));
        titleRow.add_child(new St.Label({
            text: 'iCloud Photos',
            style: fontStyle(FONT.rounded, titlePx, 1, fg) + ' font-weight: 600;',
            y_align: Clutter.ActorAlign.CENTER,
        }));
        col.add_child(titleRow);

        if (!compact) {
            const sub = new St.Label({
                text: !st.connected
                    ? 'Connect your account to\nshow photos from your library'
                    : st.reauthNeeded
                        ? 'Your session expired —\nsign in again to keep syncing'
                        : 'Fetching your photos…',
                style: fontStyle(FONT.display, subPx, 0.6, fg),
                x_align: Clutter.ActorAlign.CENTER,
            });
            sub.clutter_text.line_wrap = true;
            sub.clutter_text.justify = true;
            col.add_child(sub);
        }

        // "Open Settings" pill -- visual affordance; the whole card is the button
        const fetching = st.connected && !st.reauthNeeded;
        if (!fetching) {
            const pill = new St.BoxLayout({
                x_align: Clutter.ActorAlign.CENTER,
                style: 'background-color: rgba(255,255,255,0.16); '
                    + `border-radius: 999px; padding: ${Math.round(subPx * 0.55)}px `
                    + `${Math.round(subPx * 1.1)}px;`,
            });
            pill.add_child(new St.Label({
                text: st.reauthNeeded ? 'Sign In' : 'Open Settings',
                style: fontStyle(FONT.rounded, subPx, 1, fg) + ' font-weight: 600;',
            }));
            col.add_child(pill);
        }

        const card = new St.Button({
            width: w, height: h,
            reactive: true, can_focus: true,
            style_class: 'peachos-photos-connect',
        });
        card.set_child(col);
        card.connect('clicked', () => openICloudSettings());
        this._root.add_child(card);
    }

    destroy() {
        this._unsub?.();
        this._setImage?.(null);
        this._root.destroy();
    }
}
