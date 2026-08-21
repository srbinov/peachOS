"""Sidebar: search bar + pinned-contacts tile grid + regular chat list, matching
macOS Messages' own sidebar layout. Populated from the backend's "list-chats" IPC
method. Title/avatar color/initials come from the backend's contact-resolved
fields (title, handles[].displayName/color/initials) rather than raw
chat_identifier/phone-number data -- see
bluebubbles-app/lib/peachos_ipc/ipc_server.dart's _serializeChat/_serializeHandle.
"""
import os
import random

from gi.repository import Adw, Gdk, GObject, Gtk

import avatar_overrides
import contact_name_overrides
from image_utils import load_contained_texture, load_cover_texture

# The synced-from-iCloud/user-uploaded photo path is always .jpg/.png; the
# emoji picker's files are always .svg (macOS_Tahoe_SYSICONS/apple-emoji) --
# a reliable, cheap way to tell "this avatar_path is an emoji" from "this is
# a real photo" without needing a separate explicit flag threaded through
# every caller.
_EMOJI_SIZE_FRACTION = 0.7  # explicit user request: emoji reads as a badge on
                            # the circle, not a full-bleed fill like a photo

# Real macOS Messages: an unmatched/no-photo contact is a flat mid-gray circle
# with white initials, not a per-contact color -- matching that exactly rather
# than the earlier rainbow-hash palette this app used (explicit user
# correction). Single fixed CSS class (style.py) rather than a per-instance
# CssProvider -- one earlier had every chat row and message bubble allocate its
# own Gtk.CssProvider (60+ per chat list render, one more per rendered
# message), which piled up fast and is suspected to have contributed to a
# gnome-shell hang under this VM's already-fragile vmwgfx compositor.


def resolve_display_name(handle: dict) -> str:
    """A locally-renamed contact's (see contact_name_overrides.py) name wins
    over whatever the backend/iCloud resolved -- the override is a peachOS-
    only relabel, never written back to iCloud or the server, so this is the
    one place that has to check for it before trusting displayName."""
    address = handle.get("address") or ""
    override = contact_name_overrides.get_override(address)
    return override or handle.get("displayName") or address or "Unknown"


def _chat_title(chat: dict) -> str:
    # A 1:1 chat's title is really just its one participant's name -- route
    # through resolve_display_name so a local rename shows up here too, not
    # just on the Contact Details page it was made from.
    handles = chat.get("handles") or []
    if len(handles) == 1:
        resolved = resolve_display_name(handles[0])
        if resolved:
            return resolved
    return chat.get("title") or chat.get("displayName") or chat.get("chatIdentifier") or "Unknown"


_GROUP_AVATAR_MAX_MEMBERS = 4
_GROUP_AVATAR_MINI_FRACTION = {1: 1.0, 2: 0.62, 3: 0.52, 4: 0.48}

# Several hand-picked (halign, valign) slot arrangements per member count --
# one gets picked pseudo-randomly per chat (seeded by the chat's own guid, so
# a given chat's icon is stable across re-renders instead of jittering, but
# different group chats don't all look identical) -- explicit user request
# after every group icon came out looking the same. Every arrangement here
# still tiles cleanly within the outer circle; count 4 only has one entry
# since a 2x2 grid is really the only clean way to fit four circles.
_GROUP_AVATAR_LAYOUTS = {
    1: [[(Gtk.Align.CENTER, Gtk.Align.CENTER)]],
    2: [
        [(Gtk.Align.START, Gtk.Align.CENTER), (Gtk.Align.END, Gtk.Align.CENTER)],
        [(Gtk.Align.START, Gtk.Align.START), (Gtk.Align.END, Gtk.Align.END)],
        [(Gtk.Align.END, Gtk.Align.START), (Gtk.Align.START, Gtk.Align.END)],
    ],
    3: [
        [(Gtk.Align.CENTER, Gtk.Align.START), (Gtk.Align.START, Gtk.Align.END), (Gtk.Align.END, Gtk.Align.END)],
        [(Gtk.Align.CENTER, Gtk.Align.END), (Gtk.Align.START, Gtk.Align.START), (Gtk.Align.END, Gtk.Align.START)],
        [(Gtk.Align.START, Gtk.Align.CENTER), (Gtk.Align.END, Gtk.Align.START), (Gtk.Align.END, Gtk.Align.END)],
        [(Gtk.Align.END, Gtk.Align.CENTER), (Gtk.Align.START, Gtk.Align.START), (Gtk.Align.START, Gtk.Align.END)],
    ],
    4: [
        [(Gtk.Align.START, Gtk.Align.START), (Gtk.Align.END, Gtk.Align.START),
         (Gtk.Align.START, Gtk.Align.END), (Gtk.Align.END, Gtk.Align.END)],
    ],
}


