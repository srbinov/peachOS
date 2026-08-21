"""Per-chat avatar override store (custom photo or emoji picked in the
Contact Details panel). Local-only, peachOS-side -- deliberately does NOT try
to write back to the user's real iCloud contact (BlueBubbles has no API for
that; it only reads contacts, it doesn't manage them). A stored override is
just a file path (image or SVG emoji) that make_color_avatar() checks before
falling back to the synced-from-iCloud photo.
"""
import json
import os

_STORE_PATH = os.path.expanduser("~/.local/share/peachos-bluebubbles/avatar_overrides.json")


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


def get_override(chat_guid: str) -> str | None:
    return _load().get(chat_guid)


def set_override(chat_guid: str, path: str):
    data = _load()
    data[chat_guid] = path
    _save(data)


def clear_override(chat_guid: str):
    data = _load()
    if data.pop(chat_guid, None) is not None:
        _save(data)
