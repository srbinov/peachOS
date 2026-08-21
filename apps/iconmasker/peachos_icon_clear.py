"""Clear-mode icon transform.

Rewritten from real reference art: the user hand-authored Clear-mode icons
for Keynote (blue card), Numbers (green card), and Pages (orange card) --
see resolve_curated_clear() in peachos_icon_resolve.py, which uses those
exact files instead of this algorithm wherever they exist. This algorithm
exists to give every OTHER icon (Mail, Contacts, App Center, the Apps grid,
etc.) the same treatment those three establish, so Clear mode looks like one
consistent design language across icons nobody hand-drew a variant for.

What the reference art actually does (measured directly, pixel-by-pixel,
against the real Default vs. Clear pairs -- not guessed):

  - Fully opaque. Alpha is essentially untouched (mean ~0.998 either way).
    This is NOT a translucent/frosted-glass effect -- an earlier version of
    this file assumed liquid-glass (semi-transparent card, bright rim, top
    sheen) because that's this project's OWN visual language for other UI
    surfaces (Control Center, notifications), but real reference icon art
    proved that guess wrong for icons specifically: saturation drops to
    *exactly* zero (confirmed: max measured output saturation was 0.0000)
    but nothing goes see-through.
  - The card (backdrop) and the glyph drawn on it both fully desaturate --
    every hue (Keynote's blue, Numbers' green, Pages' orange) ends up as
    plain gray, no tint kept at all.
  - The two roles land in two different, but fixed and consistent, gray
    bands regardless of the source hue: the card region compresses into a
    muted mid-gray band, the glyph drawn on it into a lighter band -- e.g.
    Keynote's vivid blue card and Pages' vivid orange card both end up
    reading as close to the same gray, which a straight luma-preserving
    desaturation (keeping each icon's own relative brightness) would NOT
    produce, since raw blue and raw orange have very different luma. Each
    icon's own internal shading/gradient (the card's built-in light-to-dark
    sweep, the glyph's own highlight/shadow) is kept -- just percentile-
    stretched into that fixed target band instead of erased into a flat
    fill, which is what actually reads as "the same real icon, in gray"
    instead of a flat cardboard cutout.

Card vs. glyph classification reuses peachos_icon_dark.py's own
edge-sampled classifier wholesale (_classify/_card_type/_edge_band_mask) --
the same "what's the backdrop" question dark mode already had to answer
correctly (Find My's green rings covering more pixels than its white card
was the case that proved edge-sampling beats whole-image majority-by-area),
so there was no reason to re-derive it here.
"""
import numpy as np
from PIL import Image

from peachos_icon_dark import _card_type, _classify, _edge_band_mask

LUMA_WEIGHTS = (0.299, 0.587, 0.114)  # ITU-R BT.601, same as PIL's own Image.convert('L')

# Target gray bands the real reference art's card/glyph regions land in
# (measured: card region output mean ~0.60-0.63 across all 3 icons despite
# very different source hues; glyph/foreground region output mean ~0.78-0.86).
# Each region's own luma is percentile-stretched into its band below, not
# just averaged to a flat fill, so internal shading survives.
CARD_GRAY_LOW = 0.52
CARD_GRAY_HIGH = 0.72
GLYPH_GRAY_LOW = 0.76
GLYPH_GRAY_HIGH = 0.88

# Percentile (not literal min/max) for the per-region stretch -- a handful of
# antialiased edge pixels or a single near-black shadow pixel sitting at the
# extreme tail would otherwise anchor the whole stretch and wash out everything
# else in the region.
STRETCH_PERCENTILE_LOW = 2
STRETCH_PERCENTILE_HIGH = 98

SOFTEN_SIZE = 224  # final low-pass pass: downscale to this then back up to CANVAS with LANCZOS
                    # both ways -- real icon display size is a fraction of the 1024 source, so
                    # any fine per-pixel noise the stretch above leaves behind is well above what
                    # a ~45-64px dock icon can even show; capping the output's own max spatial
                    # frequency here means there's nothing left for a mediocre runtime scaler to
                    # alias into visible grain/blockiness (same idea the old version used).


def _luma(rgb):
    return LUMA_WEIGHTS[0] * rgb[..., 0] + LUMA_WEIGHTS[1] * rgb[..., 1] + LUMA_WEIGHTS[2] * rgb[..., 2]


def _stretch_into(values, mask, lo, hi):
    """Percentile-stretches values[mask] to fill [lo, hi], and returns that
    stretched result broadcast back over the full array shape (callers pick
    out only the masked pixels they need -- this doesn't touch what's
    outside `mask` itself)."""
    selected = values[mask]
    if selected.size == 0:
        return values
    vmin = np.percentile(selected, STRETCH_PERCENTILE_LOW)
    vmax = np.percentile(selected, STRETCH_PERCENTILE_HIGH)
    if vmax - vmin < 1e-6:
        return np.full_like(values, (lo + hi) / 2)
    norm = np.clip((values - vmin) / (vmax - vmin), 0, 1)
    return lo + norm * (hi - lo)


def apply_clear_mode(source_path_or_image, out_path=None):
    """Apply the clear-mode transform. Accepts a path or an already-open PIL
    Image; returns the resulting Image (and also saves it if out_path is
    given)."""
    img = source_path_or_image if isinstance(source_path_or_image, Image.Image) else Image.open(source_path_or_image)
    arr, opaque, white_mask, black_mask, chromatic_mask = _classify(img)
    rgb = arr[..., :3]
    alpha = arr[..., 3]  # untouched -- see module docstring: Clear mode is fully opaque
    edge_mask = _edge_band_mask(opaque)
    card = _card_type(rgb, white_mask, black_mask, chromatic_mask, edge_mask)
    bucket_mask = {'white': white_mask, 'black': black_mask, 'chromatic': chromatic_mask}.get(card)

    luma = _luma(rgb)

    if bucket_mask is not None and bucket_mask.any():
        card_mask = bucket_mask & opaque
        glyph_mask = opaque & ~bucket_mask
        gray = np.where(
            card_mask, _stretch_into(luma, card_mask, CARD_GRAY_LOW, CARD_GRAY_HIGH),
            np.where(glyph_mask, _stretch_into(luma, glyph_mask, GLYPH_GRAY_LOW, GLYPH_GRAY_HIGH), luma),
        )
    else:
        # 'busy' -- no single clean edge color to call "the card" (e.g. Maps'
        # multi-hued tile mosaic at its own edge). No glyph to split out
        # either, so the whole opaque region gets one stretch into the card
        # band -- still lands in the same family of gray as everything else.
        gray = _stretch_into(luma, opaque, CARD_GRAY_LOW, CARD_GRAY_HIGH)

    out_rgb = np.stack([gray, gray, gray], axis=-1)
    out = np.concatenate([np.clip(out_rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=-1)
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    result = Image.fromarray(out, 'RGBA')

    canvas = result.size[0]
    result = result.resize((SOFTEN_SIZE, SOFTEN_SIZE), Image.LANCZOS).resize((canvas, canvas), Image.LANCZOS)

    if out_path:
        result.save(out_path, 'PNG')
    return result
