#!/usr/bin/env bash
# ============================================================================
# build-iso.sh  --  turn this provisioned peachOS host into a bootable ISO
# ============================================================================
# Pipeline:  clean Ubuntu 26.04
#              -> sudo provision/provision.sh          (install everything)
#              -> sudo provision/penguins-eggs/install-eggs.sh   (once)
#              -> sudo provision/build-iso.sh          (this script)
#
# This script:
#   1. checks the host is a provisioned peachOS box with eggs available
#   2. re-bakes the dconf system defaults from the repo (so a freshly
#      installed account matches the tree, not whatever drifted on disk)
#   3. warns if the installed extension / app trees have drifted from the repo
#   4. blanks machine-id so every install from the ISO generates its own
#   5. runs `eggs remaster --debug` and sanity-checks the plan
#   6. runs `eggs remaster` for real
#   7. prints the ISO path, size and sha256
#
# Flags:
#   --provision   re-run provision.sh first (the gold-standard sync; slow --
#                 rebuilds Sidra / iCloud apps / re-clones themes)
#   --skip-checks skip the drift checks (step 3)
#   --plan-only   stop after step 5 (print the plan, don't build)
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EGGS_WORK="/home/eggs"

DO_PROVISION=0
SKIP_CHECKS=0
PLAN_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --provision)   DO_PROVISION=1 ;;
        --skip-checks) SKIP_CHECKS=1 ;;
        --plan-only)   PLAN_ONLY=1 ;;
        *) echo "unknown flag: $arg" >&2; exit 1 ;;
    esac
done

log() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[fatal]\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. preconditions -----------------------------------------------------
[[ $EUID -eq 0 ]] || die "run as root (sudo)"

. /etc/os-release
[[ "${ID:-}" == "peachos" ]] || die "/etc/os-release ID is '${ID:-}', not 'peachos' -- provision.sh hasn't run"
[[ -d /usr/lib/peachos ]] || die "/usr/lib/peachos missing -- provision.sh hasn't run"
command -v eggs >/dev/null || command -v coa >/dev/null || die "eggs not installed -- run provision/penguins-eggs/install-eggs.sh"
EGGS=$(command -v eggs || command -v coa)

[[ -f /etc/penguins-eggs.d/custom.exclude.list ]] || die "eggs custom config missing -- rerun install-eggs.sh"
if grep -qE '^\s*(snap/|var/snap/|var/lib/snapd/)\s*$' /etc/penguins-eggs.d/custom.exclude.list; then
    die "custom.exclude.list still excludes snaps -- the ISO would ship with no Firefox. Reinstall peachOS's copy."
fi
if ! grep -q 'peachOS snap skeleton' /etc/penguins-eggs.d/scripts/bootstrap-liveroot.sh 2>/dev/null; then
    die "bootstrap-liveroot.sh isn't patched for the /snap skeleton -- rerun provision/penguins-eggs/install-eggs.sh (snaps would be unlaunchable in the ISO)"
fi

# --- 2. optional full re-provision --------------------------------------
if [[ $DO_PROVISION -eq 1 ]]; then
    log "Re-running provision.sh (--provision)"
    "$REPO_DIR/provision/provision.sh"
fi

# --- 3. re-bake dconf defaults from the repo ---------------------------
# eggs squashes /etc/dconf/db/local (the compiled system db). A fresh install
# account reads its whole look from there, so it must reflect the repo's
# 01-peachos, not a stale compile.
log "Baking dconf system defaults from the repo"
install -Dm644 "$REPO_DIR/provision/dconf/01-peachos" /etc/dconf/db/local.d/01-peachos
mkdir -p /etc/dconf/db/local.d/locks
rsync -a --delete "$REPO_DIR/provision/dconf/locks/" /etc/dconf/db/local.d/locks/
if [[ -f "$REPO_DIR/provision/dconf/01-peachos-gdm" ]]; then
    install -Dm644 "$REPO_DIR/provision/dconf/01-peachos-gdm" /usr/share/gdm/dconf/01-peachos-gdm
    [[ -x /usr/share/gdm/generate-config ]] && /usr/share/gdm/generate-config || true
