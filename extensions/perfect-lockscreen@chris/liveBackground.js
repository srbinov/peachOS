import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as LoginManager from 'resource:///org/gnome/shell/misc/loginManager.js';
import { InjectionManager } from 'resource:///org/gnome/shell/extensions/extension.js';

import St from 'gi://St';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';

import { Keys, ScalingMode } from './live/enums.js';
import { MpvPlayerProcess } from './live/core/mpv_player_process.js';
import { GstPlayerProcess } from './live/core/gst_player_process.js';
import { isOnBattery } from './live/utils/battery.js';
import { SHELL_VERSION } from './live/utils/shell_version.js';
import { logInfo, logWarn, logError } from './live/utils/logging.js';
import { destroySleeps, sleep } from './live/utils/base.js';
import { isGtk4PaintableSinkAvailable, isMpvAvailable } from './live/utils/check_dependencies.js';
import { sendErrorNotification } from './live/utils/notifications.js';

const WINDOW_TIMEOUT = 10000;
const LIVE_BLUR_NAME = 'pls-live-blur';
const LIVE_DESATURATE_NAME = 'pls-live-desaturate';

export function isPlayerAvailable() {
    try {
        if (isMpvAvailable())
            return true;
    } catch (e) {
        // ignore
    }
    try {
        return isGtk4PaintableSinkAvailable();
    } catch (e) {
        return false;
    }
}

export class LiveBackground {
    constructor(extension) {
        this._extension = extension;
        this._settings = extension.getSettings();
        this._path = extension.path;
        this._resetState();
    }

    _resetState() {
        this._backgroundCreated = false;
        this._wrapperActors = [];
        this._windowActor = null;
        this._window = null;
        this._promptShown = false;
        this._injectionManager = null;
        this._player = null;
        this._blurEffectTimeoutId = 0;
    }

    async start() {
        const videoPath = this._settings.get_string(Keys.VIDEO_PATH);
        if (!videoPath) {
            logWarn('Video not set, skipping live background');
            return false;
        }

        const disableOnBattery = this._settings.get_boolean(Keys.DISABLE_ON_BATTERY);
        if (disableOnBattery && await isOnBattery()) {
            logWarn('Skipping live background on battery');
            return false;
        }

        let cls = null;
        if (isMpvAvailable()) {
            logInfo('Using MPV as playback backend');
            cls = MpvPlayerProcess;
        } else if (isGtk4PaintableSinkAvailable()) {
            logInfo('Using GStreamer as playback backend');
            cls = GstPlayerProcess;
        }

        if (!cls) {
            sendErrorNotification(
                'No playback backend available. Install MPV (recommended) or GStreamer with gtk4paintablesink.'
            );
            logError('No suitable backends available for playback');
            return false;
        }

        this._player = new cls({
            playerPath: `${this._path}/live/external/run.js`,
            videoPath,
            scalingMode: this._settings.get_int(Keys.SCALING_MODE),
            loop: this._settings.get_boolean(Keys.LOOPED),
            volume: 0,
            useVideorate: false,
            framerate: 25,
            colorAccurate: true,
        });

        await this._player.run();
        await this._onPlayerInit();
        return true;
    }

