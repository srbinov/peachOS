import os

from gi.repository import Gio, GLib, Gtk

EXTENSION_UUID = 'dash2dock-lite@icedman.github.com'
SCHEMA_ID = 'org.gnome.shell.extensions.dash2dock-lite'

# Extension GSettings schemas aren't in the global schema registry the way
# app schemas are -- Gio.Settings.new(schema_id) hard-aborts the process
# (not a catchable exception) if the schema isn't installed globally. GNOME
# Shell itself resolves these via a per-extension SettingsSchemaSource, so
# that's what this does too, checking both install locations peachOS can be
# in: system-wide (/usr/share, what provision.sh installs) and user-local
# (~/.local/share, what this dev VM currently has).
SCHEMA_SEARCH_DIRS = [
    f'/usr/share/gnome-shell/extensions/{EXTENSION_UUID}/schemas',
    os.path.expanduser(f'~/.local/share/gnome-shell/extensions/{EXTENSION_UUID}/schemas'),
]

# dock.js: `const locations = [DockPosition.BOTTOM, DockPosition.LEFT, DockPosition.RIGHT, DockPosition.TOP]`
# indexed directly by the dock-location setting. macOS only offers the first
# three (no "top" dock position), so that's all that's exposed here.
DOCK_LOCATIONS = [
    ('Bottom', 0),
    ('Left', 1),
    ('Right', 2),
]

# keys.js lists 'default' as running-indicator-style option 0, but it's not
# actually a visible style: apps/dot.js looks up a `_draw_${style}` method
# (e.g. _draw_dot, _draw_squares, _draw_diamonds...) and there is no
# _draw_default anywhere in that file, so style 0 silently draws nothing.
# It's genuinely "none," just not spelled that way in the options list.
# 'dot' (index 2) maps to the real _draw_dot method.
INDICATOR_STYLE_ON = 2   # 'dot' -- draws a real indicator
INDICATOR_STYLE_OFF = 0  # 'default' -- no _draw_default exists, draws nothing


def _load_extension_settings(schema_id: str):
    for schema_dir in SCHEMA_SEARCH_DIRS:
        if not os.path.isdir(schema_dir):
            continue
        source = Gio.SettingsSchemaSource.new_from_directory(
            schema_dir, Gio.SettingsSchemaSource.get_default(), True,
        )
        schema = source.lookup(schema_id, False)
        if schema:
            return Gio.Settings.new_full(schema, None, None)
    return None


class SliderRow(Gtk.Box):
    def __init__(self, title: str, low_label: str, high_label: str, mid_label: str = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        self.append(Gtk.Label(label=title, xalign=0, css_classes=['heading']))

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.append(self.scale)

        labels_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        labels_row.append(Gtk.Label(label=low_label, xalign=0, hexpand=True, css_classes=['caption', 'dim-label']))
        if mid_label:
            labels_row.append(Gtk.Label(label=mid_label, css_classes=['caption', 'dim-label']))
        end_label = Gtk.Label(label=high_label, xalign=1, css_classes=['caption', 'dim-label'])
        if mid_label:
            end_label.set_hexpand(True)
        labels_row.append(end_label)
        self.append(labels_row)


class DropdownRow(Gtk.Box):
    def __init__(self, title: str, options: list):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))

        self.dropdown = Gtk.DropDown.new_from_strings([label for label, _value in options])
        self._values = [value for _label, value in options]
        self.append(self.dropdown)

    def get_selected_value(self):
        return self._values[self.dropdown.get_selected()]

    def set_selected_value(self, value):
        if value in self._values:
            self.dropdown.set_selected(self._values.index(value))


class ToggleRow(Gtk.Box):
    def __init__(self, title: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.append(self.switch)


class DesktopDockPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = _load_extension_settings(SCHEMA_ID)
        self._syncing = False

        self.append(Gtk.Label(label='Dock', xalign=0, css_classes=['heading'], margin_start=4))

        if not self._settings:
            self.append(Gtk.Label(
                label='dash2dock-lite is not installed, so Dock settings can’t be changed here.',
                wrap=True, css_classes=['dim-label'], xalign=0,
            ))
            return

        self._build_ui()
        self._refresh_from_settings()
        self._settings.connect('changed', lambda *_a: self._refresh_from_settings())

    def _build_ui(self):
        size_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self._size_row = SliderRow('Size', 'Small', 'Large')
        self._size_row.set_margin_start(14)
        self._size_row.set_margin_top(14)
        self._size_row.set_margin_bottom(14)
        size_card.append(self._size_row)

        self._magnify_row = SliderRow('Magnification', 'Off', 'Large', mid_label='Small')
        self._magnify_row.set_margin_end(14)
        self._magnify_row.set_margin_top(14)
        self._magnify_row.set_margin_bottom(14)
        size_card.append(self._magnify_row)
        self.append(size_card)

        self._size_row.scale.connect('value-changed', self._on_size_changed)
        self._magnify_row.scale.connect('value-changed', self._on_magnify_changed)

        position_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._position_row = DropdownRow('Dock position on screen', DOCK_LOCATIONS)
        self._position_row.dropdown.connect('notify::selected', self._on_position_changed)
        position_card.append(self._position_row)
        self.append(position_card)

        behavior_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._autohide_row = ToggleRow('Automatically hide and show the Dock')
        self._autohide_row.switch.connect('state-set', self._on_autohide_toggled)
        behavior_card.append(self._autohide_row)
        behavior_card.append(Gtk.Separator())

        self._animate_open_row = ToggleRow('Animate opening applications')
        self._animate_open_row.switch.connect('state-set', self._on_animate_open_toggled)
        behavior_card.append(self._animate_open_row)
        behavior_card.append(Gtk.Separator())

        self._indicators_row = ToggleRow('Show indicators for open applications')
        self._indicators_row.switch.connect('state-set', self._on_indicators_toggled)
        behavior_card.append(self._indicators_row)
        self.append(behavior_card)

    def _refresh_from_settings(self):
        self._syncing = True
        self._size_row.scale.set_value(self._settings.get_double('icon-size'))
        self._magnify_row.scale.set_value(self._settings.get_double('animation-magnify'))
        self._position_row.set_selected_value(self._settings.get_int('dock-location'))
        self._autohide_row.switch.set_active(self._settings.get_boolean('autohide-dash'))
        self._animate_open_row.switch.set_active(self._settings.get_boolean('open-app-animation'))
        self._indicators_row.switch.set_active(
            self._settings.get_int('running-indicator-style') != INDICATOR_STYLE_OFF
        )
        self._syncing = False

    def _on_size_changed(self, scale):
        if self._syncing:
            return
        self._settings.set_double('icon-size', scale.get_value())

    def _on_magnify_changed(self, scale):
        if self._syncing:
            return
        self._settings.set_double('animation-magnify', scale.get_value())

    def _on_position_changed(self, dropdown, _pspec):
        if self._syncing:
            return
        self._settings.set_int('dock-location', self._position_row.get_selected_value())

    def _on_autohide_toggled(self, switch, state):
        if self._syncing:
            return False
        self._settings.set_boolean('autohide-dash', state)
        return False

    def _on_animate_open_toggled(self, switch, state):
        if self._syncing:
            return False
        self._settings.set_boolean('open-app-animation', state)
        return False

    def _on_indicators_toggled(self, switch, state):
        if self._syncing:
            return False
        self._settings.set_int(
            'running-indicator-style',
            INDICATOR_STYLE_ON if state else INDICATOR_STYLE_OFF,
        )
        return False
