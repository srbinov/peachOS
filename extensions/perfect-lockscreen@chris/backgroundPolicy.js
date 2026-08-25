export const BackgroundSource = {
    VIDEO: 'video',
    DESKTOP: 'desktop',
    STILL: 'still',
};

export function posterPathForUser(userName) {
    return `/var/tmp/pls-shared-poster-${userName}.jpg`;
}

export function resolveLockBackground({
    source,
    videoPath,
    stillPath,
    videoExists,
    stillExists,
    onBattery,
    disableOnBattery,
    playerAvailable,
}) {
    if (source === BackgroundSource.VIDEO) {
        if (!videoExists)
            return { kind: 'desktop', reason: 'missing-video' };
        if (!playerAvailable)
            return { kind: 'desktop', reason: 'no-player' };
        if (disableOnBattery && onBattery)
            return { kind: 'desktop', reason: 'battery' };
        return { kind: 'video', path: videoPath };
    }

    if (source === BackgroundSource.STILL) {
        if (!stillExists)
            return { kind: 'desktop', reason: 'missing-still' };
        return { kind: 'still', path: stillPath };
    }

    return { kind: 'desktop' };
}

export function resolveGdmBackground(_params) {
    return { kind: 'desktop' };
}
