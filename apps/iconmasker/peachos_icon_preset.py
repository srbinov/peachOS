#!/usr/bin/env python3
"""Generates a curated peachOS app-icon preset from a Simple Icons brand mark.

Simple Icons (https://simpleicons.org, CC0) ships two useful variants of every mark via its
CDN: the brand-colored original (cdn.simpleicons.org/<slug>/<hex>) and a white recolor
(cdn.simpleicons.org/<slug>/ffffff). Which one peachos_icon_mask.py's squircle treatment
actually needs depends on the mark's own shape:

  - An already near-full-bleed mark (a solid colored circle/blob spanning most of its own
    canvas, e.g. Spotify's or Steam's own logo) is a "sticker" -- generate_squircle_icon()
    just resizes it as-is, no backdrop compositing happens at all. The brand-colored
    original is exactly right for this case.
  - A smaller centered glyph (most brand wordmarks/icons, e.g. Discord's) goes through the
    backdrop-compositing path instead. Feeding it the brand-colored original there is wrong
    -- _dominant_backdrop_color() would derive a backdrop hue from the SAME single color the
    glyph itself already is, so the glyph nearly disappears into its own backdrop (confirmed
    real: Discord's own mark rendered almost invisible, just a faint outline). This case
    needs the WHITE recolor as the glyph instead, paired with an explicit backdrop_color=
    (the brand's real published hex, not an auto-detected approximation of it).

This checks _is_full_bleed() against the brand-colored original first, then picks the right
variant/backdrop_color combination automatically -- see generate_preset().
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from peachos_icon_mask import CANVAS, load_pixbuf_as_pil, _is_full_bleed, generate_squircle_icon

SIMPLEICONS_CDN = 'https://cdn.simpleicons.org'
FETCH_TIMEOUT_SECONDS = 15


def _fetch_svg(slug, color, out_path, timeout=FETCH_TIMEOUT_SECONDS):
    url = f'{SIMPLEICONS_CDN}/{slug}/{color}'
    subprocess.run(
        ['curl', '-fsSL', '--max-time', str(timeout), url, '-o', str(out_path)],
        check=True, capture_output=True,
    )
    # A slug Simple Icons doesn't have returns a 404 body (HTML/plain text), not an SVG --
    # curl's exit code alone doesn't catch that since the HTTP transfer itself still
    # "succeeds". Fail loudly instead of silently writing garbage into the pipeline.
    head = out_path.read_text(encoding='utf-8', errors='replace')[:64].lstrip()
    if not head.startswith('<svg') and not head.startswith('<?xml'):
        raise ValueError(f'no such Simple Icons slug: {slug!r} (got: {head!r})')


def hex_to_rgba(hex_str):
    hex_str = hex_str.lstrip('#')
    r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
    return (r, g, b, 255)


def generate_preset(slug, hex_color, out_path, tmp_dir=None):
    """slug: Simple Icons slug (e.g. 'discord'). hex_color: brand hex, no leading '#'
    (e.g. '5865F2'). Writes the final squircle PNG to out_path."""
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp:
        tmp = Path(tmp)
        brand_svg = tmp / 'brand.svg'
        _fetch_svg(slug, hex_color, brand_svg)

        brand_img = load_pixbuf_as_pil(str(brand_svg), CANVAS)
        if _is_full_bleed(brand_img):
            generate_squircle_icon(str(brand_svg), str(out_path))
        else:
            white_svg = tmp / 'white.svg'
            _fetch_svg(slug, 'ffffff', white_svg)
            generate_squircle_icon(str(white_svg), str(out_path), backdrop_color=hex_to_rgba(hex_color))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f'usage: {sys.argv[0]} <simple-icons-slug> <hex-color> <out.png>', file=sys.stderr)
        sys.exit(1)
    generate_preset(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f'wrote {sys.argv[3]}')
