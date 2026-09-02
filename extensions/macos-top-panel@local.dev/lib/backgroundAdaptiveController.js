import Gio from 'gi://Gio';
import Shell from 'gi://Shell';

import {relativeLuminance} from './colorUtil.js';

Gio._promisify(Shell.Screenshot.prototype, 'pick_color');

const TILE_ON_LIGHT_CLASS = 'macos-control-center-tile-on-light';
// Deliberately high -- only a genuinely white/very-light background (a browser showing a
// white page, Files on a white folder view, etc.) should flip the glass dark. Anything more
// sensitive would flip on ordinary mid-tone wallpapers too, which already read fine on the
// default light glass and don't need it. Exported so notificationBannerGlass.js's own
// adaptive sample (same idea, applied to notification banners) uses the exact same cutoff.
export const LIGHT_LUMINANCE_THRESHOLD = 0.78;

/**
 * Adaptive light/dark glass for the Control Center. Samples the actual screen pixel behind
 * the popup with Shell.Screenshot.pick_color() -- the same proven, crash-free mechanism
 * windowColorBlend.js already uses for the top bar's window-touch color -- and toggles a
 * style class on every registered tile so the shared glass recipe in stylesheet.css swaps
 * from its default white-tinted fill to a dark one when that would otherwise go
 * white-on-white over something bright.
 *
 * One-shot per menu-open (see sample()'s caller in controlCenterIndicator.js), not a live
 * continuous sampler: simpler, and "is this bright" only needs checking once when the popup
 * appears, not on every frame.
 */
export class BackgroundAdaptiveController {
    constructor(getSamplePoint) {
        this._getSamplePoint = getSamplePoint;
        this._actors = new Set();
        this._sampledLight = false;
        // Driven by the top bar's own light/dark verdict (extension.js's
        // _applyPanelForeground -> ControlCenterIndicator.setForeground). When the
        // wallpaper behind the menu bar is light enough that the bar flips its chrome to
        // black, this popup needs the same dark glass -- and that verdict is computed from
        // the wallpaper file itself (peachos-menubar-blur), so it works on the GPUs where
        // pick_color() below doesn't.
        this._forceDark = false;
    }

    /** Call once per glass tile actor right after creating it. */
    register(actor) {
        this._actors.add(actor);
    }

    /**
     * Force the dark treatment regardless of what pick_color() finds (or whether it works
     * at all). Safe to call any time; re-applies immediately if the menu is open.
     * @param {boolean} forceDark
     */
    setForceDark(forceDark) {
        forceDark = !!forceDark;
        if (forceDark === this._forceDark)
            return;
        this._forceDark = forceDark;
        this._apply();
    }

    /** Call when the menu opens. */
    async sample() {
        this._sampledLight = false;
        // Reflect _forceDark straight away so a light wallpaper doesn't get a
        // default-glass flash while the async pick_color() below is in flight.
        this._apply();

        const point = this._getSamplePoint();
        if (!point)
            return;
        try {
            const screenshot = new Shell.Screenshot();
            const [color] = await screenshot.pick_color(point.x, point.y);
            if (color) {
                this._sampledLight = relativeLuminance(
                    color.red, color.green, color.blue) >= LIGHT_LUMINANCE_THRESHOLD;
            }
        } catch (e) {
            // pick_color() is unreliable on some GPUs peachOS targets -- fall back to
            // _forceDark (the wallpaper verdict) alone, nothing worth logging.
        }

        this._apply();
    }

    _apply() {
        const dark = this._forceDark || this._sampledLight;
        for (const actor of this._actors) {
            if (dark)
                actor.add_style_class_name(TILE_ON_LIGHT_CLASS);
            else
                actor.remove_style_class_name(TILE_ON_LIGHT_CLASS);
        }
    }

    /** Call the instant the menu starts closing -- back to the default look for next time. */
    reset() {
        this._sampledLight = false;
        for (const actor of this._actors)
            actor.remove_style_class_name(TILE_ON_LIGHT_CLASS);
    }

    destroy() {
        this.reset();
        this._actors.clear();
        this._forceDark = false;
    }
}
