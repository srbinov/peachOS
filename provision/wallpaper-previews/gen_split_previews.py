#!/usr/bin/env python3
"""Regenerates dynamic-wallpaper preview thumbnails as a light/dark split composite,
matching the convention peachOS_Nectar_DynamicPreview.svg established (left half = light
variant, right half = dark variant, same crop region so the artwork lines up continuously
across the seam) -- the old giant per-wallpaper SVGs (deleted for being 9-11MB each, see
gen_wallpaper_previews.py) turned out to have had this same split treatment; replacing them
with a plain single-mode crop silently lost it. This restores it without needing a hand-made
SVG per wallpaper -- built straight from the light/dark source files already on disk.
"""
import os
from PIL import Image

WALLPAPER_DIR = '/usr/share/backgrounds/peachos'
PREVIEW_DIR = '/home/user/peachOS/apps/settings/data/wallpaper-previews'
TILE_W, TILE_H = 224, 126

SPLITS = {
    'macOS_Tahoe.jpg': ('macOS_Tahoe_Light.jpg', 'macOS_Tahoe_Dark.jpg'),
    'macOS_Sonoma.jpg': ('macOS_Sonoma_Light.jpg', 'macOS_Sonoma_Dark.jpg'),
    'macOS_Sequoia.jpg': ('macOS_Sequoia_Light.jpg', 'macOS_Sequoia_Dark.jpg'),
    'macOS_GoldenGate.jpg': ('macOS_GoldenGate_Light.png', 'macOS_GoldenGate_Dark.png'),
}


def cover_crop_scale(path, w, h):
    im = Image.open(path).convert('RGB')
    src_ratio = im.width / im.height
    tile_ratio = w / h
    if src_ratio > tile_ratio:
        new_w = int(im.height * tile_ratio)
        x0 = (im.width - new_w) // 2
        im = im.crop((x0, 0, x0 + new_w, im.height))
    else:
        new_h = int(im.width / tile_ratio)
        y0 = (im.height - new_h) // 2
        im = im.crop((0, y0, im.width, y0 + new_h))
    return im.resize((w, h), Image.LANCZOS)


for dest_name, (light_name, dark_name) in SPLITS.items():
    light = cover_crop_scale(os.path.join(WALLPAPER_DIR, light_name), TILE_W, TILE_H)
    dark = cover_crop_scale(os.path.join(WALLPAPER_DIR, dark_name), TILE_W, TILE_H)
    half = TILE_W // 2
    out = Image.new('RGB', (TILE_W, TILE_H))
    out.paste(light.crop((0, 0, half, TILE_H)), (0, 0))
    out.paste(dark.crop((half, 0, TILE_W, TILE_H)), (half, 0))
    out.save(os.path.join(PREVIEW_DIR, dest_name), 'JPEG', quality=88)
    print('wrote', dest_name)
