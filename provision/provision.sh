#!/usr/bin/env bash
#
# peachOS provisioning script.
#
# Turns a stock Ubuntu 26.04 + GNOME Shell 50 install into peachOS by
# installing every theme/icon set/extension SYSTEM-WIDE (/usr/share, /etc)
# instead of per-user, so a brand-new user account (including the one
# Calamares creates during ISO install) gets the peachOS look with zero
# manual setup. Run this on a clean VM, then snapshot the result with
# `eggs produce`.
#
# Usage: sudo ./provision.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo: sudo $0" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# Pin to the exact upstream commits that produced the currently-installed
# peachOS look, so a re-run always reproduces the same result.
MACTAHOE_GTK_REPO="https://github.com/vinceliuice/MacTahoe-gtk-theme.git"
MACTAHOE_GTK_COMMIT="5df7f86eb787e1f7054f377e2c318b8af873d705"
MACTAHOE_ICON_REPO="https://github.com/vinceliuice/MacTahoe-icon-theme.git"
MACTAHOE_ICON_COMMIT="db9a4f8b236d3c559326f041d75d5173de118c45"

echo "==> Installing build dependencies"
apt-get update -qq
apt-get install -y --no-install-recommends git rsync dconf-cli libglib2.0-bin

# peachySearch (apps/ulauncher) runtime deps: python3-gi-cairo fixes a real "Couldn't find
# foreign struct converter for 'cairo.Context'" crash on every draw (PyGObject's cairo
# integration isn't in the base gi package), python3-xlib is a hard dependency of the app
# itself, and wl-clipboard backs Clipboard mode -- GTK3's own GDK Wayland clipboard backend
# doesn't round-trip data at all in this environment (reads AND writes silently fail), so
# Clipboard mode shells out to wl-copy/wl-paste instead of using Gtk.Clipboard directly.
echo "==> Installing peachySearch (ulauncher) runtime dependencies"
apt-get install -y --no-install-recommends python3-gi-cairo python3-xlib wl-clipboard

# Settings app (apps/settings) runtime dep: gir1.2-goa-1.0 gives the Internet Accounts tab
# real GNOME Online Accounts bindings -- gnome-online-accounts itself (the goa-daemon and
# its D-Bus service) ships by default, but its GObject-Introspection typelib is a separate
# package that doesn't get pulled in automatically.
echo "==> Installing Settings app (Internet Accounts) runtime dependencies"
apt-get install -y --no-install-recommends gir1.2-goa-1.0

# peachos-applauncher.desktop's Exec= just pokes macOS-TopBar-Gnome's own AppLauncherOverlay
# (lib/appLauncher.js) over D-Bus to toggle the Launchpad-style grid -- no separate binary,
# this is purely a Dock entry point for something the top-bar extension already implements.
echo "==> Installing peachOS App Launcher (Launchpad) desktop entry"
cp "$REPO_DIR/apps/applauncher/peachos-applauncher.desktop" /usr/share/applications/
update-desktop-database /usr/share/applications

echo "==> Installing MacTahoe GTK/Shell theme system-wide -> /usr/share/themes"
git clone --quiet "$MACTAHOE_GTK_REPO" "$WORK_DIR/gtk-theme"
git -C "$WORK_DIR/gtk-theme" checkout --quiet "$MACTAHOE_GTK_COMMIT"
"$WORK_DIR/gtk-theme/install.sh" -d /usr/share/themes

echo "==> Installing MacTahoe icon theme system-wide -> /usr/share/icons"
git clone --quiet "$MACTAHOE_ICON_REPO" "$WORK_DIR/icon-theme"
git -C "$WORK_DIR/icon-theme" checkout --quiet "$MACTAHOE_ICON_COMMIT"
"$WORK_DIR/icon-theme/install.sh" -d /usr/share/icons

echo "==> Installing GNOME Shell extensions system-wide -> /usr/share/gnome-shell/extensions"
mkdir -p /usr/share/gnome-shell/extensions
for ext_dir in "$REPO_DIR"/extensions/*/; do
    uuid="$(basename "$ext_dir")"
    dest="/usr/share/gnome-shell/extensions/$uuid"
    echo "    - $uuid"
    rm -rf "$dest"
    mkdir -p "$dest"
    rsync -a "$ext_dir" "$dest/"
    if [[ -d "$dest/schemas" ]]; then
        glib-compile-schemas "$dest/schemas/"
    fi
done

echo "==> Installing wallpapers -> /usr/share/backgrounds/peachos"
mkdir -p /usr/share/backgrounds/peachos
cp "$REPO_DIR"/assets/wallpapers/*.jpg "$REPO_DIR"/assets/wallpapers/*.png /usr/share/backgrounds/peachos/

echo "==> Installing peachOS dconf system defaults"
mkdir -p /etc/dconf/db/local.d
cp "$REPO_DIR/provision/dconf/01-peachos" /etc/dconf/db/local.d/01-peachos

mkdir -p /etc/dconf/profile
if [[ ! -f /etc/dconf/profile/user ]]; then
    printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user
elif ! grep -q '^system-db:local$' /etc/dconf/profile/user; then
    printf 'system-db:local\n' >> /etc/dconf/profile/user
fi

dconf update

echo "==> Done."
echo "peachOS defaults are now system-wide. Any NEW user account gets the"
echo "full look (theme, icons, wallpaper, dock, top bar, extensions) with"
echo "zero manual setup. Existing users keep their own overrides unless"
echo "those are reset (dconf reset -f / for the current user)."
