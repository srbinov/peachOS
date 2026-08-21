import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import {LockScreenLayout} from './lib/lockScreenLayout.js';

export default class PeachOSLockScreenExtension extends Extension {
    enable() {
        this._lockScreenLayout = new LockScreenLayout();
    }

    disable() {
        this._lockScreenLayout?.destroy();
        this._lockScreenLayout = null;
    }
}
