// lib/dynamicIsland.js
//
// A center-of-the-top-bar pill, mirroring iOS's Dynamic Island in spirit but scoped to what
// actually has a real, live data source on this desktop: Peach Intelligence's own recording
// state (a waveform driven by the daemon's real, live microphone level -- see _onAudioLevel(),
// not a canned animation -- plus a real elapsed-time counter) and media playback (MPRIS, via
// the exact same MediaPlayerController controlCenterIndicator.js's own media card already
// uses -- a second, independent instance here). Deliberately NOT attempted: calls, turn-by-
// turn navigation, ride-share/delivery tracking, Face ID -- none of those have a real backing
// service on a Linux desktop the way MPRIS/this extension's own gsettings do, and a fake stub
// would just be decoration with no data behind it.
//
// Styled directly off real Dynamic Island reference screenshots (voice memo, phone call,
// Focus): always a fixed near-black pill, never adapting to the bar's own light/dark
// foreground the way every other indicator in this stylesheet does -- the real thing doesn't
// either, it's tied to the physical camera cutout, always black -- with a bright per-context
// accent color for whatever's actually active (red for recording, matching both the voice-
// memo and phone-call references) rather than a single foreground/background swap.
//
// Hidden (faded out) whenever nothing is active; Main.panel._centerBox already center-aligns
// its children in the panel, so no manual positioning math is needed the way the old floating
// pill (peachos-dictation@peachos's own, before this) required.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {MediaPlayerController} from './mediaPlayerController.js';

const DICTATION_SCHEMA_ID = 'org.gnome.shell.extensions.peachos-dictation';
const DAEMON_BUS_NAME = 'org.peachos.DictationDaemon';
const DAEMON_OBJECT_PATH = '/org/peachos/DictationDaemon';

const WAVEFORM_BAR_COUNT = 5;
const WAVEFORM_MIN_HEIGHT = 2;
const WAVEFORM_MAX_HEIGHT = 8;
// How long each bar takes to ease to a newly-received level -- matched to roughly the
// daemon's own emission cadence (LEVEL_EMIT_INTERVAL_S, ~80ms) so one bar's motion finishes
// right as the next value arrives, instead of visibly lagging behind or snapping.
const LEVEL_EASE_MS = 90;
const WAVEFORM_RESET_MS = 120;

const FADE_IN_MS = 150;
const FADE_OUT_MS = 130;

// 'listening' shows a real elapsed-time counter instead of text (see the voice-memo
// reference: no "Listening…" label at all, just the waveform and a running clock).
const TRANSIENT_LABELS = {
    transcribing: 'Transcribing…',
    error: "Couldn't transcribe",
};

function optionalSettings(schemaId) {
    // Same guard the Settings app's own _optional_settings() uses -- this extension can be
    // enabled independently of peachos-dictation@peachos (or on a machine that hasn't
    // re-provisioned since dictation was added), and a raw `new Gio.Settings({schema_id})`
    // against a schema that isn't registered aborts the whole process instead of raising.
    const source = Gio.SettingsSchemaSource.get_default();
    if (!source || !source.lookup(schemaId, true))
        return null;
    return new Gio.Settings({schema_id: schemaId});
}

function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

export class DynamicIsland {
    constructor() {
        this._recordingState = 'idle';
        this._mediaState = null;
        this._levelHistory = [];
        this._elapsedTimerId = 0;
        this._listenStartUs = 0;

        this._buildActor();
        this._subscribeToDaemon();

        this._dictationSettings = optionalSettings(DICTATION_SCHEMA_ID);
        if (this._dictationSettings) {
            this._recordingState = this._dictationSettings.get_string('recording-state');
            this._recordingChangedId = this._dictationSettings.connect('changed::recording-state', () => {
                const previous = this._recordingState;
                this._recordingState = this._dictationSettings.get_string('recording-state');
                if (this._recordingState !== 'listening')
                    this._resetWaveform();
                if (this._recordingState === 'listening' && previous !== 'listening')
                    this._startElapsedTimer();
                else if (this._recordingState !== 'listening')
                    this._stopElapsedTimer();
                this._sync();
            });
        }

        this._mediaController = new MediaPlayerController(state => {
            this._mediaState = state;
            this._sync();
        });

        this._sync();
    }

