#!/usr/bin/env python3
import os
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import local_state
from backend_launcher import ensure_backend_running, socket_path
from chat_list_view import ChatListView
from contact_details_view import build_details_page
from conversation_view import ConversationView
from fake_ipc import FakeIpcClient
from image_utils import load_contained_texture
from ipc_client import IpcClient
from setup_view import SetupView
from style import STYLE_CSS

_WARMUP_EMOJI = "/home/user/macOS_Tahoe_SYSICONS/apple-emoji/how-grinning-face.svg"

APP_ID = "org.peachos.BlueBubbles"

# Temporary: no real BlueBubbles Server to test against right now, so the
# setup screen accepts any URL/password and the whole app runs on made-up
# chats/messages (fake_ipc.py) instead of a real backend connection. Flip
# this back to False once there's a real server to point the setup screen at
# -- everything else (chat list, conversation view, compose, contact
# details) is written against the same IpcClient.request() contract either
# way, so nothing else needs to change.
FAKE_MODE = True


class BlueBubblesWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(960, 640)
        self.set_size_request(640, 480)
        self.set_title("Messages")

        self._ipc = FakeIpcClient() if FAKE_MODE else IpcClient(socket_path())
        self._backend_ready = False

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.set_content(self._stack)

        if local_state.is_setup_finished():
            # Returning user: we already know a real backend connection is
            # needed to show real chats, so start it now behind a brief
            # "connecting" page.
            self._stack.add_named(self._build_starting_page(), "starting")
            self._stack.set_visible_child_name("starting")
            self._ensure_backend_connected(self._on_returning_user_ready)
        else:
            # First run: the setup form itself needs nothing from the
            # backend, so show it immediately -- no spinner, no backend
            # process spawned at all. The backend only starts once the user
            # actually submits real server info (SetupView._on_connect_clicked).
            self._show_setup_view()

    def _build_starting_page(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            icon_name="chat-symbolic",
            title="Starting Messages…",
            description="Connecting to the local BlueBubbles backend.",
        )
        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER)
        page.set_child(spinner)
        return page

    def _build_error_page(self, message: str) -> Gtk.Widget:
        return Adw.StatusPage(
            icon_name="dialog-error-symbolic",
            title="Couldn't Start Messages",
            description=message,
        )

    # --- backend bootstrap (background thread) ---
    #
    # Shared by both the returning-user startup path above and SetupView's
    # "Connect" button -- whichever fires first actually starts the backend
    # process and connects the IPC socket; anything after that just reports
    # the already-connected state instead of doing it again.

    def _ensure_backend_connected(self, callback):
        if self._backend_ready:
            GLib.idle_add(callback, True, None)
            return

        if FAKE_MODE:
            # No process to spawn, no socket to connect -- FakeIpcClient is
            # already "connected" the moment it's constructed.
            self._backend_ready = True
            GLib.idle_add(callback, True, None)
            return

        def worker():
            ok = ensure_backend_running()
            if not ok:
                GLib.idle_add(callback, False, "The backend process did not start in time.")
                return
            try:
                self._ipc.connect()
            except OSError as exc:
                GLib.idle_add(callback, False, str(exc))
                return
            self._backend_ready = True
            GLib.idle_add(callback, True, None)

        threading.Thread(target=worker, daemon=True).start()

    def _show_backend_error(self, message: str):
        page = self._build_error_page(message)
        self._stack.add_named(page, "error")
        self._stack.set_visible_child_name("error")

    def _on_returning_user_ready(self, ok, error):
        if not ok:
            self._show_backend_error(error or "Couldn't reach the backend.")
            return
        self._ipc.request("is-setup-finished", callback=self._on_setup_status)

    def _on_setup_status(self, result, error):
        if error is not None or result is None:
            self._show_backend_error(error or "No response from backend.")
            return
        if result.get("finished"):
            self._show_main_view()
        else:
            # The persisted file said finished but the backend disagrees
            # (e.g. it was edited/cleared directly) -- fall back to the real
            # setup form instead of getting stuck on the spinner.
            self._show_setup_view()

    # --- setup ---

    def _show_setup_view(self):
        setup_view = SetupView(self._ipc, self._ensure_backend_connected, on_connected=self._show_main_view)
        self._stack.add_named(setup_view, "setup")
        self._stack.set_visible_child_name("setup")

    # --- main chat UI ---

    def _show_main_view(self):
        split_view = Adw.NavigationSplitView(min_sidebar_width=260, max_sidebar_width=320)

        sidebar_header = Adw.HeaderBar(show_title=False)
        compose_btn = Gtk.Button(icon_name="document-edit-symbolic")
        compose_btn.add_css_class("flat")
        compose_btn.set_tooltip_text("New Message")
        sidebar_header.pack_start(compose_btn)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.add_css_class("flat")
        sidebar_header.pack_end(menu_btn)

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_toolbar.add_top_bar(sidebar_header)
        self._chat_list = ChatListView(self._ipc)
        self._chat_list.connect("chat-selected", self._on_chat_selected)
        sidebar_toolbar.set_content(self._chat_list)

        sidebar_page = Adw.NavigationPage(title="Messages")
        sidebar_page.set_child(sidebar_toolbar)
        split_view.set_sidebar(sidebar_page)

        self._conversation_view = ConversationView(self._ipc)
        self._conversation_view.connect("details-requested", self._on_details_requested)

        content_header = Adw.HeaderBar()
        content_header.set_title_widget(self._conversation_view.header)
        call_btn = Gtk.Button(icon_name="camera-video-symbolic")
        call_btn.add_css_class("flat")
        content_header.pack_end(call_btn)

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(content_header)
        content_toolbar.set_content(self._conversation_view)

        conversation_page = Adw.NavigationPage(title="Messages", child=content_toolbar)
        conversation_page.set_tag("conversation")

        # A nav stack (not just the conversation view directly) so clicking the
        # header can push a real slide-in Contact Details page -- see
        # _on_details_requested -- with a native back button, instead of a
        # small popover.
        self._content_nav = Adw.NavigationView()
        self._content_nav.push(conversation_page)

        content_page = Adw.NavigationPage(title="Messages")
        content_page.set_child(self._content_nav)
        split_view.set_content(content_page)

        self._stack.add_named(split_view, "main")
        self._stack.set_visible_child_name("main")

        # The very first SVG decode in the process pays a real one-time cost
        # (rsvg/font subsystem init) -- measured live at ~3.5s, vs. ~0.2s for
        # every decode after. Left alone, that cost lands on the user's first
        # "Pick an Emoji" click. Paying it here instead, once, in idle time
        # right after the main view appears, means the picker is fast the
        # first time anyone actually opens it.
        GLib.idle_add(lambda: (load_contained_texture(_WARMUP_EMOJI, 22), False)[-1])

    def _on_chat_selected(self, _chat_list, chat: dict):
        # Picking a different chat while the Contact Details page is pushed
        # on top used to leave the user stuck looking at the old chat's
        # details -- pop back to the conversation page first so the newly
        # selected chat is actually visible.
        self._content_nav.pop_to_tag("conversation")
        self._conversation_view.show_chat(chat)

    def _on_details_requested(self, _conversation_view, chat: dict, messages: list):
        def refresh_after_avatar_change():
            self._chat_list.reload()
            self._conversation_view.header.set_chat(chat)

        page = build_details_page(
            chat, messages, self._ipc, self, refresh_after_avatar_change, push_page=self._content_nav.push)
        self._content_nav.push(page)


class BlueBubblesApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = self.props.active_window
        if not win:
            win = BlueBubblesWindow(application=self)
        win.present()


def main():
    app = BlueBubblesApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
