# peachOS

A macOS-styled Ubuntu/GNOME remix, built on Ubuntu 26.04 + GNOME Shell 50.
The goal is a distro that looks and behaves like macOS out of the box —
traffic-light window controls, a Mac-style top menu bar with a real Apple-menu
equivalent, a dock, and a native Settings app that replaces GNOME's Settings /
Tweaks / Extensions apps with one macOS System Settings–style app — while
still being a normal Ubuntu underneath (real `apt`, real GNOME Shell, real
NetworkManager/BlueZ/UPower, nothing faked).

The whole project runs out of a single dev VM. Everything gets themed/built
live in that VM, then folded into these repos so it's reproducible from a
clean install rather than living only in one hand-configured machine.

## The pieces

- **This repo (`peachOS`)** — branding assets, the provisioning script that
  turns a stock Ubuntu box into peachOS, and (as of the `apps/` folder) the
  Settings app.
- **[`macOS-TopBar-Gnome`](https://github.com/srbinov/macOS-TopBar-Gnome)**
  (submodule) — the custom GNOME Shell extension that replaces the stock top
  bar with a macOS-style menu bar: Apple-style system menu, live per-app
  File/Edit/View/Go/Window/Help bar, custom clock, battery/Wi-Fi/sound
  indicators. Its own repo since it's a standalone, reusable GNOME extension
  independent of peachOS.
- **[`macOS_Tahoe_SYSICONS`](https://github.com/srbinov/macOS_Tahoe_SYSICONS)**
  — source-of-truth repo for the real (non-placeholder) icon assets used
  around peachOS, pulled in as needed.
- **`apps/settings/`** (this repo) — the native Settings app. Unlike the
  extension, this has no identity outside peachOS (it's branded peachOS, not
  reusable), so it lives directly in this repo rather than as a submodule.

## Why "system-wide," not "however my session looks"

Everything provisioned by this repo gets installed **system-wide**
(`/usr/share`, `/etc/dconf`) rather than into one user's home directory.
That's the difference between "looks right while I'm logged in" and "looks
right for anyone who boots the ISO and creates an account" — GNOME settings
are per-user by default (stored in each user's own dconf database), so a
fresh account created by the installer only gets peachOS's look if the
defaults are written to `/etc/dconf/db/local.d/`, which applies to every
account, including ones that don't exist yet. This one principle drives most
of the structure below.

## Layout

- `assets/logos/` — peachOS branding (SVGs)
- `assets/wallpapers/` — default wallpaper
- `assets/lockscreen/live-lockscreen.mp4` — the live video background for
  the lock screen (`extensions/perfect-lockscreen@chris`, below);
  provisioned to `/usr/share/peachos/lockscreen/`
- `macOS-TopBar-Gnome/` — git submodule, the custom top-bar extension
  (`macos-top-panel@local.dev`); its own repo, edited independently
- `extensions/` — the other 6 GNOME Shell extensions peachOS ships with,
  vendored as-is from a working install (not fetched from
  extensions.gnome.org at provision time, so the exact working version is
  always what gets installed): `blur-my-shell`, `macos-dock-2026-peachos`
  (our own fork of `dash2dock-lite`, with an added Liquid Glass mode --
  see `~/macOS-Dock-2026-peachOS`, its own repo, edited independently),
  `perfect-lockscreen@chris` (macOS Sonoma/Cupertino lock + login screen
  with a live video background -- its own repo,
  `github.com/srbinov/perfect-lockscreen`, edited independently; unlike
  every other extension here it also needs GDM-side wiring beyond a plain
  file copy, so `provision.sh` runs its vendored
  `scripts/install-gdm-dlc.sh` right after the generic install loop --
  see that script/its own README for what it does and why),
  `compiz-alike-magic-lamp-effect`, `rounded-windows`, `CoverflowAltTab`,
  `user-theme`
- `apps/settings/` — the native Settings app (see below)
- `provision/provision.sh` — installs everything above system-wide on a
  clean Ubuntu 26.04 + GNOME box: theme + icons (cloned from vinceliuice's
  MacTahoe repos, pinned to a fixed commit), extensions, wallpaper, and
  the dconf system defaults
- `provision/dconf/01-peachos` — captured dconf defaults (theme, icon
  theme, wallpaper, enabled extensions, per-extension settings, window
  button layout, etc.), installed to `/etc/dconf/db/local.d/`
- `provision/verify-fresh-user.sh` — creates a throwaway user account and
  confirms it gets the peachOS look with zero personal config, then
  deletes the account. Run this after any provisioning change to make
  sure it actually applies system-wide and not just to your own session.

GTK/icon themes aren't vendored directly (upstream is ~140MB); `provision.sh`
clones them fresh and pins to a specific commit for reproducibility.

**Not wired into `provision.sh` yet:** `apps/settings` isn't part of the
system-wide install yet — right now it's still run manually
(`python3 apps/settings/src/main.py`), not installed as a real app with a
`.desktop` file and an app-grid entry. That's a known next step.

## The Settings app (`apps/settings/`)

A native GTK4 + libadwaita app (Python/PyGObject), styled to match macOS
System Settings: a sidebar of categories on the left (with real window
traffic-light controls, since those come free from the active GTK theme —
no custom drawing needed), a content pane on the right with back/forward
navigation.

Every tab wired up so far is a **real backend, not a mock** — same
philosophy as the rest of peachOS. Where a tab depends on hardware this dev
VM doesn't have (Wi-Fi, Bluetooth radios), it honestly shows "no hardware
detected" rather than faking data, and the code is written to work correctly
the moment it runs somewhere with real hardware.

**Done, fully wired:**
- **Wi-Fi** — `libnm` (`NM.Client`): radio toggle, live scan-driven known/
  other-network lists, click to connect (password prompt for unknown secured
  networks), Details dialog.
- **Bluetooth** — raw BlueZ D-Bus (`org.bluez`; no high-level GI binding
  exists for it like libnm does for network): adapter power toggle, paired
  "My Devices" (with battery % where available), discovered "Nearby
  Devices," live-updated via D-Bus signals.
- **Network** — real NetworkManager device list (icon/name/connected state)
  plus a Firewall status row read from `ufw`'s config (real status,
  read-only for now — toggling needs root).
- **Battery** (sidebar label; internal id stays `energy`) — real charge %/
  state and a computed Battery Health from UPower (this VM happens to expose
  a genuine emulated battery), a real Low Power Mode toggle backed by
  `power-profiles-daemon`. The history graphs are structurally present
  (headers, the 24-Hours/10-Days toggle) but show "not enough history yet"
  instead of fabricated chart data — no real history-logging daemon exists
  yet to back that with real numbers.
- **Appearance** — Light/Dark and accent-color selection wired to the exact
  real GNOME schema (`org.gnome.desktop.interface` `color-scheme` and
  `accent-color`), two-way synced with the actual system setting. All 10
  real GNOME accent colors (not macOS's palette), pulled from
  `Adw.AccentColor.to_standalone_rgba()` rather than guessed hex values.

**Still generic placeholders** (icon + title + "coming soon," no real
content): General, Accessibility, Menu Bar, Desktop & Dock, Displays,
Spotlight, Wallpaper, Notifications.

**Icons:** most tabs now have real icons pulled from `macOS_Tahoe_SYSICONS`;
Menu Bar, Spotlight, Wallpaper, and Notifications are still on placeholder
symbolic icons pending real assets.

**Sidebar list is incomplete:** only captured through "Notifications" from
the first reference screenshot. At least "Apple Intelligence & Siri" is
known to exist further down in the real macOS list and hasn't been added.

### A few real GTK/CSS lessons learned building this (worth knowing before touching it)

- **Margins on a card widget itself ≠ padding for its content.** Margin
  pushes a widget away from its *siblings* (external spacing); it does
  nothing for the widget's own children. Padding-intended spacing has to go
  on the children, not the card. Got this wrong three separate times before
  it stuck.
- **`Gtk.Box` has no `set_child()`** — that's only for single-child
  containers like `Gtk.Frame`/`Gtk.Button`. Swapping a `Frame` for a `Box`
  (e.g. to drop an unwanted border) means switching `set_child()` calls to
  `append()`, or the rest of that method silently no-ops (PyGObject logs
  GObject callback exceptions but doesn't crash the process, so this fails
  quietly).
- **`Gtk.Picture.set_size_request()` only sets a minimum, not a cap.**
  Picture's *natural* size comes from the source image's own resolution; if
  the source is huge, the widget stays huge regardless of the requested
  display size. Fix: pre-rasterize to the exact target pixel size with
  `GdkPixbuf.Pixbuf.new_from_file_at_scale()` up front so the resulting
  texture's natural size *is* the target size — no negotiation needed.
- **Explicit `hexpand`/`vexpand = True` propagates upward** through every
  ancestor that hasn't explicitly opted out, not just the widget it's set
  on. Setting it to fill one small box can silently inflate the whole
  container chain above it.
- **Don't fight `Gtk.ToggleButton`'s baked-in theme states.** Overriding
  `:checked`/`:hover`/`:active`/`:focus` reliably across arbitrary GTK
  themes turned out to be a losing battle (repeated attempts still showed a
  theme-drawn "container" look through the overrides). For custom-styled
  selectable tiles/swatches, a plain `Gtk.Box` + `Gtk.GestureClick` with a
  manually-toggled CSS class the theme has zero opinions about is far more
  reliable than trying to reskin a real button.
- **A `Gtk.ScrolledWindow` set to `vexpand=True` still competes for space
  even when its content is hidden**, if the ScrolledWindow itself isn't also
  hidden. Two `vexpand=True` siblings (an empty scroller + a status message)
  split the leftover space unpredictably, which showed up as inconsistently
  clipped empty-state text.

## Known issues

- **Top bar background bug (parked).** The macOS-style top panel
  (`macos-top-panel@local.dev`) sometimes renders a solid black/opaque
  background instead of the intended transparency, with no reliable repro
  found yet. Ruled out so far: the active theme's own CSS (confirmed
  `background-color: transparent` in every checked variant), `blur-my-shell`
  (its panel-blur component never even initializes when its `blur` setting
  is off), and `dash2dock-lite` (disabled live via the Extensions app GUI,
  no change). Also discovered along the way: `gnome-extensions enable/
  disable` in this VM talks to a D-Bus-activated helper process rather than
  the running compositor directly, so code changes to the extension only
  reliably take effect after a full logout/login, not a CLI toggle.

## Workflow

1. Make a change live (theme tweak, extension setting, top-bar edit, a
   Settings-app tab).
2. Once you like it, fold it into the relevant repo:
   - Top-bar extension code → edit directly in `macOS-TopBar-Gnome/`
   - Other extension/theme code → edit in `extensions/<uuid>/`
   - Settings app code → edit in `apps/settings/src/`
   - A setting you changed via Settings/Tweaks/Extension prefs → re-run
     `dconf dump` on the relevant path and update
     `provision/dconf/01-peachos`
3. Re-run `sudo provision/provision.sh` on this VM (idempotent) and
   `provision/verify-fresh-user.sh` to confirm it's really system-wide.
4. Commit (and push — auth in this dev VM is via `gh auth login`, not a
   token pasted into a terminal).

## Building the ISO

Once a clean VM has been provisioned with `provision.sh`, snapshot it into
a bootable ISO with [Penguin's Eggs](https://penguins-eggs.net/):

```
sudo eggs config   # one-time setup
sudo eggs produce  # builds the ISO from current system state
```

Because `eggs` snapshots the live filesystem, whatever is installed
system-wide (not just in your own home directory) is what ships in the
ISO — which is the whole reason this repo installs everything to
`/usr/share` and `/etc/dconf` instead of `~/.local/share` and `~/.config`.

**Before building a real, distributable ISO:** do it from a clean VM that
has never had personal credentials on it, not this dev VM. This dev VM has
had real GitHub auth, git identity (real name/email), and other personal
config on it at various points — none of that should ship in an ISO handed
to anyone else. `provision.sh` is the reproducible recipe precisely so the
actual build can happen on a throwaway clean box instead.
