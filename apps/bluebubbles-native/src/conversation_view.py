"""Content pane: header pill + message thread + compose bar for the selected
chat, matching macOS Messages' own layout (pill-shaped avatar+name+chevron
header, video-call icon, rounded "iMessage" compose field at the bottom).

Message data (including contact-resolved sender names) comes from the backend's
"get-messages" IPC method -- see ipc_server.dart's _serializeMessage. Sending
goes through "send-message" -- see ComposeBar and ipc_server.dart's
_sendMessage.
"""
import datetime
import re
import textwrap
from urllib.parse import urlparse

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from image_utils import load_bounded_texture

# A long, break-point-free line (a real example: an unbroken sentence with no
# short words) reliably made the whole window balloon out to fit it instead of
# wrapping -- measured directly (Gtk.Label.measure): with wrap=True +
# max_width_chars=42, this build's GTK still reports natural width equal to
# the full *unwrapped* text width (883px for the exact string that triggered
# this), so max-width-chars isn't constraining natural size the way its docs
# describe. Pre-wrapping the string ourselves and turning GTK's own wrap off
# sidesteps that entirely: a label given already-newline-broken text with
# wrap=False naturally reports only its longest *line's* width (confirmed:
# 237px for the same string), which is what actually stops the window from
# growing.
_BUBBLE_WRAP_WIDTH = 42


def _wrap_message_text(text: str) -> str:
    return "\n".join(
        textwrap.fill(paragraph, width=_BUBBLE_WRAP_WIDTH, break_long_words=True, break_on_hyphens=False)
        if paragraph else ""
        for paragraph in text.split("\n")
    )

from chat_list_view import _chat_title, build_chat_avatar, make_color_avatar

_COMMON_TLDS = (
    "com|net|org|io|co|dev|app|shop|store|gov|edu|info|biz|us|uk|ca|de|fr|jp|"
    "cn|au|ai|xyz|me|tv|link|site|online|tech|cloud"
)
# Three ways a link can show up in plain text: a full scheme (https://...), a
# www.-prefixed host, or a bare "word.tld" with no scheme at all (e.g.
# "nike.com") -- the last one is only safe to auto-detect against a curated
# TLD whitelist rather than any "word.word", which would also light up on
# ordinary sentences ("etc. therefore", "Mr.Smith").
_URL_RE = re.compile(
    r"(https?://\S+"
    r"|www\.\S+"
    r"|\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+(?:" + _COMMON_TLDS + r")(?:/\S*)?)"
)

_ATTACHMENT_MAX_SIZE = 240


def _href_for(url: str) -> str:
    return url if url.startswith("http") else f"https://{url}"


def _extract_domain(href: str) -> str:
    try:
        netloc = urlparse(href).netloc
    except ValueError:
        netloc = ""
    return netloc or href


def _linkify(text: str, is_from_me: bool) -> str:
    """Wraps any URL in `text` in a Pango <a href> span so it renders as a
    real clickable link (GtkLabel opens it itself via its default
    "activate-link" handler -- no extra wiring needed). The link color is
    baked into the markup rather than left to the theme's default .link
    color, which reads fine on a plain background but is low-contrast
    against the solid blue outgoing-bubble fill."""
    link_color = "#FFFFFF" if is_from_me else "#64D2FF"
    parts = []
    last = 0
    for m in _URL_RE.finditer(text):
        parts.append(GLib.markup_escape_text(text[last:m.start()]))
        url = m.group(0)
        href = _href_for(url)
        escaped_url = GLib.markup_escape_text(url)
        escaped_href = GLib.markup_escape_text(href)
        parts.append(
            f'<a href="{escaped_href}"><span foreground="{link_color}" underline="single">{escaped_url}</span></a>'
        )
        last = m.end()
    parts.append(GLib.markup_escape_text(text[last:]))
    return "".join(parts)


