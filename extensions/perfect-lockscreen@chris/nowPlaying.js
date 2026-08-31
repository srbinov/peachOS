// Now Playing widget for the lock screen: shows whatever's currently playing over MPRIS
// (Spotify, a browser tab, etc.) between the clock and the password prompt, with transport
// controls -- same idea as macOS's own lock screen Now Playing card.
//
// The MPRIS-reading half (extractMetadata/parseMediaState/MediaPlayerController) is a
// deliberate near-verbatim port of macOS-TopBar-Gnome's lib/mprisData.js and
// lib/mediaPlayerController.js, not a reimplementation -- that code is already
// crash-hardened against two real, previously-hit bugs (a raw GLib.Variant leaking into
// St.Label.text and aborting the Shell, and a delayed album-art fetch resurrecting stale
// metadata after a track change), and this is a separate GNOME Shell extension/repo with
// no supported way to import another extension's modules directly, so duplicating the
// proven logic is the right call here rather than reinventing it or reaching across
// extensions.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';
import Soup from 'gi://Soup?version=3.0';

const MPRIS_PREFIX = 'org.mpris.MediaPlayer2.';
const PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player';

/** @param {{'xesam:title'?: string, 'xesam:artist'?: string[]|string, 'mpris:artUrl'?: string}} metadata */
function extractMetadata(metadata) {
    const artistRaw = metadata['xesam:artist'];
    let artist = null;
    if (Array.isArray(artistRaw) && artistRaw.length > 0)
        artist = String(artistRaw[0]);
    else if (typeof artistRaw === 'string' && artistRaw.length > 0)
        artist = artistRaw;

    const title = metadata['xesam:title'];
    const artUrl = metadata['mpris:artUrl'];

    return {
        title: title != null && title !== '' ? String(title) : null,
        artist,
        artUrl: artUrl != null && artUrl !== '' ? String(artUrl) : null,
    };
}

/**
 * @param {{title: string|null, artist: string|null, artUrl: string|null, playbackStatus: string|null,
 *   canGoNext: boolean, canGoPrevious: boolean, canPlay: boolean, canPause: boolean}} props
 */
function parseMediaState(props) {
    const isPlaying = props.playbackStatus === 'Playing';
    const isActive = isPlaying || props.playbackStatus === 'Paused';

    return {
        isActive,
        isPlaying,
        title: props.title ?? '',
        artist: props.artist ?? '',
        artUrl: props.artUrl ?? null,
        canGoNext: Boolean(props.canGoNext),
        canGoPrevious: Boolean(props.canGoPrevious),
        canTogglePlayback: isPlaying ? Boolean(props.canPause) : Boolean(props.canPlay),
    };
}

class MediaPlayerController {
    constructor(onChange) {
        this._onChange = onChange;
        this._players = new Map(); // busName -> {proxy, propsChangedId, lastActive}
        this._artCache = new Map(); // artUrl -> Gio.Icon
        this._soupSession = new Soup.Session();
        this._selectedBusName = null;
        this._isDestroyed = false;

        this._discoverExistingPlayers();
        this._watchForNewPlayers();
        this._emitIdle();
    }

    _discoverExistingPlayers() {
        Gio.DBus.session.call(
            'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ListNames',
            null, new GLib.VariantType('(as)'), Gio.DBusCallFlags.NONE, -1, null,
            (source, result) => {
                try {
                    const reply = source.call_finish(result);
                    if (this._isDestroyed)
                        return;
                    const [names] = reply.deep_unpack();
                    names.filter(name => name.startsWith(MPRIS_PREFIX)).forEach(name => this._trackPlayer(name));
                } catch (e) {
                    logError(e, '[perfect-lockscreen] now playing: failed to list MPRIS players');
                }
            });
    }

    _watchForNewPlayers() {
        this._nameOwnerChangedId = Gio.DBus.session.signal_subscribe(
            'org.freedesktop.DBus', 'org.freedesktop.DBus', 'NameOwnerChanged', '/org/freedesktop/DBus',
            null, Gio.DBusSignalFlags.NONE,
            (connection, sender, path, iface, signal, params) => {
                const [name, oldOwner, newOwner] = params.deep_unpack();
                if (!name.startsWith(MPRIS_PREFIX))
                    return;
                if (newOwner)
                    this._trackPlayer(name);
                else
                    this._untrackPlayer(name);
            });
    }

    _trackPlayer(busName) {
        if (this._players.has(busName) || this._isDestroyed)
            return;

        this._players.set(busName, {proxy: null, propsChangedId: 0, lastActive: 0});

        Gio.DBusProxy.new(
            Gio.DBus.session, Gio.DBusProxyFlags.NONE, null,
            busName, '/org/mpris/MediaPlayer2', PLAYER_IFACE, null,
            (source, result) => {
                try {
                    const proxy = Gio.DBusProxy.new_finish(result);
                    const entry = this._players.get(busName);
                    if (this._isDestroyed || !entry)
                        return;
                    entry.proxy = proxy;
                    entry.propsChangedId = proxy.connect('g-properties-changed', () => this._onPlayerChanged(busName));
                    this._onPlayerChanged(busName);
                } catch (e) {
                    logError(e, `[perfect-lockscreen] now playing: failed to connect to MPRIS player ${busName}`);
                }
            });
    }