fi
dconf update
echo "    /etc/dconf/db/local recompiled ($(date -r /etc/dconf/db/local '+%H:%M:%S'))"

# --- 4. sync the fast-moving trees from the repo ----------------------
# The ISO captures the SYSTEM, not the repo. The heavy, slow parts of
# provision.sh (Sidra/iCloud builds, theme clones, apt/snap) rarely change and
# --provision covers them; but the extensions, the Settings app, and their
# schemas change every session, so replicate provision.sh's install for JUST
# those here so a plain `build-iso.sh` ships current code. MUST stay in step
# with provision.sh's "Installing GNOME Shell extensions" loop -- particularly
# the schema compile: a bare `rsync --delete` would drop gschemas.compiled and
# every extension that reads its schema would fail to enable (no top bar, no
# dock). Skipped by --skip-checks (assumes you synced by hand) and redundant
# after --provision.
if [[ $SKIP_CHECKS -eq 0 && $DO_PROVISION -eq 0 ]]; then
    log "Syncing extensions + Settings app from the repo (schemas included)"
    mkdir -p /usr/share/gnome-shell/extensions /usr/share/glib-2.0/schemas
    for ext_dir in "$REPO_DIR"/extensions/*/; do
        uuid=$(basename "$ext_dir")
        dest="/usr/share/gnome-shell/extensions/$uuid"
        rsync -a --delete --exclude='.git' "$ext_dir" "$dest/"
        if [[ -d "$dest/schemas" ]]; then
            glib-compile-schemas "$dest/schemas/" 2>/dev/null || true
            install -m644 "$dest"/schemas/*.gschema.xml /usr/share/glib-2.0/schemas/ 2>/dev/null || true
        fi
    done
    glib-compile-schemas /usr/share/glib-2.0/schemas/ 2>/dev/null || true
    rsync -a --delete "$REPO_DIR/apps/settings/src/" /usr/lib/peachos/settings/src/
    rsync -a --delete "$REPO_DIR/apps/settings/data/" /usr/lib/peachos/settings/data/
    # Bluetooth device-type icons (see provision.sh -- same targets)
    for f in "$REPO_DIR"/assets/bluetooth-device-icons/*.svg; do
        [[ -e "$f" ]] || continue
        install -Dm644 "$f" "/usr/share/icons/MacTahoe/devices/scalable/$(basename "$f")"
        install -Dm644 "$f" "/usr/share/icons/hicolor/scalable/devices/$(basename "$f")"
    done
    for f in "$REPO_DIR"/assets/bluetooth-device-icons/*.png; do
        [[ -e "$f" ]] || continue
        install -Dm644 "$f" "/usr/share/icons/MacTahoe/devices/32/$(basename "$f")"
        install -Dm644 "$f" "/usr/share/icons/hicolor/64x64/devices/$(basename "$f")"
    done
    gtk-update-icon-cache -f -t /usr/share/icons/MacTahoe >/dev/null 2>&1 || true
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
    echo "    extensions + Settings app now match the repo"
fi

# --- 5. blank machine-id --------------------------------------------------
# A shipped image must not carry a baked machine-id (every install would clone
# it until first boot). systemd regenerates /etc/machine-id early on the next
# boot of THIS host too -- harmless for a build box, but that's why it's noted.
log "Blanking /etc/machine-id (regenerates on next boot, here and on every install)"
: > /etc/machine-id
[[ -e /var/lib/dbus/machine-id && ! -L /var/lib/dbus/machine-id ]] && : > /var/lib/dbus/machine-id || true

# --- 5b. neutralise the build host's hostname ---------------------------
# eggs `cp -a /etc` into the liveroot, and its sanitize step only sets a
# hostname when the file is ABSENT -- so without this the live session and
# every install off the ISO would be called after this MacBook. Set a generic
# one for the build, restore the host's own afterwards. Calamares still lets
# the installing user pick their own.
ORIG_HOSTNAME="$(hostname)"
restore_hostname() {
    [[ -n "$ORIG_HOSTNAME" && "$ORIG_HOSTNAME" != "peachos" ]] || return 0
    hostname "$ORIG_HOSTNAME" 2>/dev/null || true
    echo "$ORIG_HOSTNAME" > /etc/hostname
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$ORIG_HOSTNAME/" /etc/hosts 2>/dev/null || true
}
trap restore_hostname EXIT
if [[ "$ORIG_HOSTNAME" != "peachos" ]]; then
    log "Setting hostname 'peachos' for the build (restored to '$ORIG_HOSTNAME' after)"
    # transient too -- eggs derives the ISO volume id / .disk/info from the
    # RUNNING kernel hostname, not just the file.
    hostname peachos 2>/dev/null || true
    echo "peachos" > /etc/hostname
    if grep -qE '^127\.0\.1\.1' /etc/hosts; then
        sed -i "s/^127\.0\.1\.1.*/127.0.1.1\tpeachos/" /etc/hosts
    else
        printf '127.0.1.1\tpeachos\n' >> /etc/hosts
    fi
