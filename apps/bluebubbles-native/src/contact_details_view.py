"""Contact Details slide-in page -- pushed onto the content pane's
Adw.NavigationView when the conversation header is clicked (see main.py and
ConversationHeader/ConversationView's "details-requested" signal).

Shows: big avatar (clickable -> Add Photo / Pick Emoji), name, phone/email or
member list for groups, an "Add Contact" form for unmatched 1:1 numbers (real
write to the Mac's Contacts.app via the backend's "create-contact" IPC method
-- see ipc_server.dart's _createContact), and an attachments list built from
whatever messages are already loaded in the conversation (no extra IPC round
trip; full binary download/thumbnailing is a separate, later feature).
"""
import os

from gi.repository import Adw, Gio, GLib, Gtk

import avatar_overrides
import contact_name_overrides
from chat_list_view import (
    _chat_title, build_chat_avatar, make_color_avatar, person_pseudo_guid,
    resolve_avatar_path, resolve_display_name,
)
from conversation_view import _URL_RE, _extract_domain, _href_for
from emoji_picker import EmojiPickerDialog
from photo_crop_dialog import PhotoCropDialog

_IMAGE_MIME_PREFIXES = ("image/",)
_VIDEO_MIME_PREFIXES = ("video/",)


def _is_unmatched_handle(handle: dict) -> bool:
    """True when displayName is just the formatted address (no real iCloud
    contact match) -- Handle.displayName in the backend falls back to that
    exact string when contactsV2 is empty, so comparing against it (with
    punctuation/whitespace stripped) is a reliable enough signal without
    needing a separate "isMatched" field from the backend."""
    display = (handle.get("displayName") or "").strip()
    address = (handle.get("address") or "").strip()
    if not display or not address:
        return True
    strip = lambda s: "".join(c for c in s if c.isalnum()).lower()
    return strip(display) == strip(address)


