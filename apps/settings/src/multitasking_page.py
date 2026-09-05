import os

from gi.repository import Gio, Gtk

from widgets import DropdownRow, ToggleRow, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

MUTTER_SCHEMA = 'org.gnome.mutter'
WM_SCHEMA = 'org.gnome.desktop.wm.preferences'
INTERFACE_SCHEMA = 'org.gnome.desktop.interface'
APP_SWITCHER_SCHEMA = 'org.gnome.shell.app-switcher'
WINDOW_SWITCHER_SCHEMA = 'org.gnome.shell.window-switcher'

MONITOR_OPTIONS = [
    ('Workspaces on primary display only', True),
    ('Workspaces span all displays', False),
]


def _card(page, heading=None):
    if heading:
        page.append(Gtk.Label(label=heading, xalign=0, css_classes=['heading'], margin_start=4))
    card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
    page.append(card)
    return card


class _SpinRow(Gtk.Box):
    def __init__(self, title, low, high):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        for edge in ('start', 'end'):
            getattr(self, f'set_margin_{edge}')(14)
        for edge in ('top', 'bottom'):
            getattr(self, f'set_margin_{edge}')(8)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.spin = Gtk.SpinButton.new_with_range(low, high, 1)
        self.spin.set_valign(Gtk.Align.CENTER)
        self.append(self.spin)


class MultitaskingPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._mutter = Gio.Settings.new(MUTTER_SCHEMA)
        self._wm = Gio.Settings.new(WM_SCHEMA)
        self._interface = Gio.Settings.new(INTERFACE_SCHEMA)
        self._app_switcher = Gio.Settings.new(APP_SWITCHER_SCHEMA)
        self._window_switcher = Gio.Settings.new(WINDOW_SWITCHER_SCHEMA)
        self._syncing = False

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'multitasking.svg'), 'view-app-grid-symbolic',
            'Multitasking', 'Set how windows, workspaces, and app switching behave.',
        ))

        # ---- General ----
        general = _card(self, 'General')

        hot_corner = ToggleRow(
            'Hot Corner', 'Push the pointer into the top-left corner to open the Activities overview.')
        self._interface.bind('enable-hot-corners', hot_corner.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(hot_corner)

        edge_tiling = ToggleRow(
            'Active Screen Edges',
            'Drag a window against the top, left, or right edge of the screen to resize it.')
        self._mutter.bind('edge-tiling', edge_tiling.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        general.append(edge_tiling)

        # ---- Workspaces ----
        self.append(Gtk.Label(label='Workspaces', xalign=0, css_classes=['heading'], margin_start=4))

        toggle_box = Gtk.Box(css_classes=['linked'], homogeneous=True, margin_bottom=2)
        self._dynamic_btn = Gtk.ToggleButton(label='Dynamic Workspaces', css_classes=['segmented-toggle'])
        self._fixed_btn = Gtk.ToggleButton(
            label='Fixed Number', group=self._dynamic_btn, css_classes=['segmented-toggle'])
        self._dynamic_btn.connect('toggled', self._on_workspace_mode_toggled)
        toggle_box.append(self._dynamic_btn)
        toggle_box.append(self._fixed_btn)
        self.append(toggle_box)

        workspace_card = _card(self)
        self._count_row = _SpinRow('Number of Workspaces', 1, 12)
        self._count_row.spin.connect('value-changed', self._on_count_changed)
        workspace_card.append(self._count_row)

        self._monitor_row = DropdownRow('Multi-Display', MONITOR_OPTIONS)
        self._monitor_row.dropdown.connect('notify::selected', self._on_monitor_changed)
        workspace_card.append(self._monitor_row)

        # ---- App Switching ----
        switching = _card(self, 'App Switching')
        self._current_only_row = ToggleRow(
            'Only Show the Current Workspace',
            'The app and window switchers list only what is open on the workspace you are on.')
        self._current_only_row.switch.connect('state-set', self._on_current_only_toggled)
        switching.append(self._current_only_row)

        self._mutter.connect('changed::dynamic-workspaces', lambda *_a: self._refresh())
        self._wm.connect('changed::num-workspaces', lambda *_a: self._refresh())
        self._mutter.connect('changed::workspaces-only-on-primary', lambda *_a: self._refresh())
        self._app_switcher.connect('changed::current-workspace-only', lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        self._syncing = True
        dynamic = self._mutter.get_boolean('dynamic-workspaces')
        self._dynamic_btn.set_active(dynamic)
        self._fixed_btn.set_active(not dynamic)
        self._count_row.set_sensitive(not dynamic)
        self._count_row.spin.set_value(self._wm.get_int('num-workspaces'))
        self._monitor_row.set_selected_value(self._mutter.get_boolean('workspaces-only-on-primary'))
        self._current_only_row.switch.set_active(
            self._app_switcher.get_boolean('current-workspace-only'))
        self._syncing = False

    def _on_workspace_mode_toggled(self, _btn):
        if self._syncing:
            return
        self._mutter.set_boolean('dynamic-workspaces', self._dynamic_btn.get_active())

    def _on_count_changed(self, spin):
        if not self._syncing:
            self._wm.set_int('num-workspaces', int(spin.get_value()))

    def _on_monitor_changed(self, _dd, _pspec):
        if not self._syncing:
            self._mutter.set_boolean('workspaces-only-on-primary', self._monitor_row.get_selected_value())

    def _on_current_only_toggled(self, _switch, state):
        if not self._syncing:
            self._app_switcher.set_boolean('current-workspace-only', state)
            self._window_switcher.set_boolean('current-workspace-only', state)
        return False
