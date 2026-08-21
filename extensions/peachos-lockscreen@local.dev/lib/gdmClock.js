// Adapted from wackClock.js (WACK - Sonoma Lockscreen, GPLv3,
// https://github.com/rinzler69-wastaken/wack-sonoma-lockscreen) so the GDM login
// screen's clock is pixel-for-pixel identical to the one WACK already draws on the
// in-session lock screen -- same widget, same style classes, same values. WACK itself
// only runs in session-mode 'unlock-dialog' (see its metadata.json), so it never loads
// during 'gdm' at all; this is a self-contained copy for that gap, not a dependency on
// WACK being installed.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GnomeDesktop from 'gi://GnomeDesktop';
import GObject from 'gi://GObject';
import St from 'gi://St';

export const GdmClock = GObject.registerClass(
class GdmClock extends St.BoxLayout {
    _init() {
        super._init({
            style_class: 'unlock-dialog-clock',
            vertical: true,
        });

        this._dateOutput = new St.Label({
            style_class: 'wack-date',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._time = new St.Label({
            style_class: 'unlock-dialog-clock-time wack-time',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._dateOutput);
        this.add_child(this._time);

        this._wallClock = new GnomeDesktop.WallClock({time_only: true});
        this._wallClock.connect('notify::clock', () => this._updateTime());

        this._dateTimeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 60, () => {
            this._updateDate();
            return GLib.SOURCE_CONTINUE;
        });

        this._updateTime();
        this._updateDate();

        this.connect('destroy', () => this._onDestroy());
    }

    _updateTime() {
        this._time.text = this._wallClock.clock.trim();
    }

    _updateDate() {
        let locale = (GLib.getenv('LC_TIME') || GLib.getenv('LANG') || '').split('.')[0].replace('_', '-');
        if (!locale || locale === 'C' || locale === 'POSIX')
            locale = 'en-US';
        try {
            this._dateOutput.text = new Date().toLocaleDateString(locale, {weekday: 'long', month: 'long', day: 'numeric'});
        } catch {
            this._dateOutput.text = new Date().toLocaleDateString(undefined, {weekday: 'long', month: 'long', day: 'numeric'});
        }
    }

    _onDestroy() {
        this._wallClock.run_dispose();
        if (this._dateTimeoutId) {
            GLib.source_remove(this._dateTimeoutId);
            this._dateTimeoutId = null;
        }
    }
});
