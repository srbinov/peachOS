"""App-wide CSS -- mirrors macOS Messages' own visual language: pinned-contact
tile grid, search bar, pill-shaped conversation header, iMessage-style bubbles
(blue outgoing, gray incoming), rounded compose field.
"""

STYLE_CSS = b"""
searchentry {
    border-radius: 10px;
}

/* Unmatched-contact fallback avatar -- flat mid-gray with white initials,
   matching real macOS Messages exactly (confirmed against a user-provided
   reference; an earlier per-contact rainbow palette here was wrong). */
.color-avatar {
    border-radius: 999px;
    background-color: #8E8E93;
}

/* Real contact photo avatars (synced from iCloud via the server) -- a static,
   reusable clip shape rather than a per-instance CssProvider (see
   make_color_avatar()'s docstring for why that pattern is avoided here).
   Clipping to this radius also needs Gtk.Widget.set_overflow(HIDDEN) in code --
   GTK4's CSS engine has no "overflow" property (confirmed: "No property named
   \"overflow\"" from a live Gtk.CssProvider parse), only the same-named widget
   property (gtk_widget_set_overflow), which border-radius alone doesn't imply. */
.photo-avatar {
    border-radius: 999px;
    /* Fallback fill for any transparency the cover-crop (image_utils.py)
       doesn't fully remove -- a real photo can have its own transparent
       corners too. Without this, transparent pixels show the app's dark
       background through the circle instead of a clean gray fill. */
    background-color: #8E8E93;
}

.avatar-initials {
    color: #FFFFFF;
}

/* Ring around each mini avatar inside a composite group-chat icon (see
   make_group_avatar) -- without it, same-color circles packed edge-to-edge
   just blend into one gray blob with floating initials. @window_bg_color is
   the app's own background, so the ring reads correctly in both themes
   without hardcoding a light/dark color. */
.group-mini-avatar {
    box-shadow: 0 0 0 2px @window_bg_color;
}

/* Pinned-contact tile grid (macOS Messages' top-of-sidebar row) */
.pinned-tile {
    padding: 8px 4px;
    border-radius: 12px;
}

.pinned-tile:hover {
    background-color: alpha(currentColor, 0.06);
}

.pinned-name {
    font-size: 11px;
    font-weight: 500;
}

/* Regular chat list rows */
list.navigation-sidebar row {
    margin: 1px 6px;
    padding: 0px;
    border-radius: 8px;
    min-height: 56px;
}

list.navigation-sidebar row:selected {
    background-color: #0A84FF;
}

list.navigation-sidebar row:selected .chat-row-title,
list.navigation-sidebar row:selected .chat-row-subtitle,
list.navigation-sidebar row:selected .chat-row-time {
    color: #FFFFFF;
    opacity: 1;
}

.chat-row-title {
    font-weight: 600;
    font-size: 14px;
}

.chat-row-subtitle {
    font-size: 13px;
    opacity: 0.6;
}

.chat-row-time {
    font-size: 12px;
    opacity: 0.5;
}

.unread-dot {
    background-color: #0A84FF;
    border-radius: 999px;
    min-width: 8px;
    min-height: 8px;
}

/* Conversation header pill (avatar + name + chevron) */
.header-pill {
    padding: 3px 12px 3px 6px;
    border-radius: 999px;
    background-color: alpha(currentColor, 0.06);
}

.header-pill-name {
    font-size: 13px;
    font-weight: 600;
}

/* iMessage-style bubbles. Real app uses a custom clipped "tail" point on the
   corner nearest the sender; a tight (not zero) radius on that corner reads as
   the same shape at chat-bubble sizes without a custom Cairo path. */
.bubble-outgoing {
    background-color: #0A84FF;
    color: #FFFFFF;
    border-radius: 18px 18px 4px 18px;
    padding: 8px 14px;
}

.bubble-incoming {
    background-color: #3A3A3C;
    color: #FFFFFF;
    border-radius: 18px 18px 18px 4px;
    padding: 8px 14px;
}

.bubble-outgoing label, .bubble-incoming label {
    font-size: 14px;
}

/* Attachment image sent/received inline in a message thread -- its own
   rounded rectangle, not a photo-filled speech bubble (matches real
   iMessage). */
.attachment-image {
    border-radius: 14px;
}

/* Collapsible link-preview card under a message bubble containing a URL. */
.link-preview {
    margin-top: 4px;
    border-radius: 10px;
    background-color: alpha(currentColor, 0.05);
}

.link-preview-domain {
    font-size: 12px;
    font-weight: 600;
}

.link-preview-url {
    font-size: 11px;
    padding: 0px 10px 8px 10px;
}

.sender-name {
    font-size: 12px;
    font-weight: 600;
    opacity: 0.6;
    margin-bottom: 2px;
}

.timestamp-separator {
    font-size: 12px;
    font-weight: 600;
    opacity: 0.45;
}

.read-receipt {
    font-size: 11px;
    opacity: 0.45;
    margin-right: 2px;
}

/* Compose bar */
.compose-entry {
    border-radius: 999px;
    padding: 8px 16px;
    background-color: alpha(currentColor, 0.06);
    border: none;
    box-shadow: none;
}

/* Setup screen */
.messages-logo-glow {
    border-radius: 999px;
    background-image: radial-gradient(circle, alpha(#34C759, 0.35) 0%, alpha(#34C759, 0.12) 55%, transparent 75%);
}

.messages-connect-btn {
    background-color: #34C759;
    color: #FFFFFF;
    font-weight: 600;
    min-height: 40px;
}

.messages-connect-btn:hover {
    background-color: #30B653;
}

.messages-connect-btn:disabled {
    opacity: 0.6;
}

/* Emoji picker -- light rounded card with a bottom category strip, matching
   the real macOS emoji picker rather than a plain top-tabbed dialog. */
.emoji-picker-panel {
    background-color: alpha(currentColor, 0.03);
    border-radius: 14px;
    padding: 8px;
}

.emoji-picker-search entry, .emoji-picker-search {
    border-radius: 999px;
}

.emoji-picker-tabs {
    padding: 4px 8px;
    border-radius: 999px;
    background-color: alpha(currentColor, 0.06);
}
"""
