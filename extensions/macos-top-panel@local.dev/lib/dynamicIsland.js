// lib/dynamicIsland.js
//
// A center-of-the-top-bar pill, mirroring iOS's Dynamic Island in spirit but scoped to what
// actually has a real, live data source on this desktop: Peach Intelligence's own recording
// state (an animated waveform while listening -- the concrete request this was built for) and
// media playback (MPRIS, via the exact same MediaPlayerController controlCenterIndicator.js's
// own media card already uses -- a second, independent instance here, not shared, to keep the
// two indicators' lifecycles decoupled). Deliberately NOT attempted: calls, turn-by-turn
// navigation, ride-share/delivery tracking, Face ID -- none of those have a real backing
// service on a Linux desktop the way MPRIS/this extension's own gsettings do, and a fake
// stub would just be decoration with no data behind it.
//
// Hidden (zero width, per Main.panel._centerBox's own layout) whenever nothing is active;
// fades in/out rather than popping, and Main.panel._centerBox already center-aligns its
// children in the panel, so no manual positioning math is needed the way the old floating
// pill (peachos-dictation@peachos's own, before this) required.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {MediaPlayerController} from './mediaPlayerController.js';

const DICTATION_SCHEMA_ID = 'org.gnome.shell.extensions.peachos-dictation';

const WAVEFORM_BAR_COUNT = 5;
const WAVEFORM_MIN_HEIGHT = 4;
const WAVEFORM_MAX_HEIGHT = 15;
const WAVEFORM_TICK_MS = 160;

const FADE_IN_MS = 180;
const FADE_OUT_MS = 150;

const DICTATION_LABELS = {
    listening: 'Listening…',
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

export class DynamicIsland {
    constructor() {
        this._recordingState = 'idle';
        this._mediaState = null;
        this._waveformTimerId = 0;

        this._buildActor();

        this._dictationSettings = optionalSettings(DICTATION_SCHEMA_ID);
        if (this._dictationSettings) {
            this._recordingState = this._dictationSettings.get_string('recording-state');
            this._recordingChangedId = this._dictationSettings.connect('changed::recording-state', () => {
                this._recordingState = this._dictationSettings.get_string('recording-state');
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
        this._dictationBox.add_child(new St.Icon({
            icon_name: 'audio-input-microphone-symbolic', icon_size: 15, style_class: 'dynamic-island-icon',
        }));
        this._waveformBars = [];
        const waveform = new St.BoxLayout({style_class: 'dynamic-island-waveform', vertical: false});
        for (let i = 0; i < WAVEFORM_BAR_COUNT; i++) {
            const bar = new St.Widget({style_class: 'dynamic-island-waveform-bar', height: WAVEFORM_MIN_HEIGHT});
            waveform.add_child(bar);
            this._waveformBars.push(bar);
        }
        this._dictationBox.add_child(waveform);
        this._dictationLabel = new St.Label({style_class: 'dynamic-island-label', y_align: Clutter.ActorAlign.CENTER});
        this._dictationBox.add_child(this._dictationLabel);
        this._container.add_child(this._dictationBox);

        this._mediaBox = new St.BoxLayout({style_class: 'dynamic-island-media', vertical: false});
        this._mediaArt = new St.Icon({
            icon_name: 'audio-x-generic-symbolic', icon_size: 20, style_class: 'dynamic-island-art',
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

    _sync() {
        const dictationActive = this._recordingState !== 'idle';
        const mediaActive = Boolean(this._mediaState?.isActive);

        this._dictationBox.visible = dictationActive;
        this._mediaBox.visible = !dictationActive && mediaActive;
        this._setVisible(dictationActive || mediaActive);

        if (dictationActive) {
            this._dictationLabel.set_text(DICTATION_LABELS[this._recordingState] ?? '');
            this._container.remove_style_class_name('dynamic-island--error');
            if (this._recordingState === 'error')
                this._container.add_style_class_name('dynamic-island--error');
        }
        this._setWaveformActive(dictationActive && this._recordingState === 'listening');

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

    _setWaveformActive(active) {
        if (active === Boolean(this._waveformTimerId))
            return;
        if (active) {
            this._tickWaveform();
            this._waveformTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, WAVEFORM_TICK_MS, () => {
                this._tickWaveform();
                return GLib.SOURCE_CONTINUE;
            });
        } else {
            GLib.source_remove(this._waveformTimerId);
            this._waveformTimerId = 0;
            for (const bar of this._waveformBars)
                bar.ease({height: WAVEFORM_MIN_HEIGHT, duration: 120, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        }
    }

    // Random per-bar target heights, eased -- an organic VU-meter/voice-memo look rather than
    // a literal amplitude readout (this extension has no access to the daemon's actual audio
    // stream, only its listening/transcribing/error state), which is a fair trade for how
    // simple and cheap it is to run continuously while held.
    _tickWaveform() {
        for (const bar of this._waveformBars) {
            const height = WAVEFORM_MIN_HEIGHT + Math.random() * (WAVEFORM_MAX_HEIGHT - WAVEFORM_MIN_HEIGHT);
            bar.ease({height, duration: WAVEFORM_TICK_MS, mode: Clutter.AnimationMode.EASE_IN_OUT_SINE});
        }
    }

    destroy() {
        if (this._waveformTimerId) {
            GLib.source_remove(this._waveformTimerId);
            this._waveformTimerId = 0;
        }
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