    async _onPlayerInit() {
        this._fadeInDuration = this._settings.get_int(Keys.FADE_IN_DURATION);
        this._scalingMode = this._settings.get_int(Keys.SCALING_MODE);
        this._blurRadius = this._settings.get_int(Keys.BLUR_RADIUS);
        this._blurBrightness = this._settings.get_double(Keys.BLUR_BRIGHTNESS);

        this._promptSettings = {
            [Keys.PROMPT_PAUSE]: this._settings.get_boolean(Keys.PROMPT_PAUSE),
            [Keys.PROMPT_GRAYSCALE]: this._settings.get_boolean(Keys.PROMPT_GRAYSCALE),
            [Keys.PROMPT_CHANGE_BLUR]: this._settings.get_boolean(Keys.PROMPT_CHANGE_BLUR),
            [Keys.PROMPT_BLUR_RADIUS]: this._settings.get_int(Keys.PROMPT_BLUR_RADIUS),
            [Keys.PROMPT_BLUR_ANIM_DURATION]: this._settings.get_int(Keys.PROMPT_BLUR_ANIM_DURATION),
            [Keys.PROMPT_BLUR_BRIGHTNESS]: this._settings.get_double(Keys.PROMPT_BLUR_BRIGHTNESS),
        };

        const themeContext = St.ThemeContext.get_for_stage(global.stage);
        this._blurRadius *= themeContext.scale_factor;

        this._blurEffect = {
            name: LIVE_BLUR_NAME,
            radius: this._blurRadius,
            brightness: this._blurBrightness,
        };

        this._injectionManager = new InjectionManager();
        this._injectionManager.overrideMethod(
            Main.wm,
            '_shouldAnimateActor',
            () => {
                return function() {
                    return false;
                };
            }
        );

        const win = await this._player.waitForWindow(WINDOW_TIMEOUT);
        this._window = win;
        this._windowActor = win.get_compositor_private();

        const deadline = Date.now() + WINDOW_TIMEOUT;
        while (this._player.w === 0 && Date.now() < deadline)
            await sleep(50);

        if (SHELL_VERSION > 48)
            this._window.unmaximize();
        else
            this._window.unmaximize(true);

        const parent = this._windowActor.get_parent();
        if (parent)
            parent.remove_child(this._windowActor);

        global.stage.add_child(this._windowActor);
        global.stage.set_child_below_sibling(this._windowActor, null);
        this._windowActor.opacity = 0;

        await this._injectIntoDialog();
    }

    async _injectIntoDialog() {
        const dialog = Main.screenShield?._dialog;
        if (!dialog)
            throw new Error('Unlock dialog is not available');

        this._injectionManager.overrideMethod(
            dialog, '_createBackground',
            original => {
                const self = this;
                return function(monitorIndex) {
                    original.call(this, monitorIndex);
                    self._handleMonitor(monitorIndex);
                };
            }
        );

        dialog._updateBackgrounds();
    }

    onPromptShow() {
        if (this._promptShown)
            return;
        this._promptShown = true;

        if (this._promptSettings[Keys.PROMPT_CHANGE_BLUR]) {
            const radius = this._promptSettings[Keys.PROMPT_BLUR_RADIUS];
            const brightness = radius ? this._promptSettings[Keys.PROMPT_BLUR_BRIGHTNESS] : 1;

            this._blurEffectTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 10, () => {
                this._wrapperActors.forEach(actor => {
                    actor.ease_property(`@effects.${LIVE_BLUR_NAME}.radius`, radius, {
                        duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    });
                    actor.ease_property(`@effects.${LIVE_BLUR_NAME}.brightness`, brightness, {
                        duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    });
                });
                this._blurEffectTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            });
        }

