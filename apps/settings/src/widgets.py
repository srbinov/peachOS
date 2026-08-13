import os

from gi.repository import Gdk, GLib, Gtk


def make_hero_header(icon_path: str, fallback_icon_name: str, title: str, description: str,
                      icon_size: int = 64) -> Gtk.Widget:
    """The big-icon/title/description card that sits at the top of every
    tab, matching the reference "General" page layout. Shared across all
    page modules rather than duplicated per-file."""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    inner = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
        margin_top=22, margin_bottom=22, margin_start=24, margin_end=24,
    )

    if icon_path and os.path.isfile(icon_path):
        icon = Gtk.Image.new_from_file(icon_path)
    else:
        icon = Gtk.Image.new_from_icon_name(fallback_icon_name)
    icon.set_pixel_size(icon_size)
    inner.append(icon)

    inner.append(Gtk.Label(label=title, css_classes=['title-1']))

    desc = Gtk.Label(
        label=description, wrap=True, justify=Gtk.Justification.CENTER,
        css_classes=['dim-label'],
    )
    desc.set_max_width_chars(56)
    inner.append(desc)

    card.append(inner)
    return card


class TypeaheadDropdown(Gtk.MenuButton):
    """A combo control for long option lists (time zones, locales) that
    behaves like classic type-to-jump selection: the popup always shows
    every option -- nothing is filtered out -- and each keystroke just
    moves the selection to the next best match.

    Gtk.DropDown's own enable-search does the opposite: it's a real
    filter that hides non-matching rows, and GTK4's GtkListView (unlike
    the old GtkTreeView) has no built-in non-filtering typeahead to fall
    back on either. Reimplementing the popup here instead of trying to
    bend DropDown into something it isn't."""

    def __init__(self):
        super().__init__(css_classes=['flat'])
        self._options = []
        self._rows = []
        self._selected_index = -1
        self._search_buffer = ''
        self._search_reset_id = 0
        self._on_changed = None
        # The value when the popover was last opened, and whether the
        # current close should discard the browsing-around that happened
        # in between (Escape) rather than commit it -- typing/arrowing
        # through options while the popover is open is just *browsing*;
        # only Enter, a click, or a non-cancelled close should actually
        # commit and fire on_changed. Committing on every keystroke would
        # fire a real backend call (D-Bus SetTimezone, etc.) for every
        # letter typed, before the user's even finished typing.
        self._value_on_open = None
        self._cancel_close = False

        self._label = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)  # Pango.EllipsizeMode.END
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.append(self._label)
        content.append(Gtk.Image.new_from_icon_name('pan-down-symbolic'))
        self.set_child(content)

        self._listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=['boxed-list'])
        self._listbox.connect('row-activated', self._on_row_activated)

        scroller = Gtk.ScrolledWindow(
            min_content_height=280, max_content_height=280, propagate_natural_width=True,
        )
        scroller.set_child(self._listbox)
        scroller.set_margin_start(4)
        scroller.set_margin_end(4)
        scroller.set_margin_top(4)
        scroller.set_margin_bottom(4)

        popover = Gtk.Popover(child=scroller, has_arrow=True)
        self.set_popover(popover)
        self._popover = popover

        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self._on_key_pressed)
        popover.add_controller(key_controller)
        popover.connect('show', self._on_popover_show)
        popover.connect('closed', self._on_popover_closed)

    def set_options(self, options: list, selected: str = None):
        self._options = list(options)
        while (child := self._listbox.get_first_child()) is not None:
            self._listbox.remove(child)
        self._rows = []
        for text in self._options:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(
                label=text, xalign=0,
                margin_start=10, margin_end=10, margin_top=6, margin_bottom=6,
            ))
            self._listbox.append(row)
            self._rows.append(row)

        if selected in self._options:
            self._select_index(self._options.index(selected))
        elif self._options:
            self._select_index(0)
        else:
            self._selected_index = -1
            self._label.set_label('')

    def get_selected(self):
        if 0 <= self._selected_index < len(self._options):
            return self._options[self._selected_index]
        return None

    def connect_changed(self, callback):
        """callback(new_value: str) -- fired only on a real user pick,
        never while set_options() is syncing from live system state."""
        self._on_changed = callback

    def _select_index(self, index: int):
        if not (0 <= index < len(self._options)):
            return
        self._selected_index = index
        self._label.set_label(self._options[index])
        self._listbox.select_row(self._rows[index])

    def _on_row_activated(self, _listbox, row):
        self._select_index(self._rows.index(row))
        self._popover.popdown()

    def _on_popover_show(self, _popover):
        self._search_buffer = ''
        self._value_on_open = self.get_selected()
        self._cancel_close = False
        if 0 <= self._selected_index < len(self._rows):
            self._rows[self._selected_index].grab_focus()

    def _on_popover_closed(self, _popover):
        if self._cancel_close:
            # Escape -- discard whatever browsing happened, revert to
            # what was selected before the popover opened.
            if self._value_on_open in self._options:
                self._select_index(self._options.index(self._value_on_open))
            return
        new_value = self.get_selected()
        if new_value is not None and new_value != self._value_on_open and self._on_changed:
            self._on_changed(new_value)

    def _on_key_pressed(self, _controller, keyval, _keycode, _state):
        name = Gdk.keyval_name(keyval)
        if name == 'Escape':
            self._cancel_close = True
            self._popover.popdown()
            return True
        if name in ('Return', 'KP_Enter'):
            self._popover.popdown()
            return True
        if name == 'BackSpace':
            self._search_buffer = self._search_buffer[:-1]
            self._arm_search_reset()
            return True

        codepoint = Gdk.keyval_to_unicode(keyval)
        char = chr(codepoint) if codepoint else ''
        if not char or not char.isprintable():
            return False

        self._search_buffer += char.lower()
        self._arm_search_reset()

        for i, text in enumerate(self._options):
            if self._search_buffer in text.lower():
                self._select_index(i)
                self._rows[i].grab_focus()
                break
        return True

    def _arm_search_reset(self):
        if self._search_reset_id:
            GLib.source_remove(self._search_reset_id)
        self._search_reset_id = GLib.timeout_add(1000, self._reset_search_buffer)

    def _reset_search_buffer(self):
        self._search_buffer = ''
        self._search_reset_id = 0
        return GLib.SOURCE_REMOVE
