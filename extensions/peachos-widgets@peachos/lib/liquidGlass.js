// The widget card. Three modes, matching the KDE liquidglass widgets:
//
//   glass -- translucent white fill + highlight gradient + bright rim +
//            a real backdrop blur (Shell.BlurEffect, BACKGROUND mode -- the
//            same frosted-glass technique the Control Center tiles use).
//   dark  -- opaque #1c1c1e card, white content.
//   light -- opaque #ffffff card, dark content.
//
// Always full strength; not tied to the Settings "Liquid Glass" slider.

import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Shell from 'gi://Shell';

export const MARGIN = 0;

const GLASS = `
    background-color: rgba(255, 255, 255, 0.15);
    background-gradient-direction: vertical;
    background-gradient-start: rgba(255, 255, 255, 0.30);
    background-gradient-end: rgba(255, 255, 255, 0.09);
    border: 1px solid rgba(255, 255, 255, 0.45);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
`;
const DARK = `
    background-color: #1c1c1e;
    border: 1px solid rgba(255, 255, 255, 0.10);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
`;
const LIGHT = `
    background-color: #ffffff;
    border: 1px solid rgba(0, 0, 0, 0.08);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
`;

// Content foreground "r,g,b" per mode (glass is always white, iOS-style).
export const MODE_FG = {glass: '255,255,255', dark: '255,255,255', light: '26,27,30'};

const BLUR_NAME = 'peachos-widget-blur';

function baseStyle(mode) {
    return mode === 'dark' ? DARK : mode === 'light' ? LIGHT : GLASS;
}

/**
 * @param {object} opts { innerW, innerH, x, y, radius, mode }
 */
export function makeLiquidGlass(opts) {
    const {innerW, innerH, x, y} = opts;
    const radius = opts.radius ?? 32;
    const mode = opts.mode ?? 'glass';

    const widget = new St.Widget({
        width: innerW, height: innerH, x, y,
        style: `${baseStyle(mode)} border-radius: ${radius}px;`,
        reactive: false,
        layout_manager: new Clutter.BinLayout(),
    });

    if (mode === 'glass') {
        try {
            const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
            widget.add_effect_with_name(BLUR_NAME, new Shell.BlurEffect({
                name: BLUR_NAME,
                mode: Shell.BlurMode.BACKGROUND,
                radius: 18 * scale,
                brightness: 1.0,
            }));
        } catch (e) {
            logError(e, '[peachos-widgets] backdrop blur unavailable');
        }
    }

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
        setRadius(r) {
            widget.style = `${baseStyle(mode)} border-radius: ${r}px;`;
        },
        refresh() {},
    };
}
