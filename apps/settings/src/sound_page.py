import os

import gi

gi.require_version('Gvc', '1.0')
from gi.repository import Gio, GLib, Gtk, Gvc

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

        # Real device enumeration/selection via libpulse (through Gvc, the same library
        # gnome-control-center's own Sound panel is built on) instead of the screenshot's
        # AirPlay device list, which has no Linux equivalent -- these are whatever's actually
        # plugged in/available on this machine.
        self._mixer = Gvc.MixerControl(name='peachOS Settings')
        self._mixer_state_id = self._mixer.connect('state-changed', self._on_mixer_state_changed)
        self._mixer_default_sink_id = self._mixer.connect('default-sink-changed', lambda *_a: self._rebuild_device_list())
        self._mixer_default_source_id = self._mixer.connect('default-source-changed', lambda *_a: self._rebuild_device_list())
        self._mixer.open()

        self.connect('destroy', self._on_destroy)

        if self._mixer.get_state() == _STATE_READY:
            self._rebuild_device_list()
        else:
            self._status_label.set_visible(True)

    def _on_mixer_state_changed(self, _mixer, state):
        if state == _STATE_READY:
            self._status_label.set_visible(False)
            self._rebuild_device_list()
        else:
            self._status_label.set_visible(True)

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

    def _on_destroy(self, _widget):
        for signal_id in (self._mixer_state_id, self._mixer_default_sink_id, self._mixer_default_source_id):
            if signal_id:
                self._mixer.disconnect(signal_id)
