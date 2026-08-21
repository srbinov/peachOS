"""Reads the Dart backend's persisted finishedSetup flag straight off disk,
without needing the backend process running.

Lets the window decide instantly whether to show the setup form or a
"connecting" page -- no spinner, no backend spawn, for the case where the
answer is "no, this is a first run." The backend should only ever start once
there's an actual reason to talk to it: a returning user who needs real
chat data, or a first-run user who just submitted the setup form.
"""
import json
import os

_PREFS_PATH = os.path.expanduser("~/.local/share/app.bluebubbles.BlueBubbles/shared_preferences.json")


def is_setup_finished() -> bool:
    try:
        with open(_PREFS_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return bool(data.get("finishedSetup"))
