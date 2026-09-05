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
import {PowerStatusWatcher, formatTimeToFull} from './powerStatus.js';
import {LocalSendWatcher} from './localSendWatcher.js';

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

const FADE_IN_MS = 220;
const FADE_OUT_MS = 200;
// How small the pill shrinks to on its way out (and grows from on its way in) -- a flat
// opacity-only cross-fade was the "clunky" part: the pill stayed full-size the whole time and
// just faded, no actual shrink/grow motion the way a real pop in/out reads as smooth.
const POP_SCALE = 0.65;

// Media's own "now playing" indicator -- unlike the dictation waveform, MPRIS gives no real
// audio-level data to drive this with (there's no equivalent of peachos-dictation-daemon's
// Level signal for whatever's coming out of Spotify/Firefox/etc), so this is deliberately a
// canned animation, the same way a plain "now playing" equalizer icon anywhere else is -- it
// means "something is actively playing", not "here is its literal waveform".
const MEDIA_EQ_BAR_COUNT = 4;
const MEDIA_EQ_MIN_HEIGHT = 2;
const MEDIA_EQ_MAX_HEIGHT = 8;
const MEDIA_EQ_TICK_MS = 220;

// One-off toasts (charging started, a file landed via LocalSend) briefly take over the pill
// and then hand it back -- explicitly requested to be brief, not a persistent HUD: "I would
// only want the pill to show up for like a second... then disappearing".
const TRANSIENT_TOAST_MS = 3000;

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

// MPRIS has no notion of "which window" owns a player -- there's no reliable way to know
// exactly which browser window/tab a given org.mpris.MediaPlayer2.* bus name belongs to (most
// browsers expose one player per process, not per tab or per window). This is a coarse but
// workable approximation instead: guess the owning app's name from its bus name (e.g.
// 'org.mpris.MediaPlayer2.firefox.instance_1_234' -> 'firefox') and match it against the
// focused window's own WM_CLASS. Good enough for "hide the pill while I'm actually looking at
// the app that's playing" in the common single-window case; imprecise if someone has two
// windows of the same app open, one playing and one not -- there's no fixing that without
// real per-window media session info, which Linux desktops don't have.
function guessAppNameFromBusName(busName) {
    if (!busName)
        return null;
    const withoutPrefix = busName.replace(/^org\.mpris\.MediaPlayer2\./, '');
    const withoutInstance = withoutPrefix.split(/\.instance/i)[0];
    return withoutInstance.toLowerCase();
}

