"""Drag-to-reposition, slider-to-zoom photo crop panel -- shown after picking
a photo in Contact Details, before it becomes the avatar override (explicit
user request: a picked photo shouldn't just get an automatic center-crop
silently applied, the user should be able to adjust what part of it shows).

Draws directly with Cairo (Gtk.DrawingArea.set_draw_func) rather than
composing GTK widgets for the preview, since panning/zooming an image behind
a fixed circular mask is exactly what Cairo transforms are for; GTK's own
widget layout has no equivalent op. Gdk.cairo_set_source_pixbuf() is the
standard bridge from a loaded GdkPixbuf into that Cairo context.
"""
import math
import os
import time

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, GObject, Gtk

_PREVIEW_SIZE = 280
_OUTPUT_SIZE = 400  # final saved crop resolution -- plenty for any avatar render size
_MIN_ZOOM = 1.0
_MAX_ZOOM = 3.0

_CROP_CACHE_DIR = os.path.expanduser("~/.local/share/peachos-bluebubbles/avatar_crops")


class PhotoCropDialog(Adw.Window):
    __gtype_name__ = "PhotoCropDialog"

    __gsignals__ = {
        "photo-cropped": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # saved file path
    }

    def __init__(self, parent: Gtk.Window, source_path: str, chat_guid: str):
        super().__init__(transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_title("Adjust Photo")
        self.set_resizable(False)
        self._chat_guid = chat_guid

        self._pixbuf = GdkPixbuf.Pixbuf.new_from_file(source_path)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom = 1.0
        self._drag_start_pan = (0.0, 0.0)

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)
        toolbar.add_top_bar(Adw.HeaderBar(show_title=True))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_top(20)
        root.set_margin_bottom(20)
        root.set_margin_start(20)
        root.set_margin_end(20)
        toolbar.set_content(root)

        hint = Gtk.Label(label="Drag to reposition, use the slider to zoom", halign=Gtk.Align.CENTER)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        root.append(hint)

        self._area = Gtk.DrawingArea()
        self._area.set_content_width(_PREVIEW_SIZE)
        self._area.set_content_height(_PREVIEW_SIZE)
        self._area.set_halign(Gtk.Align.CENTER)
        self._area.set_draw_func(self._on_draw)
        root.append(self._area)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        self._area.add_controller(drag)

        zoom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        zoom_row.append(Gtk.Image.new_from_icon_name("zoom-out-symbolic"))
        self._zoom_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, _MIN_ZOOM, _MAX_ZOOM, 0.01)
        self._zoom_scale.set_value(_MIN_ZOOM)
        self._zoom_scale.set_hexpand(True)
        self._zoom_scale.set_draw_value(False)
        self._zoom_scale.connect("value-changed", self._on_zoom_changed)
        zoom_row.append(self._zoom_scale)
        zoom_row.append(Gtk.Image.new_from_icon_name("zoom-in-symbolic"))
        root.append(zoom_row)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: self.close())
        btn_row.append(cancel_btn)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        btn_row.append(save_btn)
        root.append(btn_row)

    # --- geometry -----------------------------------------------------

    def _cover_scale(self) -> float:
        """Scale at which the source image, undistorted, fully covers the
        preview square -- same "cover" idea as image_utils.load_cover_texture,
        just computed here since we need the raw scale factor (not a
        pre-cropped result) to drive live panning/zooming."""
        w, h = self._pixbuf.get_width(), self._pixbuf.get_height()
        return max(_PREVIEW_SIZE / w, _PREVIEW_SIZE / h)

    def _clamp_pan(self):
        scale = self._cover_scale() * self._zoom
        img_w = self._pixbuf.get_width() * scale
        img_h = self._pixbuf.get_height() * scale
        max_pan_x = max(0.0, (img_w - _PREVIEW_SIZE) / 2)
        max_pan_y = max(0.0, (img_h - _PREVIEW_SIZE) / 2)
        self._pan_x = max(-max_pan_x, min(max_pan_x, self._pan_x))
        self._pan_y = max(-max_pan_y, min(max_pan_y, self._pan_y))

    # --- drawing --------------------------------------------------------

    def _paint_image(self, cr: cairo.Context, size: int, pan_x: float, pan_y: float, zoom: float):
        scale = (size / _PREVIEW_SIZE) * self._cover_scale() * zoom
        img_w = self._pixbuf.get_width() * scale
        img_h = self._pixbuf.get_height() * scale
        cx = size / 2 + pan_x * (size / _PREVIEW_SIZE)
        cy = size / 2 + pan_y * (size / _PREVIEW_SIZE)

        cr.save()
        cr.translate(cx - img_w / 2, cy - img_h / 2)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        pattern = cr.get_source()
        pattern.set_filter(cairo.FILTER_GOOD)
        cr.paint()
        cr.restore()

    def _on_draw(self, _area, cr: cairo.Context, width: int, height: int):
        cr.save()
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, 2 * math.pi)
        cr.clip()

        cr.set_source_rgb(0.557, 0.557, 0.576)  # #8E8E93, same gray as the real avatar fallback
        cr.paint()

        self._paint_image(cr, width, self._pan_x, self._pan_y, self._zoom)
        cr.restore()

        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.set_line_width(1.5)
        cr.arc(width / 2, height / 2, min(width, height) / 2 - 1, 0, 2 * math.pi)
        cr.stroke()

    # --- interaction ------------------------------------------------------

    def _on_drag_begin(self, _gesture, _start_x, _start_y):
        self._drag_start_pan = (self._pan_x, self._pan_y)

    def _on_drag_update(self, _gesture, offset_x, offset_y):
        self._pan_x = self._drag_start_pan[0] + offset_x
        self._pan_y = self._drag_start_pan[1] + offset_y
        self._clamp_pan()
        self._area.queue_draw()

    def _on_zoom_changed(self, scale: Gtk.Scale):
        self._zoom = scale.get_value()
        self._clamp_pan()
        self._area.queue_draw()

    # --- save -------------------------------------------------------------

    def _on_save(self, _button):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, _OUTPUT_SIZE, _OUTPUT_SIZE)
        cr = cairo.Context(surface)
        pan_x = self._pan_x * (_OUTPUT_SIZE / _PREVIEW_SIZE)
        pan_y = self._pan_y * (_OUTPUT_SIZE / _PREVIEW_SIZE)
        cr.set_source_rgb(0.557, 0.557, 0.576)
        cr.paint()
        self._paint_image(cr, _OUTPUT_SIZE, pan_x, pan_y, self._zoom)

        os.makedirs(_CROP_CACHE_DIR, exist_ok=True)
        safe_guid = "".join(c if c.isalnum() else "_" for c in self._chat_guid)
        out_path = os.path.join(_CROP_CACHE_DIR, f"{safe_guid}-{int(time.time())}.png")
        surface.write_to_png(out_path)

        self.emit("photo-cropped", out_path)
        self.close()
