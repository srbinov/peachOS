# macOS Dock 2026 peachOS

A macOS-style dock for GNOME Shell: liquid glass plate, hover magnification, autohide, trash/downloads, and a single **Size** slider that scales icons and the dock together.

This is a fork of [Dash2Dock Animated](https://github.com/icedman/dash2dock-lite) by icedman, rebranded and tuned for peachOS.

| | |
| --- | --- |
| **Extension name** | macOS Dock 2026 peachOS |
| **UUID** | `macos-dock-2026-peachos@peachos` |
| **GNOME** | 46, 47, 48, 49, 50 |
| **Install path** | `~/.local/share/gnome-shell/extensions/macos-dock-2026-peachos@peachos/` |

Do **not** run this at the same time as Dash2Dock Lite, Dash to Dock, Ubuntu Dock, or an older `macos-dock-2.00@local` copy. Disable those first.

## Install

### 1. Requirements

- GNOME Shell 46 or newer
- `glib-compile-schemas` (`libglib2.0-bin` on Debian/Ubuntu, `glib2` on Fedora)
- `make`, `git`

Optional:

- [Compiz-alike Magic Lamp](https://extensions.gnome.org/extension/3740/compiz-alike-magic-lamp-effect/) if you want the genie minimize animation
- ImageMagick if you turn on top-bar wallpaper blur

### 2. Clone and install

```bash
git clone <REPO_URL>
cd macos-dock-2026-peachos
make install
```

`make install` compiles the settings schema and copies the extension into:

```text
~/.local/share/gnome-shell/extensions/macos-dock-2026-peachos@peachos/
```

### 3. Enable it

**X11:** press `Alt+F2`, type `r`, press Enter, then:

```bash
gnome-extensions enable macos-dock-2026-peachos@peachos
```

**Wayland:** log out and log back in (or reboot), then run the same `gnome-extensions enable` command if it is not already on.

Open settings with:

```bash
gnome-extensions prefs macos-dock-2026-peachos@peachos
```

Or use **GNOME Extensions** / **Extension Manager** → macOS Dock 2026 peachOS → Settings.

### 4. Reload after updates

```bash
cd macos-dock-2026-peachos
git pull
make install
```

Then disable and re-enable the extension, or log out on Wayland.

### Uninstall

```bash
gnome-extensions disable macos-dock-2026-peachos@peachos
rm -rf ~/.local/share/gnome-shell/extensions/macos-dock-2026-peachos@peachos
```

Log out on Wayland (or `Alt+F2` → `r` on X11) so GNOME drops it.

---

## Settings

Preferences are four pages: **General**, **Style**, **Icons**, and **Tweak**.

### General

**Dock**

| Setting | What it does |
| --- | --- |
| Preferred Monitor | Which display gets the dock. |
| Preferred Dock Location | Bottom, top, left, or right. |
| Multi-Monitor Strategy | How extra monitors are handled when more than one display is connected. |

**Animation**

| Setting | What it does |
| --- | --- |
| Animate Icons | Hover magnification / macOS-style icon animation. Turn this off for a static dock. |
| Opening Animation | Bounce an icon when you launch an app. |
| Lamp Animation | Aim Compiz Magic Lamp at the app’s dock icon on minimize. Needs the Magic Lamp extension. Can be unstable; toggle may need an extension restart. |

**Autohide**

| Setting | What it does |
| --- | --- |
| Autohide Icons | Hide the dock when it would cover windows or in fullscreen. |
| Dodge Only | Only hide when overlapping a window / fullscreen — not a full always-hide. |
| Pressure Sense | Push the pointer into the screen edge to reveal a hidden dock. |
| Peek Icons | Show a sliver of the icons while the dock is hidden. |

**Debug**

| Setting | What it does |
| --- | --- |
| Visual Indicators | Overlay debug marks while animations run. Leave off unless you are debugging. |
| Test | Runs a long self-test; output goes to `journalctl`. |
| Reset Settings | Restore every preference to defaults. |

### Style

**Icons**

| Setting | What it does |
| --- | --- |
| **Size** | One slider for icon size **and** dock size (they stay linked). Left is 8px, about 0.2 is 32px, right is 128px. |
| Icons Spacing | Gap between icons. Negative values pack them tighter. |
| Icon Effect | Color treatment (none / tint / monochrome). |
| Icon Effect Color | Tint color when an effect is on. |
| Icon Shadow | Drop shadow under icons. |
| Separator Thickness | Line between app icons and trash/downloads. `0` hides it. |
| Separator Color | Color of that separator. |

**Focused Icon Background**

| Setting | What it does |
| --- | --- |
| Background Color | Plate behind the focused app icon. |
| Border Radius / Thickness / Color | Outline around that plate. |

**Dash**

| Setting | What it does |
| --- | --- |
| Panel Mode | Stretch the dock into a full-width (or full-height) panel. |
| Edge Distance | Gap between the dock and the screen edge. |
| Dock padding | Extra padding inside the glass plate. Size already grows the plate with the icons; this is extra inset. |
| Border Radius / Thickness / Color | Dock plate outline. Ignored while Liquid Glass is on. |
| **Liquid Glass** | Frosted plate with a top highlight and glass rim (macOS-style). Does not use Shell blur effects. |
| Glass Mode | Dark charcoal or light white glass. Only used when Liquid Glass is on. |
| Background Color | Solid dock fill. Ignored while Liquid Glass is on. |
| Background Blur | Wallpaper blur via Blur My Shell. Unstable — prefer Liquid Glass. |
| Transparent Background on Overview | Hide the dock plate in Activities overview. |

**App Indicators**

| Setting | What it does |
| --- | --- |
| Running Indicator Style | Dots, dashes, squares, etc. under open apps. |
| Running Indicator Size | Size of that mark. |
| Indicator Color | Color of the running mark. |
| Notification Badge Style / Size / Color | Badge on apps with notifications. |

**Topbar**

Optional styling of GNOME’s top panel: enable **Customize**, then border, background, foreground, blur (needs ImageMagick), and transparent-in-overview.

**Label**

Tooltips / icon labels: enable **Customize**, then radius, border, colors. **Hide Labels** turns them off entirely.

**Themes**

Export the current style as JSON (`/tmp/theme.json`). Copy it to `~/.config/d2da/themes/` to reuse it from the Themes menu.

### Icons

**Visibility**

| Setting | What it does |
| --- | --- |
| Favorite Apps Only | Only pinned apps; hide other running apps. |
| Apps Icon | Show the app-grid / overview button. |
| Apps Icon at Front | Put that button on the left (or top) instead of the end. |

**Dynamic icons**

| Setting | What it does |
| --- | --- |
| Trash | Trash can with Empty Trash. On by default. |
| Mounted Devices | Icons for mounted volumes. |
| Downloads | Downloads folder, with recent files. On by default. |
| Rotate labels | Spin labels on the downloads fan-out. |
| Downloads folder | Optional folder to watch instead of the default Downloads. |
| Maximum Recent Items | How many recent download items to show. |

**Custom drawn icons**

| Setting | What it does |
| --- | --- |
| Clock | Analog clock. Pin GNOME Clocks to the dock. |
| Clock Style | Clock face variant. |
| Calendar | Calendar widget. Pin GNOME Calendar to the dock. |
| Calendar Style | Calendar face variant. |

### Tweak

**Animation**

| Setting | What it does |
| --- | --- |
| Magnification | How large icons grow on hover. |
| Spread | How far neighbors move out of the way. |
| Rise | How far icons lift off the dock. |
| Rise Curve | Easing for that lift. |
| Bounce Height / Frequency | Click bounce. |
| Items Angle | Angle of the downloads/folder fan-out. |

**Autohide**

| Setting | What it does |
| --- | --- |
| Autohide Speed | How fast the dock slides away. |
| Pressure Sensitivity | How hard you have to push the edge to reveal it. |

**Blur background**

| Setting | What it does |
| --- | --- |
| Blur Quality | Resolution of wallpaper blur (higher = slower startup). |
| Disable at Overview | Skip blur in Activities overview. |

**Performance**

| Setting | What it does |
| --- | --- |
| Icon Quality | Icon texture resolution. Higher looks sharper and uses more GPU/CPU. |
| Framerate | Animation FPS. High is smoother and heavier. |

**Behavior** (these are mostly shortcuts, not toggles)

- Scroll over an icon to cycle its windows. Hold `Ctrl` to stay on the current workspace.
- Click a running icon to minimize. `Shift`+click to maximize.
- `Ctrl`+click to launch a new window.
- **Monitor Filter** limits those actions to the current display.

---

## Custom icons and config

Optional overrides live under `~/.config/d2da/`.

**Icons** — `~/.config/d2da/icons.json`:

```json
{
  "icons": {
    "view-app-grid-symbolic": "icons/show-apps-icon.svg",
    "user-trash": "icons/my-own-trash.svg",
    "user-trash-full": "icons/my-own-trash-full.svg"
  }
}
```

Put SVG files in `~/.config/d2da/icons/`, or use icon-theme names instead of paths. You can also map by app id:

```json
{
  "apps": {
    "spotify_spotify": "icons/spotify.svg"
  }
}
```

**Config** — `~/.config/d2da/config.json`:

```json
{
  "file-explorer": "nemo",
  "icon-size": "24"
}
```

`icon-size` here is a pixel override and wins over the Size slider. Disable and re-enable the extension after editing this file.

**CSS** — `~/.config/d2da/style.css` if you want extra styling.

## Troubleshooting

```bash
journalctl /usr/bin/gnome-shell -f -o cat
```

Look for `macos-dock-2026-peachos`. On Wayland, a settings change that seems stuck usually needs a log out, not just disable/enable.

If the dock never appears, confirm no other dock extension is enabled:

```bash
gnome-extensions list --enabled
```

## Credits and license

Based on **Dash2Dock Animated / Dash2Dock Lite** by icedman. Original project: https://github.com/icedman/dash2dock-lite

Distributed under the GNU GPL. See [LICENSE](LICENSE).