def person_pseudo_guid(address: str) -> str:
    """Synthetic chat guid for a single group member's own Contact Details
    page (avatar_overrides.py is keyed by chat guid, and a group member
    isn't a chat) -- lets a photo picked for "this specific person" from
    inside a group's member list stick to them independently of any separate
    real 1:1 chat that might exist with the same person."""
    return f"person:{address}"


def resolve_avatar_path(handle: dict) -> str | None:
    address = handle.get("address") or ""
    if address:
        override = avatar_overrides.get_override(person_pseudo_guid(address))
        if override and os.path.isfile(override):
            return override
    return handle.get("avatarPath")


def make_group_avatar(handles: list[dict], size: int = 44, seed: str | None = None) -> Gtk.Widget:
    """Composite group-chat icon: the outer circle contains one small circle
    per OTHER participant (handles already excludes the local user -- see
    build_chat_avatar), matching real macOS Messages' own 2-up/3-up/2x2
    mini-avatar cluster rather than a single flat icon or plain initial."""
    members = list(handles[:_GROUP_AVATAR_MAX_MEMBERS])
    count = max(1, len(members))
    rng = random.Random(seed)
    slots = rng.choice(_GROUP_AVATAR_LAYOUTS[count])
    rng.shuffle(members)  # who lands in which slot varies too, not just the geometry
    mini_size = round(size * _GROUP_AVATAR_MINI_FRACTION[count])
    margin = round(size * 0.05)

    # The clip (overflow=HIDDEN + .color-avatar's border-radius) has to live
    # on the Overlay itself, not a child of it -- overlay children are
    # painted as siblings stacked on top of the main child, not clipped by
    # anything the main child alone does.
    overlay = Gtk.Overlay(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    overlay.set_size_request(size, size)
    overlay.add_css_class("color-avatar")
    overlay.set_overflow(Gtk.Overflow.HIDDEN)
    filler = Gtk.Box()
    filler.set_size_request(size, size)
    overlay.set_child(filler)

    for handle, (halign, valign) in zip(members, slots):
        mini = make_color_avatar(resolve_display_name(handle), size=mini_size, avatar_path=resolve_avatar_path(handle))
        # A visible ring around each mini avatar -- without it, same-color
        # circles packed edge-to-edge just blend into one gray blob with
        # floating initials (confirmed against a user screenshot).
        mini.add_css_class("group-mini-avatar")
        mini.set_halign(halign)
        mini.set_valign(valign)
        if halign == Gtk.Align.START:
            mini.set_margin_start(margin)
        elif halign == Gtk.Align.END:
            mini.set_margin_end(margin)
        if valign == Gtk.Align.START:
            mini.set_margin_top(margin)
        elif valign == Gtk.Align.END:
            mini.set_margin_bottom(margin)
        overlay.add_overlay(mini)

    return overlay


def build_chat_avatar(chat: dict, size: int = 44) -> Gtk.Widget:
    """The chat's own icon, wherever it's shown (sidebar, header pill,
    Contact Details' big avatar). A user-set override (Add Photo / Pick
    Emoji from Contact Details -- see avatar_overrides.py, works the same
    for a group as a 1:1) always wins; a group with no override gets the
    composite mini-avatar cluster (stable per chat guid -- see
    make_group_avatar); a 1:1 with no override falls back to its one
    participant's synced-from-iCloud photo, same as before."""
    override = avatar_overrides.get_override(chat.get("guid", ""))
    if override and os.path.isfile(override):
        return make_color_avatar(_chat_title(chat), size=size, avatar_path=override)

    handles = chat.get("handles") or []
    if len(handles) > 1:
        return make_group_avatar(handles, size=size, seed=chat.get("guid"))

    avatar_path = handles[0].get("avatarPath") if handles else None
    return make_color_avatar(_chat_title(chat), size=size, avatar_path=avatar_path)


def _initials(title: str) -> str | None:
    """None means "no real name to initial" (an unmatched phone number/email) --
    real macOS Messages shows a plain silhouette for those rather than letters,
    so a raw number like "+1 630-642-4676" should never render digits ("16")."""
    if not any(c.isalpha() for c in title):
        return None
    words = [w for w in title.replace("+", "").split() if w and w[0].isalpha()]
    if not words:
        return None
    if len(words) == 1:
        return words[0][:1].upper()
    # "Will G" -> "WG" (run together, no space -- explicit user correction;
    # an earlier version space-separated these).
    return f"{words[0][:1].upper()}{words[-1][:1].upper()}"


def make_color_avatar(title: str, size: int = 44, avatar_path: str | None = None) -> Gtk.Widget:
    """The contact's real photo (synced from iCloud -- see avatarPath on
    ipc_server.dart's _serializeHandle/_serializeMessage) when there is one;
    otherwise a flat gray circle with white initials (or a generic person
    silhouette for unmatched numbers, see _initials) -- matches real macOS
    Messages' own unmatched-contact style exactly (confirmed against a
    user-provided reference), not a per-contact color.
    Both branches are wrapped in a fixed-size Box for layout consistency, but
    that alone isn't the real fix: loading the source file at its native
    resolution (Gtk.Picture.new_for_filename) combined with content_fit=COVER
    means the picture scales UP to fill however much space its parent
    allocates it -- and Gtk.HeaderBar's title_widget slot allocates far more
    than the widget's own size_request/hexpand=False asks for (measured
    directly: a 22px request got a 274px allocation there). content_fit=
    CONTAIN never scales past the paintable's own intrinsic size, which is
    what actually keeps a pre-scaled avatar small even inside that oversized
    allocation -- so this can't just switch to COVER to fill the circle;
    image_utils.py's helpers pre-decode to the exact final pixel size
    themselves instead."""
    wrapper = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=False, vexpand=False)
    wrapper.set_size_request(size, size)
    wrapper.add_css_class("photo-avatar")  # gray circle fallback -- see style.py
    # border-radius (CSS, .photo-avatar/.color-avatar both set it) only clips
    # if the widget also opts into clipping -- GTK4 has no CSS "overflow"
    # property, only this same-named widget property (see the .photo-avatar
    # comment in style.py). This has to be on the WRAPPER, not the picture --
    # a square photo escaped the circle entirely (confirmed live) because an
    # earlier version set overflow on the picture while the border-radius
    # class lived on the wrapper, so neither widget alone had both.
    wrapper.set_overflow(Gtk.Overflow.HIDDEN)

    if avatar_path and os.path.isfile(avatar_path):
        is_emoji = avatar_path.lower().endswith(".svg")
        if is_emoji:
            # Emoji reads as a badge on the gray circle, not a full-bleed fill
            # -- explicit user request, and also what avoids clipping real
            # content (a flag/face emoji cropped to fill the circle lost
            # visible detail; shrinking instead of cropping guarantees the
            # whole glyph stays visible).
            picture_size = round(size * _EMOJI_SIZE_FRACTION)
            texture = load_contained_texture(avatar_path, picture_size)
        else:
            picture_size = size
            texture = load_cover_texture(avatar_path, picture_size)

        if texture is not None:
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_size_request(picture_size, picture_size)
            picture.set_hexpand(False)
            picture.set_vexpand(False)
            picture.set_halign(Gtk.Align.CENTER)
            picture.set_valign(Gtk.Align.CENTER)
            wrapper.append(picture)
            return wrapper

    wrapper.remove_css_class("photo-avatar")
    wrapper.add_css_class("color-avatar")

    initials = _initials(title)
    if initials:
        # halign=CENTER alone doesn't do it: a Gtk.Box only positions a child
        # within *extra* space the child has opted into via hexpand/vexpand --
        # without that, the box allocates the label exactly its natural
        # (unpadded) size and packs it flush at the start, and halign has
        # nothing to center it within. Measured directly (get_allocation()) on
        # a live instance to confirm: left_gap=0, right_gap=16 with hexpand
        # unset; hexpand=True fixes it to equal gaps on both sides.
        child = Gtk.Label(
            label=initials, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            hexpand=True, vexpand=True, justify=Gtk.Justification.CENTER, xalign=0.5)
        child.add_css_class("title-3" if size >= 48 else "title-4")
    else:
        child = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        child.set_pixel_size(round(size * 0.6))
        child.set_hexpand(True)
        child.set_vexpand(True)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.CENTER)
    child.add_css_class("avatar-initials")
    wrapper.append(child)
    return wrapper


