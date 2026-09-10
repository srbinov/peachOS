#!/usr/bin/env bash
# Live/demo boot only: the peachOS ISO has no "try it first" desktop -- it boots
# straight into the installer.
#
#   peachos-start-installer          (autostart) waits for the session, then
#                                    runs Calamares in a loop so the live
#                                    desktop is never what the user sees;
#                                    gives up after a few quick failures and
#                                    hands back a usable desktop.
#   peachos-start-installer --once   one Calamares launch, for the "Install
#                                    peachOS" desktop icon.
#
# boot=live is live-boot's own kernel cmdline flag, set by penguins-eggs'
# generated boot menus and absent once installed to disk -- so this is a
# guaranteed no-op on a real system, same guard as peachos-disable-live-lock.
set -u

grep -qw 'boot=live' /proc/cmdline 2>/dev/null || exit 0

ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

# Live/installer boot: no "try peachOS" desktop. Before anything else, tear the
# desktop down to a black field -- every shell extension off (top bar, dock,
# widgets), solid-black background, no banners, no animations. The user should
# only ever see black, then the fullscreen installer. `gsettings reset` in
# restore_desktop() puts it all back (to the peachOS system defaults) if the
# installer can't start and we hand a desktop back.
blank_desktop() {
    gsettings set org.gnome.shell disable-user-extensions true
    gsettings set org.gnome.desktop.background picture-uri ''
    gsettings set org.gnome.desktop.background picture-uri-dark ''
    gsettings set org.gnome.desktop.background primary-color '#000000'
    gsettings set org.gnome.desktop.background secondary-color '#000000'
    gsettings set org.gnome.desktop.background color-shading-type 'solid'
    gsettings set org.gnome.desktop.screensaver picture-uri ''
    gsettings set org.gnome.desktop.screensaver primary-color '#000000'
    gsettings set org.gnome.desktop.interface enable-animations false
    gsettings set org.gnome.desktop.notifications show-banners false
} 2>/dev/null

restore_desktop() {
    for k in org.gnome.shell:disable-user-extensions \
             org.gnome.desktop.background:picture-uri \
             org.gnome.desktop.background:picture-uri-dark \
             org.gnome.desktop.background:primary-color \
             org.gnome.desktop.background:secondary-color \
             org.gnome.desktop.background:color-shading-type \
             org.gnome.desktop.screensaver:picture-uri \
             org.gnome.desktop.screensaver:primary-color \
             org.gnome.desktop.interface:enable-animations \
             org.gnome.desktop.notifications:show-banners; do
        gsettings reset "${k%%:*}" "${k##*:}"
    done
} 2>/dev/null

# Launch Calamares directly (not `eggs sysinstall`, which regenerates its own
# generic config under /etc/penguins-eggs.d/installer.d and ignores peachOS's
# hand-built /etc/calamares -- branding, module sequence). The
# eggs live-boot mounts the squashfs where our unpackfs.conf expects it
# (/run/live/medium/live/filesystem.squashfs), so /etc/calamares is complete
# on its own.
#
# It has to run as root, and the live session is GNOME/Wayland (Ubuntu 26.04
# ships no Xorg session). pkexec scrubs the environment, so re-export the
# display bits through `env` -- pkexec is still prompt-free via
# 49-peachos-live.rules (user "live" -> YES for every action). qt6-wayland
# isn't installed, so Qt uses xcb; xhost + the XAUTHORITY below let the root
# process reach the user's Xwayland (and starting xhost brings Xwayland up).
_uid=$(id -u)
: "${XDG_RUNTIME_DIR:=/run/user/$_uid}"
: "${WAYLAND_DISPLAY:=wayland-0}"

xhost +SI:localuser:root >/dev/null 2>&1 || true

run_installer() {
    pkexec env \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
        DISPLAY="${DISPLAY:-:0}" \
        XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}" \
        QT_QPA_PLATFORM="xcb;wayland" \
        calamares
}

if [ "$ONCE" -eq 1 ]; then
    run_installer
    exit $?
fi

# Black everything out immediately -- do this before waiting on the shell so the
# peachOS desktop is never what boots up, just a black screen then the installer.
blank_desktop

# Wait for the shell to finish coming up before launching over it.
for _i in $(seq 1 30); do
    gdbus introspect --session --dest org.gnome.Shell \
        --object-path /org/gnome/Shell >/dev/null 2>&1 && break
    sleep 1
done
sleep 2

fails=0
while true; do
    # Bail if the machine is on its way down (Calamares' finished page reboots).
    [ "$(systemctl is-system-running 2>/dev/null)" = stopping ] && exit 0

    start=$(date +%s)
    run_installer || true
    # eggs blocks until Calamares quits; wait it out if that ever changes.
    while pgrep -x calamares >/dev/null 2>&1; do sleep 2; done

    # A run under ~10s means it never actually opened (denied / crashed).
    if [ $(( $(date +%s) - start )) -lt 10 ]; then
        fails=$(( fails + 1 ))
        [ "$fails" -ge 4 ] && break
    else
        fails=0
    fi
    sleep 3
done

# Installer wouldn't start -- hand back a usable peachOS desktop.
restore_desktop
