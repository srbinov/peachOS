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

# Settings app (apps/settings) runtime dep: gir1.2-goa-1.0 gives the Internet Accounts tab
# real GNOME Online Accounts bindings -- gnome-online-accounts itself (the goa-daemon and
# its D-Bus service) ships by default, but its GObject-Introspection typelib is a separate
# package that doesn't get pulled in automatically.
echo "==> Installing Settings app (Internet Accounts) runtime dependencies"
apt-get install -y --no-install-recommends gir1.2-goa-1.0

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
install -Dm755 "$REPO_DIR/apps/iconmasker/peachos-icon-watcherd" /usr/lib/peachos/iconmasker/peachos-icon-watcherd
install -d /usr/share/icons/peachos-auto
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos-icon-watcherd.service" /etc/systemd/system/peachos-icon-watcherd.service
systemctl enable peachos-icon-watcherd.service

# Dark icon-appearance mode: a *separate* pass from the watcher daemon above, triggered
# on-demand (from the Settings app's Appearance tab) rather than run automatically -- it
# recolors whatever icon the watcher already settled on into a dark variant, it doesn't
# decide icon shape/backdrop itself. Runs entirely unprivileged: it only ever writes XDG
# overrides under the invoking user's own ~/.local/share, never system-wide, so no polkit
# policy/pkexec is needed -- icon appearance is a personal preference, not a system policy,
# and system-wide writes here were also what caused two real bugs (fighting the watcher
# daemon over the same files, and GNOME Shell's own app-picker-layout state getting
# corrupted by the resulting burst of changes).
echo "==> Installing peachOS icon appearance (dark/clear mode) tool -> /usr/lib/peachos/iconmasker"
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_dark.py" /usr/lib/peachos/iconmasker/peachos_icon_dark.py
install -Dm644 "$REPO_DIR/apps/iconmasker/peachos_icon_clear.py" /usr/lib/peachos/iconmasker/peachos_icon_clear.py
install -Dm755 "$REPO_DIR/apps/iconmasker/peachos-icon-appearance" /usr/lib/peachos/iconmasker/peachos-icon-appearance
install -Dm644 "$REPO_DIR/apps/settings/data/schemas/org.peachos.appearance.gschema.xml" /usr/share/glib-2.0/schemas/org.peachos.appearance.gschema.xml
glib-compile-schemas /usr/share/glib-2.0/schemas/

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
apt-get install -y --no-install-recommends calamares calamares-settings-ubuntu-common
install -d /etc/calamares/branding/peachos
install -Dm644 "$REPO_DIR/provision/calamares/settings.conf" /etc/calamares/settings.conf
for f in "$REPO_DIR"/provision/calamares/modules/*.conf; do
    install -Dm644 "$f" "/etc/calamares/modules/$(basename "$f")"
done
for f in "$REPO_DIR"/provision/calamares/branding/peachos/*; do
    install -Dm644 "$f" "/etc/calamares/branding/peachos/$(basename "$f")"
done

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
apt-get install -y --no-install-recommends cmake g++ pkg-config libgtk-3-dev libwebkit2gtk-4.1-dev

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

echo "==> Installing iCloud app icons -> /usr/share/icons/icloud-for-linux"
for icon in mail contacts calendar photos drive notes reminders pages numbers keynote find maps tv; do
    install -Dm644 "$WORK_DIR/icloud-for-linux/snap/gui/${icon}.svg" \
        "/usr/share/icons/icloud-for-linux/${icon}.svg"
done

echo "==> Installing iCloud app desktop entries -> /usr/share/applications"
install_icloud_desktop() {
    local slug="$1" exec_cmd="$2" name="$3"
    cat > "/usr/share/applications/icloud-for-linux_${slug}.desktop" <<EOF
[Desktop Entry]
Name=${name}
GenericName=${name}
Comment=${name}
Type=Application
Categories=Office
Icon=/usr/share/icons/icloud-for-linux/${slug}.svg
Exec=${exec_cmd}
StartupWMClass=icloud-for-linux.${slug}
Terminal=false
EOF
}
install_icloud_desktop mail      "/usr/bin/icloud-for-linux mail Mail"           "iCloud Mail"
install_icloud_desktop contacts  "/usr/bin/icloud-for-linux contacts Contacts"   "iCloud Contacts"
install_icloud_desktop calendar  "/usr/bin/icloud-for-linux calendar Calendar"   "iCloud Calendar"
install_icloud_desktop photos    "/usr/bin/icloud-for-linux photos Photos"       "iCloud Photos"
install_icloud_desktop drive     "/usr/bin/icloud-for-linux iclouddrive Drive"   "iCloud Drive"
install_icloud_desktop notes     "/usr/bin/icloud-for-linux notes Notes"         "iCloud Notes"
install_icloud_desktop reminders "/usr/bin/icloud-for-linux reminders Reminders" "iCloud Reminders"
install_icloud_desktop pages     "/usr/bin/icloud-for-linux pages Pages"         "iCloud Pages"
install_icloud_desktop numbers   "/usr/bin/icloud-for-linux numbers Numbers"     "iCloud Numbers"
install_icloud_desktop keynote   "/usr/bin/icloud-for-linux keynote Keynote"     "iCloud Keynote"
install_icloud_desktop find      "/usr/bin/icloud-for-linux find Find"           "iCloud Find"
install_icloud_desktop maps      "/usr/bin/apple-maps"                           "Apple Maps"
install_icloud_desktop tv        "/usr/bin/apple-tv"                             "Apple TV"
update-desktop-database /usr/share/applications

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

# BlueBubbles (snap store, jojejo's official build -- not the peachOS-native BlueBubbles
# client experiment, which was scrapped): same snap-desktop-override situation as Firefox
# above, just no rename this time, only the icon. Curated art (assets/app-icons/messages.svg
# + darkmode/messages.svg, a real macOS Messages-style bubble) replaces the snap's own bare
# glyph -- see peachos_icon_resolve.py's CURATED_DARK_SLUGS for the light/dark swap.
install -Dm644 "$REPO_DIR/assets/app-icons/messages.svg" /usr/share/icons/peachos/messages.svg
cat > /usr/share/applications/bluebubbles_bluebubbles.desktop <<'EOF'
[Desktop Entry]
X-SnapInstanceName=bluebubbles
Version=1.0
Name=BlueBubbles
Comment=BlueBubbles client for Linux
X-SnapAppName=bluebubbles
Exec=/snap/bin/bluebubbles
Icon=/usr/share/icons/peachos/messages.svg
Terminal=false
Type=Application
Categories=Network;InstantMessaging;Chat;
StartupWMClass=Bluebubbles
EOF

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
