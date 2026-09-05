// Font helpers for widget labels.
//
// The widget fonts (Barlow Condensed, SF Pro Display/Rounded) are vendored in
// fonts/ and installed system-wide by provision.sh, together with a fontconfig
// alias file (provision/fontconfig/49-peachos-widgets.conf) that maps
// keyword-free names -- Pango parses a literal "Barlow Condensed" as family
// "Barlow" + condensed-stretch and fails otherwise. Use the alias names below
// in St `font-family` (via fontStyle()).

import Pango from 'gi://Pango';

export const FONT = {
    clock: 'PeachClock',            // Barlow Condensed Medium
    rounded: 'PeachRounded',        // SF Pro Rounded
    display: 'PeachDisplay',        // SF Pro Display Regular
    displayThin: 'PeachDisplayThin', // SF Pro Display Thin
};

/** Inline St style string for a text label. */
export function fontStyle(family, px, opacity = 1) {
    const color = opacity >= 1 ? '#ffffff' : `rgba(255,255,255,${opacity})`;
    return `font-family: "${family}"; font-size: ${Math.max(1, Math.round(px))}px; color: ${color};`;
}

/** Pango.FontDescription for PangoCairo text (calendar today badge). */
export function fontDesc(family, px) {
    const d = Pango.FontDescription.from_string(family);
    d.set_absolute_size(Math.max(1, Math.round(px)) * Pango.SCALE);
    return d;
}

export {Pango};
