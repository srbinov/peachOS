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

sed -i \
    -e 's/^Name=Files$/Name=Peachy/' \
    -e 's/^Icon=org.gnome.Nautilus$/Icon=\/usr\/share\/icons\/peachos\/peachy.svg/' \
    /usr/share/applications/org.gnome.Nautilus.desktop

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
