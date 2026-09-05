// LiquidGlass: a St.Widget that paints the wallpaper crop behind it, runs the
// ported refraction shader (shaders/liquidglass.glsl) over it, and exposes a
// `content` child positioned over the visible glass for the widget to fill.
//
// The actor is (innerW + 2*MARGIN) x (innerH + 2*MARGIN). The visible glass
// squircle is the centred innerW x innerH region; the MARGIN border is extra
// wallpaper the edge refraction samples into, masked to alpha 0 by the shader.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {buildWallpaperTexture} from './wallpaperTexture.js';

export const MARGIN = 40;

// KDE LiquidGlass.qml defaults, tuned for widget-pixel coordinates.
//
// The KDE numbers make a strong lens: a fat edge band, big displacement and a
// visible rainbow fringe. peachOS wants the calmer "frosted pane with a bright
// rim" look, so the refraction is dialled right down (a gentle bend in a thin
// edge band) and the chromatic dispersion is off. The squircle silhouette and
// the edge/corner specular -- the parts that read as "glass" -- are unchanged.
const DEFAULTS = {
    radius: 28,
    roundness: 7.0,
    refractThickness: 16,
    refractIOR: 1.7,
    refractScale: 14,
    chromaStrength: 0.0,
    tint: [1.0, 1.0, 1.0, 0.12],       // r,g,b,a
    tintBottom: [0.0, 0.0, 0.0, 0.0],
    specStrength: 0.70,
    overlay: [0.0, 0.0, 0.0, 0.0],
    solid: false,
    solidColor: [0.10, 0.106, 0.118, 1.0],
};

const f = v => parseFloat(v - 1e-6);

export const LiquidGlassEffect = GObject.registerClass(
class LiquidGlassEffect extends Clutter.ShaderEffect {
    constructor() {
        super({});
        // Resolve shaders/liquidglass.glsl relative to this module (the
        // blur-my-shell pattern -- no extension-path plumbing needed).
        const shaderPath = GLib.filename_from_uri(GLib.uri_resolve_relative(
            import.meta.url, '../shaders/liquidglass.glsl', GLib.UriFlags.NONE))[0];
        this.set_shader_source(Shell.get_file_contents_utf8_sync(shaderPath));
        this._mouseU = -1;
        this._mouseV = -1;
        this._mouseFade = 0;
    }

    configure(p) {
        const cfg = {...DEFAULTS, ...p};
        const tint = cfg.solid ? cfg.solidColor : cfg.tint;

        this.set_uniform_value('innerW', f(cfg.innerW));
        this.set_uniform_value('innerH', f(cfg.innerH));
        this.set_uniform_value('marginPx', f(MARGIN));
        this.set_uniform_value('radius', f(cfg.radius));
        this.set_uniform_value('roundness', f(cfg.roundness));
        this.set_uniform_value('refractThickness', f(cfg.solid ? 0 : cfg.refractThickness));
        this.set_uniform_value('refractIOR', f(cfg.refractIOR));
        this.set_uniform_value('refractScale', f(cfg.refractScale));
        this.set_uniform_value('chromaStrength', f(cfg.chromaStrength));
        this.set_uniform_value('tintR', f(tint[0]));
        this.set_uniform_value('tintG', f(tint[1]));
        this.set_uniform_value('tintB', f(tint[2]));
        this.set_uniform_value('tintA', f(cfg.solid ? 1.0 : tint[3]));
        this.set_uniform_value('tintBottomR', f(cfg.tintBottom[0]));
        this.set_uniform_value('tintBottomG', f(cfg.tintBottom[1]));
        this.set_uniform_value('tintBottomB', f(cfg.tintBottom[2]));
        this.set_uniform_value('tintBottomA', f(cfg.tintBottom[3]));
        this.set_uniform_value('specStrength', f(cfg.specStrength));
        this.set_uniform_value('overlayR', f(cfg.overlay[0]));
        this.set_uniform_value('overlayG', f(cfg.overlay[1]));
        this.set_uniform_value('overlayB', f(cfg.overlay[2]));
        this.set_uniform_value('overlayA', f(cfg.overlay[3]));
        this.set_uniform_value('solidMode', cfg.solid ? 1 : 0);
        this.set_uniform_value('opacity', f(1.0));
        this._pushMouse();
    }

    setPointer(u, v, fade) {
        this._mouseU = u;
        this._mouseV = v;
        this._mouseFade = fade;
        this._pushMouse();
    }

    _pushMouse() {
        this.set_uniform_value('mouseU', f(this._mouseU));
        this.set_uniform_value('mouseV', f(this._mouseV));
        this.set_uniform_value('mouseFade', f(this._mouseFade));
        const actor = this.get_actor?.();
        if (actor)
            actor.queue_redraw();
    }
});