    get container() {
        return this._container;
    }

    _buildActor() {
        this._container = new St.BoxLayout({
            style_class: 'dynamic-island', vertical: false, visible: false, opacity: 0,
        });

        this._dictationBox = new St.BoxLayout({style_class: 'dynamic-island-dictation', vertical: false});
        this._dictationIcon = new St.Icon({
            icon_name: 'audio-input-microphone-symbolic', icon_size: 12, style_class: 'dynamic-island-mic-icon',
        });
        this._dictationBox.add_child(this._dictationIcon);
        this._waveformBars = [];
        this._waveformBox = new St.BoxLayout({
            style_class: 'dynamic-island-waveform', vertical: false, y_align: Clutter.ActorAlign.CENTER,
        });
        for (let i = 0; i < WAVEFORM_BAR_COUNT; i++) {
            // St.BoxLayout stretches children to fill its own allocated height by default
            // (a real bug this fixes -- explicit y_expand: false + y_align: CENTER is what
            // actually lets a bar's own `height` win instead of being re-stretched to match
            // the box/tallest sibling on every layout pass, which is what made the waveform
            // look both "too tall" AND "static": every bar was being stretched back to the
            // same full height regardless of what _onAudioLevel() had just set it to).
            const bar = new St.Widget({
                style_class: 'dynamic-island-waveform-bar', height: WAVEFORM_MIN_HEIGHT,
                y_align: Clutter.ActorAlign.CENTER, y_expand: false,
            });
            this._waveformBox.add_child(bar);
            this._waveformBars.push(bar);
        }
        this._dictationBox.add_child(this._waveformBox);
        this._dictationLabel = new St.Label({style_class: 'dynamic-island-label', y_align: Clutter.ActorAlign.CENTER});
        this._dictationBox.add_child(this._dictationLabel);
        this._elapsedLabel = new St.Label({style_class: 'dynamic-island-elapsed', y_align: Clutter.ActorAlign.CENTER});
        this._dictationBox.add_child(this._elapsedLabel);
        this._container.add_child(this._dictationBox);

        this._mediaBox = new St.BoxLayout({style_class: 'dynamic-island-media', vertical: false});
        this._mediaArt = new St.Icon({
            icon_name: 'audio-x-generic-symbolic', icon_size: 15, style_class: 'dynamic-island-art',
        });
        this._mediaBox.add_child(this._mediaArt);
        const mediaText = new St.BoxLayout({vertical: true, y_align: Clutter.ActorAlign.CENTER});
        this._mediaTitle = new St.Label({style_class: 'dynamic-island-media-title'});
        this._mediaArtist = new St.Label({style_class: 'dynamic-island-media-artist'});
        mediaText.add_child(this._mediaTitle);
        mediaText.add_child(this._mediaArtist);
        this._mediaBox.add_child(mediaText);
        this._container.add_child(this._mediaBox);
    }

    // ---- Real microphone level, from peachos-dictation-daemon's own D-Bus signal ------------

