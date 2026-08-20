"""Dark-mode icon transform.

Derived from comparing real Apple light/dark icon pairs (Mail, Keynote,
Numbers, Pages, App Center vs. Contacts, Reminders, Photos, Find My, the
Apps grid) side by side. The deciding factor turned out to be simple: what
color is the icon's outer *card* -- sampled from a thin band near the
opaque silhouette's edge, which is reliably the backdrop and not whatever
glyph sits on top of it, regardless of how much of the total pixel area
that glyph covers (this matters: Find My's green rings cover *more* pixels
than its white card, so whole-image majority-by-pixel-count picked the
wrong "backdrop" and inverted the icon -- sampling just the edge doesn't
have that problem).

- Colored card (Mail's blue, Keynote's blue, Numbers' green, Pages'
  orange, App Center's blue): card color -> dark gray, white glyph ->
  becomes the original card color, black minority -> white (so detail
  drawn in black stays visible against the new dark card instead of
  disappearing into whatever the white minority became).
- White/light card (Contacts, Reminders, Photos, Find My, the Apps grid):
  card -> dark gray, but any already-colorful content is left completely
  untouched -- not recolored, not even dimmed. Apple's own dark Photos
  and Find My icons prove this: the rainbow flower and the green radar
  rings are pixel-for-pixel as vivid in dark mode as in light mode, only
  the white backdrop actually changed.
- No clean single edge color at all (Maps -- the edge itself is a mosaic
  of different map-tile hues, not one card color): gentle uniform darken,
  since there's no single color to swap to and recoloring would just
  smear everything into a muddy average.

Icons that are ALREADY majority-dark are left alone entirely -- they
already read fine in dark mode, nothing to invert.
"""
import numpy as np
from PIL import Image

WHITE_VALUE_THRESHOLD = 0.75
WHITE_SATURATION_THRESHOLD = 0.25
BLACK_VALUE_THRESHOLD = 0.35
ALREADY_DARK_MAJORITY_THRESHOLD = 0.5  # majority-black share of opaque pixels needed to skip

DARK_TARGET = np.array([0.11, 0.11, 0.12])  # ~#1c1c1e, real macOS dark-surface gray, not pure black

EDGE_BAND_FRACTION = 0.08           # how much of the icon's own size counts as "near the edge"
EDGE_MAJORITY_RATIO_THRESHOLD = 0.6  # top edge-bucket needs at least this share to count as decisive
BUSY_HUE_VARIANCE_THRESHOLD = 0.15  # edge itself is multi-hued (no single card color) -> darken-only
GENTLE_DARKEN_FACTOR = 0.35         # value-channel multiplier for the busy-icon path -- needs to be
                                     # low enough that a white backdrop actually reads as dark, not
                                     # medium gray (0.42 landed at ~107/255, still too bright)


