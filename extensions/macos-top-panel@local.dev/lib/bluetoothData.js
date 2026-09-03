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
// BlueZ already works out what kind of thing each device is: its own `Icon`
// property is a freedesktop icon name (audio-headphones, input-keyboard,
// video-display, phone, ...) derived from the classic Class-of-Device or the
// LE Appearance. We pass that straight through with a `-symbolic` suffix --
// every value BlueZ emits has a symbolic variant in the shipped MacTahoe
// theme. For the devices BlueZ leaves unclassified we decode the raw Class
// bits ourselves, then fall back to a name guess, then a generic BT glyph.

// classic Class-of-Device major device classes (bits 8-12)
const COD_MAJOR = {
    1: 'computer-symbolic',
    2: 'phone-symbolic',
    3: 'network-wireless-symbolic', // LAN / network access point
    6: 'camera-photo-symbolic',     // imaging (refined below)
};

// audio/video (major 4), by minor device class (bits 2-7)
const COD_AV_MINOR = {
    1: 'audio-headset-symbolic',
    2: 'audio-headset-symbolic',    // hands-free
    4: 'audio-input-microphone-symbolic',
    5: 'audio-speakers-symbolic',   // loudspeaker
    6: 'audio-headphones-symbolic',
    7: 'multimedia-player-symbolic', // portable audio
    8: 'audio-card-symbolic',       // car audio
    10: 'video-display-symbolic',
    11: 'video-display-symbolic',
    12: 'video-display-symbolic',
    13: 'camera-video-symbolic',    // video conferencing
};

// peripheral (major 5), by the top two bits of the minor class
const COD_PERIPHERAL = {
    1: 'input-keyboard-symbolic',
    2: 'input-mouse-symbolic',
    3: 'input-keyboard-symbolic',   // combo keyboard/pointing
};

/**
 * A themed symbolic icon name for a device's type.
 *
 * @param {{icon?: string|null, class?: number, name?: string|null}} device
 *   `icon` = BlueZ's own Icon hint, `class` = the raw Class-of-Device uint,
 *   `name` = the friendly name (used only as a last resort).
 * @returns {string}
 */
export function deviceIconName(device) {
    const hint = device?.icon;
    if (hint)
        return hint.endsWith('-symbolic') ? hint : `${hint}-symbolic`;

    const cod = device?.class ?? 0;
    if (cod) {
        const major = (cod >> 8) & 0x1f;
        const minor = (cod >> 2) & 0x3f;
        if (major === 4)
            return COD_AV_MINOR[minor] ?? 'audio-card-symbolic';
        if (major === 5)
            return COD_PERIPHERAL[(minor >> 4) & 0x3] ?? 'input-mouse-symbolic';
        if (COD_MAJOR[major])
            return COD_MAJOR[major];
    }

    const name = (device?.name ?? '').toLowerCase();
    if (/airpod|headphone|earbud| buds|beats/.test(name))
        return 'audio-headphones-symbolic';
    if (/speaker|soundbar|homepod|sonos/.test(name))
        return 'audio-speakers-symbolic';
    if (/keyboard/.test(name))
        return 'input-keyboard-symbolic';
    if (/mouse|trackpad/.test(name))
        return 'input-mouse-symbolic';
    if (/(^| )tv($| )|television|bravia|\bwebos\b/.test(name))
        return 'video-display-symbolic';
    if (/watch/.test(name))
        return 'phone-symbolic';

    return 'bluetooth-symbolic';
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
