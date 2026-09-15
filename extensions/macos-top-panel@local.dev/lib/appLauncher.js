import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// macOS 26/27 "Apps" overlay: a full-screen chrome layer with the wallpaper still visible
// through a light dim, a floating search pill, and a rounded liquid-glass panel with
// category tabs over a vertically-scrolling app grid -- NOT the classic paged Launchpad
// (no page dots, no horizontal paging). Triggered from a Dock icon rather than launched as
// a real windowed app (see the peachos-applauncher.desktop entry this exposes a toggle for
// over D-Bus).
//
// No Shell.BlurEffect anywhere in here, same rule as the Control Center (see this
// extension's docs/liquid-glass-style.md "Hard rules"): Shell.BlurEffect on popup-style
// chrome has caused real Clutter paint-abort crashes here before, and this overlay
// (full-screen, covering everything) has an even bigger blast radius if that showed up
// again. The glass panel below is a CSS approximation (translucent fill + vertical
// gradient + rim + inset top highlight), not a real backdrop blur.
const BUS_NAME = 'org.peachos.AppLauncher';
const OBJECT_PATH = '/org/peachos/AppLauncher';
const IFACE_XML = `
<node>
  <interface name="${BUS_NAME}">
    <method name="Toggle" />
  </interface>
</node>`;

const FADE_DURATION = 280;
const DOCK_ACTOR_NAME = 'dashtodockContainer'; // dash2dock-lite's own name for its dock actor
// peachOS's own UI-toggle entries -- not real apps to launch from inside this grid.
// "Apps" is this very overlay (clicking it from within itself would be pointless/recursive),
// and peachySearch already has its own dedicated top-bar icon and shortcut.
const EXCLUDED_DESKTOP_IDS = new Set(['peachos-applauncher.desktop', 'io.ulauncher.Ulauncher.desktop']);

const COLUMNS = 7;
const VISIBLE_ROWS = 4;
const CELL_WIDTH = 118;
const CELL_HEIGHT = 108;
const ICON_SIZE = 62;

// [tab label, RegExp tested against the app's raw Categories= string, or null for "All"].
// freedesktop.org categories aren't mutually exclusive (a video editor is both AudioVideo
// AND AudioVideoEditing) and neither are these tabs -- same as macOS's own App Store
// categories, an app can reasonably show up under more than one.
const CATEGORY_TABS = [
    ['All', null],
    ['Utilities', /\bUtility\b/],
    ['Productivity', /\bOffice\b/],
    ['Social', /\b(Network|Chat|InstantMessaging|Email)\b/],
    ['Photo & Video', /\b(Photography|Graphics|Viewer)\b/],
    ['Games', /\bGame\b/],
    ['Entertainment', /\b(AudioVideo|Audio|Video|Player|Music)\b/],
    ['Creativity', /\b(2DGraphics|3DGraphics|RasterGraphics|VectorGraphics|AudioVideoEditing|Publishing)\b/],
    ['Information & Reading', /\b(News|Documentation|Education|Literature|Dictionary)\b/],
];

function _findActorByName(actor, name) {
    if (actor.name === name)
        return actor;
    for (const child of actor.get_children()) {
        const found = _findActorByName(child, name);
        if (found)
            return found;
    }
    return null;
}

