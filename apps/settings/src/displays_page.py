import math
import os

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango, PangoCairo

from widgets import load_sized_image, make_hero_header

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

POWER_SERVICE = 'org.gnome.SettingsDaemon.Power'
POWER_PATH = '/org/gnome/SettingsDaemon/Power'
SCREEN_IFACE = 'org.gnome.SettingsDaemon.Power.Screen'
PROPS_IFACE = 'org.freedesktop.DBus.Properties'

# Resolution/refresh-rate/scale/orientation/arrangement all go through Mutter's
# own display-config service -- the exact same API GNOME Settings' Displays panel
# uses. GetCurrentState returns the full monitor + logical-monitor list;
# ApplyMonitorsConfig replaces the whole logical layout at once (there is no
# "change one field" call -- every apply resends every monitor's x/y/scale/
# transform/mode together).
DISPLAYCONFIG_SERVICE = 'org.gnome.Mutter.DisplayConfig'
DISPLAYCONFIG_PATH = '/org/gnome/Mutter/DisplayConfig'
DISPLAYCONFIG_IFACE = 'org.gnome.Mutter.DisplayConfig'
GET_STATE_REPLY_TYPE = '(ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv})'
APPLY_METHOD_VERIFY = 0
APPLY_METHOD_TEMPORARY = 1
APPLY_METHOD_PERSISTENT = 2

# Mutter's Transform enum, exposed as "Orientation". Only the 4 plain rotations
# are offered, same as real GNOME Settings -- the flipped variants (4-7) exist
# in the protocol but aren't user-facing.
ORIENTATIONS = [
    ('Standard', 0),
    ('Rotate 90°', 1),
    ('Rotate 180°', 2),
    ('Rotate 270°', 3),
]

# After a resolution/scale/orientation/arrangement change, a wrong choice can
# leave the screen unreadable -- so it's applied temporarily and reverts itself
# unless confirmed, exactly like GNOME's own "Keep Changes?" dialog.
REVERT_COUNTDOWN_SECONDS = 15


