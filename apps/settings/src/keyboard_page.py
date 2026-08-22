import os

from gi.repository import Gio, Gtk

from widgets import make_hero_header, SliderRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

KEYBOARD_SCHEMA = 'org.gnome.desktop.peripherals.keyboard'


def _bind_flipped_slider(settings: Gio.Settings, key: str, scale: Gtk.Scale, low: int, high: int):
    """Binds a slider whose on-screen "more to the right" direction is the
    OPPOSITE of the underlying key's own value direction (repeat-interval/
    delay: a *smaller* number means faster/shorter) -- without Gtk.Scale's
    own set_inverted(), which was tried first and confirmed live to be the
    actual bug: inverting the widget flips which edge GTK treats as the
    value origin, but the theme's highlight-track rendering doesn't follow
    that flip, so the filled portion ends up on the wrong side of the
    handle regardless of which way the value itself reads. Flipping the
    VALUE instead (low+high-x) keeps the widget itself in its normal,
    non-inverted state -- so the highlight always correctly fills from the
    left up to the handle -- while the handle position still reads
    correctly (further right = faster/shorter, matching real macOS/GNOME
    keyboard-rate sliders)."""
    adjustment = scale.get_adjustment()
    updating = False

    def to_slider(raw_value):
        return low + high - raw_value

    def refresh_from_settings(*_args):
        nonlocal updating
        updating = True
        adjustment.set_value(to_slider(settings.get_uint(key)))
        updating = False

    def write_to_settings(_adj):
        nonlocal updating
        if updating:
            return
        settings.set_uint(key, round(to_slider(adjustment.get_value())))

    refresh_from_settings()
    adjustment.connect('value-changed', write_to_settings)
    settings.connect(f'changed::{key}', refresh_from_settings)


class KeyboardPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._settings = Gio.Settings.new(KEYBOARD_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'keyboard.svg'), 'input-keyboard-symbolic',
            'Keyboard', 'Set how quickly keys repeat, and manage your typing preferences.',
        ))

        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        repeat_row = ToggleRow('Key Repeat', 'Press and hold a key to repeat it.')
        self._settings.bind('repeat', repeat_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(repeat_row)

        # Lower repeat-interval == faster repeats, so the slider reads
        # "Slow -> Fast" left-to-right rather than backwards -- see
        # _bind_flipped_slider's docstring for why this isn't done with
        # Gtk.Scale's own set_inverted() (that flips the handle position
        # correctly but leaves the highlighted track on the wrong side of
        # it, confirmed live).
        rate_row = SliderRow('Key Repeat Rate', 20, 200, 5)
        _bind_flipped_slider(self._settings, 'repeat-interval', rate_row.scale, 20, 200)
        card.append(rate_row)

        delay_row = SliderRow('Delay Until Repeat', 100, 2000, 50)
        _bind_flipped_slider(self._settings, 'delay', delay_row.scale, 100, 2000)
        card.append(delay_row)

        self.append(card)