def _build_link_preview(url: str, href: str) -> Gtk.Widget:
    """A collapsed-by-default card below the bubble, matching the "dropdown
    previewing the link" the user asked for. Deliberately shows only the
    domain + full URL (real, already-known data) rather than a fetched
    title/thumbnail -- faking a live fetch would mean making an outbound
    request to whatever URL is in the message text, which is both a
    privacy/SSRF-shaped concern and not something worth doing quietly. The
    header toggles the detail open/closed; the actual clickable "open this
    link" affordance is the linkified text in the bubble above, so this
    doesn't try to double as that too."""
    domain = _extract_domain(href)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    card.add_css_class("link-preview")

    header_btn = Gtk.Button()
    header_btn.add_css_class("flat")
    header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
    icon.set_pixel_size(14)
    header_row.append(icon)
    domain_label = Gtk.Label(label=domain, xalign=0, hexpand=True, ellipsize=3)
    domain_label.add_css_class("link-preview-domain")
    header_row.append(domain_label)
    chevron = Gtk.Image.new_from_icon_name("pan-down-symbolic")
    chevron.set_pixel_size(12)
    header_row.append(chevron)
    header_btn.set_child(header_row)
    card.append(header_btn)

    detail_label = Gtk.Label(label=url, xalign=0, wrap=True, visible=False)
    detail_label.add_css_class("link-preview-url")
    detail_label.add_css_class("dim-label")
    card.append(detail_label)

    def toggle(_btn):
        expanded = detail_label.get_visible()
        detail_label.set_visible(not expanded)
        chevron.set_from_icon_name("pan-up-symbolic" if not expanded else "pan-down-symbolic")

    header_btn.connect("clicked", toggle)
    return card


def _build_attachment_image(path: str) -> Gtk.Widget | None:
    """Rendered outside the colored bubble (real iMessage shows a photo
    as its own rounded rectangle, not a photo-filled speech bubble) --
    load_bounded_texture (not the square-forcing avatar/emoji decoders in
    image_utils.py) so a non-square photo isn't squished."""
    texture = load_bounded_texture(path, _ATTACHMENT_MAX_SIZE)
    if texture is None:
        return None
    picture = Gtk.Picture.new_for_paintable(texture)
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_halign(Gtk.Align.START)
    picture.add_css_class("attachment-image")
    picture.set_overflow(Gtk.Overflow.HIDDEN)
    return picture


# Consecutive messages from the same sender within this gap render as one
# visually grouped block (no repeated sender name/avatar) -- same idea as the
# real app's message grouping, just time-based instead of reading its exact
# grouping heuristic.
_GROUP_GAP_SECONDS = 60


def _dt(millis):
    return datetime.datetime.fromtimestamp(millis / 1000) if millis else None


def _format_separator(dt: datetime.datetime) -> str:
    now = datetime.datetime.now()
    if dt.date() == now.date():
        return dt.strftime("Today %-I:%M %p")
    if (now.date() - dt.date()).days == 1:
        return dt.strftime("Yesterday %-I:%M %p")
    return dt.strftime("%b %-d, %-I:%M %p")