def _hsv_arrays(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    s = np.where(maxc > 0, (maxc - minc) / np.where(maxc == 0, 1, maxc), 0)
    return v, s


def _hue_array(rgb):
    """Vectorized RGB->hue (matches colorsys.rgb_to_hsv's H), no per-pixel loop."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    diff = maxc - minc
    diff_safe = np.where(diff == 0, 1, diff)
    rc = (maxc - r) / diff_safe
    gc = (maxc - g) / diff_safe
    bc = (maxc - b) / diff_safe
    hue = np.select([maxc == r, maxc == g, maxc == b], [bc - gc, 2.0 + rc - bc, 4.0 + gc - rc])
    return (hue / 6.0) % 1.0


def _classify(img):
    arr = np.asarray(img.convert('RGBA')).astype(np.float32) / 255.0
    rgb = arr[..., :3]
    a = arr[..., 3]
    opaque = a > 0.5

    v, s = _hsv_arrays(rgb)
    white_mask = opaque & (v > WHITE_VALUE_THRESHOLD) & (s < WHITE_SATURATION_THRESHOLD)
    black_mask = opaque & (v < BLACK_VALUE_THRESHOLD)
    chromatic_mask = opaque & ~white_mask & ~black_mask

    return arr, opaque, white_mask, black_mask, chromatic_mask


def is_already_dark(img):
    """True if black is already the majority -- nothing to invert."""
    _, opaque, _, black_mask, _ = _classify(img)
    n_opaque = opaque.sum()
    if n_opaque == 0:
        return True
    return (black_mask.sum() / n_opaque) >= ALREADY_DARK_MAJORITY_THRESHOLD


def _edge_band_mask(opaque):
    """A thin ring just inside the opaque silhouette's own bounding box --
    reliably the card/backdrop, not whatever glyph sits in the middle,
    regardless of how much total area that glyph covers."""
    ys, xs = np.where(opaque)
    if ys.size == 0:
        return np.zeros_like(opaque)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    band = max(2, int(min(x1 - x0, y1 - y0) * EDGE_BAND_FRACTION))

    yy, xx = np.mgrid[0:opaque.shape[0], 0:opaque.shape[1]]
    near_edge = ((xx - x0) < band) | ((x1 - xx) < band) | ((yy - y0) < band) | ((y1 - yy) < band)
    return opaque & near_edge


def _card_type(rgb, white_mask, black_mask, chromatic_mask, edge_mask):
    """Returns ('white'|'black'|'chromatic'|'busy', edge pixel masks)."""
    edge_white = white_mask & edge_mask
    edge_black = black_mask & edge_mask
    edge_chromatic = chromatic_mask & edge_mask

    counts = {'white': edge_white.sum(), 'black': edge_black.sum(), 'chromatic': edge_chromatic.sum()}
    total = sum(counts.values())
    if total == 0:
        return 'busy'

    majority = max(counts, key=counts.get)
    if counts[majority] / total < EDGE_MAJORITY_RATIO_THRESHOLD:
        return 'busy'

    if majority == 'chromatic':
        hues = _hue_array(rgb)[edge_chromatic]
        _, sat = _hsv_arrays(rgb)
        weights = sat[edge_chromatic]
        weight_sum = weights.sum()
        if weight_sum > 0:
            angles = hues * 2 * np.pi
            resultant = np.hypot((np.cos(angles) * weights).sum(), (np.sin(angles) * weights).sum()) / weight_sum
            if (1 - resultant) > BUSY_HUE_VARIANCE_THRESHOLD:
                return 'busy'

    return majority


def _gentle_darken(rgb):
    # Scaling R/G/B by the same factor scales V (=max(r,g,b)) by that factor while leaving
    # hue and saturation untouched -- no HSV round-trip needed to darken without recoloring.
    return rgb * GENTLE_DARKEN_FACTOR


def apply_dark_mode(source_path_or_image, out_path=None):
    """Apply the dark-mode transform. Accepts a path or an already-open PIL
    Image; returns the resulting Image (and also saves it if out_path is
    given)."""
    img = source_path_or_image if isinstance(source_path_or_image, Image.Image) else Image.open(source_path_or_image)
    arr, opaque, white_mask, black_mask, chromatic_mask = _classify(img)
    rgb = arr[..., :3]
    edge_mask = _edge_band_mask(opaque)
    card = _card_type(rgb, white_mask, black_mask, chromatic_mask, edge_mask)

    if card == 'busy':
        out_rgb = _gentle_darken(rgb)
    elif card == 'chromatic':
        edge_chromatic = chromatic_mask & edge_mask
        card_color = rgb[edge_chromatic].mean(axis=0) if edge_chromatic.any() else DARK_TARGET
        out_rgb = rgb.copy()
        out_rgb[chromatic_mask] = DARK_TARGET
        out_rgb[white_mask] = card_color
        out_rgb[black_mask] = np.array([1.0, 1.0, 1.0])
    elif card == 'white':
        out_rgb = rgb.copy()
        out_rgb[white_mask] = DARK_TARGET
        out_rgb[black_mask] = 1.0
        # chromatic content is deliberately left untouched -- see module docstring
    else:  # card == 'black' -- shouldn't normally reach here (caller should check is_already_dark first)
        out_rgb = rgb.copy()
        out_rgb[black_mask] = 1.0
        out_rgb[white_mask] = DARK_TARGET

    out = np.concatenate([out_rgb, arr[..., 3:4]], axis=-1)
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    result = Image.fromarray(out, 'RGBA')
    if out_path:
        result.save(out_path, 'PNG')
    return result
