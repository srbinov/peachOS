import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

// Shows in the top bar (left of the battery indicator) only while actively casting to a TV
// via "Connect to TV" (gnome-network-displays / Wi-Fi Display -- Miracast, not AirPlay; see
// apps/tv-audio/peachos-tv-audio's own comment for why that distinction matters here).
//
// There's no public D-Bus "am I casting right now" property to query -- gnome-network-
// displays doesn't expose one. apps/tv-audio/peachos-tv-audio already has the one signal
// this project trusts for "a TV is actually connected" (its own PipeWire sink,
// gnome_network_displays_*, appearing/disappearing over `pactl subscribe`) to redirect
// audio there; it touches/removes $XDG_RUNTIME_DIR/peachos-tv-active in lockstep with that
// same signal, so this just watches that file instead of re-implementing the pactl-watching
// logic a second time in JS.
//
// Caveat inherited from that same signal: if the TV never negotiates the WFD AAC audio
// codec (rare, but possible -- some receivers only support LPCM, which gnome-network-
// displays doesn't implement), no gnome_network_displays_* sink ever appears, and this
// indicator won't show even though video is actively streaming.
const ACTIVE_FILE_NAME = 'peachos-tv-active';

function _activeFilePath() {
    const dir = GLib.getenv('XDG_RUNTIME_DIR') || '/tmp';
    return GLib.build_filenamev([dir, ACTIVE_FILE_NAME]);
}

export const ScreenSharingIndicator = GObject.registerClass(
class ScreenSharingIndicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.5, 'Screen Sharing', true);
        this.visible = false;

        // Kept as its own real-color badge (not a "-symbolic" name recoloured to the panel
        // foreground) -- real macOS does the same for its own screen-sharing/AirPlay menu-
        // bar glyph, a deliberate splash of color among otherwise monochrome status icons.
        const gicon = Gio.icon_new_for_string(
            GLib.build_filenamev([extensionPath, 'icons', 'panel', 'screen-sharing.png']));
        this._icon = new St.Icon({
            gicon,
            icon_size: 18,
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this.connect('button-press-event', () => {
            const appInfo = Gio.DesktopAppInfo.new('peachos-connect-tv.desktop');
            if (appInfo)
                appInfo.launch([], null);
            return Clutter.EVENT_STOP;
        });

        // monitor_file() works fine on a path that doesn't exist yet -- GIO watches the
        // parent directory for that exact filename appearing, same as inotify would.
        this._file = Gio.File.new_for_path(_activeFilePath());
        this._monitor = this._file.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._monitorId = this._monitor.connect('changed', () => this._sync());
        this._sync();
    }

    _sync() {
        this.visible = GLib.file_test(_activeFilePath(), GLib.FileTest.EXISTS);
    }

    destroy() {
        if (this._monitor) {
            if (this._monitorId) {
                this._monitor.disconnect(this._monitorId);
                this._monitorId = 0;
            }
            this._monitor.cancel();
            this._monitor = null;
        }
        super.destroy();
    }
});