        if (this._promptSettings[Keys.PROMPT_GRAYSCALE]) {
            this._wrapperActors.forEach(actor => {
                actor.ease_property(`@effects.${LIVE_DESATURATE_NAME}.factor`, 1.0, {
                    duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
            });
        }

        if (this._promptSettings[Keys.PROMPT_PAUSE])
            this._player?.pause();
    }

    onPromptHide() {
        if (!this._promptShown)
            return;
        this._promptShown = false;

        if (this._promptSettings[Keys.PROMPT_CHANGE_BLUR]) {
            const radius = this._blurRadius;
            const brightness = radius ? this._blurBrightness : 1;

            this._wrapperActors.forEach(actor => {
                actor.ease_property(`@effects.${LIVE_BLUR_NAME}.radius`, radius, {
                    duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
                actor.ease_property(`@effects.${LIVE_BLUR_NAME}.brightness`, brightness, {
                    duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
            });
        }

        if (this._promptSettings[Keys.PROMPT_GRAYSCALE]) {
            this._wrapperActors.forEach(actor => {
                actor.ease_property(`@effects.${LIVE_DESATURATE_NAME}.factor`, 0.0, {
                    duration: this._promptSettings[Keys.PROMPT_BLUR_ANIM_DURATION],
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
            });
        }

        if (this._promptSettings[Keys.PROMPT_PAUSE])
            this._player?.play();
    }

    _handleMonitor(monitorIndex) {
        if (!this._player || !this._window)
            return;

        if (this._player.shouldResize)
            this._window.move_resize_frame(true, 0, 0, this._player.w, this._player.h);

        const isLastMonitor = monitorIndex === Main.layoutManager.monitors.length - 1;
        const monitor = Main.layoutManager.monitors[monitorIndex];
        const wrapper = new Clutter.Actor();

        if (monitorIndex === 0)
            this._wrapperActors = [];

        Main.screenShield._dialog._backgroundGroup.add_child(wrapper);
        Main.screenShield._dialog._backgroundGroup.set_child_above_sibling(wrapper, null);

        const cloneActor = new Clutter.Clone({
            source: this._windowActor,
        });

        wrapper.add_effect(new Shell.BlurEffect(this._blurEffect));

        if (this._promptSettings[Keys.PROMPT_GRAYSCALE]) {
            wrapper.add_effect_with_name(
                LIVE_DESATURATE_NAME,
                new Clutter.DesaturateEffect({ factor: 0.0 })
            );
        }

        if (!this._backgroundCreated)
            wrapper.opacity = 0;

        wrapper.add_child(cloneActor);
        wrapper.set_child_above_sibling(cloneActor, null);
        this._wrapperActors.push(wrapper);

        wrapper.set_position(monitor.x, monitor.y);
        wrapper.set_size(monitor.width, monitor.height);
        wrapper.set_clip_to_allocation(true);

        this._applyScaling(cloneActor, monitor.width, monitor.height);

        if (!this._backgroundCreated && isLastMonitor) {
            this._initLoginManager();
            this._startAnimation();
            this._player.play();
            this._backgroundCreated = true;
        }
    }

    _applyScaling(cloneActor, targetW, targetH) {
        const W = this._player.w || targetW;
        const H = this._player.h || targetH;
        cloneActor.set_size(W, H);

        switch (this._scalingMode) {
            case ScalingMode.STRETCH: {
                cloneActor.set_scale(targetW / W, targetH / H);
                cloneActor.set_position(0, 0);
                break;
            }
            case ScalingMode.FIT: {
                const scale = Math.min(targetW / W, targetH / H);
                cloneActor.set_scale(scale, scale);
                cloneActor.set_position(
                    (targetW - W * scale) / 2,
                    (targetH - H * scale) / 2
                );
                break;
            }
            default: {
                const scale = Math.max(targetW / W, targetH / H);
                cloneActor.set_scale(scale, scale);
                cloneActor.set_position(
                    (targetW - W * scale) / 2,
                    (targetH - H * scale) / 2
                );
                break;
            }
        }
    }

    _startAnimation() {
        this._wrapperActors.forEach(actor => actor.ease({
            opacity: 255,
            duration: this._fadeInDuration,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
        }));
    }

    _initLoginManager() {
        this._loginManager = LoginManager.getLoginManager();
        this._loginManager.connectObject('prepare-for-sleep', (_manager, aboutToSleep) => {
            if (!this._player)
                return;
            aboutToSleep ? this._player.pause() : this._player.play();
        }, this);
    }

    destroy() {
        destroySleeps();

        if (this._blurEffectTimeoutId) {
            GLib.source_remove(this._blurEffectTimeoutId);
            this._blurEffectTimeoutId = 0;
        }

        if (this._windowActor)
            this._windowActor.hide();

        this._player?.destroy();
        this._player = null;

        this._injectionManager?.clear();
        this._injectionManager = null;

        this._loginManager?.disconnectObject(this);
        this._loginManager = null;

        for (const actor of this._wrapperActors) {
            try {
                actor.remove_effect_by_name(LIVE_BLUR_NAME);
                actor.remove_effect_by_name(LIVE_DESATURATE_NAME);
                actor.destroy();
            } catch (e) {
                // ignore
            }
        }
        this._wrapperActors = [];
        this._resetState();
    }
}
