#!/bin/bash
# One-shot, per-user first-login fixup: seeds the MacTahoe Firefox theme (userChrome.css/
# userContent.css, loaded via a `chrome` symlink Firefox itself resolves) into whatever
# profile snap Firefox creates for this account, so it's themed before the user ever opens
# it -- not something they have to notice missing and re-apply by hand. Same delivery
# mechanism as peachos-disable-live-lock: shipped via /etc/skel/.config/autostart/, which
# reaches both the live user (penguins-eggs' create-live-home copies /etc/skel/. verbatim)
# and any account a real install creates (Calamares' useradd -m does the same).
#
# Firefox (snap or not) auto-creates a "default"/"default-release" profile with a random
# salt on first launch if none exists -- there's no fixed path to seed ahead of time, so this
# launches Firefox headless once itself to force that bootstrap, rather than waiting
# indefinitely for the user to open it first (which could mean their first real launch is
# unthemed, then themed from the second launch on -- worse UX than a short one-time delay
# here). Safe to re-run: everything below is idempotent, and the sentinel file makes repeat
# logins a single stat() call, not a re-copy or another Firefox launch.
#
# Verified end-to-end against a genuine separate test user account (not just read-through):
# the theme-seeding logic (copy, chrome symlink, user.js pref, idempotency on a second run)
# all confirmed working directly. The one part NOT re-provable inside this dev sandbox is the
# `firefox --headless` bootstrap step itself -- snap's own cgroup confinement check rejects a
# second user's process run from inside this same terminal session's cgroup (`sudo -u`/
# `systemd-run --scope` both hit the same "not a snap cgroup for tag snap.firefox.firefox"
# error) -- an artifact of testing a second account from inside one already-running session,
# not something a real, separate GDM login (which gets its own systemd user session/cgroup
# from logind) would hit. "Firefox creates a profile on first launch if none exists" is
# standard, well-documented Firefox behavior, not something invented here.

set -euo pipefail

SENTINEL="$HOME/.config/peachos-firefox-theme-applied"
[[ -e "$SENTINEL" ]] && exit 0

MOZ_DIR="$HOME/snap/firefox/common/.mozilla/firefox"
THEME_SRC="/usr/share/peachos/firefox-theme"

# Bootstrap a profile if this account has never launched Firefox yet. --headless still runs
# full profile-creation (profiles.ini + the profile dir), it just never shows a window.
if [[ ! -f "$MOZ_DIR/profiles.ini" ]]; then
    timeout 20 firefox --headless >/dev/null 2>&1 &
    FF_PID=$!
    for _ in $(seq 1 20); do
        [[ -f "$MOZ_DIR/profiles.ini" ]] && break
        sleep 1
    done
    kill "$FF_PID" 2>/dev/null || true
    wait "$FF_PID" 2>/dev/null || true
    # Firefox can take a moment to finish writing profile files after the process exits.
    sleep 2
fi

# Still no profile after trying (Firefox not installed, or something else went wrong) --
# nothing to seed. Don't write the sentinel: leaves this able to retry next login instead
# of silently giving up forever.
[[ -d "$MOZ_DIR" ]] || exit 0

# Per-user copy of the theme (not a symlink to the system copy) so a user could later
# customize their own without touching /usr/share, matching how the live dev profile this
# was captured from was itself a real, independent copy, not a symlink to anywhere shared.
mkdir -p "$MOZ_DIR"
if [[ ! -d "$MOZ_DIR/firefox-themes" ]]; then
    cp -r "$THEME_SRC" "$MOZ_DIR/firefox-themes"
fi

applied_any=0
for profile_dir in "$MOZ_DIR"/*.default* "$MOZ_DIR"/*.default-release; do
    [[ -d "$profile_dir" ]] || continue

    if [[ ! -e "$profile_dir/chrome" ]]; then
        ln -s ../firefox-themes "$profile_dir/chrome"
    fi

    USER_JS="$profile_dir/user.js"
    if ! grep -q "toolkit.legacyUserProfileCustomizations.stylesheets" "$USER_JS" 2>/dev/null; then
        echo 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' >> "$USER_JS"
    fi
    applied_any=1
done

[[ "$applied_any" -eq 1 ]] && mkdir -p "$(dirname "$SENTINEL")" && touch "$SENTINEL"