class DisplayState:
    """The live monitor layout, via Mutter's DisplayConfig D-Bus API. Handles
    any number of monitors (the panel this feeds only exercised one at the time
    it was written -- the multi-monitor paths are protocol-correct but were not
    hardware-tested)."""

    def __init__(self):
        self.available = False
        self.serial = 0
        self.layout_mode = 1
        self.monitors = []          # [{connector,name,is_builtin,modes,current_mode_id}]
        self.logical_monitors = []  # [{x,y,scale,transform,primary,connectors:[...]}]
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None
            return
        self.refresh()

    # ---- reading -----------------------------------------------------------

    def refresh(self):
        if not self._bus:
            return
        try:
            result = self._bus.call_sync(
                DISPLAYCONFIG_SERVICE, DISPLAYCONFIG_PATH, DISPLAYCONFIG_IFACE, 'GetCurrentState',
                None, GLib.VariantType.new(GET_STATE_REPLY_TYPE),
                Gio.DBusCallFlags.NONE, 3000, None,
            )
        except GLib.Error:
            self.available = False
            return

        serial, monitors, logical_monitors, props = result.unpack()
        if not monitors:
            self.available = False
            return

        self.serial = serial
        self.layout_mode = props.get('layout-mode', 1)

        self.monitors = []
        for mon_spec, modes, mon_props in monitors:
            connector = mon_spec[0]
            parsed_modes = [
                {
                    'id': mode_id, 'w': w, 'h': h, 'refresh': refresh, 'scales': list(scales),
                    'is_current': mprops.get('is-current', False),
                    'is_preferred': mprops.get('is-preferred', False),
                }
                for mode_id, w, h, refresh, _pref_scale, scales, mprops in modes
            ]
            self.monitors.append({
                'connector': connector,
                'name': mon_props.get('display-name') or connector,
                'is_builtin': mon_props.get('is-builtin', False),
                'modes': parsed_modes,
                'current_mode_id': next((m['id'] for m in parsed_modes if m['is_current']), None),
            })

        self.logical_monitors = [
            {
                'x': x, 'y': y, 'scale': scale, 'transform': transform, 'primary': is_primary,
                'connectors': [s[0] for s in lmons],
            }
            for x, y, scale, transform, is_primary, lmons, _lprops in logical_monitors
        ]
        self.available = True

    def monitor(self, connector):
        return next((m for m in self.monitors if m['connector'] == connector), None)

    def logical_for(self, connector):
        return next((lm for lm in self.logical_monitors if connector in lm['connectors']), None)

    def is_enabled(self, connector):
        return self.logical_for(connector) is not None

    def is_mirrored(self):
        return any(len(lm['connectors']) > 1 for lm in self.logical_monitors)

    def primary_connector(self):
        lm = next((lm for lm in self.logical_monitors if lm['primary']), None)
        return lm['connectors'][0] if lm and lm['connectors'] else None

    def mode(self, connector, mode_id):
        mon = self.monitor(connector)
        if not mon:
            return None
        return next((m for m in mon['modes'] if m['id'] == mode_id), None)

    def resolutions(self, connector):
        """Unique (w, h) pairs, each keeping its highest-refresh mode, largest first."""
        mon = self.monitor(connector)
        if not mon:
            return []
        best = {}
        for m in mon['modes']:
            key = (m['w'], m['h'])
            if key not in best or m['refresh'] > best[key]['refresh']:
                best[key] = m
        return sorted(best.values(), key=lambda m: m['w'] * m['h'], reverse=True)

    def modes_for_resolution(self, connector, w, h):
        mon = self.monitor(connector)
        if not mon:
            return []
        return sorted((m for m in mon['modes'] if m['w'] == w and m['h'] == h),
                      key=lambda m: m['refresh'], reverse=True)

    def logical_size(self, connector):
        """On-screen (logical) size of a monitor with its current mode, scale
        and rotation applied -- what the arrangement widget lays out with."""
        lm = self.logical_for(connector)
        mon = self.monitor(connector)
        if not lm or not mon:
            return (0, 0)
        m = self.mode(connector, mon['current_mode_id'])
        if not m:
            return (0, 0)
        w = m['w'] / lm['scale']
        h = m['h'] / lm['scale']
        if lm['transform'] in (1, 3):
            w, h = h, w
        return (round(w), round(h))

    # ---- writing ---------------------------------------------------------

    def _build_logical_configs(self, overrides):
        """One (x,y,scale,transform,primary,[(connector,mode_id,{})]) tuple per
        enabled logical monitor. `overrides` maps connector -> partial dict of
        {x,y,scale,transform,primary,mode_id,enabled,mirror_with}."""
        # Mirror: a single logical monitor holding every connector, all on a
        # mode of the same resolution.
        mirror = overrides.get('__mirror__')
        if mirror:
            common = mirror['mode_ids']  # connector -> mode_id
            first = self.monitors[0]['connector']
            return [(
                0, 0, mirror.get('scale', 1.0), 0, True,
                [(c, common[c], {}) for c in common],
            )]

        configs = []
        for lm in self.logical_monitors:
            connector = lm['connectors'][0]
            ov = overrides.get(connector, {})
            if ov.get('enabled') is False:
                continue
            mon = self.monitor(connector)
            mode_id = ov.get('mode_id') or mon['current_mode_id']
            configs.append((
                ov.get('x', lm['x']), ov.get('y', lm['y']),
                ov.get('scale', lm['scale']), ov.get('transform', lm['transform']),
                ov.get('primary', lm['primary']),
                [(connector, mode_id, {})],
            ))
        # A monitor that was disabled and is being re-enabled.
        for connector, ov in overrides.items():
            if connector.startswith('__') or self.logical_for(connector):
                continue
            if not ov.get('enabled'):
                continue
            mon = self.monitor(connector)
            mode_id = ov.get('mode_id') or mon['current_mode_id']
            configs.append((
                ov.get('x', 0), ov.get('y', 0), ov.get('scale', 1.0),
                ov.get('transform', 0), ov.get('primary', False),
                [(connector, mode_id, {})],
            ))

        # Exactly one primary. If an override picked one, it wins and every
        # other monitor loses primary; otherwise keep whoever had it, or fall
        # back to the first.
        chosen = next((c for c, ov in
                       ((cfg, overrides.get(cfg[5][0][0], {})) for cfg in configs)
                       if ov.get('primary')), None)
        if chosen is not None:
            configs = [(*c[:4], c is chosen, c[5]) for c in configs]
        elif configs and not any(c[4] for c in configs):
            configs[0] = (*configs[0][:4], True, configs[0][5])
        elif sum(1 for c in configs if c[4]) > 1:
            seen = False
            fixed = []
            for c in configs:
                keep = c[4] and not seen
                seen = seen or c[4]
                fixed.append((*c[:4], keep, c[5]))
            configs = fixed
        min_x = min(c[0] for c in configs)
        min_y = min(c[1] for c in configs)
        if min_x or min_y:
            configs = [(x - min_x, y - min_y, *rest) for x, y, *rest in configs]
        return configs

    def apply(self, overrides, method=APPLY_METHOD_PERSISTENT):
        if not self.available:
            return False
        configs = self._build_logical_configs(overrides)
        if not configs:
            return False
        args = GLib.Variant('(uua(iiduba(ssa{sv}))a{sv})', (self.serial, method, configs, {}))
        try:
            self._bus.call_sync(
                DISPLAYCONFIG_SERVICE, DISPLAYCONFIG_PATH, DISPLAYCONFIG_IFACE, 'ApplyMonitorsConfig',
                args, None, Gio.DBusCallFlags.NONE, 3000, None,
            )
        except GLib.Error:
            return False
        if method != APPLY_METHOD_VERIFY:
            self.refresh()
        return True


# ---- arrangement canvas -------------------------------------------------------

