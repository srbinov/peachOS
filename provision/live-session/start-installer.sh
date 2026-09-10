#!/usr/bin/env bash
# Live/demo boot only: the peachOS ISO has no "try it first" desktop -- it boots
# straight into the installer. This autostart brings Calamares up (fullscreen,
# per the branding's windowExpanding) as soon as the session is ready and
# relaunches it if it's closed, so the live desktop is never what the user is
# looking at. If the installer genuinely can't start (polkit / eggs broken) it
# gives up after a few quick failures and leaves the desktop usable with the
# "Install peachOS" icon rather than bricking the ISO.
#
# boot=live is live-boot's own kernel cmdline flag, set by penguins-eggs'
# generated boot menus and absent once installed to disk -- so this is a
# guaranteed no-op on a real system, same guard as peachos-disable-live-lock.
set -u

grep -qw 'boot=live' /proc/cmdline 2>/dev/null || exit 0

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
    # Force the Calamares GUI -- a bare `eggs sysinstall` falls back to the
    # Krill TUI when it can't see an active display server (which it can't,
    # from an autostart under pkexec), and Krill then dies with no controlling
    # TTY. pkexec keeps DISPLAY + XAUTHORITY (allow_gui in eggs' policy), which
    # is what Calamares needs.
    pkexec eggs sysinstall calamares || true
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
