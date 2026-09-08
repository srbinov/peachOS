// lib/dynamicIsland.js
//
// A center-of-the-top-bar pill, mirroring iOS's Dynamic Island in spirit but scoped to what
// actually has a real, live data source on this desktop. Every state below is driven by a
// genuine signal -- no stubs, no canned decoration standing in for data that doesn't exist:
//
//   Persistent (the pill stays up for the whole activity):
//     - Peach Intelligence dictation -- waveform driven by the daemon's real microphone level
//       (_onAudioLevel), plus a live elapsed counter
//     - media playback -- MPRIS, via the same MediaPlayerController the Control Center uses
//     - screen recording -- Main.screenshotUI.screencast-in-progress (the shell's own flag)
//
//   One-off toasts (take the pill over for ~3s, then hand it back -- see _showTransient):
//     - charger plugged in / battery low / battery fully charged  (UPower)
//     - Do Not Disturb toggled                                    (org.gnome.desktop.notifications)
//     - power profile changed                                     (power-profiles-daemon)
//     - USB / external drive mounted or ejected                   (Gio.VolumeMonitor)
//     - a Bluetooth device connected or disconnected              (BlueZ)
//     - a screenshot / recording was saved                        (Screenshots folder monitor)
//     - Night Light turned on or off                              (gnome-settings-daemon Color)
//     - a VPN connected or disconnected                           (NetworkManager)
//     - a file arrived over LocalSend                             (Downloads folder monitor)
//
// Deliberately NOT attempted: phone-style calls, turn-by-turn navigation, ride-share/delivery
// tracking, Face ID, a mirror of GNOME Clocks' timer/stopwatch (Clocks persists only the
// preset duration, never live countdown state) -- none have a real backing signal here.
//
// Styled off real Dynamic Island reference screenshots (voice memo, phone call, Focus):
// always a fixed near-black pill, never adapting to the bar's own light/dark foreground --
// the real thing doesn't either, it's tied to the physical camera cutout -- with a bright
// per-context accent color for whatever's active.
//
// Hidden (faded out) whenever nothing is active; Main.panel._centerBox already center-aligns
// its children in the panel, so no manual positioning math is needed the way the old floating
// pill (peachos-dictation@peachos's own, before this) required.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {SpriteAnimation, loadSpriteMeta} from './spriteAnimation.js';
import {MediaPlayerController} from './mediaPlayerController.js';
import {PowerStatusWatcher, formatTimeToFull} from './powerStatus.js';
import {LocalSendWatcher} from './localSendWatcher.js';
import {DndController} from './dndController.js';
import {PowerProfileWatcher, powerProfileLabel, powerProfileIcon} from './powerProfileWatcher.js';
import {VolumeMountWatcher} from './volumeMountWatcher.js';
import {BluetoothWatcher} from './bluetoothWatcher.js';
import {ScreenshotWatcher} from './screenshotWatcher.js';
import {NightLightWatcher} from './nightLightWatcher.js';
import {VpnWatcher} from './vpnWatcher.js';
import {ScreenRecordingWatcher} from './screenRecordingWatcher.js';

const DICTATION_SCHEMA_ID = 'org.gnome.shell.extensions.peachos-dictation';
const DAEMON_BUS_NAME = 'org.peachos.DictationDaemon';
const DAEMON_OBJECT_PATH = '/org/peachos/DictationDaemon';

// Peach Intelligence "listening" waveform: a Lottie voice animation baked to a sprite sheet
// (assets/peach-intelligence-voice.*, from tools/lottie-bake/). The baked loop plays at a
// fixed rate; real mic-level readings from the daemon drive a subtle vertical pulse on top
// (SpriteAnimation.setLevel), so it still visibly reacts to the voice without being a
// literal FFT. Height in px; width follows the sheet's own aspect.
const PI_WAVE_HEIGHT = 18;

// Appear/disappear: the pill unfurls to the RIGHT from its left edge (scale_x from a sliver
// to full) with a small slide-in, and retracts left + shrinks on the way out. Left pivot is
// what makes it read as "expanding rightward" rather than a centered pop.
const APPEAR_MS = 300;
const DISAPPEAR_MS = 220;
const COLLAPSED_SCALE_X = 0.12;  // width the pill grows from / shrinks back to
const COLLAPSED_SCALE_Y = 0.7;   // slight vertical squeeze so a bare line doesn't flash
const SLIDE_IN_PX = 7;           // how far left it starts / ends up, on top of the scale

