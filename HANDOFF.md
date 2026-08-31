# peachOS — Agent Handoff

**Written:** 2026-08-31, end of a long overnight session, in anticipation of the user getting a
new laptop tomorrow, building a fresh ISO, and continuing work live on real hardware (possibly
via a different agent/session at that point). Read this whole file before touching anything —
it is trying to save you from re-discovering things the hard way.

**Updated:** same day, later — added Phase 8 (Nectar wallpaper refresh + real chroma-key
compositing on the Appearance page's Light/Dark previews) and a real local git-corruption
incident + recovery pattern, both after the "first draft" of this doc was already committed.

## What peachOS is

A macOS-styled Linux distro built on Ubuntu 26.04 + GNOME Shell 50. Custom top bar (traffic
lights, macOS-style menu, Control Center), a macOS-style dock, a custom lock screen, a
from-scratch GTK4/libadwaita Settings app (never wraps or shells out to gnome-control-center —
see "Hard rule" below), curated app icons, MacTahoe GTK/icon theming, and a Calamares-based
installer. The dev/build machine (this sandbox, `/home/user`) runs the OS live for development;
`penguins-eggs` remasters that exact live filesystem into a bootable ISO.

**Repo:** `https://github.com/srbinov/peachOS` (main branch, everything pushed as of this
writing). Satellite repos, each independently developed and periodically synced INTO
`peachOS/extensions/`:
- `~/macOS-TopBar-Gnome` → `extensions/macos-top-panel@local.dev/`
- `~/macOS-Dock-2026-peachOS` → `extensions/macos-dock-2026-peachos@peachos/`
- `~/perfect-lockscreen/perfect-lockscreen@chris` → `extensions/perfect-lockscreen@chris/`
- `~/macOS_Tahoe_SYSICONS` (icon source assets)

## Hard rule (user-stated, non-negotiable)

**peachOS's own Settings app must NEVER shell out to gnome-control-center or any other legacy
Ubuntu app.** Always build a native replacement, with full feature parity to whatever the
legacy panel offered. This was violated in FIVE places as of last night (all fixed, see
changelog) — if you find a sixth, fix it the same way: point it at `peachos-settings <page-id>`
instead, and audit the destination page for actual feature completeness while you're there
(don't just fix the launch target and assume the page itself is done).

## THE #1 THING TO KNOW: nothing has been boot-tested yet

Every fix described below has been verified as thoroughly as this sandboxed dev VM allows
(live-applied, dconf-diffed, Calamares dry-run validated, Gvc volume control tested against
this VM's real audio device, etc.) — but **zero fresh ISO has been built with the full current
set of fixes and actually boot-tested on real hardware.** The most recent ISO that exists on
disk (`/home/eggs/egg-of-peachos-nectar-peachos-amd64-2026-08-30_2109.iso`, 8.53 GiB) only has
an early subset of tonight's fixes baked in (branding + extensions sync + onboarding-disable) —
it predates the live-session lockout fix, the real-install security fix, the installer UI
redesign, the Wi-Fi/wallpaper/dconf audit, the gnome-control-center/volume-slider fixes, and
(newest) the Nectar wallpaper refresh + Appearance-page green-screen compositing (Phase 8).
**Do not treat that file, or the GitHub release `peachos-iso-2026-08-30-v2`, as current** — the
release is actually empty (an upload was started, then interrupted before any chunk finished,
see below). A fresh `eggs remaster` is needed before anything gets tested on the new laptop.

## Session narrative — what happened and why (read this to understand *why* things are shaped the way they are)

### Phase 1: first real-hardware boot test, and it was bad
The user's first boot of an ISO built earlier this session (`peachos-iso-2026-08-30`, first
release) went badly: stock Ubuntu branding everywhere ("Welcome to Ubuntu", GRUB showed stock
penguin art, OS reported as "Ubuntu 26.04"), the dock/top-bar/traffic-lights/lock-screen were
**entirely missing** (blank desktop), no install button/flow, missing pinned apps, Settings
looked broken. This triggered the whole rest of the session.

**Root cause #1 (the big one): extension deployment topology was broken.**
`provision.sh`'s extension-install loop only installs whatever currently exists under
`peachOS/extensions/*/` into `/usr/share/gnome-shell/extensions/` — there is **no automatic
sync** from the actively-developed sibling repos (`~/macOS-TopBar-Gnome` etc.) into that
directory. It had silently drifted badly: `macos-top-panel@local.dev` had **never** existed
anywhere except a dev-convenience symlink at `~/.local/share/gnome-shell/extensions/`
(`-> /home/user/macOS-TopBar-Gnome`), so `provision.sh` could never have deployed it, ever, on
any build. The dock and lock-screen extensions were present in `peachOS/extensions/` but
several days stale. This had been silently masked in all prior local testing because dev/live
testing always used the symlink location directly, never actually exercising provision.sh's own
deployment path. **Fixed** by re-syncing all three from their live dev repos into
`peachOS/extensions/` and redeploying. **If you ever touch one of the dev extension repos
directly, remember to re-sync into `peachOS/extensions/` too, or the next build won't have your
change** — this is a standing gotcha, not a one-time fix.

**Root cause #2: OS identity was never set.** `/etc/os-release` had never been customized —
`provision.sh` now writes real `peachOS 10.0` identity (NAME/PRETTY_NAME/etc.), which is what
`gnome-initial-setup` and Calamares read for their own branding text.

**Root cause #3: GRUB/BIOS boot art.** penguins-eggs' `splash.png` (used for both GRUB and
isolinux menus) was the stock penguin photo. Replaced with a peachOS wordmark
(`assets/boot/grub-splash.png`), installed by `provision.sh`.

**Root cause #4: no real install launcher.** penguins-eggs regenerates
`/usr/share/applications/install-system.desktop` from a hardcoded template baked into its own
compiled Go binary on every remaster — you cannot edit that file's content directly, it gets
stomped every build (confirmed via `eggs remaster --debug`'s JSON plan, module type
`"template"`). The fix lives one layer over: `trust-desktop.sh` (penguins-eggs' own live-session
autostart script that copies that launcher to the Desktop and marks it trusted) is copied
verbatim at build time, not regenerated — so `provision/penguins-eggs/trust-desktop.sh`
overrides it to write peachOS-branded Desktop Entry content directly instead of trusting the
stock file. Also fixed to only act during a live/demo boot (see boot=live pattern below) so a
real install's first login doesn't get a spurious "Install peachOS" icon.

### Phase 2: "did you focus on total custom onboarding" → gnome-initial-setup
User pushed back explicitly asking whether the *onboarding* experience (not just branding) was
addressed. It wasn't yet. Fixed: `gnome-initial-setup` (GNOME's own first-login wizard) is
disabled entirely for every account, live user and real-install user alike, via its own
documented skip mechanism — seed `/etc/skel/.config/gnome-initial-setup-done`
(`gnome-initial-setup-first-login.service`'s `ConditionPathExists=!%E/gnome-initial-setup-done`).
peachOS ships fully preconfigured via dconf defaults (see below), so there's nothing left for
that wizard to ask.

### Phase 3: "stop, take a step back, audit everything" — the user caught a real lockout bug
User reported: booting the live/demo session, walking away, coming back locked out — never told
a password. Real bug: peachOS's dconf profile never touched screensaver/idle-lock settings, so
stock GNOME defaults applied, and the live user's password is penguins-eggs' own **undocumented**
default (`custom.yaml`'s commented-out example, `"evolution"`, never shown to the person trying
peachOS). **Fixed** via `provision/live-session/disable-lock.sh`, an autostart script gated on
`grep -qw 'boot=live' /proc/cmdline` — disables screensaver lock/idle-activation **only** during
a live/demo boot, so a real install's actual security is never touched. **This `boot=live`
detection pattern is now the standard way to write anything that should behave differently on
live-boot vs. a real install** — reuse it, don't invent a new detection mechanism.

**A much bigger bug surfaced while auditing that fix's blast radius:** nothing in Calamares'
install sequence removed the "live" demo account or its GDM autologin after a real install.
Confirmed by reading `users.conf` (`doAutologin: false` only governs the account Calamares
itself creates) and `displaymanager.conf` (`basicSetup: false`, `sysconfigSetup: false` — it
never touches the pre-existing `AutomaticLogin*` config already baked into the squashfs). Left
alone, **every real peachOS install would have booted straight back into the "live" account**
(sudo group, same undocumented password) instead of the user's own. Fixed with a new Calamares
shellprocess step (`provision/calamares/modules/shellprocess_cleanuplive.conf`) that deletes the
live account and clears GDM autologin on the target post-install, wired into
`provision/calamares/settings.conf`'s exec sequence right after the `users` step. Also added
`live` to `users.conf`'s `forbidden_names` so a real user can't collide with that cleanup by
picking that exact username.

**Also found while there:** `settings.conf` referenced `shellprocess_logs.conf` /
`shellprocess_rmcdrom.conf`, which existed on this live dev system (from the original Calamares
package install) but had **never been captured into the repo** — a truly fresh build would have
silently skipped both steps. Recovered both into the repo. **Lesson: whenever you find a config
file referenced by name but not obviously present in the repo, check whether it exists live and
just was never committed — this has now happened twice (extensions, Calamares shellprocess
configs) and is worth actively checking for elsewhere too.**

### Phase 4: "did you fix a total custom onboarding" (round 2) — Ubuntu-specific prompts
User asked specifically about the dark/light-mode picker, data-sharing prompt, and "App Center"
promo screen seen during onboarding. Investigated properly rather than assuming the earlier
gnome-initial-setup fix covered it: confirmed via the compiled binary's own embedded page list
(`gis-appearance-page.ui`, `gis-ubuntu-insights-page.ui`, `gis-software-page.ui`/
`gis-apps-page.ui`) that **yes**, all three are pages inside that same wizard, already fully
skipped by the marker-file fix. But `ubuntu-report` turned out to be a **genuinely separate**
mechanism (zero references anywhere in the gnome-initial-setup binary) — its own systemd path
unit fires an interactive "send hardware/usage metrics" dialog independently, and `whoopsie` is
the actual Canonical crash-submission daemon behind it. **Important gotcha caught before
damage:** `apt-get remove --simulate ubuntu-report whoopsie ...` showed it would cascade into
removing `gdm3`/`gnome-shell`/`gnome-control-center`/`ubuntu-session` entirely, since
`ubuntu-desktop-minimal` hard-depends on them. **Always `--simulate` an apt removal on a
package you didn't install yourself before running it for real** — this could have bricked the
whole desktop. Fixed instead by masking the systemd units (`systemctl mask whoopsie.path
whoopsie.service`, `systemctl --global mask ubuntu-report.path ubuntu-report.service`) — same
practical outcome, zero dependency risk. `apport` itself (local crash collection, not the
submission step) was deliberately left enabled — useful for peachOS's own debugging, doesn't
itself prompt anyone or send anything anywhere.

### Phase 5: "make the installer UI much nicer" — full Calamares UI redesign
User wanted the installer's left-hand sidebar gone, a blue accent (not the earlier orange),
sleeker/cleaner, Apple-like, with real animations. Researched Calamares' actual supported
branding mechanism first rather than guessing (`sidebar: none|widget|qml`, `navigation:
none|widget|qml` in `branding.desc` — confirmed via the installed Calamares 3.3.14's own stock
`branding.desc` docs). Pulled the **real, verified QML API** (the `Branding`/`ViewManager`
singletons and their actual properties/methods) from Calamares' own KaOS reference branding
component on GitHub (`calamares/calamares-extensions`) rather than inventing plausible-looking
QML that might silently fail. Built:
- `calamares-sidebar.qml` — replaces the left rail with a slim animated top progress bar (dots +
  a cross-fading current-step label), `sidebar: qml,top`.
- `calamares-navigation.qml` — bottom nav bar, ghost "Back" + filled blue-pill "Continue",
  real hover/press animations via QML `Behavior` (Qt Widgets stylesheets can't animate, which is
  why this needed QML and not just more QSS).
- `stylesheet.qss` — restyles the actual step content (forms/buttons/inputs) to match, same
  dark-surface (#1c1c1e) + blue accent (#0A84FF, macOS system blue) language as the rest of
  peachOS.

**Validated before ever considering a rebuild, and caught two real breakages doing so:**
1. The reference's Qt5-style versioned imports (`import QtQuick.Layouts 1.3`) don't load under
   this Calamares' actual **Qt6** runtime — fixed to version-less imports (`import
   QtQuick.Layouts`).
2. `QtQuick.Controls`/`QtQuick.Layouts` QML modules were **not installed at all** on this
   system — confirmed via `calamares --debug`'s own `module "QtQuick.Layouts" is not installed`
   warning, not assumed. Added `qml6-module-qtquick-controls qml6-module-qtquick-layouts` to
   `provision.sh`'s Calamares apt-install line.

After both fixes: `calamares --debug` under `QT_QPA_PLATFORM=offscreen` shows all 6 view
modules plus the new `cleanuplive` step loading cleanly, window reaching "visible and
populated", no fatal/crash indicators. **This is the validation pattern to reuse** whenever you
touch Calamares branding again — don't just eyeball the QML, actually run
`sudo timeout 15 env QT_QPA_PLATFORM=offscreen calamares --debug` and grep the log for
`WARNING (Qt)` / `TypeError` / `not installed` / `Fatal`.

### Phase 6: "did you fix the settings app wifi/wallpaper, confirm dconf parity"
Three asks, all real:

1. **Wi-Fi settings page** — the scan/display logic was actually solid (async `NM.Client`,
   real `request_scan_async`, AP add/remove signals, 15s periodic rescans). Found one real bug:
   `_on_activate_done` was shared between two different async call sites and tried to guess
   which `finish()` to call by catching `TypeError` — a mismatched GAsyncResult/GTask
   `finish()` call in PyGObject actually surfaces as `GLib.Error`, not `TypeError`, so that
   guess never worked. Split into two unambiguous callbacks
   (`apps/settings/src/wifi_page.py`).

2. **Wallpaper page "takes forever" / "not responding"** — root cause found and *measured*:
   every preset wallpaper (32 of them) decoded the full-resolution source image directly at
   tile size, on every single page load, in `__init__` before the window even showed. Two of
   the five dynamic-wallpaper previews were even worse — a full-5K SVG with an embedded raster
   image (9–11MB each). Measured before/after with a real timing script:
   **7.15s → 0.059s, a 121.7x speedup**, comfortably enough to explain tripping GTK's
   "not responding" watchdog. Fixed by generating real small JPEG previews for every preset and
   dynamic wallpaper (script: `provision/wallpaper-previews/gen_wallpaper_previews.py`, rerun
   it if new preset wallpapers are ever added) and pointing tiles at those; the actual applied
   wallpaper path is untouched. Custom "Your Photos" tiles get the same treatment lazily — a
   thumbnail generated once on first add/load and cached in a `.thumbnails/` subdirectory,
   cleaned up when the photo is removed.

3. **dconf parity — the user explicitly demanded this be *verified*, not assumed.** Wrote a
   script-based diff comparing a full live `dconf dump` against every baked default across
   every peachOS-relevant path, not trusting the previous snapshot was still current. Found and
   fixed real drift:
   - Desktop wallpaper: baked said `tahoe_beach_dawn`, live was actually `lion_beach` — fixed
     in both `provision/dconf/01-peachos` and the separate GDM greeter snapshot
     (`provision/dconf/01-peachos-gdm`, which is a **manual, non-live-synced snapshot by
     design** — see that file's own comment for why; **if the desktop wallpaper ever changes
     again, this GDM file needs a matching manual re-sync, it will not pick it up on its own**).
   - `macos-dock` extension's `icon-size` had drifted slightly from a small live tweak.
   - `last-selected-power-profile` was never captured at all.
   - Found and cleaned up actual **leftover test-session pollution**: the lock screen's
     `lockscreen-wallpaper-path` pointed at a file inside a previous Claude session's own
     ephemeral scratchpad (already gone) — harmless in practice since `background-source` was
     correctly still `'video'` the whole time, but dangling state that would've shipped broken
     if left in. Reset to schema defaults before re-syncing baked defaults.
   - Deliberately did **not** bake in `org/gnome/shell`'s weather/world-clock sections — a
     specific city (Iowa City) tied to this dev machine, personal location data, not a
     look-and-feel default every real install should ship with. This was a judgment call, not
     an oversight — mention it if the user asks why weather isn't preset.
   - **The diff script itself is worth keeping around** (it was inline, not saved to the repo —
     consider writing it to `provision/dconf/` as a standing tool if dconf drift becomes a
     recurring worry): dump every relevant path with `dconf dump`, parse both that and the
     baked `01-peachos` file into `{section: {key: value}}` dicts, diff.

### Phase 7: sound settings bug → systemic gnome-control-center audit
User reported the top bar's "Sound Settings…" menu item opens the **legacy** Ubuntu Settings
app. Grepped the whole repo rather than patching just that one call site — found **five**
places doing this (a systemic pattern, not a one-off):
`extensions/macos-top-panel@local.dev/lib/soundIndicator.js` (the reported one),
`lib/menuManager.js`'s `open-settings` action, `src/menulayout.json`'s top-level
"System Settings…" entry, `src/userSwitcher.js`'s "Users & Groups Settings…", and
`app/aboutWindow.js`'s "More Info…" button. All five now launch `peachos-settings` instead of
`gnome-control-center`.

Fixing the launch target alone wasn't enough — clicking "Sound Settings" needs to actually land
on the Sound page, including when Settings is already open elsewhere. Added real deep-linking:
`SettingsApp.do_command_line()` in `apps/settings/src/main.py` (Adw.Application's
`DEFAULT_FLAGS` makes it a normal single-instance D-Bus-activated app —
**`do_activate()` never receives argv, only `do_command_line()` does, including for a second
invocation while the window's already open** — this is the actual reason the override exists,
not a style choice). `peachos-settings <row_id>` now navigates straight to that page;
unrecognized/absent page args fall back to the existing placeholder-page behavior, so a typo
can't crash it. **If you ever add a way to launch a settings sub-page from outside the app
(a new top-bar menu item, a notification action, whatever), this is the mechanism — pass the
target `row_id` as argv[1], nothing more is needed.**

Then audited `sound_page.py` itself against the user's explicit "every setting the legacy app
has" standard, and it genuinely was missing the single most basic thing a sound page needs:
**no volume slider at all**, output or input. Added one, deliberately mirroring the *already
proven* logic in the top bar's own `soundIndicator.js` (same Gvc calls: `get_volume()`/
`set_volume()`/`push_volume()`, `get_is_muted()`/`change_is_muted()`, `get_vol_max_norm()`,
`notify::volume`/`notify::is-muted`) rather than reinventing it. **This VM actually has a real
audio device** — constructed the page headlessly, confirmed the mixer reached `READY` and read
the real stream's actual volume/mute state correctly, then simulated a slider drag and confirmed
it wrote the exact expected raw volume value and correctly auto-unmuted. Restored the device's
original volume/mute state afterward. **If you touch `sound_page.py` again, you have a real
device to test against on this VM — use it, don't just trust the code.**

### Phase 8: Nectar wallpaper refresh + real chroma-key compositing on Appearance previews
Two asks. First, simple: the user pushed two new commits to `~/macOS_Tahoe_SYSICONS`
(`f628406`/`83d6447` — **always `git fetch` that repo and check `HEAD..origin/main` before
assuming "new asset X isn't there yet" means it doesn't exist**, that's exactly what happened
here) with a refreshed peachOS Nectar light/dark wallpaper pair and a matching dynamic-preview
SVG. Swapped them in wholesale (old files deleted, not left alongside) — see
`wallpaper_page.py`'s `DYNAMIC_WALLPAPERS` table and regenerated
`apps/settings/data/wallpaper-previews/peachOS_Nectar.jpg` via the same
`gen_wallpaper_previews.py` crop+scale pipeline as everything else there. Nectar's dark variant
is `.jpg` now, not `.png` — the source file changed format, the table entry was updated to match
rather than force a pointless reencode.

Second, genuinely new capability: the user added `lightmode_icon_new.svg`/`darkmode_icon_new.svg`
(same icons repo) — macOS Setup-Assistant-style desktop mockups (menu bar, traffic lights, dock)
painted over a **solid `#00bf63` green-screen background** instead of a fixed photo, with the ask
being "make that green area become whatever wallpaper is currently equipped, dynamic wallpapers
included." Implemented real chroma-key compositing in `appearance_page.py`:
- Rasterize the green-screen SVG once via `GdkPixbuf` (cached — it never changes, ~0.2s each,
  the expensive half).
- On every page load and every wallpaper change, crop the user's real wallpaper to match
  (`_cover_crop_scale`, same crop-before-scale approach as the preview-thumbnail generator, not
  a naive stretch), then replace every green-screen pixel with the corresponding wallpaper pixel
  — soft-blending a distance-based band around the threshold so the anti-aliased boundary between
  the green screen and the menu-bar/dock artwork doesn't leave a visible green fringe (~0.02s,
  the cheap half).
- The Light tile composites `org.gnome.desktop.background`'s `picture-uri`, the Dark tile
  composites `picture-uri-dark`. **This is what makes dynamic wallpapers "just work" with zero
  special-casing** — those two keys already hold the correct light/dark image for whatever's
  currently equipped (a static wallpaper simply has both keys pointing at the same file); this is
  the exact same pair `wallpaper_page.py`'s own `_set_wallpaper()` writes to, so no new concept
  was needed, just reading the keys that were already the source of truth.
- Reactive: `changed::picture-uri`/`changed::picture-uri-dark` on the same `Gio.Settings` trigger
  a re-composite (cheap, since the rasterized foreground is cached) — confirmed live by actually
  changing the wallpaper while a constructed page was running and checking the texture object
  changed, not just that the code looks right.

**Verified concretely at every step, not assumed** (same discipline as the rest of this doc):
measured the composite cost directly (0.2s rasterize + 0.02s chroma-key per tile, ~1.3s for the
whole Appearance page including everything else it already builds — nowhere near GTK's
"not-responding" territory), round-tripped a known RGB value through the PIL↔`GdkPixbuf`
conversion to rule out channel/stride corruption before trusting it, rendered both composited
tiles to PNG and actually looked at them (clean edges, correct wallpaper, no green fringing), and
ran the reactive-update test above against a real constructed page rather than just trusting the
signal connection would fire correctly.

**Reusable pattern**: any future "composite the user's real wallpaper/photo into a preview"
feature should reuse this exact approach — `_rasterize_greenscreen_svg` /
`_cover_crop_scale` / `_composite_scheme_preview` in `appearance_page.py` are written generically
enough to lift if a similar green-screen asset shows up elsewhere (e.g. a lock-screen preview,
a dock-background preview). `python3-pil` is already a provisioned system dependency (the icon
masker daemon uses it — see `provision.sh`), so this didn't need a new dependency.

**A real git corruption happened during this phase, unrelated to any of the above — read the new
gotcha in Architecture reference below before assuming `git status` failing means something you
did is wrong.** It wasn't; it was pre-existing local repository corruption from earlier in the
night, recovered cleanly, no work was lost.

### Phase 9: the Phase 7 gnome-control-center fix wasn't actually fixed — a real deployment gap
User re-reported the *exact same* "Sound Settings…" bug the morning after Phase 7 claimed it
fixed. It was two separate real bugs, not a false claim, and both are worth understanding:

1. **Phase 7 only fixed `peachOS/extensions/`'s copy and the system-wide deployed copy at
   `/usr/share/gnome-shell/extensions/` — never `~/macOS-TopBar-Gnome` itself.** This is the
   *exact* dev-symlink gap from Phase 1's Root Cause #1, and it bit again: `gnome-extensions info
   macos-top-panel@local.dev` shows `Path: /home/user/.local/share/gnome-shell/extensions/
   macos-top-panel@local.dev`, which is a symlink to `~/macOS-TopBar-Gnome` — **that's what this
   live dev session's actual running GNOME Shell loads, not either of the copies that got fixed.**
   Editing/deploying the other two copies changes nothing about what's actually running until you
   also fix the real dev repo. Fixed all five call sites there too, confirmed byte-identical
   against the `peachOS/extensions/` mirror afterward, committed and pushed to
   `macOS-TopBar-Gnome` separately (its own repo, own remote, `master` branch not `main`).
   **Whenever you fix something in `macos-top-panel@local.dev` (or the dock/lockscreen
   extensions), the fix isn't real until it's in the actual `~/macOS-*` dev repo — check
   `gnome-extensions info <uuid>`'s `Path:` line if you're ever unsure which copy is live.**
2. **Editing a GNOME Shell extension's `.js` files on disk does not affect an already-running
   session** — the Shell loads extension code into its own long-running process once. Try
   `gnome-extensions disable <uuid> && gnome-extensions enable <uuid>` first, but **don't trust
   it** — Phase 10 found this does NOT reliably reload a changed submodule (confirmed stale
   through two full disable/enable cycles), only a genuine full logout/login did. Do this after
   every extension fix before claiming it's verified, not just after deploying the file, and if
   a live test still looks wrong after disable/enable, log out and back in before concluding the
   *fix* itself is broken.
3. **A second, independent bug on the destination side**: `peachos-settings sound` (Phase 7's own
   deep-linking mechanism) threw `GLib-GIO-CRITICAL: This application can not open files`, then
   `GDBus.Error...: Application does not handle command line arguments` from a stale pre-fix
   instance still holding the D-Bus name. Root cause: `SettingsApp`'s `Gio.ApplicationFlags` never
   included `HANDLES_COMMAND_LINE` — without it, `do_command_line()` (added in Phase 7
   specifically to receive argv) never actually gets called at all; GApplication's own default
   local-command-line handling intercepts non-option arguments as files to open instead. Fixed by
   adding the flag. **Verify this class of fix properly**: confirmed live via `ps aux` that the
   launched process's argv actually carried the page argument through, and via a direct in-process
   test (`SettingsWindow()._go_to('sound', ...)`, checking `_placeholder_stack.get_visible_child_name()`
   actually flips to `'sound'`) rather than just trusting the code looked right a second time —
   that's the same mistake that let this ship broken the first time.

**Lesson for whatever comes next**: "I deployed the fix and the file on disk is correct" is not
the same as "I verified the fix works in the actual running session." Last night's Phase 7 did
plenty of real verification (the Gvc volume slider test against real hardware was genuinely
thorough) but never actually reloaded the extension or relaunched `peachos-settings` against a
clean D-Bus state to confirm the *live, running* behavior changed — it checked the file contents
and stopped there. Do the reload/relaunch step every time, not just for this specific bug class.

### Phase 10: notification body text, a real selector bug, and two hard lessons
User wanted real `.notification-banner`s to match the Settings app's own Liquid Glass preview
(bold full-opacity title, dimmer 0.75-opacity body) — I initially did the reverse (changed the
preview to match reality) before being corrected; reverted that and fixed the real thing in
`notificationBannerGlass.js` instead. Two things happened worth knowing about before you touch
this extension again:

1. **`gnome-extensions disable/enable` is NOT reliable for reloading a changed submodule,
   even run twice.** Phase 9's claim that it "works live on Wayland, no logout needed" turned
   out to be wrong, or at least unproven for this extension — the generated
   `~/.cache/macos-top-panel/notification-glass.css` kept reflecting stale code through two full
   disable/enable cycles and repeated forced `_apply()` calls (nudging
   `liquid-glass-intensity` back and forth). **Only a full logout/login actually picked up the
   change.** If you edit `macos-top-panel@local.dev` again and a live test still shows old
   behavior after disable/enable, don't trust it — do a real logout/login before concluding the
   fix itself is wrong.
2. **Do not use `Shell.Eval` (or any live JS injection into the gnome-shell process) to
   introspect the actor tree — it crashed the user's session once already**, mid-investigation
   of this exact bug. Whatever the cause (a bad property access deep in Clutter, `notify-send`'s
   banner already gone by the time the eval ran, or something else), evaluating arbitrary code
   inside the compositor's own process is not a safe debugging tool here. Introspect via static
   source reading instead (fetch the real gnome-shell source from
   `gitlab.gnome.org/GNOME/gnome-shell` — `js/ui/messageList.js`'s `Message` constructor and
   `js/ui/messageTray.js`'s `NotificationBanner` are the relevant files) and reason about the
   actor hierarchy from the actual source, not by poking the live scene graph.

**The actual bug, for reference**: `.notification-banner .message .message-box .message-content
.message-body` (space-separated, a descendant combinator) requires `.message` to be a *child* of
`.notification-banner` — but they're the same single actor (`NotificationMessage extends
Message`; the extra `notification-banner` class gets added to the same outer `St.Button` that
`Message`'s own constructor already stamped `'message'` onto, not a separate wrapping node).
Confirmed two ways: fetching `Message`'s real constructor from GNOME's own GitLab (traces every
`style_class`-bearing widget from the root down to the body label), and noticing the theme's own
already-working title-bold rule (`.message .message-box .message-content .message-title`) never
prefixes `.notification-banner ` either — if it needed to be a descendant, that rule couldn't
work. Fixed to a compound selector on the shared root instead:
`.notification-banner.message .message-box .message-content .message-body` (no space).
**Update, same investigation, one more round**: the compound-selector fix above turned out to
still show no visible effect even after a confirmed-genuine reload (real logout/login, generated
stylesheet checked directly and did contain the new rule). St's CSS engine is a simplified,
custom implementation, not a full browser one, and compound multi-class selectors
(`.notification-banner.message`, no space) were never actually confirmed to be supported by it
either — two selector forms in a row that were *structurally* reasonable but unverified against
what this specific engine supports. Fixed for real by copying the ONE selector shape already
DEMONSTRABLY working for this exact problem: gnome-shell.css's own bare
`.message .message-box .message-content .message-title { font-weight: bold; }` (real bold titles
are visibly correct today, so this shape is proven) — same shape verbatim, just
`.message-title` → `.message-body`, no `.notification-banner`-specific scoping at all. Trade-off:
now also colors Notification Center's own reused `.message-body` instances the same way
(documented in `stylesheet.css`'s own updated comment) — accepted as consistent styling, not
undone. **If you add more banner-scoped CSS rules here, use this same bare
`.message .message-box .message-content .<leaf>` shape — it's the only one actually confirmed to
render — rather than trying to scope more precisely to just the banner with an untested
selector form.**

Also worth knowing: partway through this, the user reported "it crashed my machine" after a live
test. Checked `journalctl -b` directly rather than assuming — **no segfault, OOM-kill, or fatal
signal anywhere in that boot's log**, just an ordinary session logout/restart sequence with some
pre-existing, unrelated, benign "already disposed" warnings from Control Center code
(`tileBlurController.js`/`controlCenterIndicator.js`) firing during normal teardown. Don't assume
a reported "crash" was caused by whatever you just changed — check the actual logs for a real
fatal signal before treating it as confirmed regression.

## Architecture reference (things you'll need repeatedly)

- **`provision/provision.sh`** is the single source of truth for how this dev VM (and thus what
  gets remastered into an ISO) is set up. It is idempotent-ish and re-runnable. Whenever you fix
  something "live" on this VM, **also** make the same change in whatever `provision.sh` installs
  from (a repo file it copies), or the fix disappears on the next fresh provision/rebuild. This
  has been the single most common class of bug found this session — check this every time.
- **Safe root-file-edit pattern**: `sudo` needs a password piped in (`echo user123 | sudo -S
  <cmd>` — the sudo password is `user123`, distinct from the GitHub PAT). For editing a
  root-owned file, do **not** try `Edit` directly on it (permission denied) and do **not** use a
  heredoc piped alongside `sudo -S` (heredoc-stdin and the piped password conflict and can
  trigger a lockout — this happened once already). Instead: `Write`/`Edit` a scratch copy, then
  `sudo cp` it into place.
- **`eggs remaster --debug`** prints the full JSON execution plan and exits without building —
  use this to check whether a given file gets regenerated from a hardcoded template during
  remaster (search for its `dest` path) before assuming a live edit will survive a rebuild. Some
  steps (`create-live-launcher`, `eggs-icon`) write hardcoded content from the compiled Go
  binary itself, not from any editable file on disk — those need the "override the *next* thing
  that reads the stock output" trick (see `trust-desktop.sh` in Phase 1 above), not a direct
  edit.
- **Disk space**: `/home/eggs` (the eggs work dir) needs roughly 2x the estimated ISO size free
  on the *same partition* as the working dir. It also does **not** clean itself up between runs —
  `sudo rm -rf /home/eggs` before a rebuild if space is tight (confirmed safe, it's pure scratch
  space). `/tmp/.../scratchpad` is a small separate tmpfs, not the real disk — never stage
  multi-GB files there.
- **GitHub Releases 2GB-per-asset limit**: the ISO (~8GB at max zstd compression) needs
  chunking. Pattern: `dd if=ISO of=chunk bs=1M skip=N count=M` one chunk at a time (not `split`,
  which needs 2x disk), `gh release upload <tag> <chunk> --clobber`, `rm` the chunk, repeat —
  run this as a real backgrounded script (`nohup setsid bash script.sh > log 2>&1 & disown`),
  not a single foreground command (uploads take 15-20+ min each over this sandbox's bandwidth,
  well past any reasonable tool timeout). **The current release `peachos-iso-2026-08-30-v2` is
  empty** — an upload was started and interrupted before the first chunk finished. Either
  restart that upload against a freshly rebuilt ISO, or delete the empty release first
  (`gh release delete peachos-iso-2026-08-30-v2 --repo srbinov/peachOS`).
- **dconf vendor-defaults mechanism**: `/etc/dconf/db/local.d/01-peachos` (normal user session
  defaults, `dconf update` recompiles) + `/usr/share/gdm/dconf/01-peachos-gdm` (compiled via
  `/usr/share/gdm/generate-config` into `/var/lib/gdm3/greeter-dconf-defaults` — this Ubuntu
  build's GDM does **not** read the standard `/etc/dconf/db/gdm.d/` path at all, confirmed in an
  earlier session, don't waste time trying that path). Both files live in
  `provision/dconf/` in the repo and are installed by `provision.sh`.
- **`boot=live` detection**: `grep -qw 'boot=live' /proc/cmdline` — the standard, reusable way
  to make a script behave differently during a live/demo boot vs. after a real install, without
  needing to check for the literal `live` username (which itself is now a forbidden name for a
  real account, see Phase 3). Used in `disable-lock.sh` and `trust-desktop.sh`; reuse it for
  anything similar.
- **Green-screen chroma-key compositing** (Phase 8): the reusable pattern for "make this preview
  asset show the user's real wallpaper/photo instead of a fixed stock image" — a `#00bf63`
  green-screen SVG rasterized once via `GdkPixbuf` (cache it, it's the expensive part, ~0.2s),
  then a soft-thresholded per-pixel distance-from-green blend against a cover-cropped real image
  (cheap, ~0.02s at a 224×126 tile size). Implementation lives in `appearance_page.py`
  (`_rasterize_greenscreen_svg`/`_cover_crop_scale`/`_composite_scheme_preview`) — lift it
  directly rather than reinventing if another green-screen asset shows up.
- **`gnome-extensions info <uuid>`'s `Path:` line tells you which copy of an extension is
  actually running** — for `macos-top-panel@local.dev` specifically that's
  `~/.local/share/gnome-shell/extensions/macos-top-panel@local.dev` (a symlink to
  `~/macOS-TopBar-Gnome`), not `peachOS/extensions/` or `/usr/share/gnome-shell/extensions/`.
  Fixing only those other two copies changes nothing about the live session (Phase 9). After
  editing the real copy, try `gnome-extensions disable <uuid> && gnome-extensions enable <uuid>`
  first, but don't fully trust it — Phase 10 found it does NOT reliably reload a changed
  submodule (only a full logout/login confirmed did). Editing `.js` on disk alone does not
  affect an already-running session either way — some form of reload is always required, just
  verify the reload actually took (e.g. check a generated stylesheet/cache file's content, not
  just that the extension reports ACTIVE) before trusting a live test. Also: never use
  `Shell.Eval`/live JS injection into the gnome-shell process to debug this — it crashed the
  session once already (Phase 10); read GNOME's real source instead
  (`gitlab.gnome.org/GNOME/gnome-shell`, `js/ui/messageList.js` and `js/ui/messageTray.js` for
  anything notification-related).
  affect an already-running Shell process.
- **Local git corruption happened once this session, unrelated to any actual peachOS bug** —
  `git status`/`git log` started failing with `fatal: bad object HEAD` after an interrupted write
  (mid-commit, cause not fully confirmed) left three loose objects truncated to 0 bytes, one of
  them the HEAD commit itself. **Working-tree files were completely unaffected** — git object
  corruption only touches `.git/`'s internal database, never the actual checked-out files, so
  nothing was at risk of being lost. Recovery pattern, if this happens again: (1) `cp -r .git
  .git-backup` before touching anything, (2) `git fsck --full` to find the exact scope (ignore
  `dangling blob`/`dangling commit` lines, those are normal), (3) `git ls-remote origin main` to
  confirm the remote has a good copy of whatever HEAD is supposed to be, (4) delete just the
  empty/corrupt loose object files under `.git/objects/`, (5) `git fetch origin main` — git
  redownloads fresh copies of exactly what's missing, no `reset --hard` needed and no working-tree
  risk, since the ref itself was already correct and just needed its target object to exist. If
  `git fsck` comes back clean afterward, delete the backup.

## What's still genuinely open / not yet done

1. **A fresh `eggs remaster` incorporating everything through Phase 8, then an actual boot test
   on real hardware** — this is almost certainly the very next step, and per the user's plan,
   probably what tomorrow with the new laptop is for. Clean `/home/eggs` first if reusing this
   VM.
2. **The GitHub release upload** needs to be redone against whatever fresh ISO gets built — the
   current release is empty (see above).
3. The user's original bug report also mentioned "missing preset apps on the dock" and
   "Wi-Fi/Bluetooth not popping up" — both were investigated and attributed to the
   top-bar/dock extensions being entirely absent on that first bad boot (now fixed), not
   independent bugs. **This has not been re-confirmed on an actual fresh boot** — worth
   explicitly checking on the first real test.
4. No further systemic sweep has been done beyond gnome-control-center — if the user reports
   another "opens the wrong/legacy thing" bug, grep the whole repo for the legacy tool's name
   first (as in Phase 7), don't assume it's an isolated instance.
5. `provision.sh` does not install the snap packages it writes `.desktop` launchers for
   (BlueBubbles, Firefox/Orchard, App Center) — this is a reproducibility gap for a *fresh
   base-image* provision run, not a bug in what's currently shipped (those snaps are already
   manually installed on this dev VM, and the ISO is built from this VM's actual live state).
   Noted but deliberately not fixed this session — low priority relative to everything else, but
   worth knowing about if a truly from-scratch base image is ever provisioned.

## Working with this user

- Explicit, demanding, will call out anything that feels like guessing or a surface-level patch
  ("it just looks like a re-skin", "please focus"). **Verify claims concretely before stating
  them as fact** — this whole session's pattern of "confirmed via X" / "measured Y before and
  after" rather than "should work now" is what actually satisfied them; assumed fixes did not.
- Wants root causes, not symptom patches — when investigating one bug, checking whether it's
  part of a wider pattern (as in Phase 7) was explicitly the right call, not scope creep.
- Once a long background job (build, upload) is running, they've explicitly asked for *silence*
  until it's actually done or fails — no unsolicited progress narration. `Monitor`/background
  jobs, report on completion.
- Git: commits should be detailed and explain *why*, not just *what* — this repo's own commit
  log is itself a good source of truth for later reference, written with that in mind
  deliberately.
- GitHub credentials (username `srbinov`, PAT) are provided by the user directly in-session when
  needed for push/release operations — never persisted to git config or any file, used inline in
  the push URL or piped to `gh auth login --with-token`, and redacted in any echoed command
  output (`sed 's/ghp_[A-Za-z0-9]*/ghp_***REDACTED***/g'`). Ask for it fresh rather than assuming
  it's remembered from a prior session.