    _untrackPlayer(busName) {
        const entry = this._players.get(busName);
        if (!entry)
            return;
        if (entry.proxy && entry.propsChangedId)
            entry.proxy.disconnect(entry.propsChangedId);
        this._players.delete(busName);
        this._recompute();
    }

    _onPlayerChanged(busName) {
        const entry = this._players.get(busName);
        if (!entry || !entry.proxy)
            return;
        entry.lastActive = GLib.get_monotonic_time();
        this._recompute();
    }

    _recompute() {
        try {
            let selectedName = null;
            let selectedEntry = null;

            for (const [name, entry] of this._players.entries()) {
                if (!entry.proxy)
                    continue;
                const status = entry.proxy.get_cached_property('PlaybackStatus')?.unpack();
                if (status !== 'Playing' && status !== 'Paused')
                    continue;
                if (!selectedEntry || entry.lastActive > selectedEntry.lastActive) {
                    selectedEntry = entry;
                    selectedName = name;
                }
            }

            this._selectedBusName = selectedName;

            if (!selectedEntry) {
                this._emitIdle();
                return;
            }

            const {state, artUrl} = this._buildState(selectedEntry.proxy);

            this._onChange({...state, artIcon: artUrl ? (this._artCache.get(artUrl) ?? null) : null});

            if (artUrl && !this._artCache.has(artUrl))
                this._loadArt(artUrl, selectedName);
        } catch (e) {
            logError(e, '[perfect-lockscreen] now playing: failed to recompute media state');
            this._emitIdle();
        }
    }

    _buildState(proxy) {
        const metadataVariant = proxy.get_cached_property('Metadata');
        const unpackedMetadata = {};
        if (metadataVariant) {
            const rawMetadata = metadataVariant.deep_unpack();
            for (const [key, value] of Object.entries(rawMetadata))
                unpackedMetadata[key] = value instanceof GLib.Variant ? value.deep_unpack() : value;
        }

        const {title, artist, artUrl} = extractMetadata(unpackedMetadata);

        const state = parseMediaState({
            title, artist, artUrl,
            playbackStatus: proxy.get_cached_property('PlaybackStatus')?.unpack() ?? null,
            canGoNext: proxy.get_cached_property('CanGoNext')?.unpack() ?? false,
            canGoPrevious: proxy.get_cached_property('CanGoPrevious')?.unpack() ?? false,
            canPlay: proxy.get_cached_property('CanPlay')?.unpack() ?? false,
            canPause: proxy.get_cached_property('CanPause')?.unpack() ?? false,
        });

        return {state, artUrl};
    }

    _emitIdle() {
        const state = parseMediaState({
            title: null, artist: null, artUrl: null, playbackStatus: null,
            canGoNext: false, canGoPrevious: false, canPlay: false, canPause: false,
        });
        this._onChange({...state, artIcon: null});
    }

    _loadArt(url, busName) {
        if (url.startsWith('file://')) {
            const icon = Gio.icon_new_for_string(url);
            this._artCache.set(url, icon);
            this._applyArtIfRelevant(url, busName, icon);
            return;
        }

        if (!url.startsWith('http://') && !url.startsWith('https://'))
            return;

        const message = Soup.Message.new('GET', url);
        this._soupSession.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (source, result) => {
            try {
                const bytes = source.send_and_read_finish(result);
                if (this._isDestroyed || message.get_status() !== Soup.Status.OK)
                    return;
                const icon = Gio.BytesIcon.new(bytes);
                this._artCache.set(url, icon);
                this._applyArtIfRelevant(url, busName, icon);
            } catch (e) {
                logError(e, `[perfect-lockscreen] now playing: failed to fetch media art from ${url}`);
            }
        });
    }

    _applyArtIfRelevant(url, busName, icon) {
        if (this._isDestroyed || this._selectedBusName !== busName)
            return;

        const entry = this._players.get(busName);
        if (!entry?.proxy)
            return;

        const {state, artUrl} = this._buildState(entry.proxy);
        if (artUrl !== url)
            return;

        this._onChange({...state, artIcon: icon});
    }

    previous() {
        this._callPlayerMethod('Previous');
    }

    next() {
        this._callPlayerMethod('Next');
    }

    playPause() {
        this._callPlayerMethod('PlayPause');
    }

    _callPlayerMethod(method) {
        const entry = this._selectedBusName ? this._players.get(this._selectedBusName) : null;
        if (!entry?.proxy)
            return;
        entry.proxy.call(method, null, Gio.DBusCallFlags.NONE, -1, null, (source, result) => {
            try {
                source.call_finish(result);
            } catch (e) {
                logError(e, `[perfect-lockscreen] now playing: MPRIS ${method} failed`);
            }
        });
    }

    destroy() {
        this._isDestroyed = true;
        if (this._nameOwnerChangedId)
            Gio.DBus.session.signal_unsubscribe(this._nameOwnerChangedId);
        this._soupSession.abort();
        for (const entry of this._players.values()) {
            if (entry.proxy && entry.propsChangedId)
                entry.proxy.disconnect(entry.propsChangedId);
        }
        this._players.clear();
    }
}

