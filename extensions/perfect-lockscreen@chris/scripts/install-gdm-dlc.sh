#!/usr/bin/env bash

# Perfect Lock Screen GDM DLC Installer
# This script automates system-wide installation and GDM configuration.

set -euo pipefail

UUID="perfect-lockscreen@chris"
TARGET_DIR="/usr/share/gnome-shell/extensions/$UUID"
DCONF_GDM_DIR="/etc/dconf/db/gdm.d"
DCONF_FILE="$DCONF_GDM_DIR/99-perfect-lockscreen"

# Determine user home and local extension directories globally
REAL_HOME="${SUDO_USER_HOME:-${HOME}}"
if [ -n "${SUDO_USER:-}" ]; then
    REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
fi
LOCAL_USER_DIR="$REAL_HOME/.local/share/gnome-shell/extensions/$UUID"

# Ensure script is run with root privileges
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root. Elevating privileges..."
    if [[ "$0" == *"install-gdm-dlc.sh" ]]; then
        exec sudo bash "$0" "$@"
    else
        echo "Error: Run this script from the Perfect Lock Screen scripts directory (sudo bash scripts/install-gdm-dlc.sh)."
        exit 1
    fi
fi

# Try to find the source directory
SRC_DIR=""
# 1. Check if running from a local clone (scripts/ folder)
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
    if [ -d "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../metadata.json" ]; then
        SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    fi
fi

if [ -z "$SRC_DIR" ]; then
    # Fallback to known extension directories
    if [ -f "$LOCAL_USER_DIR/metadata.json" ]; then
        SRC_DIR="$LOCAL_USER_DIR"
    elif [ -f "$TARGET_DIR/metadata.json" ]; then
        SRC_DIR="$TARGET_DIR"
    else
        echo "Error: Could not locate Sonoma Lockscreen installation directory."
        echo "Please install the extension first (e.g. from Extensions.gnome.org)."
        exit 1
    fi
fi

echo "=== Perfect Lock Screen GDM DLC Installer ==="
echo "Source Directory: $SRC_DIR"
echo "Target Directory: $TARGET_DIR"
echo "User Directory:   $LOCAL_USER_DIR"

NO_RESTART=false
for arg in "$@"; do
    case "$arg" in
        --force) ;; # accepted for compatibility; installer always syncs
        --no-restart) NO_RESTART=true ;;
    esac
done

# 1. Sync extension system-wide
echo "-> Deploying extension system-wide..."
mkdir -p "$TARGET_DIR"
if [ "$SRC_DIR" != "$TARGET_DIR" ]; then
    # Dynamically handle git repository metadata
    EXCLUDE_GIT=""
    if [ ! -d "$SRC_DIR/.git" ]; then
        EXCLUDE_GIT="--exclude=.git*"
    fi

    if command -v rsync &> /dev/null; then
        rsync -a --delete \
            $EXCLUDE_GIT \
            --exclude="*.zip" \
            --exclude="pro.js" \
            --exclude="crossSessionManager.js" \
            "$SRC_DIR/" "$TARGET_DIR/"
    else
        echo "rsync not found, falling back to cp..."
        if [ -d "$SRC_DIR/.git" ]; then
            cp -rT "$SRC_DIR" "$TARGET_DIR"
        else
            mkdir -p "$TARGET_DIR"
            find "$SRC_DIR" -maxdepth 1 -not -name ".git" -not -name "." -not -name ".." -exec cp -r -t "$TARGET_DIR" {} +
        fi
    fi
else
    echo "   Source and Target are the same directory. Skipping extension files sync."
fi

# 2. Deploy DLC modules and restore unstripped hook files if needed
echo "-> Deploying DLC modules and restoring hook files..."
for file in "pro.js" "crossSessionManager.js" "extension.js" "prefs.js"; do
    USE_LOCAL=false
    if [ -f "$SRC_DIR/$file" ]; then
        if [ "$file" = "pro.js" ] || [ "$file" = "crossSessionManager.js" ]; then
            USE_LOCAL=true
        else
            if grep -q "GDM_EXCLUDE" "$SRC_DIR/$file"; then
                USE_LOCAL=true
            fi
        fi
    fi

    if [ "$USE_LOCAL" = true ]; then
        if [ "$SRC_DIR" != "$TARGET_DIR" ]; then
            echo "   Copying local $file..."
            cp "$SRC_DIR/$file" "$TARGET_DIR/"
        else
            echo "   Local $file already in target directory."
        fi
    else
        echo "Error: Required file $file is missing from $SRC_DIR. Install the extension from this repo first."
        exit 1
    fi