class MonitorArrangement(Gtk.DrawingArea):
    """Drag monitors to say where they sit relative to each other. Works in
    logical pixels; on drop it snaps the moved monitor flush against its
    nearest neighbour (no gaps, no overlaps) and re-normalises the layout."""

    __gsignals__ = {
        'layout-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'monitor-selected': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.set_content_height(190)
        self.set_hexpand(True)
        self._monitors = []          # [{connector,label,w,h,x,y,primary}]
        self._selected = None
        self._drag_connector = None
        self._drag_start = (0, 0)
        self._drag_origin = (0, 0)

        self.set_draw_func(self._draw)

        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self._on_drag_begin)
        drag.connect('drag-update', self._on_drag_update)
        drag.connect('drag-end', self._on_drag_end)
        self.add_controller(drag)

    def set_monitors(self, monitors, selected):
        self._monitors = [dict(m) for m in monitors]
        self._selected = selected
        self.queue_draw()

    def positions(self):
        return {m['connector']: (m['x'], m['y']) for m in self._monitors}

    # ---- geometry --------------------------------------------------------

    def _bounds(self):
        xs = [m['x'] for m in self._monitors] + [m['x'] + m['w'] for m in self._monitors]
        ys = [m['y'] for m in self._monitors] + [m['y'] + m['h'] for m in self._monitors]
        return min(xs), min(ys), max(xs), max(ys)

    def _transform(self):
        """Returns (scale, offset_x, offset_y) mapping logical px -> widget px."""
        if not self._monitors:
            return 1, 0, 0
        min_x, min_y, max_x, max_y = self._bounds()
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)
        pad = 24
        avail_w = max(self.get_width() - 2 * pad, 1)
        avail_h = max(self.get_height() - 2 * pad, 1)
        scale = min(avail_w / span_x, avail_h / span_y)
        off_x = (self.get_width() - span_x * scale) / 2 - min_x * scale
        off_y = (self.get_height() - span_y * scale) / 2 - min_y * scale
        return scale, off_x, off_y

    def _rect_px(self, mon):
        scale, off_x, off_y = self._transform()
        return (mon['x'] * scale + off_x, mon['y'] * scale + off_y,
                mon['w'] * scale, mon['h'] * scale)

    def _monitor_at(self, px, py):
        for mon in reversed(self._monitors):
            rx, ry, rw, rh = self._rect_px(mon)
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                return mon
        return None

    # ---- drawing --------------------------------------------------------

    def _draw(self, _area, ctx, width, height):
        sc = self.get_style_context()
        found, accent = sc.lookup_color('accent_color')
        if not found:
            accent = Gdk.RGBA()
            accent.parse('#0A84FF')

        for mon in self._monitors:
            rx, ry, rw, rh = self._rect_px(mon)
            selected = mon['connector'] == self._selected

            ctx.set_source_rgba(accent.red, accent.green, accent.blue, 0.22 if selected else 0.10)
            _rounded_rect(ctx, rx, ry, rw, rh, 8)
            ctx.fill()

            ctx.set_source_rgba(accent.red, accent.green, accent.blue, 1.0 if selected else 0.45)
            ctx.set_line_width(2.5 if selected else 1.5)
            _rounded_rect(ctx, rx + 1, ry + 1, rw - 2, rh - 2, 8)
            ctx.stroke()

            layout = self.create_pango_layout(mon['label'])
            layout.set_alignment(Pango.Alignment.CENTER)
            layout.set_width(int(max(rw - 8, 10)) * Pango.SCALE)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            tw, th = layout.get_pixel_size()
            found_fg, fg = sc.lookup_color('window_fg_color')
            if found_fg:
                ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.85)
            else:
                ctx.set_source_rgba(0.1, 0.1, 0.1, 0.85)
            ctx.move_to(rx + (rw - tw) / 2, ry + (rh - th) / 2)
            PangoCairo.show_layout(ctx, layout)

            if mon['primary']:
                ctx.set_source_rgba(accent.red, accent.green, accent.blue, 1)
                ctx.arc(rx + 10, ry + 10, 3, 0, 2 * math.pi)
                ctx.fill()

    # ---- dragging ------------------------------------------------------

    def _on_drag_begin(self, _gesture, start_x, start_y):
        mon = self._monitor_at(start_x, start_y)
        if not mon:
            self._drag_connector = None
            return
        self._drag_connector = mon['connector']
        self._drag_start = (start_x, start_y)
        self._drag_origin = (mon['x'], mon['y'])
        if mon['connector'] != self._selected:
            self._selected = mon['connector']
            self.emit('monitor-selected', mon['connector'])
        self.queue_draw()

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        if not self._drag_connector:
            return
        mon = next(m for m in self._monitors if m['connector'] == self._drag_connector)
        scale, _ox, _oy = self._transform()
        mon['x'] = self._drag_origin[0] + offset_x / scale
        mon['y'] = self._drag_origin[1] + offset_y / scale
        self.queue_draw()

    def _on_drag_end(self, _gesture, _offset_x, _offset_y):
        if not self._drag_connector:
            return
        self._snap_layout(self._drag_connector)
        self._drag_connector = None
        self.queue_draw()
        self.emit('layout-changed')

    def _snap_layout(self, moved):
        """Snap the moved monitor flush against the nearest other monitor edge,
        then normalise so the whole layout's top-left is (0, 0). Keeps it simple
        and predictable rather than reproducing every case GNOME's own
        arrangement handles."""
        if len(self._monitors) < 2:
            self._monitors[0]['x'] = 0
            self._monitors[0]['y'] = 0
            return
        mv = next(m for m in self._monitors if m['connector'] == moved)
        others = [m for m in self._monitors if m['connector'] != moved]

        # Anchor to whichever other monitor's centre is closest.
        anchor = min(others, key=lambda o: math.hypot(
            (o['x'] + o['w'] / 2) - (mv['x'] + mv['w'] / 2),
            (o['y'] + o['h'] / 2) - (mv['y'] + mv['h'] / 2)))

        dx_right = abs(mv['x'] - (anchor['x'] + anchor['w']))
        dx_left = abs((mv['x'] + mv['w']) - anchor['x'])
        dy_below = abs(mv['y'] - (anchor['y'] + anchor['h']))
        dy_above = abs((mv['y'] + mv['h']) - anchor['y'])
        best = min(dx_right, dx_left, dy_below, dy_above)

        if best in (dx_right, dx_left):
            mv['x'] = anchor['x'] + anchor['w'] if best == dx_right else anchor['x'] - mv['w']
            # keep the drag's vertical intent, clamped to touching
            mv['y'] = max(anchor['y'] - mv['h'] + 1, min(mv['y'], anchor['y'] + anchor['h'] - 1))
        else:
            mv['y'] = anchor['y'] + anchor['h'] if best == dy_below else anchor['y'] - mv['h']
            mv['x'] = max(anchor['x'] - mv['w'] + 1, min(mv['x'], anchor['x'] + anchor['w'] - 1))

        min_x = min(m['x'] for m in self._monitors)
        min_y = min(m['y'] for m in self._monitors)
        for m in self._monitors:
            m['x'] = round(m['x'] - min_x)
            m['y'] = round(m['y'] - min_y)