export class DynamicIsland {
    constructor() {
        this._recordingState = 'idle';
        this._mediaState = null;
        this._levelHistory = [];
        this._elapsedTimerId = 0;
        this._listenStartUs = 0;
        this._transientActive = false;
        this._transientTimerId = 0;
        this._transientStyleClass = null;

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
            this._setMediaEqActive(Boolean(state?.isPlaying));
            this._sync();
        });

        // Re-evaluate every time focus changes -- the media pill's own visibility depends on
        // whether the playing app's window currently has focus (see _isMediaWindowFocused()).
        this._focusChangedId = global.display.connect('notify::focus-window', () => this._sync());

        this._powerWatcher = new PowerStatusWatcher(timeToFullSeconds => {
            const suffix = formatTimeToFull(timeToFullSeconds);
            this._showTransient(
                'battery-good-charging-symbolic',
                suffix ? `Charging — ${suffix}` : 'Charging',
                'dynamic-island--charging');
        });

        this._localSendWatcher = new LocalSendWatcher(filename => {
            this._showTransient('folder-download-symbolic', `Received "${filename}"`, 'dynamic-island--localsend');
        });

        this._sync();
    }

    get container() {
        return this._container;
    }

    _buildActor() {
        this._container = new St.BoxLayout({
            style_class: 'dynamic-island', vertical: false, visible: false, opacity: 0,
            // Main.panel._centerBox stretches its children to fill its own (full panel)
            // height by default -- the exact same St.BoxLayout behavior already found and
            // fixed for the waveform bars, just never applied to the outer pill itself. This
            // is why repeated padding/font-size trims never actually made the pill shorter:
            // the container was being stretched back to full panel height regardless of what
            // its own CSS asked for. y_expand: false + y_align: CENTER lets the pill's real,
            // small content size actually win.
            y_expand: false, y_align: Clutter.ActorAlign.CENTER,
        });
        // Center pivot -- without this, scale transforms in _setVisible() shrink/grow toward
        // the top-left corner instead of the middle, which reads as lopsided rather than a
        // clean pop in/out.
        this._container.set_pivot_point(0.5, 0.5);

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
        this._mediaEqBars = [];
        this._mediaEqBox = new St.BoxLayout({
            style_class: 'dynamic-island-waveform', vertical: false, y_align: Clutter.ActorAlign.CENTER,
        });
        for (let i = 0; i < MEDIA_EQ_BAR_COUNT; i++) {
            const bar = new St.Widget({
                style_class: 'dynamic-island-eq-bar', height: MEDIA_EQ_MIN_HEIGHT,
                y_align: Clutter.ActorAlign.CENTER, y_expand: false,
            });
            this._mediaEqBox.add_child(bar);
            this._mediaEqBars.push(bar);
        }
        this._mediaBox.add_child(this._mediaEqBox);
        this._container.add_child(this._mediaBox);

        this._transientBox = new St.BoxLayout({
            style_class: 'dynamic-island-transient', vertical: false, visible: false,
        });
        this._transientIcon = new St.Icon({
            icon_size: 13, style_class: 'dynamic-island-transient-icon', y_align: Clutter.ActorAlign.CENTER,
        });
        this._transientLabel = new St.Label({
            style_class: 'dynamic-island-transient-label', y_align: Clutter.ActorAlign.CENTER,
        });
        this._transientBox.add_child(this._transientIcon);
        this._transientBox.add_child(this._transientLabel);
        this._container.add_child(this._transientBox);
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

    // ---- Media "now playing" equalizer (canned -- see MEDIA_EQ_* constants' own comment) ----

    _setMediaEqActive(active) {
        if (active === Boolean(this._mediaEqTimerId))
            return;
        if (active) {
            this._tickMediaEq();
            this._mediaEqTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MEDIA_EQ_TICK_MS, () => {
                this._tickMediaEq();
                return GLib.SOURCE_CONTINUE;
            });
        } else if (this._mediaEqTimerId) {
            GLib.source_remove(this._mediaEqTimerId);
            this._mediaEqTimerId = 0;
            for (const bar of this._mediaEqBars)
                bar.ease({height: MEDIA_EQ_MIN_HEIGHT, duration: 150, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        }
    }

    _tickMediaEq() {
        for (const bar of this._mediaEqBars) {
            const height = MEDIA_EQ_MIN_HEIGHT + Math.random() * (MEDIA_EQ_MAX_HEIGHT - MEDIA_EQ_MIN_HEIGHT);
            bar.ease({height, duration: MEDIA_EQ_TICK_MS, mode: Clutter.AnimationMode.EASE_IN_OUT_SINE});
        }
    }

    // ---- "Am I already looking at whatever's playing?" (see guessAppNameFromBusName's own
    // docstring for the approximation this relies on) --------------------------------------

    _isMediaWindowFocused() {
        const appGuess = guessAppNameFromBusName(this._mediaState?.busName);
        if (!appGuess)
            return false;
        const focusWindow = global.display.get_focus_window();
        const wmClass = focusWindow?.get_wm_class()?.toLowerCase();
        return Boolean(wmClass && wmClass.includes(appGuess));
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

    // ---- One-off toasts (charging started, LocalSend receipt) -- briefly take over the pill,
    // then hand it back to whatever _sync() would otherwise be showing. Explicitly requested
    // to be a toast, not a persistent status: "I would only want the pill to show up for like
    // a second... then disappearing" -- unlike dictation/media there's no ongoing state here,
    // just a moment-in-time event, so a fixed-duration timer (not a state machine) is honest.

    _showTransient(iconName, text, styleClass) {
        // Never interrupt an active recording with a toast -- dictation is something the user
        // deliberately started and is mid-way through; a charger toast stealing the pill out
        // from under them would be worse than just skipping it this once.
        if (this._recordingState !== 'idle')
            return;

        if (this._transientTimerId) {
            GLib.source_remove(this._transientTimerId);
            this._transientTimerId = 0;
        }
        if (this._transientStyleClass)
            this._container.remove_style_class_name(this._transientStyleClass);

        this._transientIcon.icon_name = iconName;
        this._transientLabel.set_text(text);
        this._transientStyleClass = styleClass;
        this._container.add_style_class_name(styleClass);

        this._transientActive = true;
        this._dictationBox.visible = false;
        this._mediaBox.visible = false;
        this._transientBox.visible = true;
        this._setVisible(true);

        this._transientTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TRANSIENT_TOAST_MS, () => {
            this._transientTimerId = 0;
            this._clearTransient();
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    _clearTransient() {
        if (this._transientTimerId) {
            GLib.source_remove(this._transientTimerId);
            this._transientTimerId = 0;
        }
        if (this._transientStyleClass) {
            this._container.remove_style_class_name(this._transientStyleClass);
            this._transientStyleClass = null;
        }
        this._transientActive = false;
        this._transientBox.visible = false;
    }

    // ---- State -> appearance ------------------------------------------------------------

    _sync() {
        const dictationActive = this._recordingState !== 'idle';
        // Explicit request: don't show the media pill while the user is already looking at
        // whatever's playing (its own window has focus) -- only once they've switched to
        // something else is it worth a glanceable reminder.
        const mediaActive = Boolean(this._mediaState?.isActive) && !this._isMediaWindowFocused();

        // Dictation always wins immediately, even mid-toast (see _showTransient's own guard
        // for the other direction: a toast never starts while already dictating).
        if (dictationActive && this._transientActive)
            this._clearTransient();

        // A toast owns the pill until its own timer fires -- leave media/dictation visibility
        // alone in the meantime so it doesn't get clobbered by e.g. a media-focus change.
        if (this._transientActive)
            return;

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
        // Kill any in-flight pop animation before starting the opposite one -- rapidly
        // flipping states (e.g. bouncing focus between two windows) without this would let a
        // still-running shrink and a freshly-started grow fight over the same scale/opacity
        // properties, which is its own kind of "clunky".
        this._container.remove_all_transitions();
        if (shouldShow) {
            this._container.visible = true;
            this._container.set_scale(POP_SCALE, POP_SCALE);
            this._container.opacity = 0;
            this._container.ease({
                opacity: 255, scale_x: 1, scale_y: 1,
                duration: FADE_IN_MS, mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
            });
        } else {
            this._container.ease({
                opacity: 0, scale_x: POP_SCALE, scale_y: POP_SCALE,
                duration: FADE_OUT_MS, mode: Clutter.AnimationMode.EASE_IN_CUBIC,
                onComplete: () => {
                    if (this._container)
                        this._container.visible = false;
                },
            });
        }
    }

    destroy() {
        this._stopElapsedTimer();
        if (this._transientTimerId) {
            GLib.source_remove(this._transientTimerId);
            this._transientTimerId = 0;
        }
        this._powerWatcher?.destroy();
        this._powerWatcher = null;
        this._localSendWatcher?.destroy();
        this._localSendWatcher = null;
        if (this._mediaEqTimerId) {
            GLib.source_remove(this._mediaEqTimerId);
            this._mediaEqTimerId = 0;
        }
        if (this._focusChangedId) {
            global.display.disconnect(this._focusChangedId);
            this._focusChangedId = 0;
        }
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
