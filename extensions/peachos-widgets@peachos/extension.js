// peachOS Desktop Widgets -- Phase 0 shader spike.
//
// Places one glass squircle (and one solid squircle) on the desktop, above
// the wallpaper and below all windows, to prove the ported liquid-glass
// shader (shaders/liquidglass.glsl via lib/liquidGlass.js) renders on GNOME
// and refracts the real wallpaper. No settings, no picker, no persistence yet
// -- see .claude/plans/fluffy-dreaming-canyon.md.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {makeLiquidGlass} from './lib/liquidGlass.js';

export default class PeachosWidgetsExtension extends Extension {
    enable() {
        this._bgSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});

        if (Main.layoutManager._startingUp) {
            Main.layoutManager.connectObject('startup-complete',
                () => this._build(), this);
        } else {
            this._build();
        }
    }

    _build() {
        try {
            // The widget layer lives *inside* Main.layoutManager._backgroundGroup
            // -- the same parent azclock ("Desktop Widgets") uses. That group is
            // pinned to the bottom of global.window_group, so everything in it
            // renders below every window; adding our layer as its top child puts
            // it just above the wallpaper actors. (Parenting straight into
            // global.window_group does NOT work: Mutter's stacking sync forces
            // unknown non-window actors above the windows.)
            this._layer = new Clutter.Actor({name: 'peachos-widget-layer'});
            Main.layoutManager._backgroundGroup.add_child(this._layer);
            this._raise();

            const mon = Main.layoutManager.primaryMonitor;

            // Glass squircle straddling the mountains/waterline so the
            // refraction is actually visible (over flat sky you can't tell).
            this._glass = makeLiquidGlass({
                innerW: 280, innerH: 170,
                x: mon.x + 160, y: mon.y + Math.round(mon.height * 0.42),
                radius: 34, roundness: 7.0,
            });
            this._layer.add_child(this._glass.widget);

            // Solid squircle up in the sky -- just checks opacity + silhouette.
            this._solid = makeLiquidGlass({
                innerW: 280, innerH: 170,
                x: mon.x + 160, y: mon.y + 70,
                radius: 34, roundness: 7.0, solid: true,
            });
            this._layer.add_child(this._solid.widget);

            // Seed a pointer position so the corner specular shows up in a
            // screenshot even without a live cursor over the glass.
            this._glass.effect.setPointer(0.15, 0.15, 1.0);

            // A wallpaper or monitor change rebuilds the background actors on
            // top of us -- bump the layer back above them (deferred so it runs
            // after the shell has finished its own restack).
            Main.layoutManager.connectObject('monitors-changed',
                () => this._raiseLater(), this);
            this._bgSettings.connectObject('changed',
                () => this._raiseLater(), this);

            console.log('[peachos-widgets] Phase 0 spike: 2 squircles placed on the desktop');
        } catch (e) {
            logError(e, '[peachos-widgets] _build() failed');
            this.disable();
        }
    }

    _raise() {
        if (this._layer && this._layer.get_parent())
            this._layer.get_parent().set_child_above_sibling(this._layer, null);
    }

    _raiseLater() {
        if (this._raiseId)
            return;
        this._raiseId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._raiseId = 0;
            this._raise();
            return GLib.SOURCE_REMOVE;
        });
    }

    disable() {
        Main.layoutManager.disconnectObject(this);
        this._bgSettings?.disconnectObject(this);
        this._bgSettings = null;

        if (this._raiseId) {
            GLib.source_remove(this._raiseId);
            this._raiseId = 0;
        }

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