/**
 * @param {object} opts  { innerW, innerH, x, y, radius?, roundness?, solid? }
 *   x/y are the top-left of the *visible glass* in stage coords.
 * @returns {{
 *   widget: St.Widget, effect: LiquidGlassEffect, content: St.Widget,
 *   setInnerPos: (x:number, y:number) => void, refresh: () => void,
 * }}
 */
export function makeLiquidGlass(opts) {
    const {innerW, innerH} = opts;
    const actorW = innerW + 2 * MARGIN;
    const actorH = innerH + 2 * MARGIN;
    const solid = !!opts.solid;

    const widget = new St.Widget({
        width: actorW, height: actorH,
        x: opts.x - MARGIN, y: opts.y - MARGIN,
        reactive: false,
    });

    const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;

    const applyBackdrop = () => {
        if (solid) {
            widget.style = 'background-color: rgb(26,27,30);';
            return;
        }
        const tex = buildWallpaperTexture(
            {x: widget.x, y: widget.y, width: actorW, height: actorH},
            actorW * scale, actorH * scale);
        if (tex) {
            widget.set_content(tex);
            widget.style = null;
        } else {
            widget.style = 'background-color: rgba(20,20,20,0.5);';
        }
    };
    applyBackdrop();

    // A gentle frost behind the glass (the KDE original runs a Dual-Kawase blur
    // pyramid; Shell.BlurEffect in ACTOR mode blurs this actor's own wallpaper
    // crop, which the shader then refracts). Skipped in solid mode.
    const blurRadius = opts.blurRadius ?? 10;
    if (!solid && blurRadius > 0) {
        try {
            widget.add_effect(new Shell.BlurEffect({
                radius: blurRadius * scale,
                mode: Shell.BlurMode.ACTOR,
            }));
        } catch (e) {
            // Older Shell.BlurEffect used `sigma`; fall back, then give up.
            try {
                widget.add_effect(new Shell.BlurEffect({
                    sigma: blurRadius * scale / 2,
                    mode: Shell.BlurMode.ACTOR,
                }));
            } catch (_e) {
                logError(e, '[peachos-widgets] blur effect unavailable');
            }
        }
    }

    const effect = new LiquidGlassEffect();
    widget.add_effect(effect);
    effect.configure({
        innerW, innerH,
        radius: opts.radius, roundness: opts.roundness, solid,
    });

    // The content overlay is a SIBLING of `widget`, not a child: the shader
    // effect processes its actor's whole painted subtree as one texture, so a
    // child would get refracted/tinted along with the wallpaper. Callers parent
    // both into the same container and keep them aligned via setInnerPos().
    const content = new St.Widget({
        x: opts.x, y: opts.y, width: innerW, height: innerH,
        layout_manager: new Clutter.BinLayout(),
    });

    return {
        widget,
        effect,
        content,
        setInnerPos(x, y) {
            widget.set_position(x - MARGIN, y - MARGIN);
            content.set_position(x, y);
        },
        refresh() {
            applyBackdrop();
        },
    };
}
