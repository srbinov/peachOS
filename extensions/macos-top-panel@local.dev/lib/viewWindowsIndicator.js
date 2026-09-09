import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

// A plain button (no dropdown): clicking it opens the windows overview -- the
// same "show all windows" view double-tapping the Super key gives you.
// view-windows-symbolic.svg is installed into the icon theme by provision.sh;
// being a "-symbolic" name it recolours to the panel's black/white foreground.
export const ViewWindowsIndicator = GObject.registerClass(
class ViewWindowsIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.5, 'View Windows', true);

        this._icon = new St.Icon({
            icon_name: 'view-windows-symbolic',
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this.connect('button-press-event', () => {
            Main.overview.toggle();
            return Clutter.EVENT_STOP;
        });
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
