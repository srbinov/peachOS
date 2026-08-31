#!/usr/bin/env gjs -m

import {
  LIQUID_GLASS_MODE,
  buildLiquidGlassDeclarations,
  buildDockBackgroundStyle,
  modeForColorScheme,
} from '../liquidGlass.js';

function assertIncludes(hay, needle) {
  if (!String(hay).includes(needle)) {
    throw new Error(`expected:\n  ${hay}\nto include:\n  ${needle}`);
  }
}

function assertNotIncludes(hay, needle) {
  if (String(hay).includes(needle)) {
    throw new Error(`expected:\n  ${hay}\nnot to include:\n  ${needle}`);
  }
}

function assertEqual(actual, expected) {
  if (actual !== expected) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

{
  const css = buildLiquidGlassDeclarations(LIQUID_GLASS_MODE.LIGHT).join('; ');
  assertIncludes(css, 'background-color: rgba(255, 255, 255, 0.12)');
  assertIncludes(css, 'background-gradient-direction: vertical');
  assertIncludes(css, 'background-gradient-start: rgba(255, 255, 255, 0.28)');
  assertIncludes(css, 'background-gradient-end: rgba(255, 255, 255, 0.08)');
  assertIncludes(css, 'border: 1px solid rgba(255, 255, 255, 0.42)');
  assertIncludes(css, 'box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5)');
}

{
  const css = buildLiquidGlassDeclarations(LIQUID_GLASS_MODE.DARK).join('; ');
  assertIncludes(css, 'background-color: rgba(0, 0, 0, 0.32)');
  assertIncludes(css, 'background-gradient-direction: vertical');
  assertIncludes(css, 'background-gradient-start: rgba(255, 255, 255, 0.16)');
  assertIncludes(css, 'background-gradient-end: rgba(0, 0, 0, 0.38)');
  assertIncludes(css, 'border: 1px solid rgba(255, 255, 255, 0.32)');
  assertIncludes(css, 'box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45)');
}

{
  assertEqual(LIQUID_GLASS_MODE.DARK, 0);
  assertEqual(LIQUID_GLASS_MODE.LIGHT, 1);
  const css = buildLiquidGlassDeclarations(undefined).join('; ');
  assertIncludes(css, 'background-color: rgba(0, 0, 0, 0.32)');
}

{
  const css = buildDockBackgroundStyle({
    liquidGlass: true,
    glassMode: LIQUID_GLASS_MODE.LIGHT,
    borderRadius: 42,
    panelMode: false,
    backgroundRgba: '0,0,0,0.5',
  });
  assertIncludes(css, 'border-radius: 42px');
  assertIncludes(css, 'background-gradient-start: rgba(255, 255, 255, 0.28)');
  assertNotIncludes(css, 'background: rgba(0,0,0,0.5)');
}

{
  const css = buildDockBackgroundStyle({
    liquidGlass: true,
    glassMode: LIQUID_GLASS_MODE.DARK,
    borderRadius: 24,
    panelMode: true,
    backgroundRgba: '0,0,0,0.5',
  });
  assertIncludes(css, 'border-radius: 0px');
  assertIncludes(css, 'background-color: rgba(0, 0, 0, 0.32)');
}

{
  const css = buildDockBackgroundStyle({
    liquidGlass: false,
    glassMode: LIQUID_GLASS_MODE.LIGHT,
    borderRadius: 16,
    panelMode: false,
    backgroundRgba: '10,20,30,0.4',
  });
  assertIncludes(css, 'border-radius: 16px');
  assertIncludes(css, 'background: rgba(10,20,30,0.4)');
  assertNotIncludes(css, 'background-gradient-direction');
}

{
  assertEqual(modeForColorScheme('prefer-dark'), LIQUID_GLASS_MODE.DARK);
  assertEqual(modeForColorScheme('default'), LIQUID_GLASS_MODE.LIGHT);
  assertEqual(modeForColorScheme('prefer-light'), LIQUID_GLASS_MODE.LIGHT);
  assertEqual(modeForColorScheme(undefined), LIQUID_GLASS_MODE.LIGHT);
}

print('ok');
