#!/usr/bin/env python3
"""One-off: generate small real-JPEG tile previews for every preset and dynamic wallpaper,
matching the pattern LIVE_WALLPAPERS already uses correctly (a small pre-extracted JPEG,
14-43KB) instead of decoding the multi-megabyte full-res source -- or, for the dynamic
wallpapers, a full-5K-resolution SVG with an embedded raster image -- on every Settings app
wallpaper-page load.
"""
import os
from PIL import Image

WALLPAPER_DIR = '/usr/share/backgrounds/peachos'
PREVIEW_DIR = '/home/user/peachOS/apps/settings/data/wallpaper-previews'
TILE_W, TILE_H = 224, 126  # 2x the 112x63 on-screen tile size, for HiDPI sharpness

PRESET_FILES = [
    'nectar_island.jpg', 'tahoe_beach_dawn.jpg', 'tahoe_beach_day.jpg', 'tahoe_beach_dusk.jpg',
    'tahoe_beach_night.jpg', 'apple_event_2021.jpg', 'bigsur_coastline.jpg', 'bigsur_layers.jpg',
    'bigsur_sunrise.jpg', 'catalina_island.jpg', 'leopard.jpg', 'lion_andromeda.jpg',
    'lion_beach.jpg', 'lion_tranquil.jpg', 'lion_twilight.jpg', 'mavericks_tide.jpg',
    'mojave_fusion.png', 'mojave_desert.jpg', 'mojave_starry.jpg', 'mountain_lion_1.jpg',
    'mountain_lion_2.jpg', 'mountain_lion_3.jpg', 'mountain_lion_4.jpg', 'mountain_lion_5.jpg',
    'monterey_black.jpg', 'monterey_blue.jpg', 'monterey_green.jpg', 'monterey_orange.jpg',
    'monterey_wwdc.jpg', 'sequoia_forest.jpg', 'sierra_peak.jpg', 'sonoma.jpg',
]

DYNAMIC_SOURCES = {
    'peachOS_Nectar.jpg': 'peachOS_Nectar_Light.jpg',
    'macOS_Tahoe.jpg': 'macOS_Tahoe_Light.jpg',
    'macOS_Sonoma.jpg': 'macOS_Sonoma_Light.jpg',
    'macOS_Sequoia.jpg': 'macOS_Sequoia_Light.jpg',
    'macOS_GoldenGate.jpg': 'macOS_GoldenGate_Light.png',
}


def make_preview(src_path, dest_path):
    with Image.open(src_path) as im:
        im = im.convert('RGB')
        # Cover-fit crop to the tile's aspect ratio before downscaling, so the preview
        # matches what Gtk.ContentFit.COVER actually shows on the tile (not a squashed
        # full-frame thumbnail).
        src_ratio = im.width / im.height
        tile_ratio = TILE_W / TILE_H
        if src_ratio > tile_ratio:
            new_w = int(im.height * tile_ratio)
            x0 = (im.width - new_w) // 2
            im = im.crop((x0, 0, x0 + new_w, im.height))
        else:
            new_h = int(im.width / tile_ratio)
            y0 = (im.height - new_h) // 2
            im = im.crop((0, y0, im.width, y0 + new_h))
        im = im.resize((TILE_W, TILE_H), Image.LANCZOS)
        im.save(dest_path, 'JPEG', quality=82)


count = 0
for filename in PRESET_FILES:
    src = os.path.join(WALLPAPER_DIR, 'presets', filename)
    if not os.path.isfile(src):
        print(f'MISSING SOURCE: {src}')
        continue
    dest = os.path.join(PREVIEW_DIR, 'preset_' + os.path.splitext(filename)[0] + '.jpg')
    make_preview(src, dest)
    count += 1

for dest_name, src_name in DYNAMIC_SOURCES.items():
    src = os.path.join(WALLPAPER_DIR, src_name)
    if not os.path.isfile(src):
        print(f'MISSING SOURCE: {src}')
        continue
    dest = os.path.join(PREVIEW_DIR, dest_name)
    make_preview(src, dest)
    count += 1

print(f'Generated {count} previews')
