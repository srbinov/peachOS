import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
    BackgroundSource,
    posterPathForUser,
    resolveGdmBackground,
    resolveLockBackground,
} from '../backgroundPolicy.js';

describe('posterPathForUser', () => {
    it('uses the pls-shared-poster prefix and jpg suffix', () => {
        assert.equal(
            posterPathForUser('chris'),
            '/var/tmp/pls-shared-poster-chris.jpg'
        );
    });
});

describe('resolveLockBackground', () => {
    const videoBase = {
        source: BackgroundSource.VIDEO,
        videoPath: '/home/chris/wall.mp4',
        stillPath: '/home/chris/still.png',
        videoExists: true,
        stillExists: true,
        onBattery: false,
        disableOnBattery: false,
        playerAvailable: true,
    };

    it('plays video when file and player are available', () => {
        assert.deepEqual(resolveLockBackground(videoBase), {
            kind: 'video',
            path: '/home/chris/wall.mp4',
        });
    });

    it('falls back to desktop when the video file is missing', () => {
        assert.deepEqual(
            resolveLockBackground({ ...videoBase, videoExists: false }),
            { kind: 'desktop', reason: 'missing-video' }
        );
    });

    it('falls back to desktop when no player is available', () => {
        assert.deepEqual(
            resolveLockBackground({ ...videoBase, playerAvailable: false }),
            { kind: 'desktop', reason: 'no-player' }
        );
    });

    it('falls back to desktop when disable-on-battery and on battery', () => {
        assert.deepEqual(
            resolveLockBackground({
                ...videoBase,
                onBattery: true,
                disableOnBattery: true,
            }),
            { kind: 'desktop', reason: 'battery' }
        );
    });

    it('still plays video on battery if disable-on-battery is off', () => {
        assert.deepEqual(
            resolveLockBackground({
                ...videoBase,
                onBattery: true,
                disableOnBattery: false,
            }),
            { kind: 'video', path: '/home/chris/wall.mp4' }
        );
    });

    it('uses a still image when the still file exists', () => {
        assert.deepEqual(
            resolveLockBackground({
                ...videoBase,
                source: BackgroundSource.STILL,
            }),
            { kind: 'still', path: '/home/chris/still.png' }
        );
    });

    it('falls back to desktop when the still file is missing', () => {
        assert.deepEqual(
            resolveLockBackground({
                ...videoBase,
                source: BackgroundSource.STILL,
                stillExists: false,
            }),
            { kind: 'desktop', reason: 'missing-still' }
        );
    });

    it('uses desktop wallpaper when source is desktop', () => {
        assert.deepEqual(
            resolveLockBackground({
                ...videoBase,
                source: BackgroundSource.DESKTOP,
            }),
            { kind: 'desktop' }
        );
    });
});

describe('resolveGdmBackground', () => {
    const gdmBase = {
        source: BackgroundSource.VIDEO,
        posterPath: '/var/tmp/pls-shared-poster-chris.jpg',
        posterExists: true,
        stillPath: '/home/chris/still.png',
        stillExists: true,
    };

    it('always uses the desktop wallpaper on GDM', () => {
        assert.deepEqual(resolveGdmBackground(gdmBase), { kind: 'desktop' });
        assert.deepEqual(
            resolveGdmBackground({ ...gdmBase, posterExists: false }),
            { kind: 'desktop' }
        );
        assert.deepEqual(
            resolveGdmBackground({
                ...gdmBase,
                source: BackgroundSource.STILL,
            }),
            { kind: 'desktop' }
        );
        assert.deepEqual(
            resolveGdmBackground({
                ...gdmBase,
                source: BackgroundSource.DESKTOP,
            }),
            { kind: 'desktop' }
        );
    });
});
