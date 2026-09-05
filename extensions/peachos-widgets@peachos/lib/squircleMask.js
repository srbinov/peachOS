// Shell.GLSLEffect that clips an actor to an iOS-style squircle and draws a
// hairline rim on the edge. The squircle formula + build-pipeline rules are
// lifted from the vendored rounded-windows@marcosgt effect.js (GNOME 50 /
// Mutter 18): add_glsl_snippet only in vfunc_build_pipeline; uniform locations
// resolved lazily afterwards.

import Cogl from 'gi://Cogl';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

const DECLARATIONS = /* glsl */`
uniform vec4  bounds;
uniform float clipRadius;
uniform float exponent;
uniform vec2  pixelStep;
uniform float borderWidth;
uniform vec4  borderColor;

float squircleBounds(vec2 p, vec2 center, float r, float e) {
    vec2  d    = abs(p - center);
    float dist = pow(pow(d.x, e) + pow(d.y, e), 1.0 / e);
    return clamp(r - dist + 0.5, 0.0, 1.0);
}

float circleBounds(vec2 p, vec2 center, float r) {
    float dist = length(p - center);
    return clamp(r - dist + 0.5, 0.0, 1.0);
}

float getOpacity(vec2 p, vec4 b, float r, float e) {
    if (p.x < b.x || p.x > b.z || p.y < b.y || p.y > b.w) return 0.0;
    float cl = b.x + r, cr = b.z - r;
    float ct = b.y + r, cb = b.w - r;
    vec2 c;
    if      (p.x < cl) c.x = cl;
    else if (p.x > cr) c.x = cr;
    else               return 1.0;
    if      (p.y < ct) c.y = ct;
    else if (p.y > cb) c.y = cb;
    else               return 1.0;
    return (e <= 2.0) ? circleBounds(p, c, r) : squircleBounds(p, c, r, e);
}
`;

const CODE = /* glsl */`
    vec2  p  = cogl_tex_coord0_in.xy / pixelStep;
    float a  = getOpacity(p, bounds, clipRadius, exponent);
    cogl_color_out *= a;
    if (borderWidth > 0.0) {
        vec4 inner = vec4(bounds.x + borderWidth, bounds.y + borderWidth,
                          bounds.z - borderWidth, bounds.w - borderWidth);
        float ia = getOpacity(p, inner, max(0.0, clipRadius - borderWidth), exponent);
        float edge = clamp(a - ia, 0.0, 1.0);
        cogl_color_out = mix(cogl_color_out, vec4(borderColor.rgb, 1.0), edge * borderColor.a);
    }
`;

export const SquircleMaskEffect = GObject.registerClass(
{GTypeName: 'PeachosSquircleMaskEffect'},
class SquircleMaskEffect extends Shell.GLSLEffect {
    _u = null;

    vfunc_build_pipeline() {
        this.add_glsl_snippet(Cogl.SnippetHook.FRAGMENT, DECLARATIONS, CODE, false);
    }

    _ensure() {
        if (this._u)
            return;
        this._u = {
            bounds: this.get_uniform_location('bounds'),
            clipRadius: this.get_uniform_location('clipRadius'),
            exponent: this.get_uniform_location('exponent'),
            pixelStep: this.get_uniform_location('pixelStep'),
            borderWidth: this.get_uniform_location('borderWidth'),
            borderColor: this.get_uniform_location('borderColor'),
        };
    }

    /**
     * Must be called after the effect is added to its actor.
     * @param {object} c { w, h, radius, exponent?, borderWidth?, borderColor?:[r,g,b,a] }
     */
    configure(c) {
        this._ensure();
        if (!this._u || this._u.bounds === -1)
            return;
        const {w, h} = c;
        const e = c.exponent ?? 8.0;
        const maxR = Math.min(w, h) / 2;
        let r = c.radius * 0.5 * e;
        let exp = e;
        if (r > maxR) {
            exp *= maxR / r;
            r = maxR;
        }
        const bw = c.borderWidth ?? 0;
        const bc = c.borderColor ?? [1, 1, 1, 0.45];
        this.set_uniform_float(this._u.bounds, 4, [0, 0, w, h]);
        this.set_uniform_float(this._u.clipRadius, 1, [r]);
        this.set_uniform_float(this._u.exponent, 1, [exp]);
        this.set_uniform_float(this._u.pixelStep, 2, [w > 0 ? 1 / w : 1, h > 0 ? 1 / h : 1]);
        this.set_uniform_float(this._u.borderWidth, 1, [bw]);
        this.set_uniform_float(this._u.borderColor, 4, bc);
        this.queue_repaint();
    }
});
