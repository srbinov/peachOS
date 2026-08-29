"""Registry of curated preset icons for common third-party apps -- browsers, chat clients,
dev tools, etc. that peachOS doesn't ship itself but a user is likely to install later (apt,
snap, or Flatpak).

Each entry maps a canonical slug to:
  - names: how the app's own .desktop Name= field actually reads, across every packaging
    format peachOS is likely to see it installed through (apt/.deb, snap, Flatpak often
    disagree slightly -- e.g. one ships "Visual Studio Code", another just "Code"). Matched
    case/punctuation-insensitively (see peachos_icon_resolve.py's _normalize_name()), so
    minor variants don't need their own separate entry.
  - simple_icons_slug + hex: OPTIONAL, only used by peachos_icon_preset_batch.py to generate
    a preset PNG from a Simple Icons brand mark when no hand-curated art exists yet for an
    app. Every entry below already has real hand-curated SVG art (see
    assets/app-icons/presets/), sourced/authored directly rather than auto-generated, so none
    of them set these -- they're here for whichever app gets added next without curated art
    ready yet.

The actual art lives in assets/app-icons/presets/<slug>.svg (default/light -- used for every
appearance mode unless overridden) and assets/app-icons/presets/darkmode/<slug>.svg (dark --
ALWAYS present for every slug below, even when the art is identical to the default: per this
project's own curation rule, "no separate dark art" means dark mode should look pixel-
identical to default, not run through the automatic dark-mode generator meant for uncurated
icons. See peachos_icon_resolve.py's CURATED_DARK_SLUGS, which every slug here is registered
into for exactly that reason -- currently identical-content dark files: figma, obsstudio,
spotify.)

Add an app here, drop its art into assets/app-icons/presets/ (+ darkmode/, always, even if
it's a copy of the default), then add it to CURATED_DARK_SLUGS in peachos_icon_resolve.py.
"""
from pathlib import Path

PRESET_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / 'assets' / 'app-icons' / 'presets'

PRESETS = {
    'androidstudio':  {'names': ['Android Studio']},
    'audacity':       {'names': ['Audacity']},
    'bitwarden':      {'names': ['Bitwarden']},
    'brave':          {'names': ['Brave Web Browser', 'Brave']},
    'chrome':         {'names': ['Google Chrome']},
    'chromium':       {'names': ['Chromium Web Browser', 'Chromium']},
    'discord':        {'names': ['Discord']},
    'dockerdesktop':  {'names': ['Docker Desktop']},
    'edge':           {'names': ['Microsoft Edge']},
    'figma':          {'names': ['Figma']},
    'githubdesktop':  {'names': ['GitHub Desktop']},
    'intellijidea':   {'names': ['IntelliJ IDEA', 'IntelliJ IDEA Community Edition', 'IntelliJ IDEA Ultimate Edition']},
    'mpvmediaplayer': {'names': ['mpv', 'mpv Media Player']},
    'nordvpn':        {'names': ['NordVPN']},
    'notion':         {'names': ['Notion']},
    'obsidian':       {'names': ['Obsidian']},
    'obsstudio':      {'names': ['OBS Studio', 'OBS']},
    'opera':          {'names': ['Opera', 'Opera Web Browser']},
    'plex':           {'names': ['Plex', 'Plex Desktop', 'Plex Media Player']},
    'postman':        {'names': ['Postman']},
    'protonvpn':      {'names': ['Proton VPN', 'ProtonVPN']},
    'pycharm':        {'names': ['PyCharm', 'PyCharm Community Edition', 'PyCharm Professional Edition']},
    'signal':         {'names': ['Signal', 'Signal Desktop']},
    'slack':          {'names': ['Slack']},
    'spotify':        {'names': ['Spotify']},
    'steam':          {'names': ['Steam']},
    'sublimetext':    {'names': ['Sublime Text']},
    'telegram':       {'names': ['Telegram', 'Telegram Desktop']},
    'virtualbox':     {'names': ['VirtualBox', 'Oracle VM VirtualBox']},
    'vivaldi':        {'names': ['Vivaldi', 'Vivaldi Web Browser', 'Vivaldi Stable']},
    'vlc':            {'names': ['VLC media player', 'VLC']},
    'vscode':         {'names': ['Visual Studio Code', 'Code']},
    'whatsapp':       {'names': ['WhatsApp']},
    'zoom':           {'names': ['Zoom']},
}
