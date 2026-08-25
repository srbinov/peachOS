'use strict';

export const LIQUID_GLASS_MODE = {
  DARK: 0,
  LIGHT: 1,
};

const LIGHT = {
  fill: 'rgba(255, 255, 255, 0.12)',
  gradientStart: 'rgba(255, 255, 255, 0.28)',
  gradientEnd: 'rgba(255, 255, 255, 0.08)',
  border: 'rgba(255, 255, 255, 0.42)',
  inset: 'rgba(255, 255, 255, 0.5)',
};

const DARK = {
  fill: 'rgba(0, 0, 0, 0.32)',
  gradientStart: 'rgba(255, 255, 255, 0.16)',
  gradientEnd: 'rgba(0, 0, 0, 0.38)',
  border: 'rgba(255, 255, 255, 0.32)',
  inset: 'rgba(255, 255, 255, 0.45)',
};

export const buildLiquidGlassDeclarations = (mode) => {
  const t = mode === LIQUID_GLASS_MODE.LIGHT ? LIGHT : DARK;
  return [
    `background-color: ${t.fill}`,
    'background-gradient-direction: vertical',
    `background-gradient-start: ${t.gradientStart}`,
    `background-gradient-end: ${t.gradientEnd}`,
    `border: 1px solid ${t.border}`,
    `box-shadow: inset 0 1px 0 ${t.inset}`,
  ];
};

// Liquid Glass mode isn't a manual choice -- it always follows
// org.gnome.desktop.interface's color-scheme (see extension.js's
// _syncLiquidGlassMode()), the same key macOS-TopBar-Gnome's own
// AppearanceController watches for the identical reason: the dock should
// look like the rest of peachOS, not disagree with it.
export const modeForColorScheme = (colorScheme) =>
  colorScheme === 'prefer-dark' ? LIQUID_GLASS_MODE.DARK : LIQUID_GLASS_MODE.LIGHT;

export const buildDockBackgroundStyle = (params) => {
  const {
    liquidGlass,
    glassMode,
    borderRadius,
    panelMode,
    backgroundRgba,
  } = params;
  const radius = panelMode ? 0 : borderRadius;
  const parts = [`border-radius: ${radius}px`];
  if (liquidGlass) {
    parts.push(...buildLiquidGlassDeclarations(glassMode));
  } else if (backgroundRgba) {
    parts.push(`background: rgba(${backgroundRgba})`);
  }
  return `${parts.join('; ')};`;
};