fi

# --- 6. space + scratch -------------------------------------------------
avail_kb=$(df --output=avail /home | tail -1)
if (( avail_kb < 25 * 1024 * 1024 )); then
    warn "only $((avail_kb/1024/1024)) GiB free on /home; eggs needs ~2x the ISO size"
fi
if [[ -d "$EGGS_WORK" ]]; then
    log "Clearing previous eggs scratch ($EGGS_WORK)"
    "$EGGS" destroy 2>/dev/null || true
    rm -rf "$EGGS_WORK"
fi

# --- 7. plan (debug) ---------------------------------------------------
log "Generating the remaster plan ($EGGS remaster --debug)"
PLAN="$(mktemp)"
"$EGGS" remaster --debug | tee "$PLAN" | \
    grep -iE 'squashfs|filesystem|calamares|exclude|compression|install-system' || true
echo
if grep -qi 'filesystem.squashfs' "$PLAN"; then
    echo "    squashfs target looks right"
else
    warn "no filesystem.squashfs step seen in the plan -- inspect $PLAN before trusting the build"
fi
rm -f "$PLAN"

if [[ $PLAN_ONLY -eq 1 ]]; then
    log "--plan-only: stopping before the build"
    exit 0
fi

# --- 8. build --------------------------------------------------------
log "Building the ISO ($EGGS remaster) -- this takes a while, no further output until done"
"$EGGS" remaster

# --- 9. report ------------------------------------------------------
ISO=$(find "$EGGS_WORK" -maxdepth 2 -name '*.iso' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)
[[ -n "$ISO" && -f "$ISO" ]] || die "build finished but no .iso found under $EGGS_WORK"

# eggs names the file egg-of-<id>-<codename>-<host>-<arch>-<date>.iso. Give the
# distributable a clean name (the volume id inside still reflects eggs' scheme).
CLEAN="$(dirname "$ISO")/peachos-${VERSION_CODENAME:-nectar}-amd64-$(date +%Y%m%d).iso"
if [[ "$ISO" != "$CLEAN" ]]; then
    mv -f "$ISO" "$CLEAN"
    [[ -f "$ISO.md5" ]] && mv -f "$ISO.md5" "$CLEAN.md5"
    [[ -f "$ISO.sha256" ]] && mv -f "$ISO.sha256" "$CLEAN.sha256"
    ISO="$CLEAN"
fi

log "ISO ready"
printf '  path   : %s\n' "$ISO"
printf '  size   : %s\n' "$(du -h "$ISO" | cut -f1)"
printf '  sha256 : '
sha256sum "$ISO" | cut -d' ' -f1
sha256sum "$ISO" > "$ISO.sha256"
echo
echo "Boot-test it (software GPU, proves it's not tied to this machine's nvidia):"
echo "  qemu-system-x86_64 -enable-kvm -m 4096 -smp 2 -cdrom '$ISO' -boot d -vga virtio"
