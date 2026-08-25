#!/usr/bin/env bash

# Perfect Lock Screen GDM uninstaller

set -euo pipefail

UUID="perfect-lockscreen@chris"
TARGET_DIR="/usr/share/gnome-shell/extensions/$UUID"
DCONF_GDM_DIR="/etc/dconf/db/gdm.d"
DCONF_FILE="$DCONF_GDM_DIR/99-perfect-lockscreen"
UBUNTU_GDM_DCONF_FILE="/usr/share/gdm/dconf/99-perfect-lockscreen"
SCHEMA_LINK="/usr/share/glib-2.0/schemas/org.gnome.shell.extensions.perfect-lockscreen.gschema.xml"

if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root. Elevating privileges..."
    if [[ "$0" == *"uninstall-gdm-dlc.sh" ]]; then
        exec sudo bash "$0" "$@"
    else
        echo "Error: Run this script from the Perfect Lock Screen scripts directory."
        exit 1
    fi
fi

echo "=== Perfect Lock Screen GDM Uninstaller ==="

if [ ! -d "$TARGET_DIR" ] && [ ! -f "$DCONF_FILE" ] && [ ! -f "$UBUNTU_GDM_DCONF_FILE" ]; then
    echo "GDM layout is not installed."
    exit 0
fi

echo "-> Removing GDM dconf overrides..."
rm -f "$DCONF_FILE"
rm -f "$UBUNTU_GDM_DCONF_FILE"
dconf update || true
if [ -x /usr/share/gdm/generate-config ]; then
    /usr/share/gdm/generate-config || true
fi

echo "-> Removing system schema link..."
rm -f "$SCHEMA_LINK"
if [ -d /usr/share/glib-2.0/schemas ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas/ || true
fi

echo "-> Removing system-wide extension files..."
rm -rf "$TARGET_DIR"

echo "========================================="
echo "GDM layout removed. Your user lock-screen copy in ~/.local is unchanged."
echo "Log out or run: sudo systemctl restart gdm"
if [ -t 0 ] && [ "${1:-}" != "--no-restart" ]; then
    read -rp "Restart GDM now? This logs you out. (y/N): " choice
    case "$choice" in
        [yY][eE][sS]|[yY])
            systemctl restart gdm || service gdm restart
            ;;
    esac
fi