class ConversationHeader(Adw.Bin):
    """The rounded avatar+name+chevron pill used as the content pane's
    Adw.HeaderBar title_widget -- mirrors macOS Messages' own header shape.
    Clickable: emits "details-requested" (ConversationView forwards it, with
    the chat and currently-loaded messages, to whoever owns navigation -- see
    main.py) rather than opening anything itself, so this widget doesn't need
    to know about the details page or the nav stack it lives in."""

    __gtype_name__ = "ConversationHeader"

    __gsignals__ = {
        "details-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._chat: dict | None = None

        self._button = Gtk.Button()
        self._button.add_css_class("flat")
        self._button.connect("clicked", lambda _b: self.emit("details-requested"))
        self.set_child(self._button)
        self.set_visible(False)

        self._pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._pill.add_css_class("header-pill")
        self._pill.set_halign(Gtk.Align.CENTER)
        self._button.set_child(self._pill)

    def set_chat(self, chat: dict):
        self._chat = chat

        child = self._pill.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._pill.remove(child)
            child = nxt

        title = _chat_title(chat)
        self._pill.append(build_chat_avatar(chat, size=22))

        label = Gtk.Label(label=title, ellipsize=3, max_width_chars=24)
        label.add_css_class("header-pill-name")
        self._pill.append(label)

        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        self._pill.append(chevron)

        self.set_visible(True)


class ComposeBar(Adw.Bin):
    """Sends via the backend's "send-message" IPC method, which queues the
    text through OutgoingMsgHandler.queue() -- the exact same DB-write-then-
    HTTP pipeline the real app's own send button uses (see ipc_server.dart's
    _sendMessage docstring), so a message sent here shows up as a real,
    normal iMessage/SMS send, not a local-only fake."""

    __gtype_name__ = "ComposeBar"

    __gsignals__ = {
        "message-sent": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, ipc_client):
        super().__init__()
        self._ipc = ipc_client
        self._chat_guid: str | None = None

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(10)
        row.set_margin_bottom(10)
        row.set_margin_start(12)
        row.set_margin_end(12)
        self.set_child(row)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.add_css_class("circular")
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", self._on_pick_attachment)
        row.append(add_btn)

        self._entry = Gtk.Entry(placeholder_text="iMessage", hexpand=True)
        self._entry.add_css_class("compose-entry")
        self._entry.connect("activate", self._on_send)
        row.append(self._entry)

        self._send_btn = Gtk.Button(icon_name="go-up-symbolic")
        self._send_btn.add_css_class("circular")
        self._send_btn.add_css_class("suggested-action")
        self._send_btn.connect("clicked", self._on_send)
        row.append(self._send_btn)

    def set_chat_guid(self, chat_guid: str):
        self._chat_guid = chat_guid

    def _on_send(self, _widget):
        text = self._entry.get_text().strip()
        if not text or not self._chat_guid:
            return

        self._entry.set_sensitive(False)
        self._send_btn.set_sensitive(False)
        self._ipc.request(
            "send-message",
            {"chatGuid": self._chat_guid, "text": text},
            callback=self._on_send_response,
        )

    def _on_pick_attachment(self, _btn):
        if not self._chat_guid:
            return

        dialog = Gtk.FileDialog(title="Choose an Image")
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        image_filter.add_mime_type("image/png")
        image_filter.add_mime_type("image/jpeg")
        image_filter.add_mime_type("image/gif")
        image_filter.add_mime_type("image/webp")
        image_filter.add_mime_type("image/heic")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)

        def on_chosen(_dialog, result, *_args):
            try:
                file = dialog.open_finish(result)
            except GLib.GError:
                return
            if file is None:
                return
            self._send_attachment(file.get_path())

        dialog.open(self.get_root(), None, on_chosen)

    def _send_attachment(self, path: str):
        self._entry.set_sensitive(False)
        self._send_btn.set_sensitive(False)
        self._ipc.request(
            "send-message",
            {"chatGuid": self._chat_guid, "text": "", "attachmentPath": path},
            callback=self._on_send_response,
        )

    def _on_send_response(self, result, error):
        self._entry.set_sensitive(True)
        self._send_btn.set_sensitive(True)
        if error is not None:
            # Leave the typed text in place on failure so it isn't lost --
            # the user can just hit send again once whatever's wrong (usually
            # the socket connection) recovers.
            self._entry.grab_focus()
            return
        self._entry.set_text("")
        self.emit("message-sent")


