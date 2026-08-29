#!/usr/bin/env python3
"""Generates every preset PNG in peachos_icon_presets_registry.PRESETS that doesn't already
exist in PRESET_OUTPUT_DIR, via peachos_icon_preset.generate_preset(). Safe to re-run --
already-generated presets are left alone (delete one first if you want it redone, e.g. after
a brand refresh changes its Simple Icons artwork).
"""
import sys

from peachos_icon_preset import generate_preset
from peachos_icon_presets_registry import PRESETS, PRESET_OUTPUT_DIR


def main():
    PRESET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for slug, meta in PRESETS.items():
        out_path = PRESET_OUTPUT_DIR / f'{slug}.png'
        if out_path.exists() or (PRESET_OUTPUT_DIR / f'{slug}.svg').exists():
            continue  # already has hand-curated (.svg) or previously generated (.png) art
        if 'simple_icons_slug' not in meta:
            print(f'  ! {slug}: no art and no simple_icons_slug/hex to generate from -- skipping')
            failures.append(slug)
            continue
        try:
            generate_preset(meta['simple_icons_slug'], meta['hex'], out_path)
            print(f'  generated {slug} -> {out_path}')
        except Exception as e:
            print(f'  ! failed {slug}: {e}', file=sys.stderr)
            failures.append(slug)

    if failures:
        print(f'\n{len(failures)} failed: {", ".join(failures)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
