#!/usr/bin/env gjs -m

import {
  iconSizeFromScale,
  iconSpacedSize,
  extraIconsVisible,
  SIZE_SLIDER_DEFAULT,
} from '../iconMetrics.js';

function assertEqual(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(
      `${msg || 'assertEqual'}: expected ${expected}, got ${actual}`
    );
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assert failed');
}

{
  assertEqual(iconSizeFromScale(0), 8, 'slider min is 8px');
  assertEqual(iconSizeFromScale(1), 128, 'slider max is 128px');
  assertEqual(iconSizeFromScale(SIZE_SLIDER_DEFAULT), 32, 'default slider is 32px');
  assert(iconSizeFromScale(0.5) > iconSizeFromScale(SIZE_SLIDER_DEFAULT), 'larger slider is larger icons');
  assertEqual(iconSizeFromScale(-1), 8, 'legacy values below zero clamp to min');
}

{
  const tight = iconSpacedSize(48, -0.5, 0);
  const normal = iconSpacedSize(48, 0.5, 0);
  const loose = iconSpacedSize(48, 1, 0);
  assert(tight < normal, 'negative spacing packs tighter than default');
  assert(loose > normal, 'max spacing is looser than default');
  assert(tight < 48, 'negative spacing makes the slot smaller than the icon');
}

{
  assertEqual(extraIconsVisible(1, 0), false, 'separator-only box stays hidden');
  assertEqual(extraIconsVisible(2, 0), true, 'trash/downloads make extras visible');
  assertEqual(extraIconsVisible(3, 1), true, 'separator plus folders is visible');
}

print('ok');
