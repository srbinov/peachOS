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

# OS identity -- this was never set anywhere in this project before, so every distro-name
# surface (GNOME Settings' "About", neofetch-style tools, the actual TTY login banner, and
# critically the Calamares welcome screen, which reads os-release for its own branding
# strings) was silently showing "Ubuntu 26.04" the whole time. ID_LIKE keeps BOTH "ubuntu"
# and "debian" (not just one) -- this is genuinely Ubuntu-based, and plenty of scripts
# (including some of peachOS's own, and apt tooling) branch on ID_LIKE to detect that family;
# dropping it entirely to look "more custom" would silently break real compatibility checks
# for zero branding benefit, since ID itself (checked first, always) already says "peachos".
echo "==> Setting OS identity -> peachOS 10.0 (not Ubuntu)"
cat > /etc/os-release <<'EOF'
PRETTY_NAME="peachOS 10.0"
NAME="peachOS"
VERSION_ID="10.0"
VERSION="10.0 (Nectar)"
VERSION_CODENAME=nectar
ID=peachos
ID_LIKE="ubuntu debian"
HOME_URL="https://github.com/srbinov/peachOS"
SUPPORT_URL="https://github.com/srbinov/peachOS/issues"
BUG_REPORT_URL="https://github.com/srbinov/peachOS/issues"
UBUNTU_CODENAME=resolute
LOGO=distributor-logo
EOF

cat > /etc/lsb-release <<'EOF'
DISTRIB_ID=peachOS
DISTRIB_RELEASE=10.0
DISTRIB_CODENAME=nectar
DISTRIB_DESCRIPTION="peachOS 10.0"
EOF

printf 'peachOS 10.0 \\n \\l\n\n' > /etc/issue

# Skip GNOME's own first-login wizard (gnome-initial-setup) entirely for every account --
# the live user (via penguins-eggs' create-live-home, which copies /etc/skel/. verbatim at
# remaster time) and any account Calamares creates during a real install (useradd -m also
# seeds from /etc/skel). peachOS ships fully preconfigured through the dconf defaults
# installed below -- theme, dock, top bar, wallpaper, every extension enabled -- so there is
# nothing left for that wizard to ask, and left enabled it would show generic Adwaita chrome
# plus stock Ubuntu-specific pages (Ubuntu Pro/Livepatch/Online Accounts) that clash with the
# rest of peachOS and undercut the fully-custom out-of-box experience.
# gnome-initial-setup-first-login.service's own ConditionPathExists=!%E/gnome-initial-setup-done
# (%E = $XDG_CONFIG_HOME) is the documented, standard skip mechanism -- no systemd units need
# masking, and it's what other GNOME-based distros with fully preset defaults rely on too.
echo "==> Disabling gnome-initial-setup (peachOS ships fully preconfigured, no wizard needed)"
mkdir -p /etc/skel/.config
touch /etc/skel/.config/gnome-initial-setup-done

# Found on a real first-boot test (2026-09-01): the marker above blocks
# gnome-initial-setup-first-login.service as intended, but gnome-initial-setup-upgrade-
# login.service has the OPPOSITE condition on that exact same file --
# `ConditionPathExists=%E/gnome-initial-setup-done` (requires it to EXIST) alongside
# `ConditionPathExists=!%E/gnome-initial-setup/upgrade-26.04-done` (requires THIS one to
# NOT exist) -- so seeding the first marker to stop the first-login wizard was, by itself,
# exactly what satisfies the upgrade wizard's own trigger instead. Same wizard UI either way
# (same Ubuntu-branded appearance/telemetry/app-store pages this file already documents
# below), just reached through the "upgrade" entry point rather than "first login" -- which
# is exactly what a live/demo boot showed: the marker was present (from /etc/skel), but the
# wizard still ran. Second marker closes that gap. "26.04" is a literal, non-templated string
# in that unit file (Ubuntu's own base version this build is on) -- confirm it still matches
# if the base Ubuntu version this project tracks ever changes.
mkdir -p /etc/skel/.config/gnome-initial-setup
touch /etc/skel/.config/gnome-initial-setup/upgrade-26.04-done

# The above markers skip gnome-initial-setup's whole wizard -- confirmed via its own compiled
# binary's embedded page list (gis-appearance-page.ui/"Choose how Ubuntu looks" dark-light
# toggle, gis-ubuntu-insights-page.ui, gis-software-page.ui/gis-apps-page.ui "Ubuntu's App
# Center has a range of apps") that this covers the exact dark/light + data-sharing + app-store
# prompts reported, not assumed. ubuntu-report is a genuinely SEPARATE mechanism though (no
# reference to it anywhere in the gnome-initial-setup binary's own strings) -- its own systemd
# path unit fires an interactive "send hardware/usage metrics" dialog whenever
# ~/.cache/ubuntu-report/pending exists; whoopsie is the actual Canonical crash-report
# submission daemon, woken by any change under /var/crash. Both confirmed live: a plain
# `apt-get remove ubuntu-report whoopsie ...` cascades into removing gdm3/gnome-shell/
# gnome-control-center/ubuntu-session entirely (ubuntu-desktop-minimal hard-depends on them),
# so mask their triggers instead of touching the packages -- zero dependency risk, same
# outcome. apport itself (local crash collection, not the submission step) is left enabled --
# genuinely useful for peachOS's own debugging and doesn't itself phone home or prompt anyone.
echo "==> Masking Canonical telemetry prompts (ubuntu-report, whoopsie) -- packages left alone, see above"
systemctl mask whoopsie.path whoopsie.service
systemctl --global mask ubuntu-report.path ubuntu-report.service

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# Pin to the exact upstream commits that produced the currently-installed
# peachOS look, so a re-run always reproduces the same result.
MACTAHOE_GTK_REPO="https://github.com/vinceliuice/MacTahoe-gtk-theme.git"
MACTAHOE_GTK_COMMIT="5df7f86eb787e1f7054f377e2c318b8af873d705"
MACTAHOE_ICON_REPO="https://github.com/vinceliuice/MacTahoe-icon-theme.git"
MACTAHOE_ICON_COMMIT="db9a4f8b236d3c559326f041d75d5173de118c45"
# Apple-style emoji set (72px PNGs, ~3.8k files / 33MB) -- the Settings app's Edit-Profile
# emoji avatar picker (apps/settings/src/avatar_picker.py, indexed by
# apps/settings/data/emoji_manifest.json). Cloned, not vendored -- same call as the MacTahoe
# themes above, for the same reason (bulk read-only art that would bloat the peachOS repo).
SYSICONS_REPO="https://github.com/srbinov/macOS_Tahoe_SYSICONS.git"
SYSICONS_COMMIT="d5fd1cf3f2d46b8949015bee81e99a9ab4d2cbc1"

echo "==> Installing build dependencies"
apt-get update -qq
apt-get install -y --no-install-recommends git rsync dconf-cli libglib2.0-bin gettext

# mpv drives Perfect Lock Screen's live video background (extensions/perfect-lockscreen@chris) --
# GStreamer is its own fallback if mpv is missing, but mpv is the tested/expected player.
echo "==> Installing mpv (Perfect Lock Screen live video player)"
apt-get install -y --no-install-recommends mpv

# peachySearch (apps/ulauncher) runtime deps: python3-gi-cairo fixes a real "Couldn't find
# foreign struct converter for 'cairo.Context'" crash on every draw (PyGObject's cairo
# integration isn't in the base gi package), python3-xlib is a hard dependency of the app
# itself, and wl-clipboard backs Clipboard mode -- GTK3's own GDK Wayland clipboard backend
# doesn't round-trip data at all in this environment (reads AND writes silently fail), so
# Clipboard mode shells out to wl-copy/wl-paste instead of using Gtk.Clipboard directly.
echo "==> Installing peachySearch (ulauncher) runtime dependencies"
apt-get install -y --no-install-recommends python3-gi-cairo python3-xlib wl-clipboard

