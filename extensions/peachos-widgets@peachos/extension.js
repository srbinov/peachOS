// peachOS Desktop Widgets.
//
// A widget layer above the wallpaper / below windows (lib/widgetLayer.js),
// placed widgets persisted as JSON in the `widgets` gsetting, an edit mode
// (lib/editMode.js) toggled by the `edit-mode` gsetting that the Control
// Center's "Manage Widgets" pill flips, and a bottom-left liquid-glass picker
// (lib/widgetPicker.js). Widget content lives in widgets/, shared data
// providers in lib/providers/. See .claude/plans/fluffy-dreaming-canyon.md.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {WidgetLayer} from './lib/widgetLayer.js';
import {EditMode} from './lib/editMode.js';
import {invalidateWallpaper} from './lib/wallpaperCrop.js';
import {WeatherProvider} from './lib/providers/weather.js';
import {CalendarSource} from './lib/providers/calendar.js';

export default class PeachosWidgetsExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        // Never boot straight into edit mode (e.g. after a crash mid-edit).
        this._settings.set_boolean('edit-mode', false);

        this._bgSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.background'});
        this._ifaceSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});

        if (Main.layoutManager._startingUp) {
            Main.layoutManager.connectObject('startup-complete',
                () => this._build(), this);
        } else {
            this._build();
        }
    }

    _build() {
        try {
            this._weather = new WeatherProvider(this._settings);
            this._calendar = new CalendarSource();

            const ctx = {
                settings: this._settings,
                weather: this._weather,
                calendar: this._calendar,
                path: this.path,
            };

            this._layer = new WidgetLayer(this._settings, ctx);
            this._editMode = new EditMode(this._layer, this._settings);

            this._settings.connectObject('changed::edit-mode',
                () => this._editMode.sync(), this);

            // A wallpaper / theme change rebuilds the background actors above the
            // widget layer -- re-raise it and refresh every widget's backdrop
            // crop (deferred, so it runs after the shell's own restack).
            const onBgChange = () => {
                if (this._bgRaiseId)
                    return;
                this._bgRaiseId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    this._bgRaiseId = 0;
                    invalidateWallpaper();
                    this._layer?.raise();
                    this._layer?.refreshBackdrops();
                    return GLib.SOURCE_REMOVE;
                });
            };
            this._bgSettings.connectObject('changed', onBgChange, this);
            this._ifaceSettings.connectObject('changed::color-scheme', onBgChange, this);

            console.log(`[peachos-widgets] enabled (${this._layer.count} widget(s) placed)`);
        } catch (e) {
            logError(e, '[peachos-widgets] _build() failed');
            this.disable();
        }
    }

    disable() {
        Main.layoutManager.disconnectObject(this);
        this._settings?.disconnectObject(this);
        this._bgSettings?.disconnectObject(this);
        this._ifaceSettings?.disconnectObject(this);

        if (this._bgRaiseId) {
            GLib.source_remove(this._bgRaiseId);
            this._bgRaiseId = 0;
        }

        this._editMode?.destroy();
        this._layer?.destroy();
        this._weather?.destroy();
        this._calendar?.destroy();

        this._editMode = null;
        this._layer = null;
        this._weather = null;
        this._calendar = null;
        this._settings = null;
        this._bgSettings = null;
        this._ifaceSettings = null;
    }
}
