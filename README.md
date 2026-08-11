# peachOS

A macOS-styled Ubuntu/GNOME remix, built on Ubuntu 26.04 + GNOME Shell 50.

## How this repo works

Everything in here gets installed **system-wide** (`/usr/share`, `/etc/dconf`)
rather than into a single user's home directory. That's the difference
between "looks right while I'm logged in" and "looks right for anyone who
boots the ISO and creates an account" — GNOME settings are per-user by
default (stored in each user's own dconf database), so a fresh account
created by the installer only gets peachOS's look if the defaults are
written to `/etc/dconf/db/local.d/`, which applies to every account,
including ones that don't exist yet.

## Layout

- `assets/logos/` — peachOS branding (SVGs)
- `assets/wallpapers/` — default wallpaper
- `macOS-TopBar-Gnome/` — git submodule, the custom top-bar extension
  (`macos-top-panel@local.dev`); its own repo, edited independently
- `extensions/` — the other 6 GNOME Shell extensions peachOS ships with,
  vendored as-is from a working install (not fetched from
  extensions.gnome.org at provision time, so the exact working version is
  always what gets installed): `blur-my-shell`, `dash2dock-lite`,
  `compiz-alike-magic-lamp-effect`, `rounded-windows`, `CoverflowAltTab`,
  `user-theme`
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

## Workflow

1. Make a change live (theme tweak, extension setting, top-bar edit).
2. Once you like it, fold it into this repo:
   - Extension/theme code change → edit directly in
     `macOS-TopBar-Gnome/` or `extensions/<uuid>/`
   - A setting you changed via Settings/Tweaks/Extension prefs → re-run
     `dconf dump` on the relevant path and update
     `provision/dconf/01-peachos`
3. Re-run `sudo provision/provision.sh` on this VM (idempotent) and
   `provision/verify-fresh-user.sh` to confirm it's really system-wide.
4. Commit.

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
