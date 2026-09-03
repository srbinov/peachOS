'use strict';

export const LIQUID_GLASS_MODE = {
  DARK: 0,
  LIGHT: 1,
};

// {r,g,b,a} form so the intensity slider can interpolate toward a solid target. At
// intensity 100 these are exactly the values the dock always used.
const LIGHT = {
  fill: [255, 255, 255, 0.12],
  gradientStart: [255, 255, 255, 0.28],
  gradientEnd: [255, 255, 255, 0.08],
  border: [255, 255, 255, 0.42],
  inset: [255, 255, 255, 0.5],
};

const DARK = {
  fill: [0, 0, 0, 0.32],
  gradientStart: [255, 255, 255, 0.16],
  gradientEnd: [0, 0, 0, 0.38],
  border: [255, 255, 255, 0.32],
  inset: [255, 255, 255, 0.45],
};

// Solid target each recipe collapses to at intensity 0 -- white plate in light glass mode,
// a macOS-style surface gray in dark glass mode.
const SOLID_LIGHT = [255, 255, 255];
const SOLID_DARK = [28, 28, 30];

const lerp = (a, b, t) => a + (b - a) * t;

// @param solidAlpha  alpha at intensity 0 -- 1 (opaque) for fill/gradient stops so they
//   become a solid plate; lower for border/inset so they fade toward faint instead.
const interp = (rgba, solid, t, solidAlpha) => {
  const [r, g, b, a] = rgba;
  return `rgba(${Math.round(lerp(solid[0], r, t))}, ${Math.round(lerp(solid[1], g, t))}, ` +
    `${Math.round(lerp(solid[2], b, t))}, ${Math.round(lerp(solidAlpha, a, t) * 1000) / 1000})`;
};

/**
 * @param {number} mode LIQUID_GLASS_MODE.LIGHT | .DARK
 * @param {number} [intensity] 0-100 (default 100 = full glass, the original look)
 */
export const buildLiquidGlassDeclarations = (mode, intensity = 100) => {
  const recipe = mode === LIQUID_GLASS_MODE.LIGHT ? LIGHT : DARK;
  const solid = mode === LIQUID_GLASS_MODE.LIGHT ? SOLID_LIGHT : SOLID_DARK;
  const t = Math.max(0, Math.min(100, intensity)) / 100;
  return [
    `background-color: ${interp(recipe.fill, solid, t, 1)}`,
    'background-gradient-direction: vertical',
    `background-gradient-start: ${interp(recipe.gradientStart, solid, t, 1)}`,
    `background-gradient-end: ${interp(recipe.gradientEnd, solid, t, 1)}`,
    `border: 1px solid ${interp(recipe.border, solid, t, 0.18)}`,
    `box-shadow: inset 0 1px 0 ${interp(recipe.inset, solid, t, 0)}`,
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
    glassIntensity = 100,
    borderRadius,
    panelMode,
    backgroundRgba,
  } = params;
  const radius = panelMode ? 0 : borderRadius;
  const parts = [`border-radius: ${radius}px`];
  if (liquidGlass) {
    parts.push(...buildLiquidGlassDeclarations(glassMode, glassIntensity));
  } else if (backgroundRgba) {
    parts.push(`background: rgba(${backgroundRgba})`);
  }
  return `${parts.join('; ')};`;
};