# peachySearch itself was never actually installed anywhere -- only its runtime deps were.
# The dconf default wiring the <Primary>space keybinding to it (see provision/dconf/01-peachos)
# pointed straight at $REPO_DIR/apps/ulauncher/bin/ulauncher, which only ever existed on this
# dev VM's own checkout (/home/user/peachOS/...) -- confirmed missing entirely on a real boot
# test, since a fresh account never has that dev path. bin/ulauncher (vendored upstream script)
# auto-detects its own project root from wherever it's actually run from (checks for a sibling
# `ulauncher/` package dir, sets PYTHONPATH accordingly) -- it doesn't need to be run from a
# git checkout specifically, just needs its own directory structure (bin/, ulauncher/, data/)
# copied intact, which is what this does. The dconf keybinding command itself points at this
# same system path, not the dev one -- see 01-peachos.
echo "==> Installing peachySearch (ulauncher) system-wide -> /usr/lib/peachos/ulauncher"
mkdir -p /usr/lib/peachos/ulauncher
rsync -a --delete "$REPO_DIR/apps/ulauncher/bin/" /usr/lib/peachos/ulauncher/bin/
rsync -a --delete "$REPO_DIR/apps/ulauncher/ulauncher/" /usr/lib/peachos/ulauncher/ulauncher/
rsync -a --delete "$REPO_DIR/apps/ulauncher/data/" /usr/lib/peachos/ulauncher/data/

# /usr/bin/ulauncher is what upstream's own .desktop/.service files (io.ulauncher.Ulauncher.
# desktop's TryExec, io.ulauncher.Ulauncher.service's Exec, ulauncher.service's ExecStart --
# all three, unmodified from upstream) actually expect -- installing a real wrapper here means
# those files can be deployed exactly as upstream wrote them instead of hand-patching a path
# into each one, which is what silently broke portability in the first place (a hand-edit to
# the *repo's own* io.ulauncher.Ulauncher.desktop pointed TryExec at this dev VM's own checkout
# path, /home/user/peachOS/..., invisible until a real fresh-account boot test: TryExec failing
# hides a .desktop entry from menus/app-grids entirely, which is why peachySearch didn't show
# up anywhere, not just why the keybinding failed).
install -Dm755 /dev/stdin /usr/bin/ulauncher <<'EOF'
#!/bin/sh
exec /usr/lib/peachos/ulauncher/bin/ulauncher "$@"
EOF
install -Dm644 "$REPO_DIR/apps/ulauncher/io.ulauncher.Ulauncher.desktop" /usr/share/applications/io.ulauncher.Ulauncher.desktop
install -Dm644 "$REPO_DIR/apps/ulauncher/io.ulauncher.Ulauncher.service" /usr/share/dbus-1/services/io.ulauncher.Ulauncher.service
install -Dm644 "$REPO_DIR/apps/ulauncher/ulauncher.service" /usr/lib/systemd/user/ulauncher.service
# Run peachySearch as a persistent per-user daemon so <Primary>space / the menu-bar
# magnifier toggle it instantly instead of cold-starting the Python process each time
# (Spotlight-style). --global enables it for every user's graphical session.
systemctl --global enable ulauncher.service
update-desktop-database /usr/share/applications

# Settings app (apps/settings) runtime dep: gir1.2-goa-1.0 gives the Internet Accounts tab
# real GNOME Online Accounts bindings -- gnome-online-accounts itself (the goa-daemon and
# its D-Bus service) ships by default, but its GObject-Introspection typelib is a separate
# package that doesn't get pulled in automatically.
echo "==> Installing Settings app (Internet Accounts) runtime dependencies"
apt-get install -y --no-install-recommends gir1.2-goa-1.0

# Extension Manager (com.mattjakeman.ExtensionManager) -- browse/install/configure GNOME
# Shell extensions with a real GUI. peachOS's app-grid folder (provision/dconf/01-peachos)
# already lists it; the apt build ships the same com.mattjakeman.ExtensionManager.desktop
# id as the Flathub one, no flatpak runtime needed.
echo "==> Installing Extension Manager"
apt-get install -y --no-install-recommends gnome-shell-extension-manager

# Icon masker daemon: watches every place apps drop .desktop launchers (apt, snap, per-user)
# and squircle-fies any icon that isn't already styled like one -- python3-gi backs the
# headless Gio.FileMonitor watcher, python3-pil does the actual image compositing/masking,
# and rsvg-convert (librsvg2-bin) rasterizes SVG sources. Deliberately NOT using
# GdkPixbuf/glycin for this: glycin's sandboxed loader shells out through bubblewrap + D-Bus
# per image, which reliably hangs when run from this systemd-hardened service (ProtectSystem
# vs. bwrap's own sandboxing don't mix) and stalls hard on any icon living under /snap.
echo "==> Installing icon masker daemon dependencies"
apt-get install -y --no-install-recommends python3-gi python3-pil librsvg2-bin

echo "==> Installing peachOS icon masker daemon -> /usr/lib/peachos/iconmasker"
install -d /usr/lib/peachos/iconmasker
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_mask.py" /usr/lib/peachos/iconmasker/peachos_icon_mask.py
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_resolve.py" /usr/lib/peachos/iconmasker/peachos_icon_resolve.py
# peachos_icon_resolve.py imports peachos_icon_presets_registry (and that pulls in the two
# peachos_icon_preset* helpers) -- without them the watcher daemon dies on startup with
# ModuleNotFoundError and systemd restart-loops it forever. Ship the whole module set.
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_presets_registry.py" /usr/lib/peachos/iconmasker/peachos_icon_presets_registry.py
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_preset.py" /usr/lib/peachos/iconmasker/peachos_icon_preset.py
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_preset_batch.py" /usr/lib/peachos/iconmasker/peachos_icon_preset_batch.py
install -Dm755 "$REPO_DIR/apps/iconmasker/peachos-icon-watcherd" /usr/lib/peachos/iconmasker/peachos-icon-watcherd
install -d /usr/share/icons/peachos-auto
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos-icon-watcherd.service" /etc/systemd/system/peachos-icon-watcherd.service
systemctl enable peachos-icon-watcherd.service

# Dark / Clear icon-appearance mode: a *separate* pass from the watcher daemon above,
# triggered on-demand (from the Settings app's Appearance tab). It ONLY swaps in a
# hand-authored dark/clear icon variant when the repo ships one for that app (see the
# peachos-{darkmode,clearmode}-src dirs below); apps without one keep their light icon. It
# does not synthesize a variant from the light icon. Runs entirely unprivileged: it only
# ever writes XDG overrides under the invoking user's own ~/.local/share, never system-wide,
# so no polkit policy/pkexec is needed -- and system-wide writes here were what caused two
# real bugs (fighting the watcher daemon over the same files, and GNOME Shell's own
# app-picker-layout state getting corrupted by the resulting burst of changes).
echo "==> Installing peachOS icon appearance (dark/clear mode) tool -> /usr/lib/peachos/iconmasker"
install -Dm755 "$REPO_DIR/apps/iconmasker/peachos-icon-appearance" /usr/lib/peachos/iconmasker/peachos-icon-appearance
install -Dm644 "$REPO_DIR/apps/settings/data/schemas/org.peachos.appearance.gschema.xml" /usr/share/glib-2.0/schemas/org.peachos.appearance.gschema.xml
glib-compile-schemas /usr/share/glib-2.0/schemas/

# Menu-bar "Background Blur" helper: software-blurs the wallpaper slice behind the top
# panel (macos-top-panel@local.dev's lib/panelBackground.js runs it). Deliberately not a
# GPU/Shell.BlurEffect blur -- see that file. Uses python3-pil, already provisioned above.
echo "==> Installing peachOS menu-bar background-blur helper -> /usr/lib/peachos/menubar"
install -Dm755 "$REPO_DIR/apps/menubar-blur/peachos-menubar-blur" /usr/lib/peachos/menubar/peachos-menubar-blur

