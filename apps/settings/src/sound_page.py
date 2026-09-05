import os

import gi

gi.require_version('Gvc', '1.0')
from gi.repository import Gio, GLib, GObject, Gtk, Gvc

from widgets import make_hero_header, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

SOUND_SCHEMA = 'org.gnome.desktop.sound'

# Real device data (get_sinks/get_sources/get_default_sink/get_default_source) is only
# valid once the control reaches READY -- referencing the enum symbolically rather than a
# hardcoded ordinal, since GObject enum member values aren't guaranteed to match their
# declaration order (verified directly: READY is actually 1, CONNECTING is 2, not the other
# way around as their declaration order alone would suggest).
_STATE_READY = Gvc.MixerControlState.READY


def _stream_type_label(stream) -> str:
    # Gvc doesn't expose a distinct "Built-in" vs external flag directly, but its port
    # information (from PipeWire/PulseAudio) does -- the same thing the Sound screenshot's
    # "Type" column shows ("Built-in", "AirPlay", ...). Falls back to the stream's own
    # form-factor-ish description when there's no active port to read.
    port = stream.get_port()
    if port is not None:
        return port.human_port or port.port or 'Device'
    return 'Device'


class _DeviceRow(Gtk.Box):
    def __init__(self, stream):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.stream_id = stream.get_id()
        self.append(Gtk.Label(label=stream.get_description(), xalign=0, hexpand=True))
        self.append(Gtk.Label(label=_stream_type_label(stream), xalign=1, css_classes=['dim-label']))


class SoundPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(SOUND_SCHEMA)
        self._showing_outputs = True

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'sound.svg'), 'audio-speakers-symbolic',
            'Sound', 'Choose sound effects and your input and output devices.',
        ))

        effects_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        ui_row = ToggleRow('Play user interface sound effects')
        self._settings.bind('event-sounds', ui_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        effects_card.append(ui_row)

        feedback_row = ToggleRow('Play feedback when volume is changed')
        self._settings.bind('input-feedback-sounds', feedback_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        effects_card.append(feedback_row)

        self.append(effects_card)

        # Volume slider + mute -- the single most expected control on a sound settings page,
        # and the thing this page was missing entirely. Same Gvc API/pattern as the top bar's
        # own working sound-menu slider (macos-top-panel's soundIndicator.js: stream.volume,
        # stream.push_volume(), stream.change_is_muted(), control.get_vol_max_norm(),
        # notify::volume/notify::is-muted) -- mirrored here rather than reinvented, since that
        # code is already proven against real audio hardware and this one isn't (no audio
        # device on the machine this was written on to test against directly).
        volume_card = Gtk.Box(css_classes=['wifi-card'])
        volume_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            margin_start=14, margin_end=14, margin_top=12, margin_bottom=12,
        )
        volume_row.append(Gtk.Image.new_from_icon_name('audio-volume-low-symbolic'))
        self._volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._volume_scale.set_draw_value(False)
        self._volume_scale.set_hexpand(True)
        self._volume_scale_handler = self._volume_scale.connect('value-changed', self._on_volume_changed)
        volume_row.append(self._volume_scale)
        volume_row.append(Gtk.Image.new_from_icon_name('audio-volume-high-symbolic'))
        self._mute_btn = Gtk.ToggleButton(icon_name='audio-volume-muted-symbolic', css_classes=['flat'])
        self._mute_btn_handler = self._mute_btn.connect('toggled', self._on_mute_toggled)
        volume_row.append(self._mute_btn)
        volume_card.append(volume_row)
        self.append(volume_card)

        self._volume_stream = None
        self._volume_stream_signal_ids = []

        self.append(Gtk.Label(label='Output & Input', xalign=0, css_classes=['heading']))

        toggle_box = Gtk.Box(halign=Gtk.Align.CENTER, css_classes=['linked'], margin_bottom=4)
        output_btn = Gtk.ToggleButton(label='Output', active=True, css_classes=['segmented-toggle'], hexpand=True)
        input_btn = Gtk.ToggleButton(label='Input', group=output_btn, css_classes=['segmented-toggle'], hexpand=True)
        output_btn.connect('toggled', self._on_tab_toggled)
        toggle_box.append(output_btn)
        toggle_box.append(input_btn)
        self.append(toggle_box)

        self._device_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.SINGLE)
        self._device_list.connect('row-selected', self._on_device_selected)
        self.append(self._device_list)

        self._status_label = Gtk.Label(
            label='Connecting to audio...', css_classes=['dim-label'], margin_top=8, visible=False,
        )
        self.append(self._status_label)

        self._apps_heading = Gtk.Label(label='Applications', xalign=0, css_classes=['heading'], visible=False)
        self.append(self._apps_heading)
        self._apps_list = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'],
                                      selection_mode=Gtk.SelectionMode.NONE, visible=False)
        self.append(self._apps_list)
        self._app_stream_handlers = {}

        # Real device enumeration/selection via libpulse (through Gvc, the same library
        # gnome-control-center's own Sound panel is built on) instead of the screenshot's
        # AirPlay device list, which has no Linux equivalent -- these are whatever's actually
        # plugged in/available on this machine.
        self._mixer = Gvc.MixerControl(name='peachOS Settings')
        self._mixer_state_id = self._mixer.connect('state-changed', self._on_mixer_state_changed)
        self._mixer_default_sink_id = self._mixer.connect('default-sink-changed', lambda *_a: self._rebuild_device_list())
        self._mixer_default_source_id = self._mixer.connect('default-source-changed', lambda *_a: self._rebuild_device_list())
        self._mixer_stream_added_id = self._mixer.connect('stream-added', lambda *_a: self._rebuild_app_list())
        self._mixer_stream_removed_id = self._mixer.connect('stream-removed', lambda *_a: self._rebuild_app_list())
        self._mixer.open()

        self.connect('destroy', self._on_destroy)

        if self._mixer.get_state() == _STATE_READY:
            self._rebuild_device_list()
            self._rebuild_app_list()
        else:
            self._status_label.set_visible(True)

    def _on_mixer_state_changed(self, _mixer, state):
        if state == _STATE_READY:
            self._status_label.set_visible(False)
            self._rebuild_device_list()
            self._rebuild_app_list()
        else:
            self._status_label.set_visible(True)

    # ---- per-application volume ----------------------------------------

    def _rebuild_app_list(self):
        child = self._apps_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._apps_list.remove(child)
            child = nxt

        streams = self._mixer.get_sink_inputs() if self._mixer.get_state() == _STATE_READY else []
        self._apps_heading.set_visible(bool(streams))
        self._apps_list.set_visible(bool(streams))

        max_volume = self._mixer.get_vol_max_norm() or 1
        for stream in streams:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
            row.set_margin_start(14)
            row.set_margin_end(14)
            row.set_margin_top(8)
            row.set_margin_bottom(8)

            icon = Gtk.Image.new_from_icon_name(stream.get_icon_name() or 'application-x-executable-symbolic')
            icon.set_pixel_size(22)
            row.append(icon)
            row.append(Gtk.Label(label=stream.get_name() or stream.get_description() or 'Application',
                                 xalign=0, valign=Gtk.Align.CENTER, width_chars=12, ellipsize=3))

            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            scale.set_value(round((stream.get_volume() / max_volume) * 100))
            scale.connect('value-changed', self._on_app_volume_changed, stream)
            row.append(scale)

            mute = Gtk.ToggleButton(icon_name='audio-volume-muted-symbolic', css_classes=['flat'],
                                    valign=Gtk.Align.CENTER, active=stream.get_is_muted())
            mute.connect('toggled', lambda b, s=stream: s.change_is_muted(b.get_active()))
            row.append(mute)

            self._apps_list.append(row)

    def _on_app_volume_changed(self, scale, stream):
        max_volume = self._mixer.get_vol_max_norm() or 1
        stream.set_volume(round((scale.get_value() / 100) * max_volume))
        stream.push_volume()

    def _on_tab_toggled(self, _btn):
        self._showing_outputs = not self._showing_outputs
        self._rebuild_device_list()

    def _on_device_selected(self, _list, row):
        if row is None or getattr(row, '_syncing', False):
            return
        stream_id = row.get_child().stream_id
        if self._showing_outputs:
            stream = self._mixer.lookup_output_id(stream_id)
            if stream:
                self._mixer.set_default_sink(stream)
        else:
            stream = self._mixer.lookup_input_id(stream_id)
            if stream:
                self._mixer.set_default_source(stream)

    def _rebuild_device_list(self):
        child = self._device_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._device_list.remove(child)
            child = next_child

        if self._showing_outputs:
            streams = self._mixer.get_sinks()
            default = self._mixer.get_default_sink()
        else:
            streams = self._mixer.get_sources()
            default = self._mixer.get_default_source()
        default_id = default.get_id() if default else None

        selected_row = None
        for stream in streams:
            row = Gtk.ListBoxRow(child=_DeviceRow(stream))
            self._device_list.append(row)
            if stream.get_id() == default_id:
                selected_row = row

        if selected_row is not None:
            selected_row._syncing = True
            self._device_list.select_row(selected_row)
            selected_row._syncing = False

        self._bind_volume_stream(default)

    # ---- Volume slider + mute --------------------------------------------

    def _bind_volume_stream(self, stream):
        if self._volume_stream:
            for signal_id in self._volume_stream_signal_ids:
                self._volume_stream.disconnect(signal_id)
        self._volume_stream_signal_ids = []
        self._volume_stream = stream

        if stream:
            self._volume_stream_signal_ids.append(
                stream.connect('notify::volume', lambda *_a: self._update_volume_ui()))
            self._volume_stream_signal_ids.append(
                stream.connect('notify::is-muted', lambda *_a: self._update_volume_ui()))
        self._update_volume_ui()

    def _update_volume_ui(self):
        has_stream = self._volume_stream is not None
        self._volume_scale.set_sensitive(has_stream)
        self._mute_btn.set_sensitive(has_stream)
        if not has_stream:
            return

        max_volume = self._mixer.get_vol_max_norm()
        percent = round((self._volume_stream.get_volume() / max_volume) * 100) if max_volume else 0

        with GObject.signal_handler_block(self._volume_scale, self._volume_scale_handler):
            self._volume_scale.set_value(percent)
        with GObject.signal_handler_block(self._mute_btn, self._mute_btn_handler):
            self._mute_btn.set_active(self._volume_stream.get_is_muted())

    def _on_volume_changed(self, scale):
        if not self._volume_stream:
            return
        max_volume = self._mixer.get_vol_max_norm()
        percent = scale.get_value()
        self._volume_stream.set_volume(round((percent / 100) * max_volume))
        self._volume_stream.push_volume()
        if percent > 0 and self._volume_stream.get_is_muted():
            self._volume_stream.change_is_muted(False)
            with GObject.signal_handler_block(self._mute_btn, self._mute_btn_handler):
                self._mute_btn.set_active(False)

    def _on_mute_toggled(self, btn):
        if self._volume_stream:
            self._volume_stream.change_is_muted(btn.get_active())

    def _on_destroy(self, _widget):
        for signal_id in (self._mixer_state_id, self._mixer_default_sink_id, self._mixer_default_source_id,
                          self._mixer_stream_added_id, self._mixer_stream_removed_id):
            if signal_id:
                self._mixer.disconnect(signal_id)
        if self._volume_stream:
            for signal_id in self._volume_stream_signal_ids:
                self._volume_stream.disconnect(signal_id)
