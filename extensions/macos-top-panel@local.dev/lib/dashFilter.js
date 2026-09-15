import Shell from 'gi://Shell';

// peachySearch (peachOS's Spotlight-equivalent) should never show a dock/dash icon while
// running, the same way real Spotlight has no Dock presence on macOS. The standard GTK-level
// signals for this -- skip_taskbar_hint, type_hint=UTILITY (both set in ulauncher_window.py) --
// don't actually reach Mutter here: verified directly by removing peachySearch's installed
// .desktop file entirely (which should prevent any app association at all) and the dock *still*
// showed an icon, using the window's own icon_name property. That means GNOME Shell falls back
// to a synthetic "windowless app" wrapper for the untracked window rather than skipping it, and
// the skip-taskbar/window-type hints GTK3 is supposed to relay over Wayland simply aren't
// arriving -- consistent with GTK3's Wayland clipboard backend also silently not working
// earlier in this project. So: don't rely on the window announcing its own hint: filter
// Shell.AppSystem's public, version-stable get_running() API directly, which is what both the
// stock GNOME Overview dash and dash2dock-lite (which reuses Main.overview.dash verbatim rather
// than reimplementing its own app enumeration) build their running-apps icon list from.

const PEACHY_SEARCH_TITLE = 'peachySearch';
const ABOUT_WINDOW_TITLE = 'About This PC';

// App IDs that are peachOS UI surfaces, not real apps, and must never take a dock
// slot while open (same reasoning as peachySearch: their windows can't reliably
// announce skip-taskbar over Wayland, so filter Shell.AppSystem's list directly).
//   - io.ulauncher.Ulauncher : peachySearch (Spotlight)
//   - com.github.kemma.KiwiMenu.About : the "About This PC" window spawned from the
//     KiwiMenu (aboutWindow.js) -- a transient info panel, not an application
const NON_APP_ID_PREFIXES = [
    'io.ulauncher.Ulauncher',
    'com.github.kemma.KiwiMenu',
];

function isNonAppSurface(app) {
    const id = app.get_id() ?? '';
    if (NON_APP_ID_PREFIXES.some(p => id === p || id === `${p}.desktop` || id.startsWith(`${p}.`)))
        return true;
    const windows = app.get_windows ? app.get_windows() : [];
    // The id-prefix check above is the reliable path, but it depends on WindowTracker
    // actually correlating the window back to the com.github.kemma.KiwiMenu.About app-id
    // -- confirmed live to sometimes fail (aboutWindow.js has no installed .desktop file,
    // so WindowTracker occasionally falls back to a synthetic wrapper keyed on the
    // interpreter, "GJS", instead). Title/wm_class are a second, independent signal that
    // doesn't depend on that correlation succeeding.
    return windows.some(w => {
        const title = w.get_title?.() ?? '';
        if (title === PEACHY_SEARCH_TITLE || title === ABOUT_WINDOW_TITLE)
            return true;
        const wmClass = (w.get_wm_class?.() ?? '').toLowerCase();
        return wmClass.includes('kiwimenu');
    });
}

let _originalGetRunning = null;

export function installDashFilter() {
    const appSystem = Shell.AppSystem.get_default();
    if (_originalGetRunning)
        return; // already installed
    _originalGetRunning = appSystem.get_running.bind(appSystem);
    appSystem.get_running = () => _originalGetRunning().filter(app => !isNonAppSurface(app));
}

export function uninstallDashFilter() {
    if (!_originalGetRunning)
        return;
    Shell.AppSystem.get_default().get_running = _originalGetRunning;
    _originalGetRunning = null;
}
