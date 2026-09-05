// Liquid-glass fragment shader for GNOME Shell (Clutter.ShaderEffect / Cogl GLSL).
//
// Re-implemented from jaxparrow07/liquidglass-kde-widgets
// (1-common/components/shaders/liquidglass.frag, itself ported from
// iyinchao/liquid-glass-studio). GPL-3. The refraction math is copied
// verbatim; only the shell changes -- Qt RHI `#version 440` + std140 uniform
// blocks + `texture()` become bare Cogl uniforms + `texture2D()` +
// `cogl_tex_coord_in` / `cogl_color_out`.
//
// The effect's actor paints the wallpaper crop as its own content, so the
// built-in `tex` sampler IS the backdrop -- no second sampler needed. The
// actor is (innerW + 2*margin) x (innerH + 2*margin): the glass squircle is
// the centered innerW x innerH region, and the `margin` border is extra
// wallpaper the edge refraction samples into.

uniform sampler2D tex;

uniform float innerW;
uniform float innerH;
uniform float marginPx;

uniform float radius;
uniform float roundness;          // superellipse exponent; 2 = circle, ~7 = iOS squircle

uniform float refractThickness;   // edge band width, px
uniform float refractIOR;
uniform float refractScale;
uniform float chromaStrength;

uniform float tintR;
uniform float tintG;
uniform float tintB;
uniform float tintA;
uniform float tintBottomR;
uniform float tintBottomG;
uniform float tintBottomB;
uniform float tintBottomA;

uniform float mouseU;             // widget-local UV; < 0 means no pointer
uniform float mouseV;
uniform float mouseFade;
uniform float specStrength;

uniform float overlayR;
uniform float overlayG;
uniform float overlayB;
uniform float overlayA;           // bottom-gradient darken height, 0 = off

uniform int   solidMode;          // 1 = opaque fill, skip the wallpaper sample
uniform float opacity;

// --- squircle SDF with analytic gradient ------------------------------------

vec3 sceneSDFAndNormal(vec2 p, vec2 gSize) {
    vec2 b = gSize * 0.5;
    float n = max(roundness, 2.0);
    float r = clamp(radius, 0.0, min(b.x, b.y));

    vec2 q = abs(p) - b + vec2(r);
    float qx = max(q.x, 0.0);
    float qy = max(q.y, 0.0);

    float d;
    vec2 nrm;

    if (qx <= 0.0 && qy <= 0.0) {
        d = max(q.x, q.y) - r;
        nrm = q.x >= q.y ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    } else if (qx == 0.0) {
        d = qy - r;
        nrm = vec2(0.0, 1.0);
    } else if (qy == 0.0) {
        d = qx - r;
        nrm = vec2(1.0, 0.0);
    } else {
        float qxn = pow(qx, n);
        float qyn = pow(qy, n);
        float arc = pow(qxn + qyn, 1.0 / n);
        float gx = pow(qx / arc, n - 1.0);
        float gy = pow(qy / arc, n - 1.0);
        float gradLen = sqrt(gx * gx + gy * gy);
        d   = (arc - r) / max(gradLen, 1e-3);
        nrm = vec2(gx, gy) / max(gradLen, 1e-3);
    }

    nrm *= sign(p + vec2(1e-20));
    return vec3(d, nrm);
}

// inner-glass-local UV (0..1 over innerW x innerH) -> full-texture UV.
vec3 sampleBackdrop(vec2 innerUV) {
    vec2 full = vec2(innerW + 2.0 * marginPx, innerH + 2.0 * marginPx);
    vec2 texUV = (vec2(marginPx) + innerUV * vec2(innerW, innerH)) / full;
    return texture2D(tex, clamp(texUV, vec2(0.0), vec2(1.0))).rgb;
}