def _format_bytes(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _attachment_icon_name(mime_type: str | None) -> str:
    mime_type = mime_type or ""
    if mime_type.startswith(_IMAGE_MIME_PREFIXES):
        return "image-x-generic-symbolic"
    if mime_type.startswith(_VIDEO_MIME_PREFIXES):
        return "video-x-generic-symbolic"
    if mime_type.startswith("audio/"):
        return "audio-x-generic-symbolic"
    return "text-x-generic-symbolic"


def _member_pseudo_chat(handle: dict) -> dict:
    """Wraps a single group member as a stand-in "chat" (see
    chat_list_view.person_pseudo_guid) so clicking their name in the Members
    list can reuse this exact same build_details_page function for their own
    info screen -- editable name/photo, everything -- with no separate
    per-person page implementation needed."""
    return {"guid": person_pseudo_guid(handle.get("address") or ""), "title": None, "handles": [handle]}


def build_details_page(chat: dict, messages: list, ipc_client, parent_window: Gtk.Window,
                        on_avatar_changed, push_page=None) -> Adw.NavigationPage:
    title = _chat_title(chat)
    handles = chat.get("handles") or []
    is_group = len(handles) > 1

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    toolbar.set_content(scroller)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    root.set_margin_top(24)
    root.set_margin_bottom(24)
    root.set_margin_start(24)
    root.set_margin_end(24)
    scroller.set_child(root)

    # --- big avatar + name -------------------------------------------------
    avatar_holder = Gtk.Box(halign=Gtk.Align.CENTER)
    root.append(avatar_holder)

    def render_avatar():
        child = avatar_holder.get_first_child()
        if child is not None:
            avatar_holder.remove(child)
        avatar_holder.append(build_chat_avatar(chat, size=120))

    render_avatar()

    avatar_btn = Gtk.Button(label="Edit Photo", halign=Gtk.Align.CENTER)
    avatar_btn.add_css_class("flat")
    root.append(avatar_btn)

    def refresh_avatar():
        render_avatar()
        if on_avatar_changed:
            on_avatar_changed()

    def on_pick_photo(_btn):
        dialog = Gtk.FileDialog(title="Choose a Photo")
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        image_filter.add_mime_type("image/png")
        image_filter.add_mime_type("image/jpeg")
        image_filter.add_mime_type("image/gif")
        image_filter.add_mime_type("image/webp")
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

            crop_dialog = PhotoCropDialog(parent_window, file.get_path(), chat["guid"])

            def on_cropped(_dialog, saved_path):
                avatar_overrides.set_override(chat["guid"], saved_path)
                refresh_avatar()

            crop_dialog.connect("photo-cropped", on_cropped)
            crop_dialog.present()

        dialog.open(parent_window, None, on_chosen)

    def on_pick_emoji(_btn):
        picker = EmojiPickerDialog(parent_window)

        def on_emoji_picked(_picker, file_path):
            avatar_overrides.set_override(chat["guid"], file_path)
            refresh_avatar()

        picker.connect("emoji-picked", on_emoji_picked)
        picker.present()

    def on_avatar_button_clicked(button):
        popover = Gtk.Popover()
        popover.set_parent(button)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        popover.set_child(box)

        photo_btn = Gtk.Button(label="Add Photo…")
        photo_btn.add_css_class("flat")
        photo_btn.get_child().set_halign(Gtk.Align.START)
        photo_btn.connect("clicked", lambda _b: (popover.popdown(), on_pick_photo(_b)))
        box.append(photo_btn)

        emoji_btn = Gtk.Button(label="Pick an Emoji…")
        emoji_btn.add_css_class("flat")
        emoji_btn.get_child().set_halign(Gtk.Align.START)
        emoji_btn.connect("clicked", lambda _b: (popover.popdown(), on_pick_emoji(_b)))
        box.append(emoji_btn)

        popover.popup()

    avatar_btn.connect("clicked", on_avatar_button_clicked)

    name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.CENTER)
    root.append(name_row)

    name_label = Gtk.Label(label=title)
    name_label.add_css_class("title-1")
    name_row.append(name_label)

    # Renaming is local-only (see contact_name_overrides.py) and only makes
    # sense for a single real person, not a group's own name or an unmatched
    # number with no address to key the override by.
    primary_handle = handles[0] if (not is_group and handles) else None
    if primary_handle is not None and primary_handle.get("address"):
        edit_btn = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER)
        edit_btn.add_css_class("flat")
        edit_btn.add_css_class("circular")
        name_row.append(edit_btn)

        name_edit_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, halign=Gtk.Align.CENTER)
        name_edit_row.set_visible(False)
        root.append(name_edit_row)

        name_entry = Gtk.Entry(width_chars=20)
        name_edit_row.append(name_entry)

        save_name_btn = Gtk.Button(icon_name="object-select-symbolic", valign=Gtk.Align.CENTER)
        save_name_btn.add_css_class("flat")
        save_name_btn.add_css_class("circular")
        name_edit_row.append(save_name_btn)

        cancel_name_btn = Gtk.Button(icon_name="window-close-symbolic", valign=Gtk.Align.CENTER)
        cancel_name_btn.add_css_class("flat")
        cancel_name_btn.add_css_class("circular")
        name_edit_row.append(cancel_name_btn)

        def start_edit(_btn):
            name_entry.set_text(name_label.get_label())
            name_row.set_visible(False)
            name_edit_row.set_visible(True)
            name_entry.grab_focus()

        def cancel_edit(_btn=None):
            name_edit_row.set_visible(False)
            name_row.set_visible(True)

        def save_edit(_btn=None):
            new_name = name_entry.get_text().strip()
            cancel_edit()
            if not new_name or new_name == name_label.get_label():
                return
            contact_name_overrides.set_override(primary_handle["address"], new_name)
            name_label.set_label(new_name)
            if on_avatar_changed:
                on_avatar_changed()

        edit_btn.connect("clicked", start_edit)
        cancel_name_btn.connect("clicked", cancel_edit)
        save_name_btn.connect("clicked", save_edit)
        name_entry.connect("activate", save_edit)

    if not is_group and handles:
        address = handles[0].get("address") or ""
        if address:
            address_label = Gtk.Label(label=address, halign=Gtk.Align.CENTER)
            address_label.add_css_class("dim-label")
            root.append(address_label)

    # --- members (group) or add-contact form (unmatched 1:1) ---------------
    if is_group:
        root.append(_section_heading("Members"))
        members_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        members_box.add_css_class("boxed-list")
        root.append(members_box)

        def rebuild_members():
            child = members_box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                members_box.remove(child)
                child = nxt
            for handle in handles:
                members_box.append(_member_row(handle))

        rebuild_members()

        def on_member_activated(_box, row):
            if push_page is None:
                return
            handle = handles[row.get_index()]
            member_chat = _member_pseudo_chat(handle)

            def refresh_member():
                # The member's own edited name/photo needs to show up back
                # here too, not just on the page they edited it from.
                rebuild_members()
                if on_avatar_changed:
                    on_avatar_changed()

            member_page = build_details_page(
                member_chat, [], ipc_client, parent_window, refresh_member, push_page=push_page)
            push_page(member_page)

        members_box.connect("row-activated", on_member_activated)
    elif handles and _is_unmatched_handle(handles[0]):
        root.append(_section_heading("Add Contact"))
        root.append(_build_add_contact_form(handles[0]["address"], ipc_client))

    # --- links ---------------------------------------------------------
    links = []
    seen_hrefs = set()
    for message in messages:
        for m in _URL_RE.finditer(message.get("text") or ""):
            url = m.group(0)
            href = _href_for(url)
            if href not in seen_hrefs:
                seen_hrefs.add(href)
                links.append((url, href))

    root.append(_section_heading("Links"))
    if links:
        links_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        links_box.add_css_class("boxed-list")
        for url, href in links:
            links_box.append(_link_row(url, href))
        root.append(links_box)
    else:
        empty_links_label = Gtk.Label(label="No links in the loaded messages.", xalign=0)
        empty_links_label.add_css_class("dim-label")
        root.append(empty_links_label)

    # --- attachments ---------------------------------------------------
    attachments = []
    for message in messages:
        for attachment in message.get("attachments") or []:
            attachments.append(attachment)

    root.append(_section_heading("Attachments"))
    if attachments:
        attachments_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        attachments_box.add_css_class("boxed-list")
        for attachment in attachments:
            attachments_box.append(_attachment_row(attachment))
        root.append(attachments_box)
    else:
        empty_label = Gtk.Label(label="No attachments in the loaded messages.", xalign=0)
        empty_label.add_css_class("dim-label")
        root.append(empty_label)

    page = Adw.NavigationPage(title=title, child=toolbar)
    return page


