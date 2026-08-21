import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {GdmClock} from './gdmClock.js';

const WALLPAPER_URI = 'file:///usr/share/backgrounds/peachos/macOS_Sonoma_Dark.jpg';

// GDM's LoginDialog (gdm/loginDialog.js) has no clock widget at all -- the regular
// lock screen's clock only exists because UnlockDialog builds one, and GDM's own
// session mode entry swaps in LoginDialog as the "unlockDialog" class instead (see
// ui/sessionMode.js: 'gdm': {..., unlockDialog: LoginDialog}). That's also why
// Main.screenShield's 'lock-screen-shown' signal -- the same hook a normal lock-screen
// extension would use -- fires during GDM too: screenShield.js's _ensureUnlockDialog()
// is mode-agnostic, it just constructs whatever Main.sessionMode.unlockDialog points
// at. This class only acts when that turns out to be a GDM session -- the in-session
// lock screen is intentionally left alone entirely, since the WACK - Sonoma Lockscreen
// extension (session-modes: ["unlock-dialog"], never loaded during 'gdm') already
// handles it, and this exists purely to give GDM the matching clock WACK can't reach,
// plus a stripped-down chrome to match it.
//
// The wallpaper itself needs NO code here at all -- see provision/dconf/
// 01-peachos-gdm's [com/ubuntu/login-screen] section. screenShield.js's own
// _updateBackground() already reads those exact keys and applies them as an inline
// style directly on _lockDialogGroup, LoginDialog's real parent container. Every
// extension-side attempt at painting a background (a floating overlay actor on
// uiGroup, styling LoginDialog directly, even a manually-constructed
// Background.BackgroundManager) ended up invisible regardless of z-order, because
// _lockDialogGroup's own background -- driven by those same keys -- paints on top of
// all of it. org/gnome/desktop/background does NOT work for the greeter at all
// (layout.js's _updateBackgrounds() has `if (Main.sessionMode.isGreeter) return;`).
//
// LoginDialog implements its own vfunc_allocate() directly (no separate, swappable
// Clutter.LayoutManager the way UnlockDialog's mainBox has) -- GObject vfunc dispatch
// goes through the class's vtable, not per-instance JS property lookup, so
// monkeypatching vfunc_allocate on an already-constructed instance (the way
// _setTransitionProgress gets overridden elsewhere in this codebase) silently
// wouldn't take effect, and patching the whole LoginDialog.prototype would affect a
// core GDM class shell-wide for the rest of the greeter's life -- more blast radius
// than this needs. That's why the clock is an independent overlay on
// Main.layoutManager.uiGroup rather than participating in LoginDialog's own layout at
// all -- there's nothing there to go wrong.
export class LockScreenLayout {
    constructor() {
        this._signalId = null;
        this._gdmClock = null;
        this._panelWasVisible = null;
        this._originalRefreshBackground = null;

        if (!Main.screenShield)
            return;

        this._signalId = Main.screenShield.connect('lock-screen-shown',
            () => this._onLockScreenShown());

        if (Main.screenShield._dialog)
            this._onLockScreenShown();
    }

    _onLockScreenShown() {
        if (Main.sessionMode.currentMode !== 'gdm')
            return;

        this._injectBackground();
        this._injectGdmClock();
        this._hidePanel();
    }

    _injectBackground() {
        if (this._originalRefreshBackground)
            return;
        // Own property lookup finds nothing yet here -- this captures the real
        // prototype method, restored in destroy() so disabling this extension
        // doesn't leave Main.screenShield (a long-lived singleton, unlike the
        // per-lock-cycle dialog) permanently patched.
        this._originalRefreshBackground = Main.screenShield._refreshBackground;

        // Diagnostics on a previous run proved screenShield.js's own _refreshBackground()
        // WAS reading provision/dconf/01-peachos-gdm's [com/ubuntu/login-screen] keys
        // correctly and DID apply the right inline style to _lockDialogGroup -- yet the
        // screen still showed gdm-theme.gresource/Yaru's stock `#lockDialogGroup {
        // background-color: #222222; }` stylesheet rule instead. The only way a
        // stylesheet rule wins over an already-correctly-set inline style is if
        // something calls _refreshBackground() again afterward with a gsettings read
        // that comes back empty that time, which sets the group's style back to null
        // (screenShield.js: `lockDialogGroupStyle = inlineStyle.join('; ') || null`).
        // That's consistent with this greeter's dconf cache directory having a real,
        // confirmed permission problem (gdm:gdm-owned, but the greeter itself runs as a
        // separate dynamically-allocated gdm-greeter user) -- an intermittent read
        // failure on a *second* call would explain a style that's provably correct at
        // one moment but not at the next. Rather than chase that race, this replaces
        // _refreshBackground() outright with a version that can't read anything wrong,
        // so every future call -- however many times it fires, for whatever reason --
        // applies the same known-correct style instead of whatever gsettings returns.
        Main.screenShield._refreshBackground = () => {
            const group = Main.screenShield._lockDialogGroup;
            if (!group)
                return;
            group.set_style(
                `background-color: #1c1c1e; background-image: url("${WALLPAPER_URI}"); background-size: cover;`);
            Main.screenShield._dialog?.set_style('background-image: none; background-color: transparent;');
        };
        Main.screenShield._refreshBackground();
    }

    _injectGdmClock() {
        if (this._gdmClock)
            return;

        this._gdmClock = new GdmClock();
        Main.layoutManager.uiGroup.add_child(this._gdmClock);

        const reposition = () => this._repositionGdmClock();
        this._gdmClock.connect('notify::allocation', reposition);
        reposition();
    }

    _repositionGdmClock() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor || !this._gdmClock)
            return;

        const [, , width, height] = this._gdmClock.get_preferred_size();
        if (width === 0 && height === 0)
            return; // not style-resolved yet -- the notify::allocation retry will catch it

        this._gdmClock.set_position(
            Math.floor(monitor.x + (monitor.width - width) / 2),
            Math.floor(monitor.y + monitor.height / 3.0 - height - 24));
    }

    _hidePanel() {
        if (this._panelWasVisible !== null || !Main.panel)
            return;
        this._panelWasVisible = Main.panel.visible;
        Main.panel.hide();
    }

    destroy() {
        if (this._signalId) {
            Main.screenShield?.disconnect(this._signalId);
            this._signalId = null;
        }
        if (this._originalRefreshBackground && Main.screenShield) {
            Main.screenShield._refreshBackground = this._originalRefreshBackground;
            this._originalRefreshBackground = null;
        }
        if (this._panelWasVisible !== null) {
            Main.panel?.set({visible: this._panelWasVisible});
            this._panelWasVisible = null;
        }
        this._gdmClock?.destroy();
        this._gdmClock = null;
    }
}
