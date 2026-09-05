// The widget backdrop: peachOS's own "max liquid glass" recipe -- the exact
// translucent-white fill + vertical highlight gradient + bright rim + inset top
// edge that the Notification Center and notification banners use
// (macos-top-panel/lib/liquidGlassIntensity.js SHARED_RECIPE at intensity 100).
//
// No shader, no Shell.BlurEffect, and NOT wired to the Settings "Liquid Glass"
// slider -- always full glass, by request.

import Clutter from 'gi://Clutter';
import St from 'gi://St';

// Kept (as 0) so callers that still offset by it keep working.
export const MARGIN = 0;

const GLASS = `
    background-color: rgba(255, 255, 255, 0.12);
    background-gradient-direction: vertical;
    background-gradient-start: rgba(255, 255, 255, 0.28);
    background-gradient-end: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.42);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
`;

const SOLID = `
    background-color: rgba(28, 28, 30, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.10);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
`;

/**
 * @param {object} opts { innerW, innerH, x, y, radius, solid? }
 * @returns {{ widget: St.Widget, content: St.Widget, effect: null,
 *            setInnerPos:(x,y)=>void, refresh:()=>void, setRadius:(r)=>void }}
 */
export function makeLiquidGlass(opts) {
    const {innerW, innerH, x, y} = opts;
    const radius = opts.radius ?? 32;
    const base = opts.solid ? SOLID : GLASS;

    const widget = new St.Widget({
        width: innerW, height: innerH, x, y,
        style: `${base} border-radius: ${radius}px;`,
        reactive: false,
    });

    // Transparent overlay the widget content fills; a child of `widget`, so it
    // moves and is clipped with it.
    const content = new St.Widget({
        layout_manager: new Clutter.BinLayout(),
        x_expand: true, y_expand: true,
    });
    widget.add_child(content);

    return {
        widget,
        content,
        effect: null,
        setInnerPos(nx, ny) {
            widget.set_position(Math.round(nx), Math.round(ny));
        },
        setSize(nw, nh) {
            widget.set_size(nw, nh);
        },
        setRadius(r) {
            widget.style = `${base} border-radius: ${r}px;`;
        },
        refresh() {},
    };
}
