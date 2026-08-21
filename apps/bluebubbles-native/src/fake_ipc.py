"""Drop-in stand-in for IpcClient, backed by an in-memory set of made-up chats
and messages instead of a real socket to the Dart backend.

Temporary, for UI work: lets the setup screen accept literally any server URL
and password and land straight in a populated-looking main view, so the chat
list / conversation / compose / contact-details / emoji-picker UI can all be
built and tweaked without a live BlueBubbles Server. Implements the exact same
`.request(method, params, callback)` surface real IpcClient does (see
ipc_client.py's docstring for the method contracts each view expects), so
every view built against IpcClient works against this unchanged. Swap back to
real IpcClient in main.py (flip FAKE_MODE) once there's a real server to test
against again -- nothing else needs to change.
"""
import mimetypes
import os
import time
import uuid

from gi.repository import GLib


def _millis(days_ago: float = 0, hours_ago: float = 0, minutes_ago: float = 0) -> int:
    seconds_ago = days_ago * 86400 + hours_ago * 3600 + minutes_ago * 60
    return int((time.time() - seconds_ago) * 1000)


def _seed_chats() -> list[dict]:
    return [
        {
            "guid": "fake-chat-weekend",
            "title": "Weekend Hangout \U0001F389",
            "isPinned": True,
            "hasUnreadMessage": True,
            "handles": [
                {"displayName": "Priya Nair", "address": "+1 312-555-0148"},
                {"displayName": "Marcus Webb", "address": "+1 312-555-0199"},
                {"displayName": "Dana Ferris", "address": "+1 312-555-0122"},
            ],
            "messages": [
                {"from": "Priya Nair", "text": "ok who's actually free saturday", "days_ago": 2, "hours_ago": 3},
                {"from": "Marcus Webb", "text": "me, was gonna suggest the lake trail again", "days_ago": 2, "hours_ago": 2.9},
                {"from": "Dana Ferris", "text": "in, as long as we leave before noon this time", "days_ago": 2, "hours_ago": 2.7},
                {"from": None, "text": "works for me, I'll bring the cooler", "days_ago": 2, "hours_ago": 2.5},
                {"from": "Priya Nair", "text": "bringing the good speaker too \U0001F3B6", "days_ago": 0, "hours_ago": 1.2},
                {"from": "Marcus Webb", "text": "let's do 10am at the usual spot", "days_ago": 0, "hours_ago": 0.4},
            ],
        },
        {
            "guid": "fake-chat-mom",
            "title": "Mom",
            "isPinned": True,
            "hasUnreadMessage": False,
            "handles": [{"displayName": "Mom", "address": "+1 630-555-0110"}],
            "messages": [
                {"from": "Mom", "text": "did you eat today", "days_ago": 1, "hours_ago": 8},
                {"from": None, "text": "yes mom lol", "days_ago": 1, "hours_ago": 7.8},
                {"from": "Mom", "text": "ok good. call me later, love you", "days_ago": 1, "hours_ago": 7.7},
                {"from": None, "text": "love you too, will do", "days_ago": 1, "hours_ago": 7.5},
            ],
        },
        {
            "guid": "fake-chat-alex",
            "title": "Alex Chen",
            "isPinned": False,
            "hasUnreadMessage": True,
            "handles": [{"displayName": "Alex Chen", "address": "alex.chen@example.com"}],
            "messages": [
                {"from": "Alex Chen", "text": "hey, you free for a call tomorrow?", "days_ago": 0, "hours_ago": 5},
                {"from": "Alex Chen", "text": "wanted to go over the numbers before Thursday", "days_ago": 0, "hours_ago": 4.9},
                {"from": None, "text": "yeah works, 2pm?", "days_ago": 0, "hours_ago": 4.5},
                {"from": "Alex Chen", "text": "perfect, sending an invite", "days_ago": 0, "hours_ago": 4.4},
                {"from": "Alex Chen", "text": "here's the draft btw", "days_ago": 0, "hours_ago": 0.6},
            ],
            "attachments": [{"transferName": "Q3_summary.pdf", "totalBytes": 884213, "mimeType": "application/pdf"}],
        },
        {
            "guid": "fake-chat-hiking",
            "title": "Hiking Crew \U0001F97E",
            "isPinned": False,
            "hasUnreadMessage": False,
            "handles": [
                {"displayName": "Sam Rivera", "address": "+1 773-555-0166"},
                {"displayName": "Jordan Lee", "address": "+1 773-555-0177"},
            ],
            "messages": [
                {"from": "Sam Rivera", "text": "starkweather trail was rough this week, lots of mud", "days_ago": 5, "hours_ago": 2},
                {"from": "Jordan Lee", "text": "yeah I saw the pics, still worth it though", "days_ago": 5, "hours_ago": 1.8},
                {"from": None, "text": "next one let's just do the ridge loop", "days_ago": 5, "hours_ago": 1.5},
            ],
        },
        {
            "guid": "fake-chat-sam",
            "title": "Sam Rivera",
            "isPinned": False,
            "hasUnreadMessage": True,
            "handles": [{"displayName": "Sam Rivera", "address": "+1 773-555-0166"}],
            "messages": [
                {"from": "Sam Rivera", "text": "you still have my charger?", "days_ago": 0, "hours_ago": 0.2},
            ],
        },
        {
            "guid": "fake-chat-jordan",
            "title": "Jordan Lee",
            "isPinned": False,
            "hasUnreadMessage": False,
            "handles": [{"displayName": "Jordan Lee", "address": "+1 773-555-0177"}],
            "messages": [
                {"from": "Jordan Lee", "text": "check this out", "days_ago": 9, "hours_ago": 1},
                {"from": "Jordan Lee", "text": "found it at the flea market for $8", "days_ago": 9, "hours_ago": 0.9},
                {"from": None, "text": "no way, that's a steal", "days_ago": 9, "hours_ago": 0.8},
            ],
            "attachments": [{"transferName": "IMG_0492.HEIC", "totalBytes": 2456321, "mimeType": "image/heic"}],
        },
        {
            # Unmatched number -- no title/displayName resolves, so
            # _chat_title falls back to chatIdentifier and _initials returns
            # None (plain silhouette avatar), matching how a real unrecognized
            # sender renders.
            "guid": "fake-chat-unknown",
            "title": None,
            "displayName": None,
            "chatIdentifier": "+1 224-555-0135",
            "isPinned": False,
            "hasUnreadMessage": False,
            "handles": [{"displayName": "+1 224-555-0135", "address": "+1 224-555-0135"}],
            "messages": [
                {"from": "+1 224-555-0135", "text": "Your verification code is 481204. Don't share this with anyone.", "days_ago": 3, "hours_ago": 6},
            ],
        },
    ]


