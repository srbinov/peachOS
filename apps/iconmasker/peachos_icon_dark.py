"""Dark-mode icon transform.

Two treatments, chosen per-icon:

1. Majority/minority swap (simple, mostly-two-tone icons -- Mail, Peachy,
   most app icons). Classify every opaque pixel as white, black, or
   chromatic; whichever bucket has the most pixels is the "majority":
     - chromatic majority (the common case): majority -> dark gray,
       white minority -> the icon's original majority color, black
       minority -> white (so fine detail drawn in black, like Peachy's
       eyes/mouth, stays visible against the new dark backdrop instead of
       blending into whatever the white minority became).
     - white/black majority (already-achromatic icon): swap white <-> dark
       gray directly.
   "Dark gray" rather than pure black throughout -- matches real macOS
   dark surfaces (~#1c1c1e) and reads as noticeably softer than a harsh
   true-black fill.

2. Gentle darken (busy, many-hued icons -- Maps, Find My, anything
   photographic/illustrative where there's no single clean majority
   color to swap to). Detected via hue spread: if the chromatic pixels
   don't cluster around one hue, recoloring would just smear them into a
   muddy average. Instead, leave every hue alone and only pull down
   brightness uniformly.

Icons that are ALREADY majority-dark are left alone entirely either way --
they already read fine in dark mode, nothing to invert.
"""
import numpy as np
from PIL import Image

WHITE_VALUE_THRESHOLD = 0.75
WHITE_SATURATION_THRESHOLD = 0.25
BLACK_VALUE_THRESHOLD = 0.35
ALREADY_DARK_MAJORITY_THRESHOLD = 0.5  # majority-black share of opaque pixels needed to skip

DARK_TARGET = np.array([0.11, 0.11, 0.12])  # ~#1c1c1e, real macOS dark-surface gray, not pure black

BUSY_HUE_VARIANCE_THRESHOLD = 0.15  # circular variance above this -> "too many colors", darken-only
                                     # (measured: clean two-tone icons sit at ~0.002-0.006, Maps/Find
                                     # My/Photos-style multi-hue icons at 0.23+ -- wide margin either side)
BUSY_MIN_CHROMATIC_SHARE = 0.15     # only worth computing hue spread if there's a real chromatic body
MAJORITY_RUNNERUP_RATIO_THRESHOLD = 0.8  # top two buckets nearly tied -> no clean majority to swap to
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


def _is_busy(rgb, opaque, white_mask, black_mask, chromatic_mask):
    """Many-hued icon (map, photo, illustration) vs a clean two-tone one --
    or, separately, an icon with no clear majority at all (e.g. a gradient
    logo whose highlights cover nearly as much area as its base color).
    Either way, a two-color swap has nothing solid to grab onto."""
    n_opaque = opaque.sum()
    if n_opaque == 0:
        return False

    if chromatic_mask.sum() / n_opaque >= BUSY_MIN_CHROMATIC_SHARE:
        hues = _hue_array(rgb)[chromatic_mask]
        _, sat = _hsv_arrays(rgb)
        weights = sat[chromatic_mask]
        # Weight by saturation: near-gray pixels have numerically unstable hue (tiny RGB
        # noise swings the angle wildly) that would otherwise inflate variance for icons
        # that are really just one accent color plus a lot of gray/near-white body.
        angles = hues * 2 * np.pi
        weight_sum = weights.sum()
        if weight_sum > 0:
            resultant = np.hypot((np.cos(angles) * weights).sum(), (np.sin(angles) * weights).sum()) / weight_sum
            circular_variance = 1 - resultant
            if circular_variance > BUSY_HUE_VARIANCE_THRESHOLD:
                return True

    counts = sorted([white_mask.sum(), black_mask.sum(), chromatic_mask.sum()], reverse=True)
    if counts[0] > 0 and counts[1] / counts[0] > MAJORITY_RUNNERUP_RATIO_THRESHOLD:
        return True

    return False


def _gentle_darken(rgb):
    # Scaling R/G/B by the same factor scales V (=max(r,g,b)) by that factor while leaving
    # hue and saturation untouched -- no HSV round-trip needed to darken without recoloring.
    return rgb * GENTLE_DARKEN_FACTOR


def apply_dark_mode(source_path_or_image, out_path=None):
    """Apply the dark-mode transform (majority/minority swap, or gentle
    darken for busy multi-hued icons). Accepts a path or an already-open
    PIL Image; returns the resulting Image (and also saves it if out_path
    is given)."""
    img = source_path_or_image if isinstance(source_path_or_image, Image.Image) else Image.open(source_path_or_image)
    arr, opaque, white_mask, black_mask, chromatic_mask = _classify(img)

    if _is_busy(arr[..., :3], opaque, white_mask, black_mask, chromatic_mask):
        out_rgb = _gentle_darken(arr[..., :3])
    else:
        n_white, n_black, n_chromatic = white_mask.sum(), black_mask.sum(), chromatic_mask.sum()
        buckets = {'white': n_white, 'black': n_black, 'chromatic': n_chromatic}
        majority = max(buckets, key=buckets.get)

        out_rgb = arr[..., :3].copy()
        if majority == 'chromatic':
            maj_color = arr[chromatic_mask][:, :3].mean(axis=0) if n_chromatic else DARK_TARGET
            out_rgb[chromatic_mask] = DARK_TARGET
            out_rgb[white_mask] = maj_color
            out_rgb[black_mask] = np.array([1.0, 1.0, 1.0])
        elif majority == 'white':
            out_rgb[white_mask] = DARK_TARGET
            out_rgb[black_mask] = 1.0
        else:  # majority == 'black' -- shouldn't normally reach here (caller should check is_already_dark first)
            out_rgb[black_mask] = 1.0
            out_rgb[white_mask] = DARK_TARGET

    out = np.concatenate([out_rgb, arr[..., 3:4]], axis=-1)
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    result = Image.fromarray(out, 'RGBA')
    if out_path:
        result.save(out_path, 'PNG')
    return result
