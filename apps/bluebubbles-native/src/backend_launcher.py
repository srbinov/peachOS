"""Starts the headless BlueBubbles Dart backend (bluebubbles-app/lib/main_headless.dart,
built to build/linux/x64/debug/bundle/bluebubbles) if it isn't already running, and waits
for its IPC socket to appear.

Call ensure_backend_running() from a background thread -- it blocks (subprocess spawn +
polling for the socket file).
"""
import os
import subprocess
import time

BACKEND_BIN = os.path.expanduser(
    "~/bluebubbles-app/build/linux/x64/debug/bundle/bluebubbles"
)


def socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime_dir, "peachos-bluebubbles.sock")


def ensure_backend_running(timeout_seconds: float = 60.0) -> bool:
    """Returns True once the socket file exists, False on timeout."""
    path = socket_path()
    if not os.path.exists(path):
        # "minimized" is what linux/my_application.cc's started_minimized() checks
        # for -- without it, the native layer treats this as a normal windowed
        # launch: it realizes and shows a real GTK window/FlView and leaves
        # Impeller enabled, even though main_headless.dart never calls runApp()
        # to paint anything into it. Both of those (Impeller's GPU surface init,
        # and a realized-but-nothing-ever-rendered GTK/GL surface) are the
        # exact, already-diagnosed causes of the gnome-shell SIGABRT crashes
        # (Clutter clutter-paint-nodes.c:932 assertion, windowManager.js) seen
        # throughout this project -- the fix for both was already built into
        # my_application.cc, just never actually reached because this call
        # wasn't passing the flag that turns it on.
        subprocess.Popen(
            [BACKEND_BIN, "minimized"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return False
