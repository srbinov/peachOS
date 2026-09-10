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

# The live session is GNOME/Wayland (Ubuntu 26.04 ships no Xorg session), and
# Calamares runs as root. pkexec scrubs the environment, so a bare
# `pkexec eggs sysinstall calamares` leaves Calamares (Qt) with no display at
# all ("qt.qpa.xcb: could not connect to display"). Re-export the Wayland bits
# through `env` -- pkexec is still authorised without a prompt by
# 49-peachos-live.rules (user "live" -> YES for every action) -- and let Qt
# fall back to xcb/Xwayland if the wayland plugin can't bind.
_uid=$(id -u)
: "${XDG_RUNTIME_DIR:=/run/user/$_uid}"
: "${WAYLAND_DISPLAY:=wayland-0}"

# Let root reach the user's X/Xwayland too, in case Qt uses the xcb fallback
# (also starts Xwayland-on-demand so DISPLAY is live). Harmless if xhost or
# Xwayland is missing.
xhost +SI:localuser:root >/dev/null 2>&1 || true

run_installer() {
    pkexec env \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
        DISPLAY="${DISPLAY:-:0}" \
        XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}" \
        QT_QPA_PLATFORM="wayland;xcb" \
        eggs sysinstall calamares
}

if [ "$ONCE" -eq 1 ]; then
    run_installer
    exit $?
fi

# Wait for the shell to finish coming up before launching over it.
for _i in $(seq 1 30); do
    gdbus introspect --session --dest org.gnome.Shell \
        --object-path /org/gnome/Shell >/dev/null 2>&1 && break
    sleep 1
done
sleep 2

# Nothing should pop over a running install.
gsettings set org.gnome.desktop.notifications show-banners false 2>/dev/null || true

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

# Installer wouldn't start -- hand back a usable desktop.
gsettings set org.gnome.desktop.notifications show-banners true 2>/dev/null || true