// Media's own "now playing" indicator -- unlike the dictation waveform, MPRIS gives no real
// audio-level data to drive this with (there's no equivalent of peachos-dictation-daemon's
// Level signal for whatever's coming out of Spotify/Firefox/etc), so this is deliberately a
// canned animation, the same way a plain "now playing" equalizer icon anywhere else is -- it
// means "something is actively playing", not "here is its literal waveform".
const MEDIA_EQ_BAR_COUNT = 4;
const MEDIA_EQ_MIN_HEIGHT = 2;
const MEDIA_EQ_MAX_HEIGHT = 8;
const MEDIA_EQ_TICK_MS = 220;

// One-off toasts (charging started, a file landed via LocalSend, ...) briefly take over the
// pill and then hand it back -- explicitly requested to be brief, not a persistent HUD: "I
// would only want the pill to show up for like a second... then disappearing".
const TRANSIENT_TOAST_MS = 3000;

// Per-context accent colors (iOS system palette). Toasts pass one of these; it tints the
// toast's icon + label and the pill's border for the ~3s it's up, then _clearTransient wipes
// it. Kept as inline style rather than a CSS class per toast type -- one place, easy to add.
const ACCENT = {
    green: '#30D158',
    blue: '#0A84FF',
    purple: '#BF5AF2',
    orange: '#FF9F0A',
    indigo: '#5E5CE6',
    red: '#FF453A',
};

