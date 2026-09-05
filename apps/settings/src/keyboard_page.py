import os

import gi

gi.require_version('GnomeDesktop', '4.0')

from gi.repository import Gio, GLib, GnomeDesktop, Gtk

from widgets import make_hero_header, SliderRow, ToggleRow

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icons')

KEYBOARD_SCHEMA = 'org.gnome.desktop.peripherals.keyboard'
INPUT_SOURCES_SCHEMA = 'org.gnome.desktop.input-sources'

_xkb_info = GnomeDesktop.XkbInfo()


def _layout_name(source_type, source_id):
    if source_type == 'xkb':
        info = _xkb_info.get_layout_info(source_id)
        if info and info[0]:
            return info[1] or source_id
    return source_id


def _bind_flipped_slider(settings, key, scale, low, high):
    """Slider whose "further right" direction is the opposite of the key's own
    value direction (repeat-interval / delay: a smaller number = faster). Flips
    the value (low+high-x) rather than the widget, so the highlighted track
    still fills correctly from the left (Gtk.Scale.set_inverted() doesn't move
    the fill -- confirmed live)."""
    adjustment = scale.get_adjustment()
    updating = False

    def to_slider(raw):
        return low + high - raw

    def refresh(*_a):
        nonlocal updating
        updating = True
        adjustment.set_value(to_slider(settings.get_uint(key)))
        updating = False

    def write(_adj):
        if not updating:
            settings.set_uint(key, round(to_slider(adjustment.get_value())))

    refresh()
    adjustment.connect('value-changed', write)
    settings.connect(f'changed::{key}', refresh)


class _AddInputSourceDialog(Gtk.Window):
    def __init__(self, parent, already_added, on_add):
        super().__init__(title='Add Input Source', transient_for=parent, modal=True,
                         default_width=380, default_height=460)
        self._on_add = on_add

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        self.set_child(box)

        self._search = Gtk.SearchEntry(placeholder_text='Search layouts')
        self._search.connect('search-changed', lambda *_a: self._filter.changed(Gtk.FilterChange.DIFFERENT))
        box.append(self._search)

        self._store = Gio.ListStore.new(Gtk.StringObject)
        entries = []
        for layout_id in _xkb_info.get_all_layouts():
            info = _xkb_info.get_layout_info(layout_id)
            if not info or not info[0] or ('xkb', layout_id) in already_added:
                continue
            entries.append((info[1] or layout_id, layout_id))
        for display, layout_id in sorted(entries):
            obj = Gtk.StringObject.new(display)
            obj.layout_id = layout_id
            self._store.append(obj)

        self._filter = Gtk.CustomFilter.new(self._match)
        model = Gtk.FilterListModel.new(self._store, self._filter)

        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', lambda _f, item: item.set_child(
            Gtk.Label(xalign=0, margin_top=8, margin_bottom=8, margin_start=6)))
        factory.connect('bind', lambda _f, item: item.get_child().set_label(item.get_item().get_string()))

        self._list = Gtk.ListView.new(Gtk.SingleSelection.new(model), factory)
        self._list.connect('activate', self._on_activate)
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True, css_classes=['wifi-card'])
        scroller.set_child(self._list)
        box.append(scroller)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_a: self.close())
        add = Gtk.Button(label='Add', css_classes=['suggested-action'])
        add.connect('clicked', lambda *_a: self._add_selected())
        buttons.append(cancel)
        buttons.append(add)
        box.append(buttons)

    def _match(self, obj):
        text = self._search.get_text().strip().lower()
        return not text or text in obj.get_string().lower()

    def _on_activate(self, _list, position):
        obj = self._list.get_model().get_item(position)
        if obj:
            self._on_add('xkb', obj.layout_id)
            self.close()

    def _add_selected(self):
        obj = self._list.get_model().get_selected_item()
        if obj:
            self._on_add('xkb', obj.layout_id)
            self.close()


