// The widget card. Three modes, matching the KDE liquidglass widgets:
//
//   glass -- a blurred wallpaper crop (lib/wallpaperCrop.js) + a translucent
//            white tint/gradient on top + a hairline rim.
//   dark  -- opaque #1c1c1e, white content.
//   light -- opaque #ffffff, dark content.
//
// The squircle silhouette + rim come from a Shell.GLSLEffect
// (lib/squircleMask.js). Always full strength; not tied to the Settings
// "Liquid Glass" slider.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

import {SquircleMaskEffect} from './squircleMask.js';
import {buildBlurredCrop} from './wallpaperCrop.js';

export const MARGIN = 0;
export const MODE_FG = {glass: '255,255,255', dark: '255,255,255', light: '26,27,30'};

const TINT_STYLE = `
    background-color: rgba(255, 255, 255, 0.13);
    background-gradient-direction: vertical;
    background-gradient-start: rgba(255, 255, 255, 0.26);
    background-gradient-end: rgba(255, 255, 255, 0.05);
`;
const RIM = {
    glass: [1, 1, 1, 0.5],
    dark: [1, 1, 1, 0.12],
    light: [0, 0, 0, 0.1],
};

export function makeLiquidGlass(opts) {
    const {innerW, innerH, x, y} = opts;
    const radius = opts.radius ?? 32;
    const mode = opts.mode ?? 'glass';

    const widget = new St.Widget({
        width: innerW, height: innerH, x, y,
        reactive: false,
        layout_manager: new Clutter.BinLayout(),
    });

    let applyCrop = () => {};
    if (mode === 'glass') {
        const tint = new St.Widget({style: TINT_STYLE, x_expand: true, y_expand: true});
        widget.add_child(tint);
        applyCrop = () => {
            const c = buildBlurredCrop({x: widget.x, y: widget.y, w: innerW, h: innerH});
            if (c)
                widget.set_content(c);
        };
        applyCrop();
    } else {
        widget.style = mode === 'dark'
            ? 'background-color: #1c1c1e;'
            : 'background-color: #ffffff;';
    }

    const mask = new SquircleMaskEffect();
    widget.add_effect(mask);
    mask.configure({
        w: innerW, h: innerH, radius, exponent: 8,
        borderWidth: 1,
        borderColor: RIM[mode],
    });

    const content = new St.Widget({
        layout_manager: new Clutter.BinLayout(),
        x_expand: true, y_expand: true,
    });
    widget.add_child(content);

    return {
        widget,
        content,
        mode,
        fg: MODE_FG[mode],
        setInnerPos(nx, ny) {
            widget.set_position(Math.round(nx), Math.round(ny));
        },
        refresh() {
            applyCrop();
        },
    };
}
