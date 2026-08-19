#!/usr/bin/env python3
"""Mask arbitrary app icons into peachOS's macOS-style squircle format.

Geometry is measured directly off a real Apple icon (iCloud Mail, shipped
system-wide at /usr/share/icons/icloud-for-linux/mail.svg): content fills
~81% of the canvas, corner radius is ~18% of canvas width -- matches
Apple's own documented Big Sur icon-masking spec almost exactly.
"""
import colorsys
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 1024
CONTENT_FILL = 0.81
CORNER_RADIUS_RATIO = 0.18
GLYPH_FILL = 0.80  # icon scale when placed on a generated backdrop -- real Apple glyphs
                    # (Pages' pencil, Mail's envelope) read big and bold, not a tiny stamp
BACKDROP_COLOR = (255, 255, 255, 255)
OPAQUE_ALPHA_THRESHOLD = 240
CORNER_INSET_RATIO = 0.04
DOMINANT_MIN_SATURATION = 0.25
DOMINANT_MIN_VALUE = 0.55
DOMINANT_MAX_VALUE = 0.92


RSVG_TIMEOUT_SECONDS = 10


def _load_svg(path, size):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ['rsvg-convert', '-w', str(size), '-h', str(size), '--keep-aspect-ratio', '-o', tmp_path, str(path)],
            check=True, timeout=RSVG_TIMEOUT_SECONDS, capture_output=True,
        )
        return Image.open(tmp_path).convert('RGBA').copy()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def load_pixbuf_as_pil(path, size=CANVAS):
    """Load any icon (SVG/PNG/etc) as a square RGBA canvas of `size`x`size`,
    centered with transparent padding if its own aspect ratio isn't square.

    Deliberately avoids GdkPixbuf/glycin: glycin's sandboxed loader shells
    out through bubblewrap + D-Bus per image, which reliably hangs when run
    from a systemd-hardened service (ProtectSystem/mount-namespace vs.
    bwrap's own sandboxing don't mix) and stalls on icons living under
    /snap. Plain Pillow file I/O plus rsvg-convert for SVG has none of that
    -- both are direct, synchronous, and have no D-Bus/sandbox dependency.
    """
    path = str(path)
    if path.lower().endswith('.svg'):
        img = _load_svg(path, size)
    else:
        img = Image.open(path).convert('RGBA')
        if img.size != (size, size):
            img.thumbnail((size, size), Image.LANCZOS)

    if img.size != (size, size):
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
        img = canvas
    return img


ALREADY_CONFORMING_FILL_RANGE = (0.70, 0.95)


def needs_masking(img):
    """Decide whether this icon needs squircle treatment.

    Two cases genuinely need it:
      - a plain flush square (opaque corners, ~full-bleed content) -- the
        classic "raw app icon with hard corners" case.
      - a small glyph centered on a mostly-transparent canvas -- looks like
        a stray blob next to real icon cards, needs a backdrop.

    Anything already filling ~70-95% of its canvas with transparent corners
    (an organic/circular/already-squircle silhouette, like a real Apple
    icon or a big circular logo) is left alone -- that's what "already
    conforming" looks like in practice.
    """
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return False

    fill_w = (bbox[2] - bbox[0]) / CANVAS
    fill_h = (bbox[3] - bbox[1]) / CANVAS
    lo, hi = ALREADY_CONFORMING_FILL_RANGE
    if lo <= fill_w <= hi and lo <= fill_h <= hi:
        return False

    return True


THEME_OVERSIZED_THRESHOLD = 0.85  # real MacTahoe app icons commonly run ~89-95% fill vs our
                                   # 81% Apple-matched target -- catch that gap, not just flush squares


def needs_padding_only(img):
    """For already-curated theme icons (MacTahoe): true if the icon runs
    close to full-bleed (no margin) rather than our ~81%-fill convention --
    needs shrinking to match everything else's size, but not re-masking."""
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return False
    fill_w = (bbox[2] - bbox[0]) / CANVAS
    fill_h = (bbox[3] - bbox[1]) / CANVAS
    return fill_w > THEME_OVERSIZED_THRESHOLD or fill_h > THEME_OVERSIZED_THRESHOLD