def _section_heading(text: str) -> Gtk.Widget:
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("heading")
    label.set_margin_top(6)
    return label


def _member_row(handle: dict) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_margin_top(8)
    row.set_margin_bottom(8)
    row.set_margin_start(10)
    row.set_margin_end(10)

    name = resolve_display_name(handle)
    row.append(make_color_avatar(name, size=36, avatar_path=resolve_avatar_path(handle)))

    text_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    text_column.append(Gtk.Label(label=name, xalign=0))
    address = handle.get("address")
    if address and address != name:
        address_label = Gtk.Label(label=address, xalign=0)
        address_label.add_css_class("dim-label")
        address_label.add_css_class("caption")
        text_column.append(address_label)
    row.append(text_column)
    return row


def _link_row(url: str, href: str) -> Gtk.Widget:
    button = Gtk.Button()
    button.add_css_class("flat")

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_margin_top(8)
    row.set_margin_bottom(8)
    row.set_margin_start(10)
    row.set_margin_end(10)

    icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
    icon.set_pixel_size(20)
    row.append(icon)

    text_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    text_column.append(Gtk.Label(label=_extract_domain(href), xalign=0))
    url_label = Gtk.Label(label=url, xalign=0, ellipsize=3, max_width_chars=32)
    url_label.add_css_class("dim-label")
    url_label.add_css_class("caption")
    text_column.append(url_label)
    row.append(text_column)

    button.set_child(row)
    button.connect("clicked", lambda _b: Gio.AppInfo.launch_default_for_uri(href, None))
    return button


def _attachment_row(attachment: dict) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_margin_top(8)
    row.set_margin_bottom(8)
    row.set_margin_start(10)
    row.set_margin_end(10)

    icon = Gtk.Image.new_from_icon_name(_attachment_icon_name(attachment.get("mimeType")))
    icon.set_pixel_size(24)
    row.append(icon)

    text_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    name = attachment.get("transferName") or "Attachment"
    text_column.append(Gtk.Label(label=name, xalign=0, ellipsize=3, max_width_chars=30))
    size_label = _format_bytes(attachment.get("totalBytes"))
    if size_label:
        subtitle = Gtk.Label(label=size_label, xalign=0)
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        text_column.append(subtitle)
    row.append(text_column)
    return row


def _build_add_contact_form(address: str, ipc_client) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    first_entry = Adw.EntryRow(title="First Name")
    box.append(first_entry)
    last_entry = Adw.EntryRow(title="Last Name")
    box.append(last_entry)

    status_label = Gtk.Label(xalign=0, wrap=True)
    status_label.set_visible(False)
    box.append(status_label)

    save_btn = Gtk.Button(label="Add Contact")
    save_btn.add_css_class("suggested-action")
    save_btn.set_halign(Gtk.Align.START)
    box.append(save_btn)

    def on_save(_btn):
        first_name = first_entry.get_text().strip()
        last_name = last_entry.get_text().strip()
        if not first_name and not last_name:
            status_label.set_text("Enter at least a first or last name.")
            status_label.set_visible(True)
            return

        save_btn.set_sensitive(False)
        status_label.set_visible(False)

        def on_response(result, error):
            save_btn.set_sensitive(True)
            if error is not None:
                status_label.set_text(f"Failed to add contact: {error}")
                status_label.set_visible(True)
                return
            status_label.remove_css_class("error")
            status_label.add_css_class("success")
            status_label.set_text("Contact added.")
            status_label.set_visible(True)

        ipc_client.request(
            "create-contact",
            {"firstName": first_name, "lastName": last_name, "address": address},
            callback=on_response,
        )

    save_btn.connect("clicked", on_save)
    return box
