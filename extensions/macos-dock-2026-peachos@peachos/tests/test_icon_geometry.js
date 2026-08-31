#!/usr/bin/env gjs -m

import {
  matchIconForApp,
  lampTargetFromIcon,
  separatorOverlayStyle,
  separatorOverlaySize,
} from '../iconGeometry.js';

function assertEqual(actual, expected, msg) {
  if (JSON.stringify(actual) !== JSON.stringify(expected) && actual !== expected) {
    throw new Error(
      `${msg || 'assertEqual'}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assert failed');
}

{
  const icons = [
    { appId: 'firefox.desktop', pids: [11], x: 100 },
    { appId: 'org.gnome.Nautilus.desktop', pids: [22], x: 200 },
  ];
  assertEqual(matchIconForApp(icons, { appId: 'firefox.desktop' }).x, 100, 'match by app id');
  assertEqual(matchIconForApp(icons, { pid: 22 }).x, 200, 'match by pid');
  assertEqual(matchIconForApp(icons, { appId: 'missing.desktop', pid: 99 }), null, 'no match');
}

{
  const monitor = { x: 0, y: 0, width: 1920, height: 1080 };
  const icon = { x: 640, y: 1000, width: 48, height: 48 };
  const target = lampTargetFromIcon(icon, 'bottom', monitor);
  assertEqual(target.x, 640, 'keeps icon x');
  assertEqual(target.y, 1080, 'snaps to bottom edge');
  assert(target.width >= 1 && target.height >= 1, 'non-zero size so lamp does not treat as empty');
}

{
  const monitor = { x: 0, y: 0, width: 1920, height: 1080 };
  const target = lampTargetFromIcon({ x: 10, y: 20, width: 32, height: 32 }, 'left', monitor);
  assertEqual(target.x, 0, 'snaps to left edge');
  assertEqual(target.y, 20, 'keeps icon y');
}

{
  const css = separatorOverlayStyle('255,255,255,1.0');
  assert(css.includes('background-color: rgba(255,255,255,1.0)'), 'uses the given color');
  assert(css.includes('!important'), 'beats theme dash-separator styles');
}

{
  const h = separatorOverlaySize(48, 2, false, 1);
  assertEqual(h.width, 2, 'horizontal separator thickness is width');
  assert(h.height > 20, 'horizontal separator is tall enough to see');
  const v = separatorOverlaySize(48, 2, true, 1);
  assertEqual(v.height, 2, 'vertical separator thickness is height');
}

print('ok');
