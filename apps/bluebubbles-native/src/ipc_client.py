"""Unix-socket JSON-line client for the headless BlueBubbles Dart backend.

Protocol (see bluebubbles-app/lib/peachos_ipc/ipc_server.dart):
  request:  {"type": "request", "id": <str>, "method": <str>, "params": {...}}
  response: {"type": "response", "id": <str>, "result": ...} or {..., "error": <str>}
  event:    {"type": "event", "event": <str>, "payload": ...}

All socket I/O runs on a background thread; results are marshalled back onto the
GLib main loop via GLib.idle_add so callbacks are always safe to touch GTK widgets
from.
"""
import json
import socket
import threading
import uuid

from gi.repository import GLib


class IpcClient:
    def __init__(self, socket_path: str):
        self._socket_path = socket_path
        self._sock = None
        self._connected = False
        self._pending = {}
        self._pending_lock = threading.Lock()
        self._event_listeners = []

    def connect(self):
        """Blocking -- call from a background thread."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self._socket_path)
        self._connected = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def close(self):
        self._connected = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def on_event(self, callback):
        """callback(event_name: str, payload) -- invoked on the GLib main loop."""
        self._event_listeners.append(callback)

    def request(self, method: str, params: dict | None = None, callback=None):
        """callback(result, error) -- invoked on the GLib main loop. error is a
        string or None."""
        req_id = str(uuid.uuid4())
        if callback is not None:
            with self._pending_lock:
                self._pending[req_id] = callback
        payload = {"type": "request", "id": req_id, "method": method, "params": params or {}}
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            self._sock.sendall(data)
        except OSError as exc:
            if callback is not None:
                with self._pending_lock:
                    self._pending.pop(req_id, None)
                GLib.idle_add(callback, None, str(exc))

    def _recv_loop(self):
        buf = b""
        while self._connected:
            try:
                chunk = self._sock.recv(1 << 16)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                GLib.idle_add(self._handle_message, msg)
        self._connected = False

    def _handle_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == "response":
            req_id = msg.get("id")
            with self._pending_lock:
                callback = self._pending.pop(req_id, None)
            if callback is not None:
                if "error" in msg:
                    callback(None, msg["error"])
                else:
                    callback(msg.get("result"), None)
        elif msg_type == "event":
            for listener in self._event_listeners:
                listener(msg.get("event"), msg.get("payload"))
        return GLib.SOURCE_REMOVE
