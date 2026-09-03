import {parseBluetoothState, sortBluetoothDevices, deviceIconName} from '../lib/bluetoothData.js';

function assertEqual(actual, expected, msg) {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);
    if (a !== e)
        throw new Error(`FAIL: ${msg}\n  expected: ${e}\n  actual:   ${a}`);
    print(`PASS: ${msg}`);
}

// powered off
{
    const result = parseBluetoothState({powered: false, connectedDeviceName: null});
    assertEqual(result.powered, false, 'off: powered false');
    assertEqual(result.connectedDeviceName, null, 'off: no device even if one was passed');
    assertEqual(result.statusLabel, 'Bluetooth Off', 'off: statusLabel');
}

// powered off, device name passed anyway (should still be null)
{
    const result = parseBluetoothState({powered: false, connectedDeviceName: 'AirPods'});
    assertEqual(result.connectedDeviceName, null, 'off: device name ignored while powered off');
}

// powered on, nothing connected
{
    const result = parseBluetoothState({powered: true, connectedDeviceName: null});
    assertEqual(result.powered, true, 'on/disconnected: powered true');
    assertEqual(result.statusLabel, 'Not Connected', 'on/disconnected: statusLabel');
}

// powered on, device connected
{
    const result = parseBluetoothState({powered: true, connectedDeviceName: 'AirPods'});
    assertEqual(result.connectedDeviceName, 'AirPods', 'connected: device name');
    assertEqual(result.statusLabel, 'AirPods', 'connected: statusLabel is the device name');
}

// sortBluetoothDevices: connected first, then paired, then discovered-only; alpha within group
{
    const result = sortBluetoothDevices([
        {path: '/a', name: 'Zebra Speaker', connected: false, paired: true},
        {path: '/b', name: 'AirPods', connected: true, paired: true},
        {path: '/c', name: 'Random Scanner', connected: false, paired: false},
        {path: '/d', name: 'Apple Mouse', connected: false, paired: true},
    ]);
    assertEqual(result.map(d => d.name), ['AirPods', 'Apple Mouse', 'Zebra Speaker', 'Random Scanner'],
        'connected first, then paired alphabetically, then discovered-only');
}

// sortBluetoothDevices: unnamed devices sort last within their group
{
    const result = sortBluetoothDevices([
        {path: '/a', name: null, connected: false, paired: true},
        {path: '/b', name: 'Keyboard', connected: false, paired: true},
    ]);
    assertEqual(result.map(d => d.name), ['Keyboard', null], 'unnamed device sorts after named ones');
}

// deviceIconName: BlueZ's own Icon hint -> canonical type -> shipped icon
{
    assertEqual(deviceIconName({icon: 'audio-headphones'}), 'peachos-bt-headphones',
        'iconName: BlueZ headphones hint');
    assertEqual(deviceIconName({icon: 'audio-card'}), 'peachos-bt-speakers',
        'iconName: BlueZ generic-audio hint -> speakers');
    assertEqual(deviceIconName({icon: 'input-mouse'}), 'input-mouse-symbolic',
        'iconName: BlueZ mouse hint -> themed symbolic (no custom art)');
}

// deviceIconName: Class-of-Device fallback when BlueZ gave no hint
{
    // major 4 (audio/video), minor 6 (headphones)
    assertEqual(deviceIconName({class: 0x040418}), 'peachos-bt-headphones',
        'iconName: CoD audio/headphones');
    // major 4, minor 8 (car audio)
    assertEqual(deviceIconName({class: 0x040420}), 'peachos-bt-carplay',
        'iconName: CoD car audio -> carplay');
    // major 5 (peripheral), keyboard
    assertEqual(deviceIconName({class: 0x000540}), 'peachos-bt-keyboard',
        'iconName: CoD peripheral/keyboard');
    // major 5, mouse (minor top-bits == 2): 0x000580
    assertEqual(deviceIconName({class: 0x000580}), 'input-mouse-symbolic',
        'iconName: CoD peripheral/mouse');
    // major 1 (computer)
    assertEqual(deviceIconName({class: 0x00010C}), 'peachos-bt-laptop',
        'iconName: CoD computer -> laptop');
    // major 2 (phone)
    assertEqual(deviceIconName({class: 0x00020C}), 'phone-symbolic',
        'iconName: CoD phone -> themed symbolic');
}

// deviceIconName: name guess when neither hint nor class is present
{
    assertEqual(deviceIconName({name: "Chris's AirPods Pro"}), 'peachos-bt-airpods',
        'iconName: AirPods by name -> dedicated AirPods icon');
    assertEqual(deviceIconName({name: 'Sony WH-1000 Headphones'}), 'peachos-bt-headphones',
        'iconName: headphones by name');
    assertEqual(deviceIconName({name: 'Living Room TV'}), 'peachos-bt-tv',
        'iconName: TV by name');
    assertEqual(deviceIconName({name: 'JBL Speaker'}), 'peachos-bt-speakers',
        'iconName: speaker by name');
    assertEqual(deviceIconName({name: 'Galaxy Watch6'}), 'peachos-bt-watch',
        'iconName: watch by name');
    assertEqual(deviceIconName({name: 'MX Keys'}), 'bluetooth-symbolic',
        'iconName: unknown name -> generic bluetooth glyph');
    assertEqual(deviceIconName({}), 'bluetooth-symbolic',
        'iconName: nothing known -> generic bluetooth glyph');
}

print('All bluetoothData tests passed.');
