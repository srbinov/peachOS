# Perfect Lock Screen (extension tree)

This directory is the GNOME Shell extension (`perfect-lockscreen@chris`).

**Full install instructions** (lock screen + GDM login screen, command by command) live in the [repository root README](../README.md).

Quick path from this folder:

```bash
make install
gnome-extensions enable perfect-lockscreen@chris
```

Then log out and back in on Wayland. After the lock screen looks right:

```bash
sudo bash scripts/install-gdm-dlc.sh --no-restart
```

Log out again to refresh GDM.
