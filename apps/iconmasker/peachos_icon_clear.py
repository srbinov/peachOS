"""Clear-mode ("liquid glass") icon transform.

Visual target matches this project's own liquid-glass recipe already used
for the Control Center dropdown and notifications (see
macOS-TopBar-Gnome/docs/liquid-glass-style.md): a strongly translucent
frosted card, a brighter-at-top/quieter-at-bottom sheen, a bright rim, and
a top inset highlight line. Real macOS Clear icons keep the app's own
glyph (Mail's envelope, Pages' pencil) vivid and opaque while the card
behind it goes glassy -- that contrast is the whole effect, so a weak,
whole-icon-uniform fade reads as "barely changed," not glass.

History, both false starts kept here so the actual failure modes aren't
rediscovered by a future edit:

  v1 (edge-connected flood fill of the card region, hard alpha cut):
  looked right on icons with a real card+glyph split (Mail, Contacts), but
  two bugs -- the flood fill ran on a heavily downsampled grid and was
  upsampled with nearest-neighbor, producing a blocky/pixelated boundary
  at real icon size; and full-bleed icons with no separate glyph (App
  Center, Numbers, Notes -- see peachos_icon_resolve.py's OWN_DIRS comment
  on these running edge-to-edge) got ~100% of their pixels classified as
  "card" and dropped to ~40% alpha, reading as shrunk/faded away.

  v2 (uniform whole-icon gentle fade, no card/glyph split at all): fixed
  both v1 bugs by removing the classification entirely, but overcorrected
  -- the fade was so mild the result barely looked different from Default,
  which is exactly what got called "what happened to the liquid glass
  effect."

This version keeps v1's actual idea (glass the card, keep the glyph
vivid) but fixes both bugs directly: the card mask is now a continuous
[0, 1] weight, feathered with a real Gaussian blur after upsampling
instead of nearest-neighbor (no staircase, no pixelation), and icons where
the "card" turns out to cover almost the entire icon (no real separate
glyph to protect) fall back to a gentler whole-icon glass pass instead of
nearly erasing themselves. The rim is drawn at full strength regardless --
it's what keeps an icon's outer silhouette (and so its apparent size)
crisp even where the interior has gone very translucent.
"""
import numpy as np
from PIL import Image, ImageFilter

from peachos_icon_dark import _card_type, _classify, _edge_band_mask

FLOOD_DOWNSAMPLE = 220        # low-res BFS grid -- coarse blob connectivity, not per-pixel precision
FLOOD_FEATHER_PX = 18         # Gaussian blur radius (at full res) applied to the upsampled mask

SOFTEN_SIZE = 224             # final low-pass pass: downscale to this then back up to CANVAS with
                               # LANCZOS both ways -- real icon display size is a fraction of the
                               # 1024 source, so any fine per-pixel noise the composite steps above
                               # leave behind (float rounding, blur-on-blur seams) is well above
                               # what a ~45-64px dock icon can even show; capping the output's own
                               # max spatial frequency here means there's nothing left for a
                               # mediocre runtime scaler to alias into visible grain/blockiness

FULLBLEED_CARD_FRACTION = 0.85  # card covering more than this share of the opaque area means
                                 # "this icon has no separable glyph" -- glass the whole thing gently
                                 # instead of nearly erasing it

CARD_ALPHA = 0.40             # strong glass on the card region -- this is the actual effect, not a hint
CARD_WHITEN = 0.6             # pushed toward white but keeps a hint of the card's own hue

FULLBLEED_ALPHA = 0.68        # gentler than CARD_ALPHA -- no separate glyph to protect, so the whole
                               # icon needs to stay legible on its own
FULLBLEED_WHITEN = 0.4

GRADIENT_TOP = 1.16
GRADIENT_BOTTOM = 0.90
GRADIENT_SPAN = 0.6

RIM_STRENGTH = 0.72           # deliberately strong: the rim is what keeps an icon's true silhouette
                               # (and apparent size) readable once the interior goes translucent
RIM_BAND_FRACTION = 0.04
RIM_BLUR_PX = 8

TOP_HIGHLIGHT_STRENGTH = 0.5
TOP_HIGHLIGHT_BAND_FRACTION = 0.055
TOP_HIGHLIGHT_SPAN = 0.16
TOP_HIGHLIGHT_BLUR_PX = 12

WHITE = np.array([1.0, 1.0, 1.0], dtype=np.float32)


def _flood_from_edge(region_mask, seed_mask, downsample=FLOOD_DOWNSAMPLE, feather_px=FLOOD_FEATHER_PX):
    """Continuous [0, 1] weight for the pixels of region_mask that are
    4-connected to seed_mask -- e.g. the actual backdrop card (a same-color
    blob touching the icon's edge), not some other same-coarse-color
    content sitting disconnected in the middle. BFS runs on a small
    downsampled grid for speed (icon card/glyph shapes are large simple
    blobs, coarse connectivity is all that's needed), but the result is
    upsampled with bilinear + a real Gaussian blur, not nearest-neighbor --
    a hard-edged mask reads as pixelated once composited at real icon
    size, a feathered one reads as an actual soft glass edge."""
    h, w = region_mask.shape
    scale = min(downsample / max(h, w), 1.0)
    small_h, small_w = max(1, round(h * scale)), max(1, round(w * scale))

    def down(mask):
        im = Image.fromarray((mask.astype(np.uint8) * 255)).resize((small_w, small_h), Image.NEAREST)
        return np.asarray(im) > 127

    region_s = down(region_mask)
    filled = down(seed_mask) & region_s
    while True:
        grown = (
            filled
            | np.roll(filled, 1, axis=0) | np.roll(filled, -1, axis=0)
            | np.roll(filled, 1, axis=1) | np.roll(filled, -1, axis=1)
        ) & region_s
        if np.array_equal(grown, filled):
            break
        filled = grown

    up = Image.fromarray((filled.astype(np.uint8) * 255)).resize((w, h), Image.BILINEAR)
    up = up.filter(ImageFilter.GaussianBlur(feather_px))
    weight = np.asarray(up).astype(np.float32) / 255.0
    return weight * region_mask


