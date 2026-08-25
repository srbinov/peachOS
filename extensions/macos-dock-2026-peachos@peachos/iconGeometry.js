'use strict';

export const matchIconForApp = (icons, { appId, pid } = {}) => {
  if (!icons || !icons.length) {
    return null;
  }
  if (appId) {
    const byId = icons.find((i) => i.appId === appId);
    if (byId) {
      return byId;
    }
  }
  if (pid != null) {
    const byPid = icons.find(
      (i) => Array.isArray(i.pids) && i.pids.indexOf(pid) >= 0
    );
    if (byPid) {
      return byPid;
    }
  }
  return null;
};

export const lampTargetFromIcon = (icon, position, monitor) => {
  const width = Math.max(1, Math.round(icon.width || 0));
  const height = Math.max(1, Math.round(icon.height || 0));
  let x = icon.x;
  let y = icon.y;
  switch (position) {
    case 'left':
      x = monitor.x;
      break;
    case 'right':
      x = monitor.x + monitor.width;
      break;
    case 'top':
      y = monitor.y;
      break;
    case 'bottom':
    default:
      y = monitor.y + monitor.height;
      break;
  }
  return { x, y, width, height };
};

export const separatorOverlayStyle = (rgbaString) => {
  return `background-color: rgba(${rgbaString}) !important; border-radius: 1px;`;
};

export const separatorOverlaySize = (
  iconSize,
  thickness,
  vertical,
  scaleFactor
) => {
  let t = Math.max(1, Number(thickness) || 0);
  let sf = scaleFactor || 1;
  if (vertical) {
    return { width: iconSize * 0.5 * sf, height: t };
  }
  return { width: t, height: iconSize * 0.55 * sf };
};
