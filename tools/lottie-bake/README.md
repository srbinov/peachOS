# lottie-bake

Bakes a Lottie JSON animation into a **sprite-sheet PNG** the GNOME Shell
extensions can play with a plain timer (`lib/spriteAnimation.js`).

GNOME Shell / GJS has no Lottie runtime — `lottie-web` needs a DOM and there's
no GIR typelib for `rlottie`. Rather than add a native dependency, we render the
loop offline here (headless `lottie-web` + `node-canvas`), auto-crop the shared
transparent margin, and tile the frames into one grid PNG. The extension slices
that PNG into `St.ImageContent` textures once and swaps them on a `GLib` timer.

## Use

```sh
cd tools/lottie-bake
npm install
node bake.mjs <input.json> <output.png> [frames] [cols] [cellW]
```

`bake.mjs` also writes `<output>.json` next to the PNG with the geometry the
extension reads: `{ frames, cols, rows, cellW, cellH, durationMs }`.

## Current bakes

| animation | source | output | params |
|---|---|---|---|
| Peach Intelligence voice waveform (Dynamic Island "listening") | `extensions/macos-top-panel@local.dev/assets/peach-intelligence-voice.lottie.json` | `…/peach-intelligence-voice.png` | `40 8 400` |

Regenerate: `npm run bake:pi-voice`.

`node_modules/` is **not** committed — the baked PNGs + `.json` are the shipped
artifacts, plus the pinned source `*.lottie.json`.
