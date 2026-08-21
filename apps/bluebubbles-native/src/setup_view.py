"""First-run "connect to server" screen, shown immediately on a fresh
install (local_state.is_setup_finished() false) -- with no backend process
running yet. The backend only gets started once the user actually submits
real server info here (see _on_connect_clicked/_ensure_backend_connected),
not just because the window opened.

Submits the URL + password over IPC via "run-setup", which drives the Dart
backend's real first-time-setup path (full sync against the user's actual
BlueBubbles Server) -- see bluebubbles-app/lib/peachos_ipc/headless_setup.dart.
(Currently wired to fake_ipc.FakeIpcClient instead -- see main.py's
FAKE_MODE -- which accepts any URL/password and never actually validates
them; this view doesn't know or care which one it's talking to.)

Uses the same light/dark Messages app icon as the rest of peachOS (see
assets/app-icons/messages.svg + darkmode/messages.svg), and plays a short
fade-in once the window is actually on screen so the form doesn't just pop
in instantly.
"""
from gi.repository import Adw, Gtk

from image_utils import load_contained_texture

_ICON_LIGHT = "/home/user/peachOS/assets/app-icons/messages.svg"
_ICON_DARK = "/home/user/peachOS/assets/app-icons/darkmode/messages.svg"
_ICON_SIZE = 96


class SetupView(Adw.Bin):
    __gtype_name__ = "SetupView"

    def __init__(self, ipc_client, ensure_backend_connected, on_connected):
        super().__init__()
        self._ipc = ipc_client
        self._ensure_backend_connected = ensure_backend_connected
        self._on_connected = on_connected

        clamp = Adw.Clamp(maximum_size=420, tightening_threshold=320)
        self.set_child(clamp)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        self._content_box.set_margin_top(48)
        self._content_box.set_margin_bottom(48)
        self._content_box.set_margin_start(24)
        self._content_box.set_margin_end(24)
        clamp.set_child(self._content_box)

        # Soft radial glow behind the app icon (matches the icon's own
        # Messages-green) -- an Overlay rather than a plain stacked Box so the
        # glow can be sized larger than the icon without pushing it around.
        logo_holder = Gtk.Overlay(halign=Gtk.Align.CENTER)
        glow = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        glow.add_css_class("messages-logo-glow")
        glow.set_size_request(_ICON_SIZE + 48, _ICON_SIZE + 48)
        logo_holder.set_child(glow)

        self._logo_image = Gtk.Picture()
        self._logo_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._logo_image.set_size_request(_ICON_SIZE, _ICON_SIZE)
        self._logo_image.set_halign(Gtk.Align.CENTER)
        self._logo_image.set_valign(Gtk.Align.CENTER)
        logo_holder.add_overlay(self._logo_image)
        self._content_box.append(logo_holder)

        # Theme-aware, and stays that way live -- matches how iconmasker
        # swaps every other app icon when the user flips Appearance mode,
        # instead of needing a restart to pick up the right variant.
        style_manager = Adw.StyleManager.get_default()
        self._apply_icon(style_manager.get_dark())
        style_manager.connect("notify::dark", lambda mgr, _p: self._apply_icon(mgr.get_dark()))

        title = Gtk.Label(label="Messages")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.CENTER)
        self._content_box.append(title)

        subtitle = Gtk.Label(
            label="Enter the address and password of your BlueBubbles Server to get started.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        subtitle.add_css_class("dim-label")
        self._content_box.append(subtitle)

        group = Adw.PreferencesGroup()
        self._content_box.append(group)

        self._url_row = Adw.EntryRow(title="Server URL")
        self._url_row.set_input_purpose(Gtk.InputPurpose.URL)
        group.add(self._url_row)

        self._password_row = Adw.PasswordEntryRow(title="Password")
        group.add(self._password_row)

        self._error_label = Gtk.Label(wrap=True, visible=False)
        self._error_label.add_css_class("error")
        self._content_box.append(self._error_label)

        self._spinner = Gtk.Spinner(visible=False)
        self._button_label = Gtk.Label(label="Connect")
        button_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        button_content.append(self._spinner)
        button_content.append(self._button_label)

        self._connect_button = Gtk.Button()
        self._connect_button.set_child(button_content)
        self._connect_button.add_css_class("pill")
        self._connect_button.add_css_class("messages-connect-btn")
        self._connect_button.connect("clicked", self._on_connect_clicked)
        self._content_box.append(self._connect_button)

        self._url_row.connect("entry-activated", self._on_connect_clicked)
        self._password_row.connect("entry-activated", self._on_connect_clicked)

        # Fade the whole form in once it's actually on screen, rather than
        # popping in fully-formed the instant the stack switches to it.
        self._content_box.set_opacity(0)
        self.connect("map", self._play_entrance_animation)

    def _apply_icon(self, dark: bool):
        path = _ICON_DARK if dark else _ICON_LIGHT
        texture = load_contained_texture(path, _ICON_SIZE)
        self._logo_image.set_paintable(texture)

    def _play_entrance_animation(self, _widget):
        target = Adw.CallbackAnimationTarget.new(self._content_box.set_opacity)
        animation = Adw.TimedAnimation.new(self._content_box, 0, 1, 450, target)
        animation.set_easing(Adw.Easing.EASE_OUT_QUAD)
        # Kept alive on self -- an animation with no other reference holder
        # can get garbage-collected mid-play, which stops it dead partway
        # through instead of finishing at opacity 1.
        self._entrance_animation = animation
        animation.play()

    def _set_busy(self, busy: bool):
        self._connect_button.set_sensitive(not busy)
        self._url_row.set_sensitive(not busy)
        self._password_row.set_sensitive(not busy)
        self._spinner.set_visible(busy)
        self._spinner.set_spinning(busy)
        self._button_label.set_label("Connecting…" if busy else "Connect")

    def _show_error(self, message: str):
        self._error_label.set_label(message)
        self._error_label.set_visible(True)

    def _on_connect_clicked(self, _widget):
        url = self._url_row.get_text().strip()
        password = self._password_row.get_text()

        if not url or not password:
            self._show_error("Enter both a server URL and password.")
            return

        self._error_label.set_visible(False)
        self._set_busy(True)

        def on_backend_ready(ok, error):
            if not ok:
                self._set_busy(False)
                self._show_error(error or "Couldn't start the backend.")
                return
            self._ipc.request(
                "run-setup",
                {"serverUrl": url, "password": password},
                callback=self._on_setup_response,
            )

        self._ensure_backend_connected(on_backend_ready)

    def _on_setup_response(self, result, error):
        self._set_busy(False)
        if error is not None:
            self._show_error(error)
            return
        self._on_connected()