class FakeIpcClient:
    def __init__(self):
        self._chats: dict[str, dict] = {}
        for seed in _seed_chats():
            messages = []
            for m in seed.pop("messages", []):
                sent_at = _millis(days_ago=m.get("days_ago", 0), hours_ago=m.get("hours_ago", 0))
                is_from_me = m["from"] is None
                messages.append({
                    "guid": str(uuid.uuid4()),
                    "text": m["text"],
                    "isFromMe": is_from_me,
                    "dateCreated": sent_at,
                    "dateRead": sent_at if not is_from_me else None,
                    "isDelivered": True,
                    "senderName": None if is_from_me else m["from"],
                    "senderAvatarPath": None,
                    "attachments": [],
                })
            attachments = seed.pop("attachments", [])
            if attachments and messages:
                messages[-1]["attachments"] = attachments
            messages.sort(key=lambda msg: msg["dateCreated"])
            latest = messages[-1] if messages else None
            seed["dbOnlyLatestMessageDate"] = latest["dateCreated"] if latest else 0
            seed["previewText"] = (latest["text"] if latest else "")
            seed["_messages"] = messages
            self._chats[seed["guid"]] = seed

    # --- IpcClient-compatible surface ---

    def connect(self):
        pass

    def close(self):
        pass

    def on_event(self, callback):
        pass

    def request(self, method: str, params: dict | None = None, callback=None):
        params = params or {}
        handler = getattr(self, f"_handle_{method.replace('-', '_')}", None)
        if handler is None:
            if callback is not None:
                GLib.idle_add(callback, None, f"Unknown method: {method}")
            return
        result, error = handler(params)
        if callback is not None:
            GLib.idle_add(callback, result, error)

    # --- method handlers ---

    def _handle_run_setup(self, params):
        return {"success": True}, None

    def _handle_is_setup_finished(self, params):
        return {"finished": True}, None

    def _handle_list_chats(self, params):
        return [self._public_chat(c) for c in self._chats.values()], None

    def _handle_get_messages(self, params):
        chat = self._chats.get(params.get("chatGuid"))
        if chat is None:
            return None, "Unknown chat"
        limit = params.get("limit") or 50
        # newest-first, matching the real backend's get-messages contract.
        return list(reversed(chat["_messages"]))[:limit], None

    def _handle_send_message(self, params):
        chat = self._chats.get(params.get("chatGuid"))
        text = (params.get("text") or "").strip()
        attachment_path = params.get("attachmentPath")
        if chat is None or (not text and not attachment_path):
            return None, "Invalid chat or empty message"

        attachments = []
        if attachment_path and os.path.isfile(attachment_path):
            mime_type, _ = mimetypes.guess_type(attachment_path)
            attachments.append({
                "transferName": os.path.basename(attachment_path),
                "totalBytes": os.path.getsize(attachment_path),
                "mimeType": mime_type or "application/octet-stream",
                # Only meaningful here in fake mode -- we picked this file
                # straight off local disk, so there's nothing to download.
                # The real backend's attachments don't have a local path
                # until a separate download step (out of scope for now).
                "localPath": attachment_path,
            })

        now = _millis()
        message = {
            "guid": str(uuid.uuid4()),
            "text": text,
            "isFromMe": True,
            "dateCreated": now,
            "dateRead": None,
            "isDelivered": True,
            "senderName": None,
            "senderAvatarPath": None,
            "attachments": attachments,
        }
        chat["_messages"].append(message)
        chat["dbOnlyLatestMessageDate"] = now
        chat["previewText"] = text or (f"\U0001F4F7 {attachments[0]['transferName']}" if attachments else "")
        return {"success": True}, None

    def _handle_set_chat_pinned(self, params):
        chat = self._chats.get(params.get("chatGuid"))
        if chat is None:
            return None, "Unknown chat"
        chat["isPinned"] = bool(params.get("pinned"))
        return {"success": True}, None

    def _handle_create_contact(self, params):
        return {"success": True}, None

    @staticmethod
    def _public_chat(chat: dict) -> dict:
        return {k: v for k, v in chat.items() if k != "_messages"}