export class AppLauncherOverlay {
    constructor() {
        this._open = false;
        this._allApps = [];
        this._category = CATEGORY_TABS[0];
        this._categoryButtons = [];
        this._capturedEventId = 0;
        this._ownerId = 0;
        this._exportedObject = null;
        this._dockActor = null;
        this._dockActorSearched = false;

        this._root = new St.Widget({
            style_class: 'macos-applauncher-root',
            layout_manager: new Clutter.BinLayout(),
            reactive: true,
            visible: false,
        });

        // A light wash the wallpaper still reads through, not the old flat-black Launchpad
        // veil -- macOS's own Apps overlay keeps the desktop visibly present behind it.
        this._dim = new St.Widget({style_class: 'macos-applauncher-dim', reactive: true});
        this._dim.connect('button-press-event', () => {
            this.close();
            return Clutter.EVENT_STOP;
        });
        this._root.add_child(this._dim);

        this._content = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'macos-applauncher-content',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._content.set_pivot_point(0.5, 0.5);
        this._root.add_child(this._content);

        this._content.add_child(this._buildSearchBar());

        this._panel = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'macos-applauncher-panel',
        });
        this._content.add_child(this._panel);

        this._panel.add_child(this._buildCategoryTabs());
        this._panel.add_child(this._buildGrid());

        Main.layoutManager.addChrome(this._root);

        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            this._onBusAcquired.bind(this), null, null,
        );
    }

    // ---- construction ---------------------------------------------------------------

    _buildSearchBar() {
        const bar = new St.BoxLayout({
            style_class: 'macos-applauncher-searchbar',
            x_align: Clutter.ActorAlign.CENTER,
        });
        bar.spacing = 8; // not constructible on St.BoxLayout -- see below

        bar.add_child(new St.Icon({
            icon_name: 'edit-find-symbolic',
            style_class: 'macos-applauncher-searchbar-icon',
            icon_size: 15,
            y_align: Clutter.ActorAlign.CENTER,
        }));

        this._searchEntry = new St.Entry({
            style_class: 'macos-applauncher-searchbar-entry',
            hint_text: 'Search',
            can_focus: true,
            x_expand: true,
        });
        this._searchEntry.clutter_text.connect('text-changed', () => this._refresh());
        // No blinking text cursor at all, by explicit request -- set_cursor_visible(false)
        // is the real ClutterText API for this, distinct from just recoloring it.
        this._searchEntry.clutter_text.set_cursor_visible(false);
        bar.add_child(this._searchEntry);

        const more = new St.Button({
            style_class: 'macos-applauncher-searchbar-more',
            child: new St.Label({text: '⋯'}), // "⋯"
            y_align: Clutter.ActorAlign.CENTER,
        });
        more.connect('clicked', () => {
            this._searchEntry.set_text('');
            this._selectCategory(CATEGORY_TABS[0]);
        });
        bar.add_child(more);

        return bar;
    }

    _buildCategoryTabs() {
        this._catsBox = new St.BoxLayout({
            style_class: 'macos-applauncher-cats',
            x_align: Clutter.ActorAlign.CENTER,
        });
        this._catsBox.spacing = 4; // not constructible -- see the search bar comment above

        this._categoryButtons = CATEGORY_TABS.map((tab) => {
            const btn = new St.Button({
                style_class: 'macos-applauncher-cat',
                label: tab[0],
                can_focus: true,
            });
            btn.connect('clicked', () => this._selectCategory(tab));
            this._catsBox.add_child(btn);
            return btn;
        });

        return this._catsBox;
    }

    _buildGrid() {
        this._scroll = new St.ScrollView({
            style_class: 'macos-applauncher-scroll',
            width: COLUMNS * CELL_WIDTH,
            height: VISIBLE_ROWS * CELL_HEIGHT,
            overlay_scrollbars: true,
        });
        this._scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);

        // St.ScrollView.set_child() requires an St.Scrollable -- St.BoxLayout is one,
        // a bare St.Widget with a Clutter.GridLayout is NOT. Handing it the grid widget
        // directly throws "Object is of type St.Widget - cannot convert to StScrollable"
        // out of set_child(), which aborts this constructor and (uncaught, before
        // extension.js wrapped this construction in its own try/catch) took the entire
        // top bar down with it on login -- confirmed live. The grid must go inside a real
        // St.BoxLayout host, same pattern as every other scrollable list in this
        // extension (e.g. wifiIndicator.js's networks box).
        this._gridHost = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
        });
        this._grid = new St.Widget({
            layout_manager: new Clutter.GridLayout(),
            width: COLUMNS * CELL_WIDTH,
        });
        this._gridHost.add_child(this._grid);
        this._scroll.set_child(this._gridHost); // St.BoxLayout, never the grid widget itself

        return this._scroll;
    }

    _onBusAcquired(connection) {
        this._exportedObject = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._exportedObject.export(connection, OBJECT_PATH);
    }

    // D-Bus-facing method name, called by peachos-applauncher.desktop's Exec= via gdbus.
    Toggle() {
        this.toggle();
    }

    toggle() {
        if (this._open)
            this.close();
        else
            this.open();
    }

    open() {
        if (this._open)
            return;
        this._open = true;

        this._reposition();
        this._loadApps();
        this._searchEntry.set_text('');
        this._selectCategory(CATEGORY_TABS[0]);
        this._scroll.vscroll?.adjustment.set_value(0);

        this._root.visible = true;
        this._root.opacity = 0;
        this._root.remove_all_transitions();
        this._root.ease({
            opacity: 255,
            duration: FADE_DURATION,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });

        // Subtle zoom-in on the content (search + panel) on top of the dim background's
        // plain fade -- the same "settles into place" read real macOS has, rather than
        // just popping straight to full size.
        this._content.remove_all_transitions();
        this._content.scale_x = 0.94;
        this._content.scale_y = 0.94;
        this._content.ease({
            scale_x: 1,
            scale_y: 1,
            duration: FADE_DURATION,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });

        this._setDockVisible(false);

        this._searchEntry.grab_key_focus();
        this._capturedEventId = global.stage.connect('captured-event', this._onCapturedEvent.bind(this));
    }

    close() {
        if (!this._open)
            return;
        this._open = false;

        this._root.remove_all_transitions();
        this._root.ease({
            opacity: 0,
            duration: FADE_DURATION,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onStopped: () => {
                this._root.visible = false;
            },
        });

        this._content.remove_all_transitions();
        this._content.ease({
            scale_x: 0.94,
            scale_y: 0.94,
            duration: FADE_DURATION,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
        });

        this._setDockVisible(true);

        if (this._capturedEventId) {
            global.stage.disconnect(this._capturedEventId);
            this._capturedEventId = 0;
        }
    }

    // dash2dock-lite's dock actor isn't something this extension owns or imports directly
    // (avoids coupling to its internal module structure, which could change independently
    // of this file) -- found once, by the actor name it gives itself, and cached. Missing
    // entirely (dash2dock-lite disabled, or some future rename) just means the dock stays
    // as it was, not a hard failure.
    _getDockActor() {
        if (!this._dockActorSearched) {
            this._dockActorSearched = true;
            this._dockActor = _findActorByName(Main.layoutManager.uiGroup, DOCK_ACTOR_NAME);
        }
        return this._dockActor;
    }

    _setDockVisible(visible) {
        const dock = this._getDockActor();
        if (!dock)
            return;
        dock.remove_all_transitions();
        if (visible) {
            // Visible again right away, opacity still eases up -- same order as _root's own
            // open(), so nothing is briefly unclickable while only half faded in.
            dock.visible = true;
            dock.ease({
                opacity: 255,
                duration: FADE_DURATION,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        } else {
            dock.ease({
                opacity: 0,
                duration: FADE_DURATION,
                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                // Only actually hidden (removed from picking entirely, same as _root's own
                // close()) once the fade finishes -- opacity alone doesn't stop an actor
                // from still receiving clicks along the way.
                onStopped: () => {
                    dock.visible = false;
                },
            });
        }
    }

    _onCapturedEvent(_actor, event) {
        if (event.type() === Clutter.EventType.KEY_PRESS && event.get_key_symbol() === Clutter.KEY_Escape) {
            this.close();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _reposition() {
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        this._root.set_position(monitor.x, monitor.y);
        this._root.set_size(monitor.width, monitor.height);
        this._dim.set_position(0, 0);
        this._dim.set_size(monitor.width, monitor.height);
    }

    // ---- apps / filtering -------------------------------------------------------------

    _loadApps() {
        this._allApps = Gio.AppInfo.get_all()
            .filter(app => app.should_show() && !EXCLUDED_DESKTOP_IDS.has(app.get_id()))
            .sort((a, b) => a.get_name().localeCompare(b.get_name()));
        this._refresh();
    }

    _selectCategory(tab) {
        this._category = tab;
        this._categoryButtons.forEach((btn, i) => {
            btn[CATEGORY_TABS[i] === tab ? 'add_style_class_name' : 'remove_style_class_name']('selected');
        });
        this._refresh();
    }

    _filteredApps() {
        let apps = this._allApps;
        const [, categoryRe] = this._category;
        if (categoryRe) {
            apps = apps.filter((app) => {
                try {
                    return categoryRe.test(app.get_categories?.() ?? '');
                } catch (e) {
                    return false;
                }
            });
        }
        const query = this._searchEntry.get_text().trim().toLowerCase();
        if (query) {
            apps = apps.filter((app) => {
                const name = app.get_name().toLowerCase();
                const generic = (app.get_generic_name?.() ?? '').toLowerCase();
                return name.includes(query) || generic.includes(query);
            });
        }
        return apps;
    }

    _refresh() {
        const apps = this._filteredApps();
        this._grid.destroy_all_children();
        const grid = this._grid.layout_manager;
        apps.forEach((appInfo, i) => {
            grid.attach(this._createAppTile(appInfo), i % COLUMNS, Math.floor(i / COLUMNS), 1, 1);
        });
        const rows = Math.max(1, Math.ceil(apps.length / COLUMNS));
        this._grid.height = rows * CELL_HEIGHT;
    }

    _createAppTile(appInfo) {
        const tile = new St.Button({
            style_class: 'macos-applauncher-tile',
            width: CELL_WIDTH,
            height: CELL_HEIGHT,
        });
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        box.spacing = 6; // not constructible -- see the search bar comment above
        box.add_child(new St.Icon({gicon: appInfo.get_icon(), icon_size: ICON_SIZE}));
        box.add_child(new St.Label({
            text: appInfo.get_name(),
            style_class: 'macos-applauncher-label',
            x_align: Clutter.ActorAlign.CENTER,
        }));
        tile.set_child(box);
        tile.connect('clicked', () => {
            this.close();
            appInfo.launch([], null);
        });
        return tile;
    }

    destroy() {
        // Don't leave the dock faded out/hidden behind if the extension gets disabled
        // while the launcher happened to be open.
        if (this._open && this._dockActor) {
            this._dockActor.remove_all_transitions();
            this._dockActor.opacity = 255;
            this._dockActor.visible = true;
        }

        if (this._capturedEventId) {
            global.stage.disconnect(this._capturedEventId);
            this._capturedEventId = 0;
        }
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._exportedObject) {
            this._exportedObject.flush();
            this._exportedObject.unexport();
            this._exportedObject = null;
        }
        Main.layoutManager.removeChrome(this._root);
        this._root.destroy();
        this._root = null;
    }
}
