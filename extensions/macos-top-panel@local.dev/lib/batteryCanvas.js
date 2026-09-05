// Draws a real macOS-style battery glyph -- outline + a fill bar sized proportionally to
// the actual charge percentage, plus a small lightning-bolt overlay while charging.
// Replaces the old static battery-*.png / battery-charging-*.png assets, which always
// looked "full" no matter the real charge level.
//
// St.DrawingArea + the legacy `imports.cairo` binding (Cairo has no GObject-Introspection
// namespace, so it's not a `gi://Cairo` import) -- confirmed as the correct, working
// pattern for GNOME Shell 50 against a real, currently-loaded extension
// (ubuntu-dock@ubuntu.com/appIconIndicators.js), not guessed.
const {cairo: Cairo} = imports;

// All authored for a 22x13 glyph; drawBattery() scales to whatever pixel size it's
// actually asked to render at.
const GLYPH_WIDTH = 22;
const GLYPH_HEIGHT = 13;
const NUB_WIDTH = 2;
const NUB_HEIGHT_RATIO = 0.42;
const OUTLINE_WIDTH = 1.3;
const CORNER_RADIUS = 2.3;
const FILL_INSET = 2;
// Fill-color thresholds (explicit request): <=10% red, 11-20% yellow while on battery;
// green once it's hit 100% but the charger is still plugged in; normal foreground otherwise.
const RED_THRESHOLD = 10;
const YELLOW_THRESHOLD = 20;
const FILL_RED = [1, 0.23, 0.19, 1];       // macOS low-battery red
const FILL_YELLOW = [1, 0.8, 0.0, 1];      // macOS charging-bolt yellow
const FILL_GREEN = [0.3, 0.85, 0.39, 1];   // macOS "full" green

function roundedRectPath(cr, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    cr.newSubPath();
    cr.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
    cr.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    cr.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
    cr.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
    cr.closePath();
}

/**
 * @param {Cairo.Context} cr
 * @param {number} widthPx actor width in device pixels (already scale-factor-adjusted)
 * @param {number} heightPx actor height in device pixels
 * @param {{percentage: number, charging: boolean, foreground: 'black'|'white'}} state
 */
export function drawBattery(cr, widthPx, heightPx, state) {
    const scale = widthPx / GLYPH_WIDTH;
    cr.save();
    cr.scale(scale, scale);

    const fg = state.foreground === 'black' ? [0, 0, 0] : [1, 1, 1];
    const bodyWidth = GLYPH_WIDTH - NUB_WIDTH;
    const nubHeight = GLYPH_HEIGHT * NUB_HEIGHT_RATIO;

    // Outline
    cr.setLineWidth(OUTLINE_WIDTH);
    cr.setSourceRGBA(fg[0], fg[1], fg[2], 0.6);
    roundedRectPath(
        cr, OUTLINE_WIDTH / 2, OUTLINE_WIDTH / 2,
        bodyWidth - OUTLINE_WIDTH, GLYPH_HEIGHT - OUTLINE_WIDTH, CORNER_RADIUS
    );
    cr.stroke();

    // Terminal nub
    cr.setSourceRGBA(fg[0], fg[1], fg[2], 0.6);
    cr.rectangle(bodyWidth - OUTLINE_WIDTH / 2, (GLYPH_HEIGHT - nubHeight) / 2, NUB_WIDTH, nubHeight);
    cr.fill();

    // Fill bar -- width is the actual accuracy fix; everything above is fixed chrome.
    const pct = Math.max(0, Math.min(100, state.percentage));
    const innerX = FILL_INSET;
    const innerY = FILL_INSET;
    const innerW = bodyWidth - FILL_INSET * 2;
    const innerH = GLYPH_HEIGHT - FILL_INSET * 2;
    const fillW = Math.max(0, Math.round((innerW * pct) / 100));

    if (fillW > 0) {
        let color;
        if (state.charging && pct >= 100)
            color = FILL_GREEN;
        else if (!state.charging && pct <= RED_THRESHOLD)
            color = FILL_RED;
        else if (!state.charging && pct <= YELLOW_THRESHOLD)
            color = FILL_YELLOW;
        else
            color = [fg[0], fg[1], fg[2], 0.9];
        cr.setSourceRGBA(color[0], color[1], color[2], color[3]);
        roundedRectPath(cr, innerX, innerY, fillW, innerH, Math.min(1.2, innerH / 2));
        cr.fill();
    }

    // Charging bolt, centered on the body, drawn on top of the fill.
    if (state.charging) {
        cr.save();
        cr.translate(bodyWidth / 2, GLYPH_HEIGHT / 2);
        const boltScale = GLYPH_HEIGHT / 13; // path authored for a 13px-tall glyph
        cr.scale(boltScale, boltScale);
        cr.moveTo(0.6, -4.5);
        cr.lineTo(-2.6, 0.6);
        cr.lineTo(-0.3, 0.6);
        cr.lineTo(-0.9, 4.5);
        cr.lineTo(2.6, -0.8);
        cr.lineTo(0.2, -0.8);
        cr.closePath();
        cr.setSourceRGBA(1, 0.8, 0.2, 1); // matches macOS's own charging-bolt yellow
        cr.fill();
        cr.restore();
    }

    cr.restore();
}
