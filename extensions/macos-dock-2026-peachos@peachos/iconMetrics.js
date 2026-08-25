'use strict';

export const DEFAULT_ICON_PX = 32;
export const MIN_ICON_PX = 8;
export const MAX_ICON_PX = 128;
export const SIZE_SLIDER_DEFAULT =
  (DEFAULT_ICON_PX - MIN_ICON_PX) / (MAX_ICON_PX - MIN_ICON_PX);

export const preferredIconSizes = () => {
  const sizes = [];
  for (let i = MIN_ICON_PX; i <= MAX_ICON_PX; i += 4) {
    sizes.push(i);
  }
  return sizes;
};

export const iconSizeFromScale = (scale) => {
  const sizes = preferredIconSizes();
  let t = Number(scale);
  if (!Number.isFinite(t)) t = SIZE_SLIDER_DEFAULT;
  t = Math.min(1, Math.max(0, t));
  const idx = Math.round(t * (sizes.length - 1));
  return sizes[idx];
};

export const iconSpacedSize = (iconSize, iconSpacing, animationSpread) => {
  const extra = 2 + 8 * (animationSpread || 0) + 8 * (iconSpacing || 0);
  return Math.max(iconSize * 0.5, iconSize + extra);
};

export const extraIconsVisible = (childCount, _separatorThickness) => {
  return childCount > 1;
};
