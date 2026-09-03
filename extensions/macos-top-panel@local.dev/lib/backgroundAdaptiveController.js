const TILE_ON_LIGHT_CLASS = 'macos-control-center-tile-on-light';
// Deliberately high -- only a genuinely white/very-light background (a browser showing a
// white page, Files on a white folder view, etc.) should flip the glass dark. Anything more
// sensitive would flip on ordinary mid-tone wallpapers too, which already read fine on the
// default light glass and don't need it. Exported so notificationBannerGlass.js's own
// adaptive sample (same idea, applied to notification banners) uses the exact same cutoff.
export const LIGHT_LUMINANCE_THRESHOLD = 0.78;

/**
 * Adaptive light/dark glass for the Control Center. Toggles a style class on every
 * registered tile so the shared glass recipe in stylesheet.css swaps from its default
 * white-tinted fill to a dark one when the surface behind it is light.
 *
 * Was `Shell.Screenshot.pick_color()` sampling the actual pixel behind the popup -- but
 * that path SIGSEGVs gnome-shell on the GPUs peachOS targets (nouveau: "Failed to create
 * 0x0 texture" -> signal 11 -> whole session lost). Now driven purely by the top bar's own
 * light/dark verdict (extension.js `_applyPanelForeground` -> `setForceDark`), which is
 * computed from the wallpaper file itself (peachos-menubar-blur), no GPU capture. The
 * "light window behind the popup" case is no longer detected -- acceptable, stability wins.
 */
export class BackgroundAdaptiveController {
    constructor(_getSamplePoint) {
        this._actors = new Set();
        this._forceDark = false;
    }

    /** Call once per glass tile actor right after creating it. */
    register(actor) {
        this._actors.add(actor);
        if (this._forceDark)
            actor.add_style_class_name(TILE_ON_LIGHT_CLASS);
    }

    /**
     * @param {boolean} forceDark  from the menu-bar wallpaper verdict (light wallpaper -> true)
     */
    setForceDark(forceDark) {
        forceDark = !!forceDark;
        if (forceDark === this._forceDark)
            return;
        this._forceDark = forceDark;
        this._apply();
    }

    /** Call when the menu opens -- re-asserts the current verdict on the tiles. */
    async sample() {
        this._apply();
    }

    _apply() {
        for (const actor of this._actors) {
            if (this._forceDark)
                actor.add_style_class_name(TILE_ON_LIGHT_CLASS);
            else
                actor.remove_style_class_name(TILE_ON_LIGHT_CLASS);
        }
    }

    /** Call the instant the menu starts closing -- back to the default look for next time. */
    reset() {
        for (const actor of this._actors)
            actor.remove_style_class_name(TILE_ON_LIGHT_CLASS);
    }

    destroy() {
        this.reset();
        this._actors.clear();
        this._forceDark = false;
    }
}