class KeyboardPage(Gtk.Box):
    def __init__(self, on_open_shortcuts=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(18)
        self.set_margin_bottom(18)

        self._on_open_shortcuts = on_open_shortcuts
        self._settings = Gio.Settings.new(KEYBOARD_SCHEMA)
        self._input_sources = Gio.Settings.new(INPUT_SOURCES_SCHEMA)

        self.append(make_hero_header(
            os.path.join(ICON_DIR, 'keyboard.svg'), 'input-keyboard-symbolic',
            'Keyboard', 'Manage input sources, keyboard shortcuts, and key repeat.',
        ))

        # ---- Input Sources ----
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.append(Gtk.Label(label='Input Sources', xalign=0, hexpand=True,
                                css_classes=['heading'], margin_start=4))
        add_btn = Gtk.Button(icon_name='list-add-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER)
        add_btn.connect('clicked', self._on_add_source)
        header.append(add_btn)
        self.append(header)

        self._sources_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        self.append(self._sources_card)
        self._input_sources.connect('changed::sources', lambda *_a: self._rebuild_sources())

        # ---- Shortcuts drill-in ----
        shortcuts_card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, css_classes=['network-row'])
        row.set_margin_start(14)
        row.set_margin_end(10)
        row.set_margin_top(12)
        row.set_margin_bottom(12)
        row.append(Gtk.Label(label='Keyboard Shortcuts', xalign=0, hexpand=True, valign=Gtk.Align.CENTER))
        row.append(Gtk.Image.new_from_icon_name('go-next-symbolic'))
        if on_open_shortcuts:
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a: on_open_shortcuts())
            row.add_controller(click)
            row.set_cursor_from_name('pointer')
        shortcuts_card.append(row)
        self.append(shortcuts_card)

        # ---- Key repeat ----
        self.append(Gtk.Label(label='Key Repeat', xalign=0, css_classes=['heading'], margin_start=4))
        card = Gtk.ListBox(css_classes=['wifi-card', 'boxed-list'], selection_mode=Gtk.SelectionMode.NONE)

        repeat_row = ToggleRow('Key Repeat', 'Press and hold a key to repeat it.')
        self._settings.bind('repeat', repeat_row.switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        card.append(repeat_row)

        rate_row = SliderRow('Key Repeat Rate', 20, 200, 5)
        _bind_flipped_slider(self._settings, 'repeat-interval', rate_row.scale, 20, 200)
        card.append(rate_row)

        delay_row = SliderRow('Delay Until Repeat', 100, 2000, 50)
        _bind_flipped_slider(self._settings, 'delay', delay_row.scale, 100, 2000)
        card.append(delay_row)
        self.append(card)

        self._rebuild_sources()

    # ---- input sources ----------------------------------------------

    def _sources(self):
        return [(t, i) for t, i in self._input_sources.get_value('sources').unpack()]

    def _write_sources(self, sources):
        self._input_sources.set_value('sources', GLib.Variant('a(ss)', sources))

    def _rebuild_sources(self):
        child = self._sources_card.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._sources_card.remove(child)
            child = nxt

        sources = self._sources()
        for index, (source_type, source_id) in enumerate(sources):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, css_classes=['network-row'])
            row.set_margin_start(14)
            row.set_margin_end(8)
            row.set_margin_top(8)
            row.set_margin_bottom(8)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
            text.append(Gtk.Label(label=_layout_name(source_type, source_id), xalign=0))
            if index == 0:
                text.append(Gtk.Label(label='Default', xalign=0, css_classes=['caption', 'dim-label']))
            row.append(text)

            up = Gtk.Button(icon_name='go-up-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER,
                            sensitive=index > 0)
            up.connect('clicked', lambda _b, i=index: self._move_source(i, -1))
            down = Gtk.Button(icon_name='go-down-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER,
                              sensitive=index < len(sources) - 1)
            down.connect('clicked', lambda _b, i=index: self._move_source(i, 1))
            remove = Gtk.Button(icon_name='list-remove-symbolic', css_classes=['flat'], valign=Gtk.Align.CENTER,
                                sensitive=len(sources) > 1)
            remove.connect('clicked', lambda _b, i=index: self._remove_source(i))
            row.append(up)
            row.append(down)
            row.append(remove)
            self._sources_card.append(row)

    def _move_source(self, index, delta):
        sources = self._sources()
        j = index + delta
        if 0 <= j < len(sources):
            sources[index], sources[j] = sources[j], sources[index]
            self._write_sources(sources)

    def _remove_source(self, index):
        sources = self._sources()
        if len(sources) > 1:
            del sources[index]
            self._write_sources(sources)

    def _on_add_source(self, _btn):
        root = self.get_root()
        dialog = _AddInputSourceDialog(
            root if isinstance(root, Gtk.Window) else None, set(self._sources()), self._add_source)
        dialog.present()

    def _add_source(self, source_type, source_id):
        sources = self._sources()
        if (source_type, source_id) not in sources:
            sources.append((source_type, source_id))
            self._write_sources(sources)
