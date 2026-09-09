# peachos-icloud-photos

Feeds the desktop **Photos widget** (`extensions/peachos-widgets@peachos`,
`widgets/photos.js`) with random pictures from your iCloud Photo Library.

## Why it's a helper and not part of the extension

iCloud has **no public Photos API**. This talks to the same private endpoint
iCloud.com and the Photos app use, via [`pyicloud`](https://github.com/picklepete/pyicloud)
(Debian: `python3-pyicloud`). GNOME Shell extensions are GJS and can't do that;
a small Python process can.

## Usage

```
peachos-icloud-photos auth      # Apple ID + password + a 2FA code, once
peachos-icloud-photos sync      # refresh the cache (the systemd timer runs this)
peachos-icloud-photos status    # JSON: connected? library size, last sync
peachos-icloud-photos logout    # forget the account + wipe the cache
```

- Password → the login keyring (libsecret), never a file.
- pyicloud session cookies → `~/.local/share/peachos/icloud-photos/session/`.
- Random JPEG derivatives (no HEIC decoding needed) → `~/.cache/peachos-widgets/icloud-photos/`.
- `peachos-icloud-photos.timer` re-syncs every 3h; the widget also kicks one if
  the cache is > 4h old.

## Caveats

- **First sign-in needs a 2FA code** from another Apple device.
- The session **trust token expires every few weeks** → run `auth` again
  (the widget shows "Sign in to iCloud again" and `status` reports
  `reauth_needed`).
- Private API — Apple can change it; `pyicloud` is patched when they do.
- Random-samples the library (`_get_photos_at` at random ranks), never
  downloads everything. Videos are skipped.
