import Meta from 'gi://Meta';

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
 * Pixel-sampling the surface behind the popup is off the table -- `Shell.Screenshot.
 * pick_color()` SIGSEGVs gnome-shell on the GPUs peachOS targets (nouveau: "Failed to
 * create 0x0 texture" -> signal 11 -> whole session lost). So the verdict is inferred,
 * no GPU capture:
 *
 *   - desktop behind the popup  -> the menu bar's own wallpaper light/dark verdict
 *     (extension.js `_applyPanelForeground` -> `setForceDark`)
 *   - ANY normal window behind the popup -> dark glass. We can't tell the window's
 *     colour, so we don't try: the dark tile recipe (ADAPTIVE_RECIPE) is opaque + bordered
 *     enough to read on a light window (the case that was broken) AND on a dark one
 *     (better than translucent light glass, which washes out over either).
 */
export class BackgroundAdaptiveController {
    /** @param {() => ({x,y,width,height}|null)} getRegion  where the popup will render */
    constructor(getRegion) {
        this._getRegion = getRegion;
        this._actors = new Set();
        this._wallpaperForceDark = false;
        this._effective = false;
    }

    /** Call once per glass tile actor right after creating it. */
    register(actor) {
        this._actors.add(actor);
        if (this._effective)
            actor.add_style_class_name(TILE_ON_LIGHT_CLASS);
    }

    /**
     * @param {boolean} forceDark  the menu-bar wallpaper verdict (light wallpaper -> true)
     */
    setForceDark(forceDark) {
        forceDark = !!forceDark;
        if (forceDark === this._wallpaperForceDark)
            return;
        this._wallpaperForceDark = forceDark;
        this._effective = this._compute();
        this._apply();
    }

    /** Call when the menu opens -- recomputes against whatever is behind it now. */
    async sample() {
        this._effective = this._compute();
        this._apply();
    }

    _compute() {
        let region = null;
        try {
            region = this._getRegion?.();
        } catch (e) {
            region = null;
        }
        if (region && this._windowBehind(region))
            return true;
        return this._wallpaperForceDark;
    }

    /** A normal, visible window on the active workspace overlapping `region`. */
    _windowBehind(region) {
        const ws = global.workspace_manager?.get_active_workspace();
        if (!ws)
            return false;
        const rx2 = region.x + region.width;
        const ry2 = region.y + region.height;
        let found = false;
        // get_window_actors() is bottom-to-top; a later overlap is a higher window, but
        // for a boolean "is anything there" the first hit is enough.
        for (const actor of global.get_window_actors()) {
            const w = actor.meta_window;
            if (!w || w.minimized || w.is_override_redirect())
                continue;
            if (!w.located_on_workspace(ws))
                continue;
            const t = w.get_window_type();
            if (t !== Meta.WindowType.NORMAL && t !== Meta.WindowType.DIALOG &&
                t !== Meta.WindowType.MODAL_DIALOG)
                continue;
            const r = w.get_frame_rect();
            if (r.x < rx2 && r.x + r.width > region.x &&
                r.y < ry2 && r.y + r.height > region.y) {
                found = true;
                break;
            }
        }
        return found;
    }

    _apply() {
        for (const actor of this._actors) {
            if (this._effective)
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
        this._wallpaperForceDark = false;
        this._effective = false;
    }
}