class ChatListView(Adw.Bin):
    __gtype_name__ = "ChatListView"

    __gsignals__ = {
        "chat-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, ipc_client):
        super().__init__()
        self._ipc = ipc_client
        self._all_chats = []
        self._by_guid = {}
        self._selected_guid = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Search")
        self._search_entry.set_margin_top(8)
        self._search_entry.set_margin_bottom(4)
        self._search_entry.set_margin_start(10)
        self._search_entry.set_margin_end(10)
        self._search_entry.connect("search-changed", self._on_search_changed)
        root.append(self._search_entry)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        root.append(scroller)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroller.set_child(content)

        self._pinned_flow = Gtk.FlowBox()
        self._pinned_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._pinned_flow.set_max_children_per_line(3)
        self._pinned_flow.set_min_children_per_line(3)
        self._pinned_flow.set_homogeneous(True)
        self._pinned_flow.set_margin_start(6)
        self._pinned_flow.set_margin_end(6)
        self._pinned_flow.set_margin_bottom(6)
        self._pinned_flow.connect("child-activated", self._on_pinned_activated)
        content.append(self._pinned_flow)

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.connect("row-selected", self._on_row_selected)
        content.append(self._list_box)

        self.reload()

    def reload(self):
        self._ipc.request("list-chats", callback=self._on_chats_loaded)

    def _on_chats_loaded(self, result, error):
        if error is not None or result is None:
            return
        self._all_chats = sorted(result, key=lambda c: c.get("dbOnlyLatestMessageDate") or 0, reverse=True)
        self._by_guid = {c["guid"]: c for c in self._all_chats}
        self._render(self._search_entry.get_text())

    def _on_search_changed(self, entry):
        self._render(entry.get_text())

    def _render(self, query: str):
        query = (query or "").strip().lower()

        def matches(chat):
            if not query:
                return True
            return query in _chat_title(chat).lower() or query in (chat.get("previewText") or "").lower()

        visible = [c for c in self._all_chats if matches(c)]
        pinned = [c for c in visible if c.get("isPinned")] if not query else []
        pinned_guids = {c["guid"] for c in pinned}
        regular = [c for c in visible if c["guid"] not in pinned_guids]

        child = self._pinned_flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._pinned_flow.remove(child)
            child = nxt
        for chat in pinned:
            self._pinned_flow.append(self._build_pinned_tile(chat))
        self._pinned_flow.set_visible(bool(pinned))

        child = self._list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt
        for chat in regular:
            self._list_box.append(self._build_row(chat))

    def _build_pinned_tile(self, chat: dict) -> Gtk.Widget:
        title = _chat_title(chat)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("pinned-tile")
        box.guid = chat["guid"]
        box.append(build_chat_avatar(chat, size=56))

        name_label = Gtk.Label(label=title, ellipsize=3, max_width_chars=10, justify=Gtk.Justification.CENTER)
        name_label.add_css_class("pinned-name")
        box.append(name_label)

        if chat.get("hasUnreadMessage"):
            dot = Gtk.Box(halign=Gtk.Align.CENTER)
            dot.add_css_class("unread-dot")
            box.append(dot)

        self._attach_context_menu(box, chat)
        return box

    def _on_pinned_activated(self, _flow, child):
        guid = child.get_child().guid
        self._selected_guid = guid
        self.emit("chat-selected", self._by_guid[guid])

    def _build_row(self, chat: dict) -> Gtk.Widget:
        row = Gtk.ListBoxRow()
        row.guid = chat["guid"]

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        row.set_child(box)

        title = _chat_title(chat)
        avatar = build_chat_avatar(chat)
        box.append(avatar)

        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        label_box.set_hexpand(True)
        box.append(label_box)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_box.append(top_row)

        title_label = Gtk.Label(label=title, xalign=0, ellipsize=3)
        title_label.add_css_class("chat-row-title")
        title_label.set_hexpand(True)
        top_row.append(title_label)

        time_label = Gtk.Label(label=_format_time(chat.get("dbOnlyLatestMessageDate")))
        time_label.add_css_class("chat-row-time")
        top_row.append(time_label)

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_box.append(bottom_row)

        preview = chat.get("previewText") or ""
        preview_label = Gtk.Label(label=preview, xalign=0, ellipsize=3)
        preview_label.add_css_class("chat-row-subtitle")
        preview_label.set_hexpand(True)
        bottom_row.append(preview_label)

        if chat.get("hasUnreadMessage"):
            dot = Gtk.Box()
            dot.add_css_class("unread-dot")
            dot.set_valign(Gtk.Align.CENTER)
            bottom_row.append(dot)

        self._attach_context_menu(row, chat)
        return row

    def _on_row_selected(self, _list_box, row):
        if row is None:
            return
        self._selected_guid = row.guid
        self.emit("chat-selected", self._by_guid[row.guid])

    def _attach_context_menu(self, widget: Gtk.Widget, chat: dict):
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", lambda _g, _n, x, y: self._show_context_menu(widget, chat, x, y))
        widget.add_controller(click)

    def _show_context_menu(self, widget: Gtk.Widget, chat: dict, x: float, y: float):
        popover = Gtk.Popover()
        popover.set_parent(widget)
        popover.set_has_arrow(False)
        # Gdk.Rectangle(x=..., y=...) kwarg construction is deprecated and
        # silently ignores every argument (confirmed live: always yields
        # (0,0,0,0)) -- fields have to be set individually after construction.
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        popover.set_child(box)

        is_pinned = bool(chat.get("isPinned"))
        pin_btn = Gtk.Button(label="Unpin Conversation" if is_pinned else "Pin Conversation")
        pin_btn.add_css_class("flat")
        pin_btn.set_halign(Gtk.Align.FILL)
        pin_btn.get_child().set_halign(Gtk.Align.START)
        pin_btn.connect("clicked", lambda _b: self._toggle_pin(chat, not is_pinned, popover))
        box.append(pin_btn)

        popover.popup()

    def _toggle_pin(self, chat: dict, new_value: bool, popover: Gtk.Popover):
        popover.popdown()
        self._ipc.request(
            "set-chat-pinned",
            {"chatGuid": chat["guid"], "pinned": new_value},
            callback=lambda result, error: self.reload() if error is None else None,
        )


def _format_time(millis) -> str:
    if not millis:
        return ""
    import datetime

    dt = datetime.datetime.fromtimestamp(millis / 1000)
    now = datetime.datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%-I:%M %p")
    if (now.date() - dt.date()).days < 7:
        return dt.strftime("%a")
    return dt.strftime("%-m/%-d/%y")
