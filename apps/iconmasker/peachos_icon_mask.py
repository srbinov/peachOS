#!/usr/bin/env python3
"""Mask arbitrary app icons into peachOS's macOS-style squircle format.

Geometry is measured directly off a real Apple icon (iCloud Mail, shipped
system-wide at /usr/share/icons/icloud-for-linux/mail.svg): content fills
~81% of the canvas, corner radius is ~18% of canvas width -- matches
Apple's own documented Big Sur icon-masking spec almost exactly.
"""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 1024
CONTENT_FILL = 0.81
CORNER_RADIUS_RATIO = 0.18
GLYPH_FILL = 0.62  # icon scale when placed on a generated backdrop
BACKDROP_COLOR = (255, 255, 255, 255)
OPAQUE_ALPHA_THRESHOLD = 240
CORNER_INSET_RATIO = 0.04


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


def _squircle_mask(size, radius):
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


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
        backdrop = Image.new('RGBA', (content_size, content_size), BACKDROP_COLOR)
        glyph_size = int(content_size * GLYPH_FILL)
        bbox = src.split()[3].getbbox() or (0, 0, canvas, canvas)
        glyph = src.crop(bbox)
        glyph.thumbnail((glyph_size, glyph_size), Image.LANCZOS)
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