const ART_SIZE = 44;
const BUTTON_ICON_SIZE = 12;

function makeTransportButton(iconName, onActivate) {
    const button = new St.Button({
        style_class: 'wack-now-playing-button', reactive: true, can_focus: true, track_hover: true,
    });
    button.connect('clicked', onActivate);
    const icon = new St.Icon({
        icon_name: iconName, icon_size: BUTTON_ICON_SIZE,
        x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER,
    });
    button.set_child(icon);
    return {button, icon};
}

/**
 * The card itself, kept separate from MediaPlayerController so the extension can own that
 * controller's lifecycle explicitly if it ever needs to (it doesn't currently -- this class
 * owns both, same as controlCenterIndicator.js's own media card does for the top bar).
 */
export class NowPlayingWidget {
    constructor() {
        this.actor = new St.BoxLayout({
            style_class: 'wack-now-playing', vertical: false, reactive: true,
            visible: false, opacity: 0,
        });
        this.actor.set_pivot_point(0.5, 0.5);

        this._artBin = new St.Bin({style_class: 'wack-now-playing-art', x_align: Clutter.ActorAlign.START});
        this._artIcon = new St.Icon({icon_name: 'audio-x-generic-symbolic', icon_size: ART_SIZE});
        this._artBin.set_child(this._artIcon);
        this.actor.add_child(this._artBin);

        const textCol = new St.BoxLayout({
            vertical: true, style_class: 'wack-now-playing-text', x_expand: true, y_align: Clutter.ActorAlign.CENTER,
        });
        this._titleLabel = new St.Label({style_class: 'wack-now-playing-title', text: ''});
        this._titleLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this._artistLabel = new St.Label({style_class: 'wack-now-playing-artist', text: ''});
        this._artistLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        textCol.add_child(this._titleLabel);
        textCol.add_child(this._artistLabel);
        this.actor.add_child(textCol);

        const transportRow = new St.BoxLayout({style_class: 'wack-now-playing-transport', y_align: Clutter.ActorAlign.CENTER});
        const prev = makeTransportButton('media-skip-backward-symbolic', () => this._controller.previous());
        const playPause = makeTransportButton('media-playback-start-symbolic', () => this._controller.playPause());
        const next = makeTransportButton('media-skip-forward-symbolic', () => this._controller.next());
        this._prevButton = prev.button;
        this._playPauseButton = playPause.button;
        this._playPauseIcon = playPause.icon;
        this._nextButton = next.button;
        transportRow.add_child(this._prevButton);
        transportRow.add_child(this._playPauseButton);
        transportRow.add_child(this._nextButton);
        this.actor.add_child(transportRow);

        this._visible = false;
        this._controller = new MediaPlayerController(state => this._update(state));
    }

    _update(state) {
        const shouldShow = state.isActive && (state.title || state.artist);

        this._titleLabel.text = state.title || 'Unknown Title';
        this._artistLabel.text = state.artist || '';
        this._artistLabel.visible = Boolean(state.artist);

        this._artIcon.gicon = state.artIcon ?? null;
        this._artIcon.icon_name = state.artIcon ? null : 'audio-x-generic-symbolic';

        this._playPauseIcon.icon_name = state.isPlaying
            ? 'media-playback-pause-symbolic' : 'media-playback-start-symbolic';
        this._prevButton.reactive = state.canGoPrevious;
        this._prevButton.opacity = state.canGoPrevious ? 255 : 90;
        this._nextButton.reactive = state.canGoNext;
        this._nextButton.opacity = state.canGoNext ? 255 : 90;
        this._playPauseButton.reactive = state.canTogglePlayback;
        this._playPauseButton.opacity = state.canTogglePlayback ? 255 : 90;

        if (shouldShow === this._visible)
            return;
        this._visible = shouldShow;

        this.actor.remove_all_transitions();
        if (shouldShow) {
            this.actor.visible = true;
            this.actor.scale_x = 0.96;
            this.actor.scale_y = 0.96;
            this.actor.ease({
                opacity: 255, scale_x: 1, scale_y: 1,
                duration: 220, mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        } else {
            this.actor.ease({
                opacity: 0, scale_x: 0.96, scale_y: 0.96,
                duration: 180, mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onStopped: () => {
                    this.actor.visible = false;
                },
            });
        }
    }

    destroy() {
        this._controller?.destroy();
        this._controller = null;
        this.actor.destroy();
        this.actor = null;
    }
}