done

# 3. Patch metadata.json to include 'gdm' in session-modes and 'PRO' in version-name
echo "-> Adding 'gdm' session-mode and 'PRO' version tag in metadata.json..."
python3 -c "
import json, sys
metadata_path = '$TARGET_DIR/metadata.json'
try:
    with open(metadata_path, 'r') as f:
        data = json.load(f)
    modes = data.get('session-modes', [])
    updated = False
    if 'gdm' not in modes:
        modes.append('gdm')
        data['session-modes'] = modes
        updated = True
    vname = str(data.get('version-name', ''))
    if vname and 'PRO' not in vname:
        data['version-name'] = f'{vname} PRO'
        updated = True
    if updated:
        with open(metadata_path, 'w') as f:
            json.dump(data, f, indent=2)
        print('Successfully updated metadata.json for PRO/GDM.')
    else:
        print('metadata.json already up to date.')
except Exception as e:
    print(f'Error patching metadata.json: {e}', file=sys.stderr)
    sys.exit(1)
"

# 4. Compile schemas system-wide
echo "-> Compiling GSettings schemas..."
if [ -d "$TARGET_DIR/schemas" ]; then
    glib-compile-schemas "$TARGET_DIR/schemas/"
else
    echo "Warning: No schemas directory found in target!"
fi

# 5. Configure GDM dconf so the greeter actually loads the extension.
# Fedora reads /etc/dconf/db/gdm.d via system-db:gdm.
# Ubuntu/Debian compiles /usr/share/gdm/dconf into /var/lib/gdm3/greeter-dconf-defaults
# and ignores /etc/dconf/db/gdm.d unless the profile includes system-db:gdm.
echo "-> Configuring GDM dconf so the login screen can load the extension..."
DCONF_BODY="$(cat <<EOF
[org/gnome/shell]
enabled-extensions=['$UUID']
disable-user-extensions=false

[org/gnome/login-screen]
logo=''
fallback-logo=''
EOF
)"

mkdir -p "$DCONF_GDM_DIR"
printf '%s\n' "$DCONF_BODY" > "$DCONF_FILE"
chmod 644 "$DCONF_FILE"
dconf update || true

UBUNTU_GDM_DCONF_DIR="/usr/share/gdm/dconf"
UBUNTU_GDM_DCONF_FILE="$UBUNTU_GDM_DCONF_DIR/99-perfect-lockscreen"
if [ -d "$UBUNTU_GDM_DCONF_DIR" ]; then
    echo "-> Writing Ubuntu/Debian GDM greeter dconf drop-in..."
    printf '%s\n' "$DCONF_BODY" > "$UBUNTU_GDM_DCONF_FILE"
    chmod 644 "$UBUNTU_GDM_DCONF_FILE"
    if [ -x /usr/share/gdm/generate-config ]; then
        /usr/share/gdm/generate-config
    elif [ -d /var/lib/gdm3 ]; then
        dconf compile /var/lib/gdm3/greeter-dconf-defaults "$UBUNTU_GDM_DCONF_DIR"
    fi
fi

# System schema so GDM can read extension settings (Cupertino default).
SCHEMA_XML="$TARGET_DIR/schemas/org.gnome.shell.extensions.perfect-lockscreen.gschema.xml"
if [ -f "$SCHEMA_XML" ]; then
    echo "-> Installing GSettings schema system-wide..."
    ln -sf "$SCHEMA_XML" /usr/share/glib-2.0/schemas/org.gnome.shell.extensions.perfect-lockscreen.gschema.xml
    glib-compile-schemas /usr/share/glib-2.0/schemas/
fi

# Keep the user copy. GDM only sees /usr/share; the lock screen keeps using ~/.local.

echo "========================================="
echo "GDM login-screen layout is installed."
echo "The login screen will use Cupertino chrome and your desktop wallpaper (no video)."
echo ""
echo "Log out (or switch user) to see it. Restarting GDM now would kill this session."
if [ -t 0 ] && [ "$NO_RESTART" = false ]; then
    read -rp "Restart GDM now? This logs you out. (y/N): " choice
    case "$choice" in
        [yY][eE][sS]|[yY])
            echo "Restarting GDM..."
            systemctl restart gdm || service gdm restart
            ;;
        *)
            echo "Later: sudo systemctl restart gdm   — or just log out."
            ;;
    esac
else
    echo "Later: sudo systemctl restart gdm   — or just log out."
fi
