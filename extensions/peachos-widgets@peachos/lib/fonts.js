// Font application for widget labels.
//
// St CSS `font-family` and Clutter.Text.set_font_name() both round-trip through
// pango_font_description_from_string(), which parses a trailing "Condensed" (or
// "Light", "Black", ...) as a stretch/weight keyword -- so "Barlow Condensed"
// resolves to family "Barlow" + condensed stretch, finds nothing, and falls
// back to the UI font. Building the PangoFontDescription by hand with
// set_family() avoids that entirely.

import Pango from 'gi://Pango';

export const FAMILIES = {
    // digital clock readout
    barlow: 'Barlow Condensed',
    // analog dial numbers
    rounded: 'SF Pro Rounded',
    // everything else (weather, calendar)
    display: 'SF Pro Display',
};

/**
 * @param {St.Label} stLabel
 * @param {string} family  one of FAMILIES.*
 * @param {number} px      pixel size
 * @param {Pango.Weight} [weight]
 */
export function applyFont(stLabel, family, px, weight = Pango.Weight.NORMAL) {
    stLabel.clutter_text.set_font_description(fontDesc(family, px, weight));
}

/** A Pango.FontDescription for Cairo (PangoCairo) text. */
export function fontDesc(family, px, weight = Pango.Weight.NORMAL) {
    const d = Pango.FontDescription.new();
    d.set_family(family);
    d.set_weight(weight);
    d.set_absolute_size(Math.max(1, Math.round(px)) * Pango.SCALE);
    return d;
}

export {Pango};
