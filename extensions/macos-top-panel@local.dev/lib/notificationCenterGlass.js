// lib/notificationCenterGlass.js
//
// The Notification Center's individual notification cards (.macos-notification-center
// .message) and their collapsed-stack peek copies (:second-in-stack / :lower-in-stack)
// get NO background from stylesheet.css -- the base `.message` is transparent, and the
// peek-card fill comes entirely from the *active shell theme* (MacTahoe-Dark /
// MacTahoe-Light). peachOS's dark-mode toggle only reliably flips
// org.gnome.desktop.interface color-scheme; the user-theme name lags behind it (only
// re-synced when Settings > Appearance runs), so in light mode the peek cards were
// still being painted #404040 by MacTahoe-Dark's `.message:second-in-stack` rule.
//
// Fix: own those rules ourselves, computed from color-scheme, in a supplementary
// !important stylesheet (re)loaded after stylesheet.css -- exactly the mechanism
// notificationBannerGlass.js already uses for .notification-banner. This makes the
// stack theme-independent and lets the peek cards recede cleanly (progressive
// translucency on top of GNOME's own 6px/10px peek offset).

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';

const INTERFACE_SCHEMA_ID = 'org.gnome.desktop.interface';

// [top card, 2nd in stack, 3rd+] fills, plus the hairline border, per mode.
// `fg`/`fgDim` are the card's text colours -- the shell theme's own .message-title /
// .message-body rules follow the *installed theme name*, which lags the color-scheme
// toggle, so a dark card kept getting dark text (dark-on-dark). Own them here too.
const PALETTE = {
    light: {
        card: 'rgba(255, 255, 255, 0.72)',
        card2: 'rgba(255, 255, 255, 0.55)',
        card3: 'rgba(255, 255, 255, 0.40)',
        hairline: 'rgba(255, 255, 255, 0.55)',
        shadow: 'rgba(0, 0, 0, 0.12)',
        fg: 'rgba(0, 0, 0, 0.9)',
        fgDim: 'rgba(0, 0, 0, 0.6)',
        chip: 'rgba(60, 60, 67, 0.25)',
    },
    dark: {
        card: 'rgba(44, 44, 48, 0.72)',
        card2: 'rgba(44, 44, 48, 0.55)',
        card3: 'rgba(44, 44, 48, 0.40)',
        hairline: 'rgba(255, 255, 255, 0.12)',
        shadow: 'rgba(0, 0, 0, 0.28)',
        fg: 'rgba(255, 255, 255, 0.95)',
        fgDim: 'rgba(255, 255, 255, 0.68)',
        chip: 'rgba(235, 235, 245, 0.20)',
    },
};

export class NotificationCenterGlass {
    constructor() {
        this._file = Gio.File.new_for_path(GLib.build_filenamev(
            [GLib.get_user_cache_dir(), 'macos-top-panel', 'nc-messages.css']));
        this._loaded = false;
        this._forceDark = false;

        this._interfaceSettings = new Gio.Settings({schema_id: INTERFACE_SCHEMA_ID});
        this._colorSchemeChangedId = this._interfaceSettings.connect(
            'changed::color-scheme', () => this._apply());

        this._apply();
    }

    /**
     * @param {'black'|'white'} foreground  the menu bar's chrome colour -- 'black'
     *   means the wallpaper behind the bar is light, so the panel glass goes dark
     *   and the cards should follow.
     */
    setPanelForeground(foreground) {
        const dark = foreground === 'black';
        if (dark === this._forceDark)
            return;
        this._forceDark = dark;
        this._apply();
    }

    _apply() {
        if (!this._interfaceSettings)
            return;
        const isDark = this._forceDark ||
            this._interfaceSettings.get_string('color-scheme') === 'prefer-dark';
        const p = isDark ? PALETTE.dark : PALETTE.light;

        const css = [
            '.macos-notification-center .message {',
            `    background-color: ${p.card} !important;`,
            '    border-radius: 14px !important;',
            `    color: ${p.fg} !important;`,
            '}',
            '.macos-notification-center .message:second-in-stack {',
            `    background-color: ${p.card2} !important;`,
            '}',
            '.macos-notification-center .message:lower-in-stack {',
            `    background-color: ${p.card3} !important;`,
            '}',
            // Text: title solid, body/time dimmed -- so a dark card never keeps
            // dark theme text.
            '.macos-notification-center .message .message-title,',
            '.macos-notification-center .message .message-content .message-title {',
            `    color: ${p.fg} !important;`,
            '}',
            '.macos-notification-center .message .message-body,',
            '.macos-notification-center .message .message-content .message-body,',
            '.macos-notification-center .message .event-time,',
            '.macos-notification-center .message .message-source-title {',
            `    color: ${p.fgDim} !important;`,
            '}',
            // The per-card ✕ overlay (lib/notificationCenter.js _decorateMessage).
            '.macos-notification-center .macos-nc-close {',
            `    color: ${p.fg} !important;`,
            `    background-color: ${p.chip} !important;`,
            '}',
            '',
        ].join('\n');

        try {
            const dir = this._file.get_parent();
            if (!dir.query_exists(null))
                dir.make_directory_with_parents(null);
            this._file.replace_contents(
                css, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        } catch (e) {
            logError(e, '[macos-top-panel] failed to write nc-messages stylesheet');
            return;
        }

        const theme = St.ThemeContext.get_for_stage(global.stage).get_theme();
        if (!theme)
            return;
        try {
            if (this._loaded)
                theme.unload_stylesheet(this._file);
            theme.load_stylesheet(this._file);
            this._loaded = true;
        } catch (e) {
            logError(e, '[macos-top-panel] failed to (re)load nc-messages stylesheet');
        }
    }

    destroy() {
        if (this._colorSchemeChangedId) {
            this._interfaceSettings.disconnect(this._colorSchemeChangedId);
            this._colorSchemeChangedId = 0;
        }
        if (this._loaded) {
            try {
                St.ThemeContext.get_for_stage(global.stage).get_theme()
                    ?.unload_stylesheet(this._file);
            } catch (e) {
                // theme already gone
            }
            this._loaded = false;
        }
        this._interfaceSettings = null;
    }
}