def _band_weight(opaque, band_fraction, blur_px, y_span=None):
    """A continuous (blurred) weight in [0, 1] for a band near the opaque
    silhouette's own edge -- same feathering rationale as _flood_from_edge."""
    ys, xs = np.where(opaque)
    if ys.size == 0:
        return np.zeros(opaque.shape, dtype=np.float32)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    band = max(2, int(min(x1 - x0, y1 - y0) * band_fraction))

    yy, xx = np.mgrid[0:opaque.shape[0], 0:opaque.shape[1]]
    mask = opaque & (((xx - x0) < band) | ((x1 - xx) < band) | ((yy - y0) < band) | ((y1 - yy) < band))
    if y_span is not None:
        span_end = y0 + int((y1 - y0) * y_span)
        mask = mask & (yy >= y0) & (yy < span_end)

    im = Image.fromarray((mask.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(blur_px))
    weight = np.asarray(im).astype(np.float32) / 255.0
    return weight * opaque


def apply_clear_mode(source_path_or_image, out_path=None):
    """Apply the clear/liquid-glass transform. Accepts a path or an already-
    open PIL Image; returns the resulting Image (and also saves it if
    out_path is given)."""
    img = source_path_or_image if isinstance(source_path_or_image, Image.Image) else Image.open(source_path_or_image)
    arr, opaque, white_mask, black_mask, chromatic_mask = _classify(img)
    rgb = arr[..., :3].copy()
    alpha = arr[..., 3].copy()
    edge_mask = _edge_band_mask(opaque)
    card = _card_type(rgb, white_mask, black_mask, chromatic_mask, edge_mask)

    bucket_mask = {'white': white_mask, 'black': black_mask, 'chromatic': chromatic_mask}.get(card)
    n_opaque = opaque.sum()
    if bucket_mask is None or not bucket_mask.any() or n_opaque == 0:
        card_weight = opaque.astype(np.float32)
        full_bleed = True
    else:
        seed = bucket_mask & edge_mask
        card_weight = _flood_from_edge(bucket_mask, seed if seed.any() else bucket_mask)
        full_bleed = (card_weight > 0.5).sum() / n_opaque > FULLBLEED_CARD_FRACTION

    card_alpha, card_whiten = (FULLBLEED_ALPHA, FULLBLEED_WHITEN) if full_bleed else (CARD_ALPHA, CARD_WHITEN)
    w = card_weight[..., None]
    rgb = rgb * (1 - w * card_whiten) + WHITE * (w * card_whiten)
    alpha = alpha * (1 - card_weight * (1 - card_alpha))

    ys, xs = np.where(opaque)
    if ys.size:
        y0, y1 = ys.min(), ys.max()
        height = max(y1 - y0, 1)
        grad_rows = np.linspace(GRADIENT_TOP, GRADIENT_BOTTOM, int(height * GRADIENT_SPAN) or 1)
        grad = np.full(opaque.shape[0], GRADIENT_BOTTOM, dtype=np.float32)
        grad[y0:y0 + len(grad_rows)] = grad_rows
        grad[:y0] = GRADIENT_TOP
        # Only the glassed part of the icon gets the curvature sheen -- an untouched glyph
        # shouldn't dim/brighten on top of its own real color.
        blend = card_weight[:, :, None]
        rgb = np.clip(rgb * (1 - blend) + np.clip(rgb * grad[:, None, None], 0, 1) * blend, 0, 1)

    rim_w = _band_weight(opaque, RIM_BAND_FRACTION, RIM_BLUR_PX)[..., None] * RIM_STRENGTH
    rgb = rgb * (1 - rim_w) + WHITE * rim_w
    alpha = np.maximum(alpha, rim_w[..., 0])

    top_w = _band_weight(opaque, TOP_HIGHLIGHT_BAND_FRACTION, TOP_HIGHLIGHT_BLUR_PX, y_span=TOP_HIGHLIGHT_SPAN)
    top_w = top_w[..., None] * TOP_HIGHLIGHT_STRENGTH
    rgb = rgb * (1 - top_w) + WHITE * top_w

    out = np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=-1)
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    result = Image.fromarray(out, 'RGBA')

    canvas = result.size[0]
    result = result.resize((SOFTEN_SIZE, SOFTEN_SIZE), Image.LANCZOS).resize((canvas, canvas), Image.LANCZOS)

    if out_path:
        result.save(out_path, 'PNG')
    return result
