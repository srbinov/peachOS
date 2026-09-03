/** @param {{powered: boolean, connectedDeviceName: string|null}} props */
export function parseBluetoothState(props) {
    const powered = props.powered;
    const connectedDeviceName = powered ? (props.connectedDeviceName ?? null) : null;

    let statusLabel;
    if (!powered)
        statusLabel = 'Bluetooth Off';
    else if (connectedDeviceName)
        statusLabel = connectedDeviceName;
    else
        statusLabel = 'Not Connected';

    return {powered, connectedDeviceName, statusLabel};
}

// --- device type -> icon ---------------------------------------------------
//
// Work out a canonical device type (deviceType), then map it to an icon
// (deviceIconName). BlueZ already classifies most devices for us in its own
// `Icon` property -- a freedesktop name derived from the classic
// Class-of-Device or the LE Appearance -- so that's the primary signal, with
// the raw Class bits and then the friendly name as fallbacks.
//
// peachOS ships hand-drawn icons for the common types (peachos-bt-*, from the
// macOS_Tahoe_SYSICONS set, installed to hicolor by provision.sh); the rest
// fall back to a themed `-symbolic` name that resolves in MacTahoe.

const TYPE_ICON = {
    airpods:    'peachos-bt-airpods',
    headphones: 'peachos-bt-headphones',
    headset:    'peachos-bt-headphones',
    speakers:   'peachos-bt-speakers',
    carplay:    'peachos-bt-carplay',
    airplay:    'peachos-bt-airplay',
    microphone: 'peachos-bt-microphone',
    tv:         'peachos-bt-tv',
    computer:   'peachos-bt-laptop',
    keyboard:   'peachos-bt-keyboard',
    watch:      'peachos-bt-watch',
    printer:    'peachos-bt-printer',
    // no custom art -- themed symbolic fallback
    phone:      'phone-symbolic',
    mouse:      'input-mouse-symbolic',
    gamepad:    'input-gaming-symbolic',
    tablet:     'input-tablet-symbolic',
    camera:     'camera-photo-symbolic',
    camcorder:  'camera-video-symbolic',
    network:    'network-wireless-symbolic',
    player:     'multimedia-player-symbolic',
    generic:    'bluetooth-symbolic',
};

// BlueZ `Icon` hint -> our canonical type
const HINT_TYPE = {
    'audio-headphones': 'headphones', 'audio-headset': 'headset',
    'audio-speakers': 'speakers', 'audio-card': 'speakers',
    'audio-input-microphone': 'microphone', 'multimedia-player': 'player',
    'computer': 'computer', 'phone': 'phone', 'network-wireless': 'network',
    'input-keyboard': 'keyboard', 'input-mouse': 'mouse',
    'input-gaming': 'gamepad', 'input-tablet': 'tablet',
    'video-display': 'tv', 'camera-photo': 'camera', 'camera-video': 'camcorder',
    'printer': 'printer',
};

// classic Class-of-Device audio/video (major 4) minor -> type
const COD_AV_MINOR = {
    1: 'headset', 2: 'headset', 4: 'microphone', 5: 'speakers', 6: 'headphones',
    7: 'player', 8: 'carplay', 10: 'tv', 11: 'tv', 12: 'tv', 13: 'camcorder',
};

/**
 * The canonical device type -- a key of TYPE_ICON.
 * @param {{icon?: string|null, class?: number, name?: string|null}} device
 */
export function deviceType(device) {
    const name = (device?.name ?? '').toLowerCase();

    // most-specific name overrides first (AirPods vs generic headphones, etc.)
    if (/airpod/.test(name)) return 'airpods';
    if (/\bairplay\b/.test(name)) return 'airplay';
    if (/carplay/.test(name)) return 'carplay';

    // BlueZ's own classification
    const hint = device?.icon;
    if (hint && HINT_TYPE[hint]) return HINT_TYPE[hint];

    // raw Class-of-Device
    const cod = device?.class ?? 0;
    if (cod) {
        const major = (cod >> 8) & 0x1f;
        const minor = (cod >> 2) & 0x3f;
        if (major === 1) return 'computer';
        if (major === 2) return 'phone';
        if (major === 3) return 'network';
        if (major === 4) return COD_AV_MINOR[minor] ?? 'speakers';
        if (major === 5) return ((minor >> 4) & 0x3) === 2 ? 'mouse' : 'keyboard';
        if (major === 6) return 'camera';
    }

    // looser name guesses
    if (/headphone|earbud| buds|beats/.test(name)) return 'headphones';
    if (/speaker|soundbar|homepod|sonos/.test(name)) return 'speakers';
    if (/keyboard/.test(name)) return 'keyboard';
    if (/mouse|trackpad/.test(name)) return 'mouse';
    if (/(^| )tv($| )|television|bravia|\bwebos\b/.test(name)) return 'tv';
    if (/watch/.test(name)) return 'watch';
    if (/printer/.test(name)) return 'printer';

    return 'generic';
}

/**
 * The icon name for a device's type -- a peachos-bt-* custom icon where we
 * ship one, otherwise a themed `-symbolic` name.
 * @param {{icon?: string|null, class?: number, name?: string|null}} device
 * @returns {string}
 */
export function deviceIconName(device) {
    return TYPE_ICON[deviceType(device)] ?? 'bluetooth-symbolic';
}

/**
 * Sort BlueZ devices for display: connected first, then other paired
 * devices, then everything else merely discovered by a scan -- each group
 * alphabetical by name. Unnamed devices (bare MAC, no name/alias reported
 * yet) sort last within their group rather than cluttering the top under
 * whatever locale-dependent order a raw MAC string would fall into.
 *
 * @param {{path: string, name: string|null, connected: boolean, paired: boolean}[]} devices
 */
export function sortBluetoothDevices(devices) {
    const rank = d => (d.connected ? 0 : d.paired ? 1 : 2);
    return [...devices].sort((a, b) => {
        const rankDiff = rank(a) - rank(b);
        if (rankDiff !== 0)
            return rankDiff;
        if (!a.name !== !b.name)
            return a.name ? -1 : 1;
        return (a.name ?? '').localeCompare(b.name ?? '');
    });
}
