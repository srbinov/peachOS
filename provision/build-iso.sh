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
if [[ -f "$REPO_DIR/provision/dconf/01-peachos-gdm" ]]; then
    install -Dm644 "$REPO_DIR/provision/dconf/01-peachos-gdm" /usr/share/gdm/dconf/01-peachos-gdm
    [[ -x /usr/share/gdm/generate-config ]] && /usr/share/gdm/generate-config || true
fi
dconf update
echo "    /etc/dconf/db/local recompiled ($(date -r /etc/dconf/db/local '+%H:%M:%S'))"

# --- 4. drift checks ---------------------------------------------------
if [[ $SKIP_CHECKS -eq 0 ]]; then
    log "Checking installed trees against the repo"
    drift=0
    for ext in "$REPO_DIR"/extensions/*/; do
        name=$(basename "$ext")
        sys="/usr/share/gnome-shell/extensions/$name"
        [[ -d "$sys" ]] || { warn "extension not installed: $name"; drift=1; continue; }
        if ! diff -rq --exclude='gschemas.compiled' --exclude='.git' "$ext" "$sys" >/dev/null 2>&1; then
            warn "extension differs from repo: $name  (run provision.sh)"
            drift=1
        fi
    done
    for tree in "settings:/usr/lib/peachos/settings/src:apps/settings/src"; do
        IFS=: read -r label sys repo <<< "$tree"
        if [[ -d "$sys" ]] && ! diff -rq "$REPO_DIR/$repo" "$sys" >/dev/null 2>&1; then
            warn "$label app differs from repo (run provision.sh)"
            drift=1
        fi
    done
    if [[ $drift -eq 1 ]]; then
        warn "installed system is behind the repo. The ISO captures the SYSTEM, not the repo."
        warn "Re-run with --provision, or 'sudo provision/provision.sh', to sync first."
        read -r -p "Continue building from the current on-disk state anyway? [y/N] " ans
        [[ "$ans" == [yY] ]] || die "aborted -- sync the system first"
    else
        echo "    installed extensions + Settings app match the repo"
    fi
fi

# --- 5. blank machine-id --------------------------------------------------
# A shipped image must not carry a baked machine-id (every install would clone
# it until first boot). systemd regenerates /etc/machine-id early on the next
# boot of THIS host too -- harmless for a build box, but that's why it's noted.
log "Blanking /etc/machine-id (regenerates on next boot, here and on every install)"
: > /etc/machine-id
[[ -e /var/lib/dbus/machine-id && ! -L /var/lib/dbus/machine-id ]] && : > /var/lib/dbus/machine-id || true

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

log "ISO ready"
printf '  path   : %s\n' "$ISO"
printf '  size   : %s\n' "$(du -h "$ISO" | cut -f1)"
printf '  sha256 : '
sha256sum "$ISO" | cut -d' ' -f1
sha256sum "$ISO" > "$ISO.sha256"
echo
echo "Boot-test it (software GPU, proves it's not tied to this machine's nvidia):"
echo "  qemu-system-x86_64 -enable-kvm -m 4096 -smp 2 -cdrom '$ISO' -boot d -vga virtio"