# Hand-authored dark variants for the icons peachOS ships hand-picked light versions of --
# used as-is instead of running them through the majority/minority algorithm above, which is
# only ever an approximation of what a real designer would do.
install -d /usr/share/icons/peachos-darkmode-src
for f in "$REPO_DIR"/assets/app-icons/darkmode/*.svg; do
    install -Dm644 "$f" "/usr/share/icons/peachos-darkmode-src/$(basename "$f")"
done

# Curated presets for common third-party apps (browsers, chat clients, dev tools, ...) a
# user is likely to install later, not something peachOS ships itself -- see
# apps/iconmasker/peachos_icon_presets_registry.py for the actual app list/matching names.
# peachos-icon-watcherd matches a newly-installed app by its own .desktop Name= field and
# points Icon= straight at one of these instead of running it through the masking pipeline.
# darkmode/ always has one file per app registered in PRESETS, even when it's just a copy of
# the default (see that dir's own build step) -- landing in the SAME peachos-darkmode-src
# already populated above is what makes CURATED_DARK_SLUGS resolve every preset app
# deterministically, never falling through to the automatic dark-mode generator meant for
# uncurated icons.
install -d /usr/share/icons/peachos-presets
for f in "$REPO_DIR"/assets/app-icons/presets/*.svg; do
    install -Dm644 "$f" "/usr/share/icons/peachos-presets/$(basename "$f")"
done
for f in "$REPO_DIR"/assets/app-icons/presets/darkmode/*.svg; do
    install -Dm644 "$f" "/usr/share/icons/peachos-darkmode-src/$(basename "$f")"
done

# Calamares installer (the GUI setup screen shown booting the eventual ISO from USB) --
# peachOS's own branding + module sequence, on top of calamares-settings-ubuntu-common
# (only ships shared exec-stage modules: bootloader/fstab/grub/mount/etc., not a complete
# installer). Adapted from a REAL, currently-shipping reference (Ubuntu 26.04's own
# calamares-settings-kubuntu, `apt-get download` + `dpkg-deb -x`'d to inspect without
# installing it -- it conflicts on shared file paths with ubuntu-common if actually
# installed alongside it), not written from guesswork: settings.conf's module sequence,
# users.conf, and partition.conf are only lightly adapted (peachos_boot/peachos_root
# partition names, gdm instead of sddm); displaymanager.conf verified against this actual
# system's own /usr/share/wayland-sessions/ubuntu.desktop rather than assumed; dropped
# Kubuntu/KDE-specific bug workarounds (fixconkeys, add386arch, oemprep, ...) whose
# applicability to peachOS was never confirmed, and the pkgselect "optional extras" screen
# entirely (KDE-app-specific button text/packages, no peachOS equivalent designed yet).
# unpackfs.conf's source path is the one real unknown left: adapted from penguins-eggs'
# own installed remaster template (/etc/penguins-eggs.d/brain.d/modules/debian/
# remaster.bash.tmpl, which copies the squashfs to $ISODIR/live/filesystem.squashfs, a
# Debian-Live layout -- NOT Kubuntu's casper-based /cdrom/casper/filesystem.squashfs) but
# the live-boot mount point itself (/run/live/medium) is live-boot's documented default,
# not something confirmed by actually booting an eggs-built ISO -- re-verify the first time
# `eggs remaster` produces one. Verified end-to-end short of that: `calamares --debug`
# actually launches with this exact config and reports "Loaded branding component
# 'peachos'" plus every view module (welcome/locale/keyboard/partition/users/summary)
# "loading complete" with zero errors, only benign warnings matching the real Kubuntu
# reference's own (e.g. partition's "unknown" filesystem meaning "let the user pick").
echo "==> Installing Calamares installer -> peachOS branding"
# qml6-module-qtquick-{controls,layouts}: NOT pulled in by the calamares package itself (it
# runs fine without them, in its default all-widget mode) but required by peachOS's own
# calamares-sidebar.qml/calamares-navigation.qml, which replace the stock left-hand widget
# sidebar with custom QML panels -- confirmed missing live (`calamares --debug` logged
# `module "QtQuick.Layouts" is not installed` until these were installed) rather than assumed.
apt-get install -y --no-install-recommends calamares calamares-settings-ubuntu-common \
    qml6-module-qtquick-controls qml6-module-qtquick-layouts
install -d /etc/calamares/branding/peachos
install -Dm644 "$REPO_DIR/provision/calamares/settings.conf" /etc/calamares/settings.conf
for f in "$REPO_DIR"/provision/calamares/modules/*.conf; do
    install -Dm644 "$f" "/etc/calamares/modules/$(basename "$f")"
done
for f in "$REPO_DIR"/provision/calamares/branding/peachos/*; do
    install -Dm644 "$f" "/etc/calamares/branding/peachos/$(basename "$f")"
done

# penguins-eggs itself ships stock branding baked into its own compiled binary/config that
# provisioning must override on the same host that runs `eggs remaster` (this config lives
# under /etc/penguins-eggs.d/, is NOT part of what gets squashed into the ISO, and is read
# fresh by the eggs binary on every remaster -- so these overrides only take effect on a
# build host that already has penguins-eggs installed; skip cleanly otherwise). Two overrides:
# (1) splash.png -- used verbatim for BOTH the GRUB and isolinux/BIOS boot menu backgrounds
# (generate-menus.sh), replacing the stock penguins-on-ice photo. (2) trust-desktop.sh -- the
# live-session autostart script that copies the installer launcher to the Desktop and marks
# it trusted; its LAUNCHER_SRC (/usr/share/applications/install-system.desktop) is regenerated
# every remaster by eggs' own hardcoded "create-live-launcher" step ("Install System" name,
# penguin icon) and is NOT itself editable, so this override writes peachOS's branded
# Desktop-Entry content directly in the script rather than fighting that step. Its Icon= points
# at install-peachos.svg, installed system-wide here too so the reference resolves at first boot.
if [ -d /etc/penguins-eggs.d ]; then
    echo "==> Rebranding penguins-eggs boot/install assets -> peachOS"
    install -Dm644 "$REPO_DIR/assets/boot/grub-splash.png" /etc/penguins-eggs.d/brain.d/assets/splash.png
    install -Dm755 "$REPO_DIR/provision/penguins-eggs/trust-desktop.sh" /etc/penguins-eggs.d/scripts/trust-desktop.sh
    install -Dm644 "$REPO_DIR/assets/logos/PeachICON_BLACK.svg" /usr/share/icons/peachos/install-peachos.svg
fi

# Live/demo-boot-only fix: without this, an idle live session locks via stock GNOME
# screensaver defaults and asks for the "live" account's undocumented password (penguins-eggs'
# own commented-out custom.yaml example, never shown to whoever's actually trying peachOS) --
# see disable-lock.sh's own docstring for the full reasoning and its boot=live guard, which is
# what keeps this a no-op on a real install rather than where the file lives.
echo "==> Installing live-session lock guard (boot=live only, see disable-lock.sh)"
install -Dm755 "$REPO_DIR/provision/live-session/disable-lock.sh" /usr/local/bin/peachos-disable-live-lock
install -Dm644 "$REPO_DIR/provision/live-session/disable-lock.desktop" /etc/skel/.config/autostart/peachos-disable-live-lock.desktop

# Firefox's MacTahoe theme (userChrome.css/userContent.css) only ever lived inside this dev
# VM's own snap Firefox profile -- no install step anywhere seeded it for a new account,
# meaning a fresh install or live boot would show completely stock Firefox. The theme assets
# themselves are shipped system-wide here (any account can reference them); the actual
# per-profile seeding (chrome symlink + the legacyUserProfileCustomizations pref, since a new
# profile's random salt can't be known ahead of time) happens at first login instead -- see
# setup-firefox-theme.sh's own docstring for the full reasoning and what was/wasn't
# re-provable inside this dev sandbox.
echo "==> Installing Firefox MacTahoe theme assets -> /usr/share/peachos/firefox-theme"
mkdir -p /usr/share/peachos/firefox-theme
cp -r "$REPO_DIR"/assets/firefox-theme/. /usr/share/peachos/firefox-theme/
chmod -R a+rX /usr/share/peachos/firefox-theme
echo "==> Installing Firefox theme first-login seeder"
install -Dm755 "$REPO_DIR/provision/live-session/setup-firefox-theme.sh" /usr/local/bin/peachos-setup-firefox-theme
install -Dm644 "$REPO_DIR/provision/live-session/setup-firefox-theme.desktop" /etc/skel/.config/autostart/peachos-setup-firefox-theme.desktop

# Boot splash: peachOS's own Plymouth theme (two-step module) instead of stock Ubuntu's bgrt
# -- black or white full-screen fill, the peachOS mark (same peach-icon-symbolic.svg the top
# bar's own KiwiMenuButton uses at index 19, kiwimenu.js/icons.json) centered above a simple
# progress bar, no spinner, no text. Its own dark/light variant PNGs (watermark-dark.png,
# watermark-light.png) and the two-step config both ship in the repo; the small set of
# password-dialog assets two-step also expects (entry/lock/capslock/bullet/keymap-render)
# are reused as-is from plymouth-theme-spinner rather than duplicated into this repo, since
# they're stock Plymouth artwork this theme doesn't customize.
echo "==> Installing peachOS boot splash (Plymouth theme) -> /usr/share/plymouth/themes/peachos"
apt-get install -y --no-install-recommends plymouth-theme-spinner
install -d /usr/share/plymouth/themes/peachos
install -Dm644 "$REPO_DIR/apps/plymouth/theme/peachos.plymouth" /usr/share/plymouth/themes/peachos/peachos.plymouth
install -Dm644 "$REPO_DIR/apps/plymouth/theme/watermark-dark.png" /usr/share/plymouth/themes/peachos/watermark-dark.png
install -Dm644 "$REPO_DIR/apps/plymouth/theme/watermark-light.png" /usr/share/plymouth/themes/peachos/watermark-light.png
for f in entry.png lock.png capslock.png bullet.png keymap-render.png; do
    install -Dm644 "/usr/share/plymouth/themes/spinner/$f" "/usr/share/plymouth/themes/peachos/$f"
done

install -d /usr/lib/peachos/plymouth
install -Dm755 "$REPO_DIR/apps/plymouth/peachos-plymouth-sync" /usr/lib/peachos/plymouth/peachos-plymouth-sync

update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
    /usr/share/plymouth/themes/peachos/peachos.plymouth 100
update-alternatives --set default.plymouth /usr/share/plymouth/themes/peachos/peachos.plymouth

# Seeds the theme's own watermark.png/colors and bakes them into the initramfs (see
# peachos-plymouth-sync's own docstring for why Plymouth can't just read the desktop's
# color-scheme itself at boot). Unconditionally "dark" here rather than reading the
# installing user's live color-scheme -- matches the feature's own explicit spec (black
# screen by default) and doesn't depend on dconf/dbus being reachable from a provisioning
# script the way a live desktop session's own toggle (appearance_page.py's
# _sync_plymouth_theme(), called from then on) can assume. update-initramfs only needs to
# run once here even though the script normally does it on every real change, since this is
# the very first run and there's nothing yet to compare against.
/usr/lib/peachos/plymouth/peachos-plymouth-sync dark

# Same idea for Clear mode -- a smaller set (peachos_icon_clear.py's own algorithm was
# calibrated against these exact three files, see that module's docstring).
install -d /usr/share/icons/peachos-clearmode-src
for f in "$REPO_DIR"/assets/app-icons/clearmode/*.svg; do
    install -Dm644 "$f" "/usr/share/icons/peachos-clearmode-src/$(basename "$f")"
done

# System Settings app (apps/settings): a from-scratch GTK4/libadwaita replacement for
# gnome-control-center, not a wrapper around it (see apps/settings/CLAUDE.md-adjacent
# feedback: never shell out to the stock Settings app). Installed as a real repo checkout
# under /usr/lib/peachos rather than packaged, matching the icon masker daemon above --
# src/ and data/ are copied together so the app's own relative `../data/...` lookups
# (icons, wallpaper previews, dock presets) keep resolving correctly post-install.
echo "==> Installing peachOS System Settings app -> /usr/lib/peachos/settings"
mkdir -p /usr/lib/peachos/settings
rsync -a --delete "$REPO_DIR/apps/settings/src/" /usr/lib/peachos/settings/src/
rsync -a --delete "$REPO_DIR/apps/settings/data/" /usr/lib/peachos/settings/data/
install -Dm755 "$REPO_DIR/apps/settings/peachos-settings" /usr/bin/peachos-settings
install -Dm644 "$REPO_DIR/apps/settings/peachos-settings.desktop" /usr/share/applications/peachos-settings.desktop
update-desktop-database /usr/share/applications

# Emoji set for the Settings app's Edit-Profile emoji avatar picker. Sparse-checkout just
# the apple-emoji dir (33MB) from the pinned SYSICONS commit -> /usr/share/peachos/emoji.
echo "==> Installing emoji set (Settings profile picker) -> /usr/share/peachos/emoji"
git clone --quiet --no-checkout --depth 1 --filter=blob:none "$SYSICONS_REPO" "$WORK_DIR/sysicons"
git -C "$WORK_DIR/sysicons" sparse-checkout set --no-cone apple-emoji
git -C "$WORK_DIR/sysicons" fetch --quiet --depth 1 origin "$SYSICONS_COMMIT"
git -C "$WORK_DIR/sysicons" checkout --quiet "$SYSICONS_COMMIT"
install -d /usr/share/peachos/emoji
rsync -a --delete "$WORK_DIR/sysicons/apple-emoji/" /usr/share/peachos/emoji/
chmod -R a+rX /usr/share/peachos/emoji

# Sidra: an Apple Music desktop client (Electron, github.com/srbinov/sidra -- our own fork of
# wimpysworld/sidra, currently one commit ahead with a custom splash/icon). Built from source
# rather than pulling wimpysworld's own GitHub release, since that release predates our fork's
# icon/splash commit and would ship the wrong branding. Requires the CastLabs Widevine-patched
# Electron build (github:castlabs/electron-releases, pulled automatically by `npm install` via
# package.json's own devDependency) -- standard Electron has no Widevine DRM support on Linux,
# and Apple Music needs it to play anything. electron-builder (also a devDependency) produces a
# real .deb with its own postinst/icon/.desktop handling, installed the same way as any other
# apt package rather than run in place out of a source checkout.
SIDRA_REPO="https://github.com/srbinov/sidra.git"
SIDRA_COMMIT="4f561fe9823ef1a90f97a8dee76ad991f6978fe1"

echo "==> Installing Node.js 24 (Sidra build dependency)"
if ! command -v node >/dev/null || [[ "$(node --version)" != v24* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
    apt-get install -y nodejs
fi

echo "==> Building Sidra (Apple Music client) -> /opt/Sidra"
git clone --quiet "$SIDRA_REPO" "$WORK_DIR/sidra"
git -C "$WORK_DIR/sidra" checkout --quiet "$SIDRA_COMMIT"
(
    cd "$WORK_DIR/sidra"
    npm install
    npm run build
    npx electron-builder --linux deb
)
apt-get install -y "$WORK_DIR/sidra/release/Sidra-"*-linux-amd64.deb

# Same treatment as peachy.svg/orchard_icon.svg/app_center_icon.svg above -- Sidra's own
# music_icon_DEFAULTMODE.svg/music_icon_darkMODE.svg are already real, pixel-perfect, pre-styled
# app icons (squircle backdrop and all, confirmed by rendering both), not raw glyphs -- exactly
# the "hand-picked, never touched" category those are, not a job for the generic masking
# algorithm. Icon= gets repointed at the curated absolute path so peachos-icon-watcherd's
# resolve_icon() categorizes it CATEGORY_OWN and leaves it alone entirely; the matching
# peachos_icon_resolve.py CURATED_DARK_SLUGS entry (installed above) is what makes the Dark
# Mode toggle use Sidra's own dark SVG instead of running peachos_icon_dark.py's algorithm on
# the light one.
install -Dm644 "$REPO_DIR/assets/app-icons/sidra.svg" /usr/share/icons/peachos/sidra.svg
sed -i "s|^Icon=.*|Icon=/usr/share/icons/peachos/sidra.svg|; /^X-PeachOS-OriginalIcon=/d" \
    /usr/share/applications/sidra.desktop
update-desktop-database /usr/share/applications

# iCloud apps (Mail/Contacts/Calendar/Photos/Drive/Notes/Reminders/Pages/Numbers/Keynote/
# Find/Maps/TV) are built from source here rather than pulled from the Snap Store -- the
# published Store package (Marcus Tomlinson's upstream) is missing Maps and TV, which only
# exist in this fork. Ubuntu no longer ships webkit2gtk-4.0 (only 4.1, API-identical, differs
# only in the libsoup2 vs libsoup3 backend this app never touches), so a local pkg-config
# shim satisfies CMakeLists.txt's `webkit2gtk-4.0` REQUIRED check against the installed 4.1
# package instead of patching the upstream build file.
ICLOUD_REPO="https://github.com/srbinov/icloud-for-linux.git"
ICLOUD_COMMIT="329c519"

echo "==> Installing iCloud apps build dependencies"
apt-get install -y --no-install-recommends make cmake g++ pkg-config libgtk-3-dev libwebkit2gtk-4.1-dev

echo "==> Building iCloud apps from source -> /usr/bin"
git clone --quiet --recurse-submodules "$ICLOUD_REPO" "$WORK_DIR/icloud-for-linux"
git -C "$WORK_DIR/icloud-for-linux" checkout --quiet "$ICLOUD_COMMIT"

mkdir -p "$WORK_DIR/icloud-pkgconfig-shim"
WEBKIT2GTK41_PC="/usr/lib/x86_64-linux-gnu/pkgconfig/webkit2gtk-4.1.pc"
{
    echo "prefix=/usr"
    echo "exec_prefix=\${prefix}"
    echo "libdir=/usr/lib/x86_64-linux-gnu"
    echo "includedir=\${prefix}/include"
    echo
    echo "Name: WebKitGTK (4.0 compat shim -> 4.1)"
    echo "Description: Web content engine for GTK (build shim, points at the installed webkit2gtk-4.1)"
    echo "URL: https://webkitgtk.org"
    grep '^Version:' "$WEBKIT2GTK41_PC"
    echo "Requires: glib-2.0 gtk+-3.0 libsoup-3.0 javascriptcoregtk-4.1"
    echo "Libs: -L\${libdir} -lwebkit2gtk-4.1"
    echo "Cflags: -I\${includedir}/webkitgtk-4.1"
} > "$WORK_DIR/icloud-pkgconfig-shim/webkit2gtk-4.0.pc"

mkdir -p "$WORK_DIR/icloud-build"
(
    cd "$WORK_DIR/icloud-build"
    PKG_CONFIG_PATH="$WORK_DIR/icloud-pkgconfig-shim" \
        cmake "$WORK_DIR/icloud-for-linux" -DCMAKE_BUILD_TYPE=Release
    cmake --build . -- -j"$(nproc)"
)
install -Dm755 "$WORK_DIR/icloud-build/icloud-for-linux" /usr/bin/icloud-for-linux
install -Dm755 "$WORK_DIR/icloud-for-linux/scripts/apple-maps" /usr/bin/apple-maps
install -Dm755 "$WORK_DIR/icloud-for-linux/scripts/apple-tv" /usr/bin/apple-tv

# icloud-for-linux is a single choc/GTK3 binary with no GtkApplication, so its Wayland
# app_id (and X11 WM_CLASS) is derived from argv[0]'s basename -- every app it opens would
# otherwise report "icloud-for-linux" and neither the shell nor the dock can tell Mail from
# Photos from TV (windows collapse into one generic entry). Launch each through a per-app
# symlink named exactly the StartupWMClass its .desktop declares.
install -d /usr/lib/peachos/icloud
for slug in mail contacts calendar photos drive notes reminders pages numbers keynote find maps tv; do
    ln -sfn /usr/bin/icloud-for-linux "/usr/lib/peachos/icloud/icloud-for-linux.$slug"
done

echo "==> Installing iCloud app icons -> /usr/share/icons/icloud-for-linux"
for icon in mail contacts calendar photos drive notes reminders pages numbers keynote find maps tv; do
    install -Dm644 "$WORK_DIR/icloud-for-linux/snap/gui/${icon}.svg" \
        "/usr/share/icons/icloud-for-linux/${icon}.svg"
done

echo "==> Installing iCloud app desktop entries -> /usr/share/applications"
install_icloud_desktop() {
    local slug="$1" args="$2" name="$3"
    cat > "/usr/share/applications/icloud-for-linux_${slug}.desktop" <<EOF
[Desktop Entry]
Name=${name}
GenericName=${name}
Comment=${name}
Type=Application
Categories=Office
Icon=/usr/share/icons/icloud-for-linux/${slug}.svg
Exec=/usr/lib/peachos/icloud/icloud-for-linux.${slug} ${args}
StartupWMClass=icloud-for-linux.${slug}
Terminal=false
StartupNotify=true
EOF
}
install_icloud_desktop mail      "mail Mail"                            "iCloud Mail"
install_icloud_desktop contacts  "contacts Contacts"                    "iCloud Contacts"
install_icloud_desktop calendar  "calendar Calendar"                    "iCloud Calendar"
install_icloud_desktop photos    "photos Photos"                        "iCloud Photos"
install_icloud_desktop drive     "iclouddrive Drive"                    "iCloud Drive"
install_icloud_desktop notes     "notes Notes"                          "iCloud Notes"
install_icloud_desktop reminders "reminders Reminders"                  "iCloud Reminders"
install_icloud_desktop pages     "pages Pages"                          "iCloud Pages"
install_icloud_desktop numbers   "numbers Numbers"                      "iCloud Numbers"
install_icloud_desktop keynote   "keynote Keynote"                      "iCloud Keynote"
install_icloud_desktop find      "find Find"                            "iCloud Find"
install_icloud_desktop maps      'https://maps.apple.com/ "Apple Maps"' "Apple Maps"
install_icloud_desktop tv        'https://tv.apple.com/ "Apple TV"'     "Apple TV"
update-desktop-database /usr/share/applications

# These four were never actually installed by this script -- only their .desktop rebrands and
# icon overrides were, further down, which silently assumed the underlying snap already
# existed. Confirmed missing entirely on a real boot test (Orchard/BlueBubbles/App Center all
# absent) -- this dev VM had them installed manually at some point outside provision.sh
# entirely, which is why the gap went unnoticed here. `--classic` only where actually needed
# (desktop-security-center and firmware-updater are Canonical's own confined snaps, no classic
# flag); plain `snap install firefox`/`bluebubbles`/`snap-store` pull their own required base/
# content snaps (core22, gnome-42-2204, etc.) automatically, same as this VM's own install did.
echo "==> Installing snap packages the app rebrands below expect to already exist"
snap install firefox
snap install snap-store
snap install desktop-security-center
snap install firmware-updater

# peachOS-branded rebrands of stock apps: Files -> Peachy, Firefox -> Orchard. Firefox's real
# .desktop is regenerated by snapd on every refresh (/var/lib/snapd/desktop/applications), so a
# direct edit there would get silently reverted -- instead this installs an override of the same
# desktop ID into /usr/share/applications, which wins because /usr/share comes before
# /var/lib/snapd/desktop in $XDG_DATA_DIRS. Nautilus's .desktop is a normal apt-shipped file, so
# it's edited in place (only at risk of reverting on a nautilus package upgrade, same as any other
# provisioned tweak -- provision.sh re-applies it on every image rebuild anyway).
echo "==> Installing peachOS app-icon rebrands (Files -> Peachy, Firefox -> Orchard)"
install -Dm644 "$REPO_DIR/assets/app-icons/peachy.svg" /usr/share/icons/peachos/peachy.svg
install -Dm644 "$REPO_DIR/assets/app-icons/orchard_icon.svg" /usr/share/icons/peachos/orchard_icon.svg
install -Dm644 "$REPO_DIR/assets/app-icons/apps.svg" /usr/share/icons/peachos/apps.svg
install -Dm644 "$REPO_DIR/assets/app-icons/app_center_icon.svg" /usr/share/icons/peachos/app_center_icon.svg
install -Dm644 "$REPO_DIR/assets/app-icons/terminal_icon.svg" /usr/share/icons/peachos/terminal_icon.svg
install -Dm644 "$REPO_DIR/assets/app-icons/systemsettings_icon.svg" /usr/share/icons/peachos/systemsettings_icon.svg

sed -i \
    -e 's/^Name=Files$/Name=Peachy/' \
    -e 's/^Icon=org.gnome.Nautilus$/Icon=\/usr\/share\/icons\/peachos\/peachy.svg/' \
    /usr/share/applications/org.gnome.Nautilus.desktop

sed -i \
    -e 's/^Icon=org.gnome.Ptyxis$/Icon=\/usr\/share\/icons\/peachos\/terminal_icon.svg/' \
    /usr/share/applications/org.gnome.Ptyxis.desktop

cat > /usr/share/applications/firefox_firefox.desktop <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=Orchard
GenericName=Web Browser
Comment=Fast and private browser
Icon=/usr/share/icons/peachos/orchard_icon.svg
Exec=/snap/bin/firefox %u
Terminal=false
StartupNotify=true
StartupWMClass=firefox_firefox
Categories=GNOME;GTK;Network;WebBrowser;
MimeType=application/json;application/pdf;application/rdf+xml;application/rss+xml;application/x-xpinstall;application/xhtml+xml;application/xml;audio/flac;audio/ogg;audio/webm;image/avif;image/gif;image/jpeg;image/png;image/svg+xml;image/webp;text/html;text/xml;video/ogg;video/webm;x-scheme-handler/chrome;x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/mailto;
Keywords=Internet;WWW;Browser;Web;Explorer;
Actions=new-window;new-private-window;open-profile-manager;

[Desktop Action new-window]
Exec=/snap/bin/firefox --new-window %u
Name=New Window

[Desktop Action new-private-window]
Exec=/snap/bin/firefox --private-window %u
Name=New Private Window

[Desktop Action open-profile-manager]
Exec=/snap/bin/firefox --ProfileManager
Name=Open Profile Manager
EOF

# NOTE: BlueBubbles (iMessage client) is deliberately NOT shipped -- dropped from
# the image on request. If it comes back, it's `snap install bluebubbles` here plus
# a /usr/share/applications/bluebubbles_bluebubbles.desktop override for the curated
# messages.svg icon, and re-add it to favorite-apps in provision/dconf/01-peachos.

# App Center is also snapd-managed (/var/lib/snapd/desktop/applications), same override
# reasoning as Firefox above.
cat > /usr/share/applications/snap-store_snap-store.desktop <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=App Center
GenericName=App Center
Comment=Install, remove, and update apps
Icon=/usr/share/icons/peachos/app_center_icon.svg
Exec=snap-store %U
Terminal=false
StartupNotify=true
Categories=System;Utility;PackageManager;SoftwareManagement;Network;Settings;
Keywords=Ubuntu;Applications;Apps;Store;Software;Snaps;
MimeType=x-scheme-handler/snap;application/vnd.debian.binary-package;
EOF

# peachos-applauncher.desktop's Exec= just pokes macOS-TopBar-Gnome's own AppLauncherOverlay
# (lib/appLauncher.js) over D-Bus to toggle the Launchpad-style grid -- no separate binary,
# this is purely a Dock entry point for something the top-bar extension already implements.
echo "==> Installing peachOS App Launcher (Launchpad) desktop entry"
cp "$REPO_DIR/apps/applauncher/peachos-applauncher.desktop" /usr/share/applications/
update-desktop-database /usr/share/applications

# LocalSend (Flathub, github.com/localsend/localsend -- an open-source cross-platform
# AirDrop alternative, opened from the Control Center's airdrop circle -- see
# macOS-TopBar-Gnome's controlCenterIndicator.js). Flathub over a vendored .deb: always
# current, no binary to keep re-vendoring into this repo for every release.
#
# Unlike Firefox/BlueBubbles/App Center above (all snaps), this is a Flatpak -- Flathub's
# own exported desktop file + icon take priority over /usr/share/applications in
# XDG_DATA_DIRS (the *reverse* of snap's priority order), so the usual override-in-
# /usr/share/applications trick silently loses here. $XDG_DATA_HOME (~/.local/share) is
# implicitly checked before every XDG_DATA_DIRS entry, including Flatpak's own export
# dirs, which is why the override goes to ~/.local/share/applications per user instead.
#
# "per user" for real this time, not just whoever's logged in during provisioning: written
# to /etc/skel (so any account created after this runs gets it automatically, same as the
# dconf defaults below already do) AND backfilled for every real account already on the
# machine, since an existing user's home was already copied from the OLD /etc/skel before
# this file existed in it.
echo "==> Installing LocalSend (Flathub) -> curated AirDrop-style icon"
# flatpak itself is not in Ubuntu 26.04's default desktop install -- the dev VM had it, a
# clean box does not, and the bare `flatpak` calls below (LocalSend/Calendar/Weather) then
# abort the whole run under `set -euo pipefail`.
apt-get install -y --no-install-recommends flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y --system --noninteractive flathub org.localsend.localsend_app

install -Dm644 "$REPO_DIR/assets/app-icons/localsend.svg" /usr/share/icons/peachos/localsend.svg
install -Dm644 "$REPO_DIR/assets/app-icons/darkmode/localsend.svg" /usr/share/icons/peachos-darkmode-src/localsend.svg

write_localsend_override() {
    local apps_dir="$1/.local/share/applications"
    mkdir -p "$apps_dir"
    cat > "$apps_dir/org.localsend.localsend_app.desktop" <<'EOF'
[Desktop Entry]
Name=LocalSend
Comment=Share files to nearby devices
Exec=/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=localsend --file-forwarding org.localsend.localsend_app @@u %U @@
Icon=/usr/share/icons/peachos/localsend.svg
Terminal=false
Type=Application
Categories=GTK;FileTransfer;Utility;
Keywords=Sharing;LAN;Files;
StartupNotify=true
X-Flatpak=org.localsend.localsend_app
EOF
}

write_localsend_override /etc/skel

# UID 1000-59999 is the standard Debian/Ubuntu range for real (non-system, non-service)
# accounts -- everything outside it (root, daemon users, etc.) has no business getting a
# desktop launcher written into it.
while IFS=: read -r account _ uid _ _ homedir _; do
    if [[ "$uid" -ge 1000 && "$uid" -lt 60000 && -d "$homedir" ]]; then
        write_localsend_override "$homedir"
        chown -R "$account:$account" "$homedir/.local/share/applications"
    fi
done < <(getent passwd)

# Image Viewer (Loupe, apt-installed): same treatment as Sidra above -- a real, pre-styled
# curated icon (assets/app-icons/imageviewer.svg), Icon= repointed at the absolute path so
# peachos-icon-watcherd's resolve_icon() sees CATEGORY_OWN and never touches it. Lives
# directly in /usr/share/applications (a normal apt package, not a snap/flatpak), so this
# is the simple in-place sed rewrite, not the per-user override LocalSend needed above. Dark
# variant (assets/app-icons/darkmode/imageviewer.svg) is picked up by the generic darkmode/
# glob loop near the top of this script + its own CURATED_DARK_SLUGS entry -- nothing else
# to do here for it.
echo "==> Installing Image Viewer (Loupe) -> curated icon"
install -Dm644 "$REPO_DIR/assets/app-icons/imageviewer.svg" /usr/share/icons/peachos/imageviewer.svg
sed -i "s|^Icon=.*|Icon=/usr/share/icons/peachos/imageviewer.svg|; /^X-PeachOS-OriginalIcon=/d" \
    /usr/share/applications/org.gnome.Loupe.desktop
update-desktop-database /usr/share/applications

# Calculator (gnome-calculator, part of the base Ubuntu desktop image -- nothing to install
# here): no curated light icon, it keeps whatever peachos-icon-watcherd's own generic
# padding pass already gives it. Dark mode is still curated though -- CURATED_DARK_SLUGS
# keys off that padded output's own path, which is deterministic (slug_for() hashes the
# *desktop file's* path, not its content -- see peachos_icon_resolve.py's own comment on
# this entry), so it's stable across every machine without any provisioning step at all.

# Text Editor (gnome-text-editor, also part of the base Ubuntu image): NoDisplay'd so the
# real, curated Flatpak version (added separately, if ever) is the only "Text Editor" a
# user ever sees -- otherwise this native copy collides on the exact same desktop-file ID
# and peachos-icon-appearance silently overwrites whichever curated override exists with
# this one's own icon (a real bug this hit once already -- see git history).
sed -i '/^\[Desktop Entry\]/a NoDisplay=true' /usr/share/applications/org.gnome.TextEditor.desktop
update-desktop-database /usr/share/applications

# GNOME Calendar (Flathub): pinned in the dock's own favorite-apps (see provision/dconf/
# 01-peachos) but never actually installed by this script -- confirmed missing entirely from
# /usr/share/applications on this dev VM too (only present via flatpak's own export dir and a
# leftover per-user copy in ~/.local/share/applications that only exists on this one account).
# Same reasoning as Weather below applies: needs an explicit copy in /usr/share/applications
# since peachos-icon-appearance/-icon-watcherd never scan Flatpak's own export dir.
echo "==> Installing GNOME Calendar (Flathub)"
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y --system --noninteractive flathub org.gnome.Calendar

cat > /usr/share/applications/org.gnome.Calendar.desktop <<'EOF'
[Desktop Entry]
Name=Calendar
Comment=Access and manage your calendars
Exec=/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=gnome-calendar --file-forwarding org.gnome.Calendar @@u %U @@
Icon=org.gnome.Calendar
Terminal=false
Type=Application
StartupNotify=true
Categories=GNOME;GTK;Office;Calendar;Core;
MimeType=text/calendar;
DBusActivatable=true
X-Flatpak=org.gnome.Calendar
EOF

# GNOME Weather (Flathub): same story as Calculator above -- no curated light icon, keeps
# whatever peachos-icon-watcherd's padding pass gives it, dark mode is curated via
# CURATED_DARK_SLUGS. Flatpak, though, so unlike Calculator it needs an explicit copy in
# /usr/share/applications: peachos-icon-appearance/-icon-watcherd only ever scan there (+
# snapd's own dir) for *candidates*, never Flatpak's own export dir or any per-user path --
# without this copy neither script can ever find Weather to process it at all.
echo "==> Installing GNOME Weather (Flathub)"
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y --system --noninteractive flathub org.gnome.Weather

cat > /usr/share/applications/org.gnome.Weather.desktop <<'EOF'
[Desktop Entry]
Name=Weather
Comment=Show weather conditions and forecast
Exec=/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=gapplication org.gnome.Weather launch org.gnome.Weather
Icon=org.gnome.Weather
Terminal=false
Type=Application
Categories=GNOME;GTK;Utility;
X-Flatpak=org.gnome.Weather
EOF
update-desktop-database /usr/share/applications

# LibreOffice suite (Writer/Calc/Impress/Draw/Math/Base) -- preinstalled, not left for
# peachos-icon-watcherd to discover after the fact. libreoffice-gnome (not pulled in by
# --no-install-recommends alone) gives it real GTK/GNOME integration -- native file picker,
# proper icon theme/font rendering -- worth the extra package for a themed distro like this.
# No curated icon overrides needed: LibreOffice's own stock icons (Ubuntu's package) already
# ship as proper macOS-style squircles close to Apple's own Pages/Numbers/Keynote look, so
# peachos-icon-watcherd's light-touch padding pass (not full masking) is all they get, same
# as any other already-conforming icon.
echo "==> Installing LibreOffice suite (Writer, Calc, Impress, Draw, Math, Base)"
apt-get install -y --no-install-recommends libreoffice libreoffice-gnome

# Writer/Calc/Impress are the genuine iWork equivalents (Pages/Numbers/Keynote) -- rebranded
# to the same curated iCloud art those already use, not left as LibreOffice's own (perfectly
# fine, just not what this project wants shown) stock icons. Only the Icon= line changes,
# matching Files->Peachy's own sed rebrand pattern above -- Name=/Exec=/everything else
# about these apps stays real LibreOffice. Base/Draw/Math are left with their own stock
# icons; nothing in the curated iCloud set actually corresponds to what they are (a
# database tool and a diagramming tool, not part of the Pages/Numbers/Keynote trio).
#
# No separate dark-mode step needed here: icloud-for-linux is already in OWN_DIRS
# (peachos_icon_resolve.py) and pages/numbers/keynote are already registered in
# CURATED_DARK_SLUGS -- retargeting Icon= at that same curated path is what makes
# peachos-icon-appearance's existing dark-mode generation pick the right art up
# automatically, the same mechanism first-party curated icons already rely on.
sed -i 's|^Icon=libreoffice-writer$|Icon=/usr/share/icons/icloud-for-linux/pages.svg|' \
    /usr/share/applications/libreoffice-writer.desktop
sed -i 's|^Icon=libreoffice-calc$|Icon=/usr/share/icons/icloud-for-linux/numbers.svg|' \
    /usr/share/applications/libreoffice-calc.desktop
sed -i 's|^Icon=libreoffice-impress$|Icon=/usr/share/icons/icloud-for-linux/keynote.svg|' \
    /usr/share/applications/libreoffice-impress.desktop

# AirMirror (github.com/srbinov/airmirror -- our own GTK4/libadwaita AirPlay-mirroring
# receiver, wrapping UxPlay's engine). Cloned to /opt (matching Sidra's own /opt/Sidra
# convention) rather than any one user's home -- its own scripts/install.sh writes a
# launcher that hardcodes a reference back to wherever the clone lives, so /opt has to
# survive regardless of which account eventually runs it.
echo "==> Installing AirMirror (AirPlay receiver) -> /opt/airmirror"
apt-get install -y --no-install-recommends uxplay avahi-daemon gstreamer1.0-gtk4 \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav \
    python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0
systemctl enable --now avahi-daemon

rm -rf /opt/airmirror
git clone --quiet https://github.com/srbinov/airmirror.git /opt/airmirror
chmod +x /opt/airmirror/bin/mirror /opt/airmirror/scripts/install.sh /opt/airmirror/scripts/uninstall.sh
chown -R root:root /opt/airmirror
chmod -R a+rX /opt/airmirror

install -Dm644 "$REPO_DIR/assets/app-icons/airmirror.svg" /usr/share/icons/peachos/airmirror.svg

# scripts/install.sh is per-user by design (writes $HOME/.local/bin, .../applications,
# .../icons/hicolor) -- HOME is overridden per target rather than reimplementing its own
# logic, so this stays in sync automatically if install.sh ever changes upstream. Icon=
# gets repointed at our curated art afterward, same as every other curated app above.
install_airmirror_for() {
    local home_dir="$1" owner="$2"
    HOME="$home_dir" bash /opt/airmirror/scripts/install.sh >/dev/null
    sed -i "s|^Icon=.*|Icon=/usr/share/icons/peachos/airmirror.svg|" \
        "$home_dir/.local/share/applications/app.mirror.Mirror.desktop"
    if [[ -n "$owner" ]]; then
        chown -R "$owner:$owner" "$home_dir/.local/bin" "$home_dir/.local/share/applications" \
            "$home_dir/.local/share/icons"
    fi
}

install_airmirror_for /etc/skel ""
while IFS=: read -r account _ uid _ _ homedir _; do
    if [[ "$uid" -ge 1000 && "$uid" -lt 60000 && -d "$homedir" ]]; then
        install_airmirror_for "$homedir" "$account"
    fi
done < <(getent passwd)

# Also needs a copy directly in /usr/share/applications, same reasoning as Weather above:
# peachos-icon-appearance/-icon-watcherd can't see the per-user copies at all. Exec= here
# is self-contained (mirrors bin/mirror's own generated wrapper) rather than assuming any
# specific user's ~/.local/bin/mirror exists -- this copy's only real job is being visible
# to those two scripts; actual launches always resolve to one of the higher-priority
# per-user copies above instead.
cat > /usr/share/applications/app.mirror.Mirror.desktop <<EOF
[Desktop Entry]
Name=Mirror
Comment=AirPlay receiver for this computer
Exec=/usr/bin/python3 -c "import sys; sys.path.insert(0, '/opt/airmirror'); from mirror.identity import apply; apply(); from mirror.app import main; raise SystemExit(main())"
Path=/opt/airmirror
Icon=/usr/share/icons/peachos/airmirror.svg
Terminal=false
Type=Application
Categories=AudioVideo;Network;
StartupNotify=true
StartupWMClass=app.mirror.Mirror
EOF
update-desktop-database /usr/share/applications

echo "==> Installing MacTahoe GTK/Shell theme system-wide -> /usr/share/themes"
git clone --quiet "$MACTAHOE_GTK_REPO" "$WORK_DIR/gtk-theme"
git -C "$WORK_DIR/gtk-theme" checkout --quiet "$MACTAHOE_GTK_COMMIT"
# Reverted `-t all -b` after a real boot test on a 2012 MacBook Pro froze the desktop
# completely -- renders once, cursor moves, nothing else responds, permanently. Root cause not
# conclusively provable from this sandbox (headless testing can't reproduce real-GPU rendering
# bugs), but `-t all -b` was the single largest, most novel change between a working build and
# the frozen one, on hardware old enough that extra CSS variants + a blur render path are a
# real risk. It also turned out to be *unnecessary*: directly diffed a plain install against
# the `-t all -b` one -- identical titlebutton SVGs, identical 89 button-CSS references in
# gtk.css. Traffic lights were never missing because of a missing accent/blur variant; this
# project's own dconf theme names (MacTahoe-Light/MacTahoe-Dark, no color suffix) never
# referenced the extra variants `-t all` generates in the first place. The actual traffic-light
# fix is the `-l`/libadwaita seeding below, confirmed unrelated to this flag and independently
# tested against fresh accounts already.
"$WORK_DIR/gtk-theme/install.sh" -d /usr/share/themes

# The theme's own -l/--libadwaita flag (installs a GTK4 CSS override into ~/.config/gtk-4.0/,
# the standard mechanism libaswaita apps -- Files, Calendar, Text Editor, this project's own
# Settings app -- actually respect, unlike a legacy GTK theme name alone) refuses to run as
# root, and it seeds a single user's home, not something new accounts inherit automatically
# either way. Rather than re-run the generator during every provision (needs a non-root user
# context this script doesn't have mid-provision), assets/gtk4-libadwaita/ ships the exact,
# verified output of `install.sh -l` run once (confirmed byte-identical against this dev VM's
# own already-working ~/.config/gtk-4.0/, which is what this project's actual look has been
# running on) -- same pattern as assets/firefox-theme/ below. Seeded via /etc/skel like
# everything else here, RELATIVE symlinks only (the tool itself generates absolute ones tied
# to whatever $HOME it ran against, which would silently point at the wrong user's home once
# copied into skel and expanded for a different account -- confirmed this was actually the
# case on the dev VM's own copy before fixing it here).
echo "==> Installing GTK4/libadwaita theme override -> /etc/skel/.config/gtk-4.0"
mkdir -p /etc/skel/.config/gtk-4.0
rsync -a --delete "$REPO_DIR/assets/gtk4-libadwaita/" /etc/skel/.config/gtk-4.0/
ln -sf gtk-Dark.css /etc/skel/.config/gtk-4.0/gtk.css
ln -sf gtk-Dark.css /etc/skel/.config/gtk-4.0/gtk-dark.css
ln -sf gtk-Light.css /etc/skel/.config/gtk-4.0/gtk-light.css

echo "==> Installing MacTahoe icon theme system-wide -> /usr/share/icons"
git clone --quiet "$MACTAHOE_ICON_REPO" "$WORK_DIR/icon-theme"
git -C "$WORK_DIR/icon-theme" checkout --quiet "$MACTAHOE_ICON_COMMIT"
"$WORK_DIR/icon-theme/install.sh" -d /usr/share/icons

# Bluetooth device-type icons (peachos-bt-*) -- shown next to each device in the
# top-bar Bluetooth dropdown (macos-top-panel bluetoothIndicator.js) and the
# Settings app's Bluetooth page. Hand-drawn SF-Symbols-style set from
# macOS_Tahoe_SYSICONS; the SVGs are recoloured to currentColor at author time
# so the top bar's dark/light adaptive panel can tint them. They go into
# MacTahoe's OWN tree (not just hicolor) because MacTahoe's hicolor inheritance
# doesn't reliably surface a newly-created hicolor/scalable/devices dir --
# dropping them where MacTahoe already keeps device icons is what actually
# resolves for both St and GTK. deviceType() in bluetoothData.js picks which one;
# anything without a custom icon falls back to a themed -symbolic name.
echo "==> Installing Bluetooth device-type icons -> MacTahoe + hicolor"
# MacTahoe lays icon dirs out context-first (devices/scalable); hicolor is
# size-first (scalable/devices). Install into both so a non-MacTahoe theme
# still gets them via hicolor fallback.
for f in "$REPO_DIR"/assets/bluetooth-device-icons/*.svg; do
    [ -e "$f" ] || continue
    install -Dm644 "$f" "/usr/share/icons/MacTahoe/devices/scalable/$(basename "$f")"
    install -Dm644 "$f" "/usr/share/icons/hicolor/scalable/devices/$(basename "$f")"
done
for f in "$REPO_DIR"/assets/bluetooth-device-icons/*.png; do
    [ -e "$f" ] || continue
    install -Dm644 "$f" "/usr/share/icons/MacTahoe/devices/32/$(basename "$f")"
    install -Dm644 "$f" "/usr/share/icons/hicolor/64x64/devices/$(basename "$f")"
done
gtk-update-icon-cache -f -t /usr/share/icons/MacTahoe >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true

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
        # macos-top-panel's lib/*.js use raw `new Gio.Settings({schema_id})`, which resolves
        # ONLY against the global schema source, not the extension's own schemas/ dir (only
        # extension.js's this.getSettings() checks the local dir). Without the schemas also
        # in /usr/share/glib-2.0/schemas the extension throws "schema not found" on enable and
        # never loads -- no top bar. The Settings app's Menu Bar page reads the same schema
        # and crashes for the same reason. Install every extension schema globally too.
        install -d /usr/share/glib-2.0/schemas
        install -m644 "$dest"/schemas/*.gschema.xml /usr/share/glib-2.0/schemas/
    fi
done
glib-compile-schemas /usr/share/glib-2.0/schemas/

# Perfect Lock Screen needs more than the plain file copy the loop above just did: GDM
# only loads a login-screen extension once metadata.json lists 'gdm' in session-modes,
# a dconf drop-in exists telling the greeter to enable it, and its schema is symlinked
# into /usr/share/glib-2.0/schemas so the greeter process (which never reads
# /usr/share/gnome-shell/extensions/*/schemas itself) can see Cupertino-mode settings.
# install-gdm-dlc.sh (vendored alongside the extension, see its own README) does exactly
# that -- re-syncing the same target the loop above already wrote is intentional and
# idempotent, not wasted work. --no-restart: restarting GDM mid-provision would kill
# this very session.
echo "==> Wiring Perfect Lock Screen into the GDM login screen"
bash "$REPO_DIR/extensions/perfect-lockscreen@chris/scripts/install-gdm-dlc.sh" --no-restart