def pad_icon_to_target(source_path, out_path, canvas=CANVAS):
    """Shrink + center an already-good (curated) icon to match peachOS's
    fill convention. No masking, no recoloring, no backdrop -- the icon is
    already the right shape and color, it's just drawn too close to its own
    edges compared to everything else."""
    src = load_pixbuf_as_pil(source_path, canvas)
    bbox = src.split()[3].getbbox() or (0, 0, canvas, canvas)
    content = src.crop(bbox)

    target_size = int(canvas * CONTENT_FILL)
    scale = min(target_size / content.width, target_size / content.height)
    content = content.resize(
        (max(1, round(content.width * scale)), max(1, round(content.height * scale))), Image.LANCZOS,
    )

    out = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    out.paste(content, ((canvas - content.width) // 2, (canvas - content.height) // 2), content)
    out.save(out_path, 'PNG')


def _squircle_mask(size, radius):
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _dominant_backdrop_color(glyph_rgba):
    """Read the glyph's own dominant opaque color and turn it into a flat
    backdrop swatch -- App Center's orange bag should sit on an orange
    squircle, not get buried under an unrelated white square, the same way
    real Apple glyphs (Pages' white pencil on orange, Mail's white envelope
    on blue) use their own brand color as the card background.

    Falls back to white when the glyph is basically monochrome (white/gray/
    black line art, or a many-hued photographic logo where "dominant color"
    isn't a meaningful single swatch) -- matches Notes/Calendar/Contacts/
    Photos, which really are white-backed in real macOS.
    """
    small = glyph_rgba.resize((48, 48), Image.LANCZOS)
    counts = {}
    for r, g, b, a in small.getdata():
        if a < 200:
            continue
        key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return BACKDROP_COLOR

    r, g, b = max(counts.items(), key=lambda kv: kv[1])[0]
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < DOMINANT_MIN_SATURATION:
        return BACKDROP_COLOR

    v = min(DOMINANT_MAX_VALUE, max(DOMINANT_MIN_VALUE, v))
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255), 255)


def _is_full_bleed(img):
    """True if the source already fills most of its own canvas (a 'sticker'
    icon) rather than being a small centered glyph that needs a backdrop."""
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return False
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return (w / CANVAS) > 0.85 and (h / CANVAS) > 0.85


def generate_squircle_icon(source_path, out_path, canvas=CANVAS):
    src = load_pixbuf_as_pil(source_path, canvas)

    content_size = int(canvas * CONTENT_FILL)
    radius = int(content_size * CORNER_RADIUS_RATIO)

    if _is_full_bleed(src):
        content = src.resize((content_size, content_size), Image.LANCZOS)
    else:
        bbox = src.split()[3].getbbox() or (0, 0, canvas, canvas)
        glyph = src.crop(bbox)
        backdrop = Image.new('RGBA', (content_size, content_size), _dominant_backdrop_color(glyph))
        glyph_size = int(content_size * GLYPH_FILL)
        # scale-to-fit, not Image.thumbnail() -- thumbnail() only ever shrinks, so a small
        # source glyph (e.g. a logo drawn tiny within a large padded canvas) never actually
        # grew to fill the backdrop, leaving it a stamp-sized dot no matter how big GLYPH_FILL is
        scale = min(glyph_size / glyph.width, glyph_size / glyph.height)
        glyph = glyph.resize((max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))), Image.LANCZOS)
        gx = (content_size - glyph.width) // 2
        gy = (content_size - glyph.height) // 2
        backdrop.paste(glyph, (gx, gy), glyph)
        content = backdrop

    mask = _squircle_mask(content_size, radius)
    content.putalpha(Image.composite(content.split()[3], Image.new('L', content.size, 0), mask))

    out = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    offset = (canvas - content_size) // 2
    out.paste(content, (offset, offset), content)
    out.save(out_path, 'PNG')


if __name__ == '__main__':
    import sys

    if len(sys.argv) != 3:
        print(f'usage: {sys.argv[0]} <source-icon> <out.png>', file=sys.stderr)
        sys.exit(1)
    src_path, dst_path = sys.argv[1], sys.argv[2]
    img = load_pixbuf_as_pil(src_path)
    if needs_masking(img):
        generate_squircle_icon(src_path, dst_path)
        print(f'masked -> {dst_path}')
    else:
        print('already conforming, skipped')