class ConversationView(Adw.Bin):
    __gtype_name__ = "ConversationView"

    __gsignals__ = {
        # (chat: dict, messages: list) -- forwarded from the header click so
        # whoever owns the nav stack (main.py) can push the details page
        # without ConversationView needing a reference to that stack itself.
        "details-requested": (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
    }

    def __init__(self, ipc_client):
        super().__init__()
        self._ipc = ipc_client
        self._chat_guid = None
        self._chat: dict | None = None
        self._last_messages: list = []
        # Per-chat set of message guids already rendered once -- lets a
        # reload after sending animate in only the newly-arrived bubble(s)
        # instead of replaying the entrance for the whole thread every time.
        self._known_message_guids: dict[str, set] = {}
        # Adw.TimedAnimation instances have to be kept referenced from
        # Python for their whole play -- an unreferenced one can get
        # garbage-collected mid-animation, which just stops it dead partway.
        self._row_animations: list = []

        self.header = ConversationHeader()
        self.header.connect("details-requested", self._on_details_requested)

        toolbar = Adw.ToolbarView()
        self.set_child(toolbar)

        self._message_host = Adw.Bin()
        toolbar.set_content(self._message_host)
        self._show_placeholder()

        self._compose_bar = ComposeBar(ipc_client)
        self._compose_bar.set_visible(False)
        self._compose_bar.connect("message-sent", self._on_message_sent)
        toolbar.add_bottom_bar(self._compose_bar)

    def _show_placeholder(self):
        self._message_host.set_child(Adw.StatusPage(
            icon_name="chat-symbolic",
            title="Select a Conversation",
            description="Choose a chat from the sidebar to view its messages.",
        ))

    def _on_details_requested(self, _header):
        if self._chat is not None:
            self.emit("details-requested", self._chat, self._last_messages)

    def show_chat(self, chat: dict):
        self._chat_guid = chat["guid"]
        self._chat = chat
        self.header.set_chat(chat)
        self._compose_bar.set_visible(True)
        self._compose_bar.set_chat_guid(chat["guid"])

        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self._message_host.set_child(spinner)
        self._reload_messages()

    def _on_message_sent(self, _compose_bar):
        # No spinner here -- swapping the whole message host on every send
        # would flicker the list the user is actively looking at.
        self._reload_messages()

    def _reload_messages(self):
        if self._chat_guid is None:
            return
        self._ipc.request(
            "get-messages",
            {"chatGuid": self._chat_guid, "limit": 50},
            callback=lambda result, error: self._on_messages_loaded(self._chat_guid, result, error),
        )

    def _on_messages_loaded(self, chat_guid, result, error):
        # A newer selection may have raced ahead of this response -- drop stale results.
        if chat_guid != self._chat_guid:
            return

        if error is not None:
            self._message_host.set_child(Adw.StatusPage(
                icon_name="dialog-error-symbolic", title="Failed to Load Messages", description=str(error)))
            return

        # hscrollbar_policy defaulted to AUTOMATIC -- GTK only wraps a label when
        # its *allocated* width is less than its natural (unwrapped) width, and
        # AUTOMATIC let the ScrolledWindow grow horizontally to fit that natural
        # width instead of constraining it, so wrapping never actually triggered
        # (confirmed live: a long URL forced the whole window wider instead of
        # wrapping). NEVER forces content to fit the available width, which is
        # what actually makes wrap=True take effect.
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._message_host.set_child(scroller)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        column.set_margin_top(16)
        column.set_margin_bottom(16)
        column.set_margin_start(16)
        column.set_margin_end(16)
        scroller.set_child(column)

        self._last_messages = result or []

        current_guids = {m["guid"] for m in self._last_messages if m.get("guid")}
        known_guids = self._known_message_guids.get(chat_guid)
        # None (never rendered this chat before) means "just opened it" --
        # treat everything already there as the baseline, not "new", so
        # opening a chat with history doesn't animate the whole thread in at
        # once. Only a guid that showed up since the *last* render (i.e. a
        # message actually just sent/received) counts as new.
        new_guids = (current_guids - known_guids) if known_guids is not None else set()
        self._known_message_guids[chat_guid] = current_guids

        # get-messages returns newest-first; render oldest-first, top to bottom.
        messages = list(reversed(result or []))
        prev = None
        for i, message in enumerate(messages):
            if self._needs_separator(prev, message):
                column.append(self._build_separator(message))
            next_message = messages[i + 1] if i + 1 < len(messages) else None
            is_last_in_group = not (next_message is not None and self._same_group(message, next_message))
            animate = message.get("guid") in new_guids
            column.append(self._build_row(message, prev, is_last_in_group, animate=animate))
            prev = message

        if messages and messages[-1].get("isFromMe"):
            column.append(self._build_read_receipt(messages[-1]))

        adj = scroller.get_vadjustment()
        adj.set_value(adj.get_upper())

    @staticmethod
    def _needs_separator(prev, message) -> bool:
        if prev is None:
            return True
        prev_date, cur_date = prev.get("dateCreated"), message.get("dateCreated")
        if not prev_date or not cur_date:
            return False
        return (cur_date - prev_date) / 1000 > _GROUP_GAP_SECONDS * 5

    @classmethod
    def _same_group(cls, prev, message) -> bool:
        """Same visual run as the previous message: same sender, and no
        timestamp separator would be inserted between them. Tying this to
        _needs_separator (rather than a separate, tighter time threshold) is
        what makes "no header shown" and "avatar shown once, not per-message"
        agree with each other -- they used to use different thresholds, which
        is why a burst of messages under one header still showed a repeated
        avatar on every line."""
        if prev is None:
            return False
        if bool(prev.get("isFromMe")) != bool(message.get("isFromMe")):
            return False
        if prev.get("senderName") != message.get("senderName"):
            return False
        return not cls._needs_separator(prev, message)

    def _build_separator(self, message: dict) -> Gtk.Widget:
        dt = _dt(message.get("dateCreated"))
        label = Gtk.Label(label=_format_separator(dt) if dt else "")
        label.add_css_class("timestamp-separator")
        label.set_margin_top(12)
        label.set_margin_bottom(8)
        return label

    def _build_read_receipt(self, message: dict) -> Gtk.Widget:
        text = "Read" if message.get("dateRead") else ("Delivered" if message.get("isDelivered") else "")
        label = Gtk.Label(label=text, xalign=1, halign=Gtk.Align.END)
        label.add_css_class("read-receipt")
        label.set_margin_top(2)
        return label

    def _build_row(self, message: dict, prev: dict | None, is_last_in_group: bool, animate: bool = False) -> Gtk.Widget:
        is_from_me = bool(message.get("isFromMe"))
        grouped = self._same_group(prev, message)
        sender_name = message.get("senderName")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2 if grouped else 8)
        row.set_halign(Gtk.Align.END if is_from_me else Gtk.Align.START)

        if animate:
            # Fade the newly-sent/received bubble in rather than having it
            # just pop into the thread -- only for guids not seen on a
            # previous render (see _on_messages_loaded), so opening a chat
            # with history doesn't replay this for every message at once.
            row.set_opacity(0)
            row.connect("map", self._play_row_entrance)

        if not is_from_me:
            # Real Messages aligns the avatar with the LAST bubble of a
            # consecutive run, not the first -- an empty same-size slot keeps
            # every other row in the run indented to match.
            avatar_slot = Gtk.Box(valign=Gtk.Align.END)
            avatar_slot.set_size_request(28, 28)
            if is_last_in_group:
                avatar_slot.append(make_color_avatar(
                    sender_name or "?", size=28, avatar_path=message.get("senderAvatarPath")))
            row.append(avatar_slot)

        bubble_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bubble_column.set_halign(Gtk.Align.END if is_from_me else Gtk.Align.START)
        row.append(bubble_column)

        if not is_from_me and sender_name and not grouped:
            name_label = Gtk.Label(label=sender_name, xalign=0)
            name_label.add_css_class("sender-name")
            bubble_column.append(name_label)

        for attachment in message.get("attachments") or []:
            local_path = attachment.get("localPath")
            mime_type = attachment.get("mimeType") or ""
            if local_path and mime_type.startswith("image/"):
                image_widget = _build_attachment_image(local_path)
                if image_widget is not None:
                    bubble_column.append(image_widget)

        text = message.get("text") or ""
        url_matches = list(_URL_RE.finditer(text)) if text else []

        if text.strip():
            bubble = Gtk.Box()
            bubble.add_css_class("bubble-outgoing" if is_from_me else "bubble-incoming")
            bubble_column.append(bubble)

            wrapped = _wrap_message_text(text)
            label = Gtk.Label(xalign=0)
            if url_matches:
                label.set_use_markup(True)
                label.set_markup(_linkify(wrapped, is_from_me))
            else:
                label.set_label(wrapped)
            bubble.append(label)

        if url_matches:
            # Only the first link gets a preview card -- matches real
            # iMessage (one preview per message even with multiple links).
            # Extracted from the original unwrapped text, not the
            # word-wrapped label text, so a long URL that got hyphen-broken
            # for display still previews as the real, complete URL.
            url = url_matches[0].group(0)
            bubble_column.append(_build_link_preview(url, _href_for(url)))

        return row

    def _play_row_entrance(self, row: Gtk.Widget):
        target = Adw.CallbackAnimationTarget.new(row.set_opacity)
        animation = Adw.TimedAnimation.new(row, 0, 1, 350, target)
        animation.set_easing(Adw.Easing.EASE_OUT_QUAD)
        self._row_animations.append(animation)
        animation.play()