echo "==> Installing wallpapers -> /usr/share/backgrounds/peachos"
mkdir -p /usr/share/backgrounds/peachos
cp "$REPO_DIR"/assets/wallpapers/*.jpg "$REPO_DIR"/assets/wallpapers/*.png /usr/share/backgrounds/peachos/
mkdir -p /usr/share/backgrounds/peachos/presets
cp "$REPO_DIR"/assets/wallpapers/presets/*.jpg "$REPO_DIR"/assets/wallpapers/presets/*.png /usr/share/backgrounds/peachos/presets/

echo "==> Installing lock screen live wallpapers -> /usr/share/peachos/lockscreen"
mkdir -p /usr/share/peachos/lockscreen
cp "$REPO_DIR"/assets/lockscreen/*.mp4 /usr/share/peachos/lockscreen/

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

echo "==> Installing peachOS dconf defaults for the GDM greeter session"
# Not the standard /etc/dconf/db/gdm.d/ mechanism -- see provision/dconf/01-peachos-gdm's
# own header comment for why this Ubuntu build's GDM needs a different install path.
install -Dm644 "$REPO_DIR/provision/dconf/01-peachos-gdm" /usr/share/gdm/dconf/01-peachos-gdm
/usr/share/gdm/generate-config

echo "==> Done."
echo "peachOS defaults are now system-wide. Any NEW user account gets the"
echo "full look (theme, icons, wallpaper, dock, top bar, extensions) with"
echo "zero manual setup. Existing users keep their own overrides unless"
echo "those are reset (dconf reset -f / for the current user)."
