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

// deviceIconName: BlueZ's own Icon hint wins, normalised to -symbolic
{
    assertEqual(deviceIconName({icon: 'audio-headphones'}), 'audio-headphones-symbolic',
        'iconName: BlueZ hint gets -symbolic suffix');
    assertEqual(deviceIconName({icon: 'input-keyboard-symbolic'}), 'input-keyboard-symbolic',
        'iconName: hint already symbolic is left alone');
}

// deviceIconName: Class-of-Device fallback when BlueZ gave no hint
{
    // major 4 (audio/video), minor 6 (headphones): 0x040418 -> (>>8 &0x1f)=4, (>>2 &0x3f)=6
    assertEqual(deviceIconName({class: 0x040418}), 'audio-headphones-symbolic',
        'iconName: CoD audio/headphones');
    // major 5 (peripheral), minor top-bits 1 (keyboard): 0x000540
    assertEqual(deviceIconName({class: 0x000540}), 'input-keyboard-symbolic',
        'iconName: CoD peripheral/keyboard');
    // major 1 (computer): 0x00010C
    assertEqual(deviceIconName({class: 0x00010C}), 'computer-symbolic',
        'iconName: CoD computer');
    // major 2 (phone): 0x00020C
    assertEqual(deviceIconName({class: 0x00020C}), 'phone-symbolic',
        'iconName: CoD phone');
}

// deviceIconName: name guess when neither hint nor class is present
{
    assertEqual(deviceIconName({name: "Chris's AirPods Pro"}), 'audio-headphones-symbolic',
        'iconName: AirPods by name');
    assertEqual(deviceIconName({name: 'Living Room TV'}), 'video-display-symbolic',
        'iconName: TV by name');
    assertEqual(deviceIconName({name: 'JBL Speaker'}), 'audio-speakers-symbolic',
        'iconName: speaker by name');
    assertEqual(deviceIconName({name: 'MX Keys'}), 'bluetooth-symbolic',
        'iconName: unknown name -> generic bluetooth glyph');
    assertEqual(deviceIconName({}), 'bluetooth-symbolic',
        'iconName: nothing known -> generic bluetooth glyph');
}

print('All bluetoothData tests passed.');