    _subscribeToDaemon() {
        try {
            this._daemonProxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, null,
                DAEMON_BUS_NAME, DAEMON_OBJECT_PATH, DAEMON_BUS_NAME, null,
            );
            this._daemonSignalId = this._daemonProxy.connect('g-signal', (_proxy, _sender, signalName, params) => {
                if (signalName === 'Level')
                    this._onAudioLevel(params.deep_unpack()[0]);
            });
        } catch (e) {
            // No daemon (not installed / not running yet) -- the waveform just stays flat
            // during 'listening', which is a reasonable degrade, not worth surfacing an error.
            logError(e, 'dynamicIsland: failed to connect to peachos-dictation-daemon');
        }
    }

    // One real amplitude reading (0..1, already noise-floored and gamma-curved by the daemon
    // -- see peachos-dictation-daemon's own _emit_level() docstring) becomes the newest bar; a
    // short rolling history slides through the rest, so adjacent bars read as adjacent recent
    // instants (like a trailing oscilloscope trace) instead of five bars all doing the same
    // thing at once.
    _onAudioLevel(level) {
        if (this._recordingState !== 'listening')
            return;
        this._levelHistory.push(level);
        if (this._levelHistory.length > WAVEFORM_BAR_COUNT)
            this._levelHistory.shift();

        const n = this._waveformBars.length;
        for (let i = 0; i < n; i++) {
            const historyIndex = this._levelHistory.length - n + i;
            const v = historyIndex >= 0 ? this._levelHistory[historyIndex] : 0;
            const height = WAVEFORM_MIN_HEIGHT + v * (WAVEFORM_MAX_HEIGHT - WAVEFORM_MIN_HEIGHT);
            this._waveformBars[i].ease({height, duration: LEVEL_EASE_MS, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        }
    }

    _resetWaveform() {
        this._levelHistory = [];
        for (const bar of this._waveformBars)
            bar.ease({height: WAVEFORM_MIN_HEIGHT, duration: WAVEFORM_RESET_MS, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
    }

    // ---- Elapsed-time counter (the 'listening' state's own label -- see the voice-memo
    // reference: no "Listening…" text, just the waveform and a running clock) ----------------

    _startElapsedTimer() {
        this._listenStartUs = GLib.get_monotonic_time();
        this._updateElapsedLabel();
        if (this._elapsedTimerId)
            GLib.source_remove(this._elapsedTimerId);
        this._elapsedTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._updateElapsedLabel();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopElapsedTimer() {
        if (this._elapsedTimerId) {
            GLib.source_remove(this._elapsedTimerId);
            this._elapsedTimerId = 0;
        }
    }

    _updateElapsedLabel() {
        const elapsedSeconds = (GLib.get_monotonic_time() - this._listenStartUs) / 1000000;
        this._elapsedLabel.set_text(formatElapsed(elapsedSeconds));
    }

    // ---- State -> appearance ------------------------------------------------------------

    _sync() {
        const dictationActive = this._recordingState !== 'idle';
        const mediaActive = Boolean(this._mediaState?.isActive);

        this._dictationBox.visible = dictationActive;
        this._mediaBox.visible = !dictationActive && mediaActive;
        this._setVisible(dictationActive || mediaActive);

        if (dictationActive) {
            const listening = this._recordingState === 'listening';
            this._dictationLabel.set_text(TRANSIENT_LABELS[this._recordingState] ?? '');
            this._dictationLabel.visible = !listening;
            this._elapsedLabel.visible = listening;
            this._waveformBox.visible = listening;

            this._container.remove_style_class_name('dynamic-island--error');
            if (this._recordingState === 'error')
                this._container.add_style_class_name('dynamic-island--error');
        }

        if (!dictationActive && mediaActive) {
            this._mediaTitle.set_text(this._mediaState.title || 'Now Playing');
            this._mediaArtist.set_text(this._mediaState.artist || '');
            this._mediaArtist.visible = Boolean(this._mediaState.artist);
            this._mediaArt.gicon = this._mediaState.artIcon ?? null;
            if (!this._mediaState.artIcon)
                this._mediaArt.icon_name = 'audio-x-generic-symbolic';
        }
    }

    _setVisible(shouldShow) {
        if (shouldShow === this._container.visible)
            return;
        if (shouldShow) {
            this._container.visible = true;
            this._container.ease({opacity: 255, duration: FADE_IN_MS, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        } else {
            this._container.ease({
                opacity: 0, duration: FADE_OUT_MS, mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onComplete: () => {
                    if (this._container)
                        this._container.visible = false;
                },
            });
        }
    }

    destroy() {
        this._stopElapsedTimer();
        if (this._daemonSignalId && this._daemonProxy) {
            this._daemonProxy.disconnect(this._daemonSignalId);
            this._daemonSignalId = 0;
        }
        this._daemonProxy = null;
        if (this._recordingChangedId && this._dictationSettings) {
            this._dictationSettings.disconnect(this._recordingChangedId);
            this._recordingChangedId = 0;
        }
        this._dictationSettings = null;
        this._mediaController?.destroy();
        this._mediaController = null;
        this._container?.destroy();
        this._container = null;
    }
}