def _rounded_rect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


# ---- small shared rows -----------------------------------------------------

def _format_refresh(hz):
    return f'{hz:.2f} Hz'.replace('.00 Hz', ' Hz')


def _format_resolution(w, h):
    return f'{w} × {h}'


def _format_scale(scale):
    return f'{round(scale * 100)}%'


class _DropdownRow(Gtk.Box):
    def __init__(self, title):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        for m in ('start', 'end'):
            getattr(self, f'set_margin_{m}')(14)
        for m in ('top', 'bottom'):
            getattr(self, f'set_margin_{m}')(10)
        self.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        self.dropdown = Gtk.DropDown.new_from_strings([' '])
        self._values = []
        self.append(self.dropdown)

    def set_options(self, options):
        self.dropdown.set_model(Gtk.StringList.new([label for label, _v in options] or [' ']))
        self._values = [v for _l, v in options]

    def get_selected_value(self):
        return self._values[self.dropdown.get_selected()] if self._values else None

    def set_selected_value(self, value):
        if value in self._values:
            self.dropdown.set_selected(self._values.index(value))


class _ToggleRow(Gtk.Box):
    def __init__(self, title, subtitle=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'])
        for m in ('start', 'end'):
            getattr(self, f'set_margin_{m}')(14)
        for m in ('top', 'bottom'):
            getattr(self, f'set_margin_{m}')(10)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text.append(Gtk.Label(label=title, xalign=0))
        if subtitle:
            text.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=['caption', 'dim-label']))
        self.append(text)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.append(self.switch)


class ScalingSliderRow(Gtk.Box):
    # text-scaling-factor's real range is 0.5-3.0; the extremes are unusable,
    # 0.8-1.3 covers "more space" to "larger text".
    MIN, MAX, DEFAULT = 0.8, 1.3, 1.0

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(Gtk.Label(label='Text Scaling', xalign=0, css_classes=['heading']))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, self.MIN, self.MAX, 0.01)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.add_mark(self.DEFAULT, Gtk.PositionType.BOTTOM, None)
        self.append(self.scale)
        labels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        labels.append(Gtk.Label(label='More Space', xalign=0, hexpand=True, css_classes=['caption', 'dim-label']))
        labels.append(Gtk.Label(label='Default', css_classes=['caption', 'dim-label']))
        labels.append(Gtk.Label(label='Larger Text', xalign=1, hexpand=True, css_classes=['caption', 'dim-label']))
        self.append(labels)


class BrightnessRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'], spacing=10)
        for m in ('start', 'end'):
            getattr(self, f'set_margin_{m}')(14)
        for m in ('top', 'bottom'):
            getattr(self, f'set_margin_{m}')(10)
        self.append(Gtk.Image.new_from_icon_name('display-brightness-symbolic'))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.append(self.scale)
        icon = Gtk.Image.new_from_icon_name('display-brightness-symbolic')
        icon.set_pixel_size(20)
        self.append(icon)


class TemperatureRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, css_classes=['network-row'], spacing=10)
        for m in ('start', 'end'):
            getattr(self, f'set_margin_{m}')(14)
        for m in ('top', 'bottom'):
            getattr(self, f'set_margin_{m}')(10)
        self.append(Gtk.Label(label='Color Temperature', xalign=0))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1700, 4700, 50)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.append(self.scale)


# ---- the page -------------------------------------------------------------

class DisplaysPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._interface_settings = Gio.Settings.new('org.gnome.desktop.interface')
        self._power_settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.power')
        self._color_settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.color')
        self._state = DisplayState()
        self._selected = None
        self._syncing = False
        self._brightness_available = False
        self._revert_dialog = None
        self._revert_source = 0

        self._build_ui()
        self._connect_power_proxy()
        self._refresh_all()

        self._interface_settings.connect('changed::text-scaling-factor', lambda *_a: self._refresh_scaling())
        self._power_settings.connect('changed::ambient-enabled', lambda *_a: self._refresh_scaling())
        for key in ('night-light-enabled', 'night-light-schedule-automatic', 'night-light-temperature'):
            self._color_settings.connect(f'changed::{key}', lambda *_a: self._refresh_night_light())

    # ---- build ---------------------------------------------------------

    def _build_ui(self):
        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'displays.svg'), 'video-display-symbolic',
            'Displays', 'Arrange your displays and set the resolution, scale, and color of each.',
        ))

        # Display mode (only shown with 2+ monitors).
        self._mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        self._mode_box.append(Gtk.Label(label='Display Arrangement', xalign=0, css_classes=['heading'], margin_start=4))
        mode_toggle = Gtk.Box(css_classes=['linked'], homogeneous=True)
        self._join_btn = Gtk.ToggleButton(label='Join Displays', css_classes=['segmented-toggle'], active=True)
        self._mirror_btn = Gtk.ToggleButton(label='Mirror', group=self._join_btn, css_classes=['segmented-toggle'])
        self._join_btn.connect('toggled', self._on_mode_toggled)
        mode_toggle.append(self._join_btn)
        mode_toggle.append(self._mirror_btn)
        self._mode_box.append(mode_toggle)
        self.append(self._mode_box)

        # Arrangement canvas (only shown with 2+ monitors, join mode).
        self._arrangement = MonitorArrangement()
        self._arrangement.connect('layout-changed', self._on_arrangement_changed)
        self._arrangement.connect('monitor-selected', lambda _a, connector: self._select_monitor(connector))
        self._arrangement_card = Gtk.Box(css_classes=['wifi-card'], visible=False)
        self._arrangement_card.append(self._arrangement)
        self.append(self._arrangement_card)

        # Which monitor the settings below control (only with 2+ monitors).
        self._picker_box = Gtk.Box(css_classes=['linked'], homogeneous=True, visible=False)
        self.append(self._picker_box)

        # Single-display header icon (kept from the original single-monitor page).
        self._single_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
        laptop_icon = os.path.join(ICON_DIR, 'laptop.svg')
        if os.path.isfile(laptop_icon):
            self._single_header.append(load_sized_image(laptop_icon, 110))
        else:
            img = Gtk.Image.new_from_icon_name('video-display-symbolic')
            img.set_pixel_size(96)
            self._single_header.append(img)
        self._single_header_label = Gtk.Label(css_classes=['title-4'])
        self._single_header.append(self._single_header_label)
        self.append(self._single_header)

        # Per-monitor settings.
        self._monitor_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        self._primary_row = _ToggleRow('Use as Primary Display',
                                       'Shows the top bar and new windows by default.')
        self._primary_row.switch.connect('state-set', self._on_primary_toggled)
        self._monitor_card.append(self._primary_row)

        self._orientation_row = _DropdownRow('Orientation')
        self._orientation_row.set_options(ORIENTATIONS)
        self._orientation_row.dropdown.connect('notify::selected', self._on_orientation_changed)
        self._monitor_card.append(self._orientation_row)

        self._resolution_row = _DropdownRow('Resolution')
        self._resolution_row.dropdown.connect('notify::selected', self._on_resolution_changed)
        self._monitor_card.append(self._resolution_row)

        self._refresh_rate_row = _DropdownRow('Refresh Rate')
        self._refresh_rate_row.dropdown.connect('notify::selected', self._on_refresh_rate_changed)
        self._monitor_card.append(self._refresh_rate_row)

        self._scale_row = _DropdownRow('Scale')
        self._scale_row.dropdown.connect('notify::selected', self._on_scale_changed)
        self._monitor_card.append(self._scale_row)

        self._enabled_row = _ToggleRow('Turn On This Display')
        self._enabled_row.switch.connect('state-set', self._on_enabled_toggled)
        self._monitor_card.append(self._enabled_row)

        self.append(self._monitor_card)

        self._monitor_status = Gtk.Label(
            label='No configurable display detected.', xalign=0, wrap=True,
            css_classes=['dim-label', 'caption'], margin_start=4, visible=False)
        self.append(self._monitor_status)

        # Text scaling.
        scaling_card = Gtk.Box(css_classes=['wifi-card'], orientation=Gtk.Orientation.VERTICAL)
        self._scaling_row = ScalingSliderRow()
        for m in ('start', 'end', 'top'):
            getattr(self._scaling_row, f'set_margin_{m}')(14)
        self._scaling_row.set_margin_bottom(10)
        self._scaling_row.scale.connect('value-changed', self._on_scaling_changed)
        scaling_card.append(self._scaling_row)
        self.append(scaling_card)

        # Brightness.
        brightness_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._brightness_row = BrightnessRow()
        self._brightness_row.scale.connect('value-changed', self._on_brightness_changed)
        brightness_card.append(self._brightness_row)
        self._auto_brightness_row = _ToggleRow('Automatically Adjust Brightness')
        self._auto_brightness_row.switch.connect('state-set', self._on_auto_brightness_toggled)
        brightness_card.append(self._auto_brightness_row)
        self.append(brightness_card)
        self._brightness_status = Gtk.Label(
            label='No display brightness control available on this computer.', xalign=0, wrap=True,
            css_classes=['dim-label', 'caption'], margin_start=4, visible=False)
        self.append(self._brightness_status)

        # Night Light.
        self.append(Gtk.Label(label='Night Light', xalign=0, css_classes=['heading'], margin_start=4))
        night_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self._night_light_row = _ToggleRow(
            'Night Light', 'Shifts the display to warmer colors to reduce eye strain.')
        self._night_light_row.switch.connect('state-set', self._on_night_light_toggled)
        night_card.append(self._night_light_row)
        self._schedule_row = _DropdownRow('Schedule')
        self._schedule_row.set_options([('Sunset to Sunrise', True), ('Manual', False)])
        self._schedule_row.dropdown.connect('notify::selected', self._on_schedule_changed)
        night_card.append(self._schedule_row)
        self._temperature_row = TemperatureRow()
        self._temperature_row.scale.connect('value-changed', self._on_temperature_changed)
        night_card.append(self._temperature_row)
        self.append(night_card)

    # ---- refresh -------------------------------------------------------

    def _refresh_all(self):
        self._refresh_monitors()
        self._refresh_scaling()
        self._refresh_night_light()

    def _refresh_monitors(self):
        self._state.refresh()
        available = self._state.available
        self._monitor_card.set_visible(available)
        self._monitor_status.set_visible(not available)
        if not available:
            self._mode_box.set_visible(False)
            self._arrangement_card.set_visible(False)
            self._picker_box.set_visible(False)
            self._single_header.set_visible(False)
            return

        connectors = [m['connector'] for m in self._state.monitors]
        if self._selected not in connectors:
            self._selected = self._state.primary_connector() or connectors[0]

        multi = len(self._state.monitors) > 1
        mirrored = self._state.is_mirrored()

        self._syncing = True
        self._mode_box.set_visible(multi)
        self._mirror_btn.set_active(mirrored)
        self._join_btn.set_active(not mirrored)
        self._arrangement_card.set_visible(multi and not mirrored)
        self._single_header.set_visible(not multi)
        if not multi:
            self._single_header_label.set_label(self._state.monitors[0]['name'])
        self._syncing = False

        self._rebuild_picker(multi)
        self._refresh_arrangement()
        self._refresh_monitor_card()

    def _rebuild_picker(self, multi):
        child = self._picker_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._picker_box.remove(child)
            child = nxt
        self._picker_box.set_visible(multi)
        if not multi:
            return
        first_btn = None
        for mon in self._state.monitors:
            btn = Gtk.ToggleButton(label=mon['name'], css_classes=['segmented-toggle'])
            if first_btn is None:
                first_btn = btn
            else:
                btn.set_group(first_btn)
            btn.set_active(mon['connector'] == self._selected)
            btn.connect('toggled', self._on_picker_toggled, mon['connector'])
            self._picker_box.append(btn)

    def _refresh_arrangement(self):
        if not self._arrangement_card.get_visible():
            return
        monitors = []
        for mon in self._state.monitors:
            lm = self._state.logical_for(mon['connector'])
            if not lm:
                continue
            w, h = self._state.logical_size(mon['connector'])
            monitors.append({
                'connector': mon['connector'], 'label': mon['name'],
                'w': w, 'h': h, 'x': lm['x'], 'y': lm['y'],
                'primary': lm['primary'],
            })
        self._arrangement.set_monitors(monitors, self._selected)

    def _refresh_monitor_card(self):
        mon = self._state.monitor(self._selected)
        if not mon:
            return
        self._syncing = True

        multi = len(self._state.monitors) > 1
        enabled = self._state.is_enabled(self._selected)
        lm = self._state.logical_for(self._selected)

        self._primary_row.set_visible(multi)
        self._primary_row.switch.set_active(bool(lm and lm['primary']))
        self._primary_row.switch.set_sensitive(enabled and not (lm and lm['primary']))

        self._enabled_row.set_visible(multi)
        self._enabled_row.switch.set_active(enabled)

        for row in (self._orientation_row, self._resolution_row, self._refresh_rate_row, self._scale_row):
            row.set_sensitive(enabled)

        transform = lm['transform'] if lm else 0
        self._orientation_row.set_selected_value(transform)

        resolutions = self._state.resolutions(self._selected)
        self._resolution_row.set_options([
            (_format_resolution(m['w'], m['h']), (m['w'], m['h'])) for m in resolutions])
        cur = self._state.mode(self._selected, mon['current_mode_id'])
        if cur:
            self._resolution_row.set_selected_value((cur['w'], cur['h']))
            self._populate_refresh_rates(cur['w'], cur['h'], select_id=cur['id'])
            self._populate_scales(cur['id'], select_scale=lm['scale'] if lm else 1.0)

        self._syncing = False

    def _populate_refresh_rates(self, w, h, select_id=None):
        modes = self._state.modes_for_resolution(self._selected, w, h)
        self._refresh_rate_row.set_options([(_format_refresh(m['refresh']), m['id']) for m in modes])
        if select_id:
            self._refresh_rate_row.set_selected_value(select_id)
        elif modes:
            self._refresh_rate_row.set_selected_value(modes[0]['id'])

    def _populate_scales(self, mode_id, select_scale=None):
        mode = self._state.mode(self._selected, mode_id)
        scales = mode['scales'] if mode else [1.0]
        self._scale_row.set_options([(_format_scale(s), s) for s in scales])
        if select_scale is not None and _closest(scales, select_scale) is not None:
            self._scale_row.set_selected_value(_closest(scales, select_scale))
        elif scales:
            self._scale_row.set_selected_value(scales[0])

    def _refresh_scaling(self):
        self._syncing = True
        self._scaling_row.scale.set_value(self._interface_settings.get_double('text-scaling-factor'))
        self._auto_brightness_row.switch.set_active(self._power_settings.get_boolean('ambient-enabled'))
        if self._brightness_available:
            level = self._get_brightness()
            if level is not None:
                self._brightness_row.scale.set_value(level)
        self._syncing = False

    def _refresh_night_light(self):
        self._syncing = True
        self._night_light_row.switch.set_active(self._color_settings.get_boolean('night-light-enabled'))
        self._schedule_row.set_selected_value(
            self._color_settings.get_boolean('night-light-schedule-automatic'))
        self._temperature_row.scale.set_value(self._color_settings.get_uint('night-light-temperature'))
        self._syncing = False

    # ---- selection ----------------------------------------------------

    def _select_monitor(self, connector):
        if connector == self._selected:
            return
        self._selected = connector
        child = self._picker_box.get_first_child()
        idx = 0
        for mon in self._state.monitors:
            if isinstance(child, Gtk.ToggleButton):
                child.set_active(mon['connector'] == connector)
            child = child.get_next_sibling() if child else None
            idx += 1
        self._refresh_arrangement()
        self._refresh_monitor_card()

    def _on_picker_toggled(self, btn, connector):
        if btn.get_active() and not self._syncing:
            self._select_monitor(connector)

    # ---- apply with revert-safety ------------------------------------

    def _apply_safely(self, overrides, label):
        """Apply temporarily, then ask to keep. If the confirm window can't be
        shown or times out, Mutter itself reverts (temporary configs auto-
        revert after ~20s) and we re-read state."""
        if not self._state.apply(overrides, method=APPLY_METHOD_TEMPORARY):
            self._refresh_monitors()
            return
        self._open_revert_dialog(overrides, label)

    def _open_revert_dialog(self, overrides, label):
        self._close_revert_dialog()
        win = Gtk.Window(modal=True, resizable=False, title='Keep Display Changes?')
        root = self.get_root()
        if isinstance(root, Gtk.Window):
            win.set_transient_for(root)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        box.append(Gtk.Label(label=f'Keep the new {label}?', css_classes=['title-4']))
        countdown = Gtk.Label(css_classes=['dim-label'])
        box.append(countdown)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        revert_btn = Gtk.Button(label='Revert')
        keep_btn = Gtk.Button(label='Keep Changes', css_classes=['suggested-action'])
        buttons.append(revert_btn)
        buttons.append(keep_btn)
        box.append(buttons)
        win.set_child(box)

        state = {'left': REVERT_COUNTDOWN_SECONDS}

        def tick():
            state['left'] -= 1
            countdown.set_label(f'Reverting in {state["left"]} seconds…')
            if state['left'] <= 0:
                do_revert()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        def do_keep(*_a):
            self._state.apply(overrides, method=APPLY_METHOD_PERSISTENT)
            self._close_revert_dialog()
            self._refresh_monitors()

        def do_revert(*_a):
            self._state.refresh()
            self._state.apply({}, method=APPLY_METHOD_PERSISTENT)
            self._close_revert_dialog()
            self._refresh_monitors()

        keep_btn.connect('clicked', do_keep)
        revert_btn.connect('clicked', do_revert)
        win.connect('close-request', lambda *_a: (do_revert(), True)[1])

        countdown.set_label(f'Reverting in {state["left"]} seconds…')
        self._revert_dialog = win
        self._revert_source = GLib.timeout_add_seconds(1, tick)
        win.present()

    def _close_revert_dialog(self):
        if self._revert_source:
            GLib.source_remove(self._revert_source)
            self._revert_source = 0
        if self._revert_dialog:
            self._revert_dialog.destroy()
            self._revert_dialog = None

    # ---- monitor-setting handlers ----------------------------------

    def _on_mode_toggled(self, _btn):
        if self._syncing:
            return
        want_mirror = self._mirror_btn.get_active()
        if want_mirror == self._state.is_mirrored():
            return
        if want_mirror:
            # Pick the largest resolution every monitor can do.
            common = None
            for mon in self._state.monitors:
                res = {(m['w'], m['h']) for m in mon['modes']}
                common = res if common is None else (common & res)
            if not common:
                self._mirror_btn.set_active(False)
                return
            w, h = max(common, key=lambda r: r[0] * r[1])
            mode_ids = {}
            for mon in self._state.monitors:
                modes = self._state.modes_for_resolution(mon['connector'], w, h)
                mode_ids[mon['connector']] = modes[0]['id']
            self._apply_safely({'__mirror__': {'mode_ids': mode_ids, 'scale': 1.0}}, 'mirror setup')
        else:
            self._apply_safely({}, 'display arrangement')  # {} rebuilds from per-monitor state = un-mirror

    def _on_arrangement_changed(self, _widget):
        if self._syncing:
            return
        positions = self._arrangement.positions()
        overrides = {c: {'x': int(x), 'y': int(y)} for c, (x, y) in positions.items()}
        self._apply_safely(overrides, 'arrangement')

    def _on_primary_toggled(self, switch, state):
        if self._syncing or not state:
            return False
        self._state.apply({self._selected: {'primary': True}}, method=APPLY_METHOD_PERSISTENT)
        self._refresh_monitors()
        return False

    def _on_enabled_toggled(self, switch, state):
        if self._syncing:
            return False
        enabled_count = sum(1 for m in self._state.monitors if self._state.is_enabled(m['connector']))
        if not state and enabled_count <= 1:
            switch.set_active(True)
            return True
        self._apply_safely({self._selected: {'enabled': state}}, 'display setup')
        return False

    def _on_orientation_changed(self, _dd, _pspec):
        if self._syncing:
            return
        self._apply_safely({self._selected: {'transform': self._orientation_row.get_selected_value()}},
                           'orientation')

    def _on_resolution_changed(self, _dd, _pspec):
        if self._syncing:
            return
        value = self._resolution_row.get_selected_value()
        if not value:
            return
        w, h = value
        modes = self._state.modes_for_resolution(self._selected, w, h)
        if not modes:
            return
        self._syncing = True
        self._populate_refresh_rates(w, h, select_id=modes[0]['id'])
        self._populate_scales(modes[0]['id'])
        self._syncing = False
        self._apply_safely(
            {self._selected: {'mode_id': modes[0]['id'], 'scale': self._scale_row.get_selected_value()}},
            'resolution')

    def _on_refresh_rate_changed(self, _dd, _pspec):
        if self._syncing:
            return
        mode_id = self._refresh_rate_row.get_selected_value()
        if not mode_id:
            return
        self._syncing = True
        self._populate_scales(mode_id, select_scale=self._scale_row.get_selected_value())
        self._syncing = False
        self._apply_safely(
            {self._selected: {'mode_id': mode_id, 'scale': self._scale_row.get_selected_value()}},
            'refresh rate')

    def _on_scale_changed(self, _dd, _pspec):
        if self._syncing:
            return
        mode_id = self._refresh_rate_row.get_selected_value()
        self._apply_safely(
            {self._selected: {'mode_id': mode_id, 'scale': self._scale_row.get_selected_value()}},
            'scale')

    # ---- text scaling / brightness / night light ------------------

    def _on_scaling_changed(self, scale):
        if not self._syncing:
            self._interface_settings.set_double('text-scaling-factor', scale.get_value())

    def _on_brightness_changed(self, scale):
        if not self._syncing:
            self._set_brightness(round(scale.get_value()))

    def _on_auto_brightness_toggled(self, _switch, state):
        if not self._syncing:
            self._power_settings.set_boolean('ambient-enabled', state)
        return False

    def _on_night_light_toggled(self, _switch, state):
        if not self._syncing:
            self._color_settings.set_boolean('night-light-enabled', state)
        return False

    def _on_schedule_changed(self, _dd, _pspec):
        if not self._syncing:
            self._color_settings.set_boolean(
                'night-light-schedule-automatic', self._schedule_row.get_selected_value())

    def _on_temperature_changed(self, scale):
        if not self._syncing:
            self._color_settings.set_uint('night-light-temperature', round(scale.get_value()))

    # ---- brightness D-Bus ----------------------------------------

    def _connect_power_proxy(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Get',
                GLib.Variant('(ss)', (SCREEN_IFACE, 'Brightness')),
                GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None)
            self._brightness_available = True
            self._bus.signal_subscribe(
                POWER_SERVICE, PROPS_IFACE, 'PropertiesChanged', POWER_PATH, SCREEN_IFACE,
                Gio.DBusSignalFlags.NONE, lambda *_a: self._refresh_scaling())
        except GLib.Error:
            self._bus = None
            self._brightness_available = False
        self._brightness_row.set_visible(self._brightness_available)
        self._brightness_status.set_visible(not self._brightness_available)

    def _get_brightness(self):
        try:
            r = self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Get',
                GLib.Variant('(ss)', (SCREEN_IFACE, 'Brightness')),
                GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 2000, None)
            return r.unpack()[0]
        except GLib.Error:
            return None

    def _set_brightness(self, value):
        if not self._brightness_available:
            return
        try:
            self._bus.call_sync(
                POWER_SERVICE, POWER_PATH, PROPS_IFACE, 'Set',
                GLib.Variant('(ssv)', (SCREEN_IFACE, 'Brightness', GLib.Variant('i', value))),
                None, Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            pass


def _closest(values, target):
    if not values:
        return None
    return min(values, key=lambda v: abs(v - target))
