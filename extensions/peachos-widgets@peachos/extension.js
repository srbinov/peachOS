// peachOS Desktop Widgets -- Phase 0 shader spike.
//
// Places one glass squircle (and one solid squircle) on the desktop, above
// the wallpaper and below all windows, to prove the ported liquid-glass
// shader (shaders/liquidglass.glsl via lib/liquidGlass.js) renders on GNOME
// and refracts the real wallpaper. No settings, no picker, no persistence yet
// -- see .claude/plans/fluffy-dreaming-canyon.md.

import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass} from './lib/liquidGlass.js';

export default class PeachosWidgetsExtension extends Extension {
    enable() {
        try {
            // A layer just above the wallpaper (Main.layoutManager._backgroundGroup,
            // which layout.js pins to the bottom of global.window_group) and below
            // every window.
            this._layer = new Clutter.Actor({name: 'peachos-widget-layer'});
            global.window_group.add_child(this._layer);
            global.window_group.set_child_above_sibling(
                this._layer, Main.layoutManager._backgroundGroup);

            const mon = Main.layoutManager.primaryMonitor;

            this._glass = makeLiquidGlass({
                innerW: 280, innerH: 170,
                x: mon.x + 220, y: mon.y + 180,
                radius: 34, roundness: 7.0,
            });
            this._layer.add_child(this._glass.widget);

            this._solid = makeLiquidGlass({
                innerW: 280, innerH: 170,
                x: mon.x + 220, y: mon.y + 400,
                radius: 34, roundness: 7.0, solid: true,
            });
            this._layer.add_child(this._solid.widget);

            // Seed a pointer position so the corner specular is visible in a
            // screenshot even without a live cursor over the glass.
            this._glass.effect.setPointer(0.15, 0.15, 1.0);

            console.log('[peachos-widgets] Phase 0 spike: 2 squircles placed on the desktop');
        } catch (e) {
            logError(e, '[peachos-widgets] enable() failed');
            this.disable();
        }
    }

    disable() {
        this._glass?.widget?.destroy();
        this._solid?.widget?.destroy();
        this._glass = null;
        this._solid = null;
        if (this._layer) {
            this._layer.destroy();
            this._layer = null;
        }
    }
}
