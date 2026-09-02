import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import St from 'gi://St';

import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

// peachySearch (apps/ulauncher in the peachOS repo) is installed system-wide by
// provision.sh: /usr/bin/ulauncher is a thin wrapper around /usr/lib/peachos/ulauncher.
// Same command the <Primary>space keybinding uses (provision/dconf/01-peachos).
const PEACHY_SEARCH_TOGGLE_CMD = ['/usr/bin/ulauncher', 'toggle'];

export const SearchIndicator = GObject.registerClass(
class SearchIndicator extends PanelMenu.Button {
    _init() {
        // dontCreateMenu=true: this is a plain launcher button, not a dropdown -- clicking it
        // should toggle peachySearch directly rather than opening a popup menu.
        super._init(0.5, 'peachySearch', true);

        this._icon = new St.Icon({icon_name: 'edit-find-symbolic', style_class: 'system-status-icon'});
        this.add_child(this._icon);

        this.connect('button-press-event', () => {
            this._launch();
            return Clutter.EVENT_STOP;
        });
    }

    _launch() {
        try {
            Gio.Subprocess.new(PEACHY_SEARCH_TOGGLE_CMD, Gio.SubprocessFlags.NONE);
        } catch (e) {
            logError(e, 'peachySearch: failed to launch');
        }
    }

    /**
     * @param {'black'|'white'} foreground
     */
    setForeground(foreground) {
        if (foreground !== 'black' && foreground !== 'white')
            return;
        this._icon.style = `color: ${foreground};`;
    }
});