const RECORDING_ELAPSED_TICK_MS = 500;

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
    constructor(extensionPath) {
        this._path = extensionPath;
        this._recordingState = 'idle';
        this._mediaState = null;
        this._transientActive = false;
        this._transientTimerId = 0;
        this._dndInitialized = false;
        this._screenRecording = false;
        this._recElapsedTimerId = 0;
        this._recStartUs = 0;

        this._buildActor();
        this._subscribeToDaemon();

        this._dictationSettings = optionalSettings(DICTATION_SCHEMA_ID);
        if (this._dictationSettings) {
            this._recordingState = this._dictationSettings.get_string('recording-state');
            this._recordingChangedId = this._dictationSettings.connect('changed::recording-state', () => {
                this._recordingState = this._dictationSettings.get_string('recording-state');
                if (this._recordingState !== 'listening')
                    this._piWave?.stop();
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

        this._powerWatcher = new PowerStatusWatcher({
            onChargingStarted: timeToFullSeconds => {
                const suffix = formatTimeToFull(timeToFullSeconds);
                this._showTransient(
                    null, suffix ? `Charging — ${suffix}` : 'Charging',
                    ACCENT.green, {anim: 'charge'});
            },
            onLowBattery: percent =>
                this._showTransient(null, `Low Battery — ${percent}%`, ACCENT.red, {anim: 'lowbat'}),
            onFullyCharged: () =>
                this._showTransient(null, 'Fully Charged', ACCENT.green, {anim: 'charge'}),
        });

        this._localSendWatcher = new LocalSendWatcher(filename => {
            this._showTransient('folder-download-symbolic', `Received "${filename}"`, ACCENT.blue);
        });

        // Do Not Disturb toggled -> a brief toast, on and off. DndController fires its
        // callback once synchronously from its own constructor to report the current state;
        // that first call is the startup value, not a toggle, so it must not toast (the
        // _dndInitialized latch -- undefined/false on that first synchronous call).
        this._dndController = new DndController(({dnd}) => {
            if (!this._dndInitialized) {
                this._dndInitialized = true;
                return;
            }
            this._showTransient(
                'weather-clear-night-symbolic',
                dnd ? 'Do Not Disturb On' : 'Do Not Disturb Off', ACCENT.purple);
        });

        this._powerProfileWatcher = new PowerProfileWatcher(profileId => {
            this._showTransient(powerProfileIcon(profileId), powerProfileLabel(profileId),
                profileId === 'performance' ? ACCENT.orange
                    : profileId === 'power-saver' ? ACCENT.green : ACCENT.indigo);
        });

        this._volumeMountWatcher = new VolumeMountWatcher({
            onMounted: name => this._showTransient('drive-removable-media-symbolic', `${name} connected`, ACCENT.indigo),
            onUnmounted: name => this._showTransient('drive-removable-media-symbolic', `${name} ejected`, ACCENT.indigo),
        });

        this._bluetoothWatcher = new BluetoothWatcher({
            onConnected: name => this._showTransient('bluetooth-active-symbolic', `${name} connected`, ACCENT.blue),
            onDisconnected: name => this._showTransient('bluetooth-symbolic', `${name} disconnected`, ACCENT.blue),
        });

        // Reuse the Control Center screenshot-button icon (camera in a capture
        // frame). screenshot.png is already pure white -- the "white filter" is
        // baked into the asset -- so it reads on the dark pill as-is.
        this._screenshotGicon = Gio.icon_new_for_string(GLib.build_filenamev(
            [this._path, 'icons', 'control-center', 'screenshot.png']));
        this._screenshotWatcher = new ScreenshotWatcher({
            onCaptured: kind => this._showTransient(
                null,
                kind === 'recording' ? 'Recording saved' : 'Screenshot saved',
                ACCENT.indigo, {gicon: this._screenshotGicon, iconSize: 16}),
        });

        this._nightLightWatcher = new NightLightWatcher(active => {
            this._showTransient('night-light-symbolic',
                active ? 'Night Light On' : 'Night Light Off', ACCENT.orange);
        });

        this._vpnWatcher = new VpnWatcher({
            onConnected: name => this._showTransient('network-vpn-symbolic', `${name} connected`, ACCENT.green),
            onDisconnected: name => this._showTransient('network-vpn-symbolic', `${name} disconnected`, ACCENT.green),
        });

        this._recordingWatcher = new ScreenRecordingWatcher(recording => {
            if (recording === this._screenRecording)
                return;
            this._screenRecording = recording;
            if (recording) {
                this._startRecElapsed();
                this._pulseRecordingDot();
            } else {
                this._stopRecElapsed();
            }
            this._sync();
        });
        this._screenRecording = this._recordingWatcher.isRecording;
        if (this._screenRecording) {
            this._startRecElapsed();
            this._pulseRecordingDot();
        }

        this._sync();

        // Slice every baked animation into GL textures while the shell is idle,
        // one sheet per idle pass (each upload briefly blocks), so the first
        // toast that needs one isn't the thing that pays for it.
        this._warmQueue = [this._piWave, ...Object.values(this._toastAnims ?? {})].filter(Boolean);
        this._warmId = GLib.idle_add(GLib.PRIORITY_LOW, () => {
            this._warmQueue.shift()?.warm();
            if (this._warmQueue.length)
                return GLib.SOURCE_CONTINUE;
            this._warmId = 0;
            return GLib.SOURCE_REMOVE;
        });
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
        // Left-edge pivot (vertically centered): scale_x transforms in _setVisible() then
        // grow/shrink the pill toward the RIGHT from its left edge -- the "unfurl right,
        // retract left" motion -- instead of a symmetric centered pop.
        this._container.set_pivot_point(0.0, 0.5);

        this._dictationBox = new St.BoxLayout({
            style_class: 'dynamic-island-dictation', vertical: false, y_align: Clutter.ActorAlign.CENTER,
        });
        // The full-colour Peach Intelligence badge -- the same themed icon the top-bar
        // history dropdown uses (lib/dictationHistoryIndicator.js), reused verbatim.
        this._dictationIcon = new St.Icon({
            icon_name: 'peachos-dictation-topbar', icon_size: 18,
            style_class: 'dynamic-island-pi-icon', y_align: Clutter.ActorAlign.CENTER,
        });
        this._dictationBox.add_child(this._dictationIcon);

        // Baked-Lottie voice waveform (assets/peach-intelligence-voice.*), shown only
        // while actively listening. Missing/broken assets just leave it out -- the icon
        // and any status label still work.
        try {
            const meta = loadSpriteMeta(
                GLib.build_filenamev([this._path, 'assets', 'peach-intelligence-voice.json']));
            this._piWave = new SpriteAnimation(
                GLib.build_filenamev([this._path, 'assets', 'peach-intelligence-voice.png']),
                meta,
                {width: Math.round(PI_WAVE_HEIGHT * meta.cellW / meta.cellH), height: PI_WAVE_HEIGHT});
            this._dictationBox.add_child(this._piWave.actor);
        } catch (e) {
            logError(e, '[macos-top-panel] Peach Intelligence waveform unavailable');
        }

        this._dictationLabel = new St.Label({style_class: 'dynamic-island-label', y_align: Clutter.ActorAlign.CENTER});
        this._dictationBox.add_child(this._dictationLabel);
        this._container.add_child(this._dictationBox);

        this._mediaBox = new St.BoxLayout({
            style_class: 'dynamic-island-media', vertical: false, y_align: Clutter.ActorAlign.CENTER,
        });
        this._mediaArt = new St.Icon({
            icon_name: 'audio-x-generic-symbolic', icon_size: 15, style_class: 'dynamic-island-art',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._mediaBox.add_child(this._mediaArt);
        // One line only -- every pill is now the same (Peach Intelligence) height,
        // so the old stacked title + artist block doesn't fit. Title, ellipsized.
        this._mediaTitle = new St.Label({
            style_class: 'dynamic-island-media-title', y_align: Clutter.ActorAlign.CENTER,
        });
        this._mediaTitle.clutter_text.set({
            single_line_mode: true, ellipsize: 3 /* Pango.EllipsizeMode.END */,
        });
        this._mediaBox.add_child(this._mediaTitle);
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
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._transientIcon = new St.Icon({
            icon_size: 15, style_class: 'dynamic-island-transient-icon', y_align: Clutter.ActorAlign.CENTER,
        });
        this._transientLabel = new St.Label({
            style_class: 'dynamic-island-transient-label', y_align: Clutter.ActorAlign.CENTER,
        });
        this._transientBox.add_child(this._transientIcon);
        this._transientBox.add_child(this._transientLabel);
        this._container.add_child(this._transientBox);

        // Some toasts use a baked-Lottie glyph (assets/*.png, from the icons repo)
        // that draws itself once, instead of the flat symbolic icon. Each sits
        // where _transientIcon is; whichever is active draws, the rest hide.
        // Keyed by the name passed as _showTransient(..., {anim: <key>}).
        this._toastAnims = {};
        for (const [key, file, w, h, dur] of [
            ['charge', 'charging', 20, 20, 1900],
            ['lowbat', 'low-battery', 27, 16, 1700],
        ]) {
            try {
                const meta = loadSpriteMeta(
                    GLib.build_filenamev([this._path, 'assets', `${file}.json`]));
                const sprite = new SpriteAnimation(
                    GLib.build_filenamev([this._path, 'assets', `${file}.png`]),
                    meta, {width: w, height: h, loop: false, durationMs: dur});
                sprite.actor.visible = false;
                this._transientBox.insert_child_at_index(sprite.actor, 0);
                this._toastAnims[key] = sprite;
            } catch (e) {
                logError(e, `[macos-top-panel] toast animation ${file} unavailable`);
            }
        }

        // Persistent "screen recording" pill: a pulsing red dot + a running clock, the same
        // read as iOS's recording indicator. Driven by ScreenRecordingWatcher.
        this._recordingBox = new St.BoxLayout({
            style_class: 'dynamic-island-recording', vertical: false, visible: false,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._recordingDot = new St.Widget({
            style_class: 'dynamic-island-recording-dot',
            y_align: Clutter.ActorAlign.CENTER, y_expand: false,
        });
        this._recordingLabel = new St.Label({
            style_class: 'dynamic-island-recording-label', text: 'Screen Recording',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._recordingElapsed = new St.Label({
            style_class: 'dynamic-island-recording-elapsed', y_align: Clutter.ActorAlign.CENTER,
        });
        this._recordingBox.add_child(this._recordingDot);
        this._recordingBox.add_child(this._recordingLabel);
        this._recordingBox.add_child(this._recordingElapsed);
        this._container.add_child(this._recordingBox);
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
    // -- see peachos-dictation-daemon's own _emit_level() docstring). The baked waveform
    // loop carries the motion; this just adds a subtle live vertical pulse on top so it
    // still reacts to how loudly you're speaking.
    _onAudioLevel(level) {
        if (this._recordingState !== 'listening')
            return;
        this._piWave?.setLevel(level);
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

    // ---- Screen-recording elapsed clock (its own timer -- the dictation one above is tied to
    // the 'listening' gsetting state; these two can't run at once anyway, dictation wins) -----

    _startRecElapsed() {
        this._recStartUs = GLib.get_monotonic_time();
        this._updateRecElapsed();
        if (this._recElapsedTimerId)
            GLib.source_remove(this._recElapsedTimerId);
        this._recElapsedTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, RECORDING_ELAPSED_TICK_MS, () => {
            this._updateRecElapsed();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopRecElapsed() {
        if (this._recElapsedTimerId) {
            GLib.source_remove(this._recElapsedTimerId);
            this._recElapsedTimerId = 0;
        }
        // Settle the dot back to full opacity so it's clean if the pill shows again later.
        this._recordingDot?.remove_all_transitions();
        if (this._recordingDot)
            this._recordingDot.opacity = 255;
    }

    _updateRecElapsed() {
        this._recordingElapsed.set_text(formatElapsed((GLib.get_monotonic_time() - this._recStartUs) / 1000000));
    }

    // Slow, soft breathing on the red dot for the life of the recording -- a self-rescheduling
    // ease rather than CSS (St has no @keyframes). The _screenRecording / _recordingDot guards
    // stop it when recording ends or the pill is torn down.
    _pulseRecordingDot() {
        if (!this._screenRecording || !this._recordingDot)
            return;
        const next = this._recordingDot.opacity > 150 ? 80 : 255;
        this._recordingDot.ease({
            opacity: next,
            duration: 750,
            mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
            onComplete: () => this._pulseRecordingDot(),
        });
    }

    // ---- One-off toasts (charging started, LocalSend receipt) -- briefly take over the pill,
    // then hand it back to whatever _sync() would otherwise be showing. Explicitly requested
    // to be a toast, not a persistent status: "I would only want the pill to show up for like
    // a second... then disappearing" -- unlike dictation/media there's no ongoing state here,
    // just a moment-in-time event, so a fixed-duration timer (not a state machine) is honest.

    _showTransient(iconName, text, accentColor, opts = {}) {
        // Don't let a toast stomp on something the user is actively doing in the pill:
        // dictation (mid-utterance, has a modal grab) or a screen recording (would land in
        // the recorded video). The event is edge-triggered, so it's just dropped, not queued.
        if (this._recordingState !== 'idle' || this._screenRecording)
            return;

        if (this._transientTimerId) {
            GLib.source_remove(this._transientTimerId);
            this._transientTimerId = 0;
        }

        const sprite = opts.anim ? this._toastAnims[opts.anim] : null;
        // A "drawn glyph" toast (baked animation, or a pre-coloured white raster
        // icon) carries its own colour -> white label, no coloured pill border.
        const drawnGlyph = Boolean(sprite || opts.gicon);

        for (const [key, s] of Object.entries(this._toastAnims))
            s.actor.visible = key === opts.anim;
        this._transientIcon.visible = !sprite;

        if (!sprite) {
            this._transientIcon.icon_size = opts.iconSize ?? 15;
            if (opts.gicon) {
                this._transientIcon.gicon = opts.gicon;
                this._transientIcon.icon_name = null;
                this._transientIcon.set_style(null);
            } else {
                this._transientIcon.gicon = null;
                this._transientIcon.icon_name = iconName;
                this._transientIcon.set_style(`color: ${accentColor};`);
            }
        }
        this._transientLabel.set_text(text);
        this._transientLabel.set_style(drawnGlyph ? 'color: #ffffff;' : `color: ${accentColor};`);
        this._container.set_style(drawnGlyph ? null : `border: 1px solid ${accentColor}99;`);

        this._transientActive = true;
        this._dictationBox.visible = false;
        this._mediaBox.visible = false;
        this._recordingBox.visible = false;
        this._transientBox.visible = true;
        this._setVisible(true);

        // Kick the animation only after the pill is on screen -- the first play()
        // slices the sprite sheet into GL textures, which on a slow GPU can block
        // the main loop for a beat (idle pre-warm below usually beats it to it).
        if (sprite)
            sprite.play();

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
        // set_style(null) drops the inline border added above; the pill's base look comes
        // from the .dynamic-island class, and the dictation --error border is a style class,
        // so neither is touched by this.
        this._container.set_style(null);
        for (const s of Object.values(this._toastAnims)) {
            s.stop();
            s.actor.visible = false;
        }
        this._transientIcon.visible = true;
        this._transientActive = false;
        this._transientBox.visible = false;
    }

    // ---- State -> appearance ------------------------------------------------------------

    _sync() {
        const dictationActive = this._recordingState !== 'idle';
        const screenRec = this._screenRecording;
        // Explicit request: don't show the media pill while the user is already looking at
        // whatever's playing (its own window has focus) -- only once they've switched to
        // something else is it worth a glanceable reminder.
        const mediaActive = Boolean(this._mediaState?.isActive) && !this._isMediaWindowFocused();

        // Dictation or a recording starting always wins immediately, even mid-toast (see
        // _showTransient's guard for the other direction: a toast never starts during either).
        if ((dictationActive || screenRec) && this._transientActive)
            this._clearTransient();

        // A toast owns the pill until its own timer fires -- leave the other boxes' visibility
        // alone in the meantime so it doesn't get clobbered by e.g. a media-focus change.
        if (this._transientActive)
            return;

        // Priority: dictation (actively speaking into it) > screen recording (important,
        // must stay visible the whole time) > media (ambient reminder).
        const showDictation = dictationActive;
        const showRecording = !dictationActive && screenRec;
        const showMedia = !dictationActive && !screenRec && mediaActive;

        this._dictationBox.visible = showDictation;
        this._recordingBox.visible = showRecording;
        this._mediaBox.visible = showMedia;
        this._setVisible(showDictation || showRecording || showMedia);

        if (showDictation) {
            const listening = this._recordingState === 'listening';
            this._dictationLabel.set_text(TRANSIENT_LABELS[this._recordingState] ?? '');
            this._dictationLabel.visible = !listening;
            if (this._piWave) {
                this._piWave.actor.visible = listening;
                if (listening)
                    this._piWave.play();
                else
                    this._piWave.stop();
            }

            this._container.remove_style_class_name('dynamic-island--error');
            if (this._recordingState === 'error')
                this._container.add_style_class_name('dynamic-island--error');
        }

        if (showMedia) {
            const {title, artist} = this._mediaState;
            this._mediaTitle.set_text(
                title && artist ? `${title} — ${artist}` : title || artist || 'Now Playing');
            this._mediaArt.gicon = this._mediaState.artIcon ?? null;
            if (!this._mediaState.artIcon)
                this._mediaArt.icon_name = 'audio-x-generic-symbolic';
        }
    }

    _setVisible(shouldShow) {
        if (shouldShow === this._container.visible)
            return;
        // Kill any in-flight animation before starting the opposite one -- rapidly flipping
        // states (e.g. bouncing focus between two windows) would otherwise let a still-running
        // retract and a freshly-started unfurl fight over the same properties.
        this._container.remove_all_transitions();
        if (shouldShow) {
            this._container.visible = true;
            this._container.set_scale(COLLAPSED_SCALE_X, COLLAPSED_SCALE_Y);
            this._container.translation_x = -SLIDE_IN_PX;
            this._container.opacity = 0;
            this._container.ease({
                opacity: 255, scale_x: 1, scale_y: 1, translation_x: 0,
                duration: APPEAR_MS, mode: Clutter.AnimationMode.EASE_OUT_QUINT,
            });
        } else {
            this._container.ease({
                opacity: 0, scale_x: COLLAPSED_SCALE_X, scale_y: COLLAPSED_SCALE_Y,
                translation_x: -SLIDE_IN_PX,
                duration: DISAPPEAR_MS, mode: Clutter.AnimationMode.EASE_IN_CUBIC,
                onComplete: () => {
                    if (!this._container)
                        return;
                    this._container.visible = false;
                    // Reset so the next unfurl starts clean regardless of where this landed.
                    this._container.set_scale(1, 1);
                    this._container.translation_x = 0;
                    this._container.opacity = 255;
                },
            });
        }
    }

    destroy() {
        if (this._warmId) {
            GLib.source_remove(this._warmId);
            this._warmId = 0;
        }
        this._piWave?.destroy();
        this._piWave = null;
        for (const s of Object.values(this._toastAnims ?? {}))
            s.destroy();
        this._toastAnims = {};
        this._stopRecElapsed();
        if (this._transientTimerId) {
            GLib.source_remove(this._transientTimerId);
            this._transientTimerId = 0;
        }
        this._powerWatcher?.destroy();
        this._powerWatcher = null;
        this._localSendWatcher?.destroy();
        this._localSendWatcher = null;
        this._dndController?.destroy();
        this._dndController = null;
        this._powerProfileWatcher?.destroy();
        this._powerProfileWatcher = null;
        this._volumeMountWatcher?.destroy();
        this._volumeMountWatcher = null;
        this._bluetoothWatcher?.destroy();
        this._bluetoothWatcher = null;
        this._screenshotWatcher?.destroy();
        this._screenshotWatcher = null;
        this._nightLightWatcher?.destroy();
        this._nightLightWatcher = null;
        this._vpnWatcher?.destroy();
        this._vpnWatcher = null;
        this._recordingWatcher?.destroy();
        this._recordingWatcher = null;
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
