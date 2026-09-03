#!/usr/bin/env bash
# ============================================================================
# install-eggs.sh  --  set up penguins-eggs on a peachOS BUILD host
# ============================================================================
# penguins-eggs is only needed on the machine that produces the ISO, not on
# every peachOS install, so it lives here rather than in provision.sh. Run it
# once on the build host (provision.sh must have run first); build-iso.sh then
# drives the actual remaster.
#
# What it does:
#   1. installs the pinned penguins-eggs .deb + its apt dependencies
#   2. creates /usr/bin/eggs (the .deb ships `coa`/`oa` but no `eggs` link)
#   3. drops peachOS's custom.exclude.list + custom.yaml over the stock ones
#      (the stock exclude list strips every snap out of the ISO -- peachOS
#       ships Firefox and others AS snaps, see that file's header)
#   4. re-applies the eggs boot/installer rebranding that provision.sh only
#      does when /etc/penguins-eggs.d already exists
#
# Source of the .deb: the per-distro zip attached to the penguins-eggs GitHub
# release. Pinned by version + sha256 so a build is reproducible. Override the
# download with:  install-eggs.sh /path/to/penguins-eggs_<ver>_amd64.deb
# ============================================================================
set -euo pipefail

EGGS_VERSION="26.8.29"
EGGS_DEB="penguins-eggs_${EGGS_VERSION}-1_amd64.deb"
EGGS_ZIP_URL="https://github.com/pieroproietti/penguins-eggs/releases/download/v${EGGS_VERSION}/penguins-eggs-debian.zip"
EGGS_DEB_SHA256="d63ef2319b9ef64bf738603a3d4611e474babcd6f2b3ec5c2afa808218826887"
EGGS_ZIP_SHA256="306a810855f23b47426d867ec24ccaaf53166865ae45faa56422729676f275ed"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "install-eggs.sh must run as root (sudo)." >&2
    exit 1
fi

if [[ ! -d /usr/lib/peachos ]]; then
    echo "This host doesn't look provisioned (/usr/lib/peachos missing)." >&2
    echo "Run 'sudo provision/provision.sh' first." >&2
    exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# --- 1. obtain the .deb -----------------------------------------------------
DEB_PATH="${1:-}"
if [[ -n "$DEB_PATH" ]]; then
    echo "==> Using supplied package: $DEB_PATH"
    [[ -f "$DEB_PATH" ]] || { echo "no such file: $DEB_PATH" >&2; exit 1; }
else
    echo "==> Downloading penguins-eggs $EGGS_VERSION"
    curl -fsSL -o "$WORK_DIR/eggs.zip" "$EGGS_ZIP_URL"
    echo "$EGGS_ZIP_SHA256  $WORK_DIR/eggs.zip" | sha256sum -c - \
        || { echo "eggs zip checksum mismatch -- refusing to continue" >&2; exit 1; }
    ( cd "$WORK_DIR" && bsdtar -xf eggs.zip 2>/dev/null || unzip -q eggs.zip )
    DEB_PATH="$WORK_DIR/$EGGS_DEB"
    [[ -f "$DEB_PATH" ]] || { echo "expected $EGGS_DEB inside the zip, not found" >&2; exit 1; }
fi
echo "$EGGS_DEB_SHA256  $DEB_PATH" | sha256sum -c - \
    || { echo "eggs .deb checksum mismatch -- refusing to install" >&2; exit 1; }

# --- 2. install it + dependencies -----------------------------------------
echo "==> Installing penguins-eggs and dependencies"
apt-get update
# apt resolves the Depends: line (live-boot, mtools, grub-pc-bin, yq, ...).
apt-get install -y "$DEB_PATH"

# The .deb ships /usr/bin/coa (the "eggs" CLI) and /usr/bin/oa (the plan
# runner) but no `eggs` entry point, though every man page and the shell
# completions call it `eggs`. Bridge that.
if [[ ! -e /usr/bin/eggs ]]; then
    ln -s coa /usr/bin/eggs
    echo "    linked /usr/bin/eggs -> coa"
fi

# --- 3. peachOS config over the stock files -------------------------------
echo "==> Installing peachOS eggs config (exclude list keeps snaps IN)"
install -Dm644 "$REPO_DIR/provision/penguins-eggs/custom.exclude.list" \
    /etc/penguins-eggs.d/custom.exclude.list
install -Dm644 "$REPO_DIR/provision/penguins-eggs/custom.yaml" \
    /etc/penguins-eggs.d/custom.yaml

# --- 4. rebrand eggs' boot + installer assets ----------------------------
# Mirror of the guarded block in provision.sh -- safe to run again there.
echo "==> Rebranding penguins-eggs boot/install assets -> peachOS"
install -Dm644 "$REPO_DIR/assets/boot/grub-splash.png" \
    /etc/penguins-eggs.d/brain.d/assets/splash.png
install -Dm755 "$REPO_DIR/provision/penguins-eggs/trust-desktop.sh" \
    /etc/penguins-eggs.d/scripts/trust-desktop.sh
install -Dm644 "$REPO_DIR/assets/logos/PeachICON_BLACK.svg" \
    /usr/share/icons/peachos/install-peachos.svg

# --- 5. sanity check -----------------------------------------------------
echo "==> penguins-eggs installed:"
eggs version || coa version || true
echo
echo "Next: sudo provision/build-iso.sh"
