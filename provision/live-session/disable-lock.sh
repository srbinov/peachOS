#!/bin/bash
# Live/demo boot only: the "live" account's password is an undocumented penguins-eggs default
# (custom.yaml's own commented-out example -- "evolution" -- is never shown to the person
# actually trying peachOS). Stock GNOME screensaver/idle defaults are untouched anywhere in
# peachOS's dconf profile (checked: 01-peachos has no screensaver/session keys at all), so an
# unmodified live session idles into a lock screen nobody can get back out of. Real installs
# must keep their normal lock-screen security -- this only ever acts during a live/demo boot,
# detected via live-boot's own boot=live kernel cmdline parameter (set by penguins-eggs'
# generated boot menus, not something peachOS invents), so it's a guaranteed no-op once
# installed to disk.
#
# Shipped via /etc/skel/.config/autostart/ (see provision.sh), so it reaches both the live
# user (penguins-eggs' create-live-home copies /etc/skel/. verbatim) and any account a real
# install creates (Calamares' users module -- useradd -m -- does the same) -- the boot=live
# guard is what actually keeps its effect live-only, not where the file lives.
if grep -qw 'boot=live' /proc/cmdline 2>/dev/null; then
    gsettings set org.gnome.desktop.screensaver lock-enabled false
    gsettings set org.gnome.desktop.screensaver idle-activation-enabled false
    gsettings set org.gnome.desktop.session idle-delay 0
fi
