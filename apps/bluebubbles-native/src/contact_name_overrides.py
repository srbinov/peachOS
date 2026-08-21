"""Per-handle display-name override (renaming a contact from their Contact
Details page). Local-only, peachOS-side -- deliberately does NOT write back
to the user's real iCloud contact or the BlueBubbles Server (same reasoning
as avatar_overrides.py: this is a local relabel, not a real contact edit).
Keyed by the handle's address (phone number/email) rather than a chat guid so
the same person renders with the new name everywhere they appear, not just
in the one chat the rename was made from.
"""
import json
import os

_STORE_PATH = os.path.expanduser("~/.local/share/peachos-bluebubbles/contact_name_overrides.json")


def _load() -> dict:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "w") as f:
        json.dump(data, f)


def get_override(address: str) -> str | None:
    if not address:
        return None
    return _load().get(address)


def set_override(address: str, name: str):
    data = _load()
    data[address] = name
    _save(data)


def clear_override(address: str):
    data = _load()
    if data.pop(address, None) is not None:
        _save(data)