vec3 cornerSpec(vec2 p, float depthPx, vec2 gSize) {
    if (specStrength <= 0.0) return vec3(0.0);

    const float MAX_STROKE_PX = 3.0;
    const float FEATHER_PX    = 2.0;
    const float SECONDARY_INT = 0.65;

    vec2 b = gSize * 0.5;
    vec2 restLight = vec2(-b.x, b.y) * 1.2;
    bool hovering  = mouseFade > 0.0 && mouseU >= 0.0 && mouseV >= 0.0;
    vec2 cursorPx  = (vec2(mouseU, mouseV) - vec2(0.5)) * gSize;
    vec2 lightPx   = hovering ? mix(restLight, cursorPx, mouseFade) : restLight;
    vec2 antiLight = -lightPx;

    float taper = max(gSize.x, gSize.y) * 0.7;
    float primaryAtt   = exp(-distance(p, lightPx)  / taper);
    float secondaryAtt = exp(-distance(p, antiLight) / taper) * SECONDARY_INT;

    float tPx = max(primaryAtt, secondaryAtt) * MAX_STROKE_PX;
    float stroke = 1.0 - smoothstep(tPx - FEATHER_PX, tPx, depthPx);
    float I = stroke * specStrength * 0.55;
    return vec3(1.0, 0.98, 0.94) * I;
}

vec3 edgeSpec(vec2 ndir, float depthPx) {
    if (specStrength <= 0.0) return vec3(0.0);
    float lip = 1.0 - smoothstep(0.0, 3.0, max(depthPx, 0.0));
    vec2 lightDir = normalize(vec2(-0.45, 0.90));
    float facing = 0.35 + 0.65 * clamp(dot(ndir, lightDir) * 0.5 + 0.5, 0.0, 1.0);
    float I = lip * facing * specStrength * 0.10;
    return vec3(1.0, 0.98, 0.94) * I;
}

void main() {
    vec2 gSize = vec2(innerW, innerH);
    vec2 full  = gSize + vec2(2.0 * marginPx);

    // cogl_tex_coord_in[0] spans the full actor (glass + margin).
    vec2 fullUV = cogl_tex_coord_in[0].st;
    vec2 fullPx = fullUV * full;
    vec2 p = fullPx - full * 0.5;            // centred on the inner glass, px
    vec2 uv = p / gSize + vec2(0.5);         // inner-glass-local UV

    vec3 dn = sceneSDFAndNormal(p, gSize);
    float d = dn.x;
    vec2 ndir = dn.yz;

    if (d > 1.5) {
        cogl_color_out = vec4(0.0);
        return;
    }

    vec3 col;
    float depthPx = -d;

    vec3 tintColor = mix(vec3(tintR, tintG, tintB),
                         vec3(tintBottomR, tintBottomG, tintBottomB),
                         tintBottomA > 0.0 ? uv.y : 0.0);
    float tintAlpha = tintA;

    if (solidMode == 1) {
        col = tintColor;
    } else {
        bool canRefract = refractThickness > 0.0;
        if (!canRefract || depthPx >= refractThickness) {
            col = sampleBackdrop(uv);
            col = mix(col, tintColor, tintAlpha);
        } else {
            float t = clamp(depthPx / refractThickness, 0.0, 1.0);
            float sinThetaI = (1.0 - t) * (1.0 - t);
            float thetaI = asin(clamp(sinThetaI, 0.0, 1.0));
            float sinThetaT = sinThetaI / refractIOR;
            float thetaT = asin(clamp(sinThetaT, 0.0, 1.0));
            float edgeMag = tan(thetaI - thetaT);

            vec2 displaceUV = (-ndir * edgeMag * refractScale) / gSize;

            float edgeWeight = 1.0 - t;
            float chromaPx = chromaStrength * refractThickness * 0.35 * edgeWeight;
            vec2 chromaUV = (-ndir * chromaPx) / gSize;

            col.r = sampleBackdrop(uv + displaceUV + chromaUV).r;
            col.g = sampleBackdrop(uv + displaceUV).g;
            col.b = sampleBackdrop(uv + displaceUV - chromaUV).b;
            col = mix(col, tintColor, tintAlpha);
        }
    }

    if (overlayA > 0.0) {
        float darkenT = smoothstep(1.0 - overlayA, 1.0, uv.y);
        col = mix(col, vec3(overlayR, overlayG, overlayB), darkenT);
    }

    col += edgeSpec(ndir, depthPx);
    col += cornerSpec(p, depthPx, gSize);

    float mask = 1.0 - smoothstep(-0.5, 0.5, d);
    cogl_color_out = vec4(col * mask, mask) * opacity;
}
