#!/usr/bin/env bash
# One-shot check: does a brand-new user account get the peachOS look
# purely from system dconf defaults, with zero personal config?
set -euo pipefail

sudo useradd -m -s /bin/bash peachtest

echo "--- gtk-theme ---"
sudo -u peachtest dconf read /org/gnome/desktop/interface/gtk-theme
echo "--- icon-theme ---"
sudo -u peachtest dconf read /org/gnome/desktop/interface/icon-theme
echo "--- wallpaper ---"
sudo -u peachtest dconf read /org/gnome/desktop/background/picture-uri
echo "--- enabled-extensions ---"
sudo -u peachtest dconf read /org/gnome/shell/enabled-extensions
echo "--- window button layout ---"
sudo -u peachtest dconf read /org/gnome/desktop/wm/preferences/button-layout

echo "--- cleanup ---"
sudo userdel -r peachtest
