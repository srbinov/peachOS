// Builds a St.ImageContent of the wallpaper region behind a given screen rect,
// so a LiquidGlass actor can paint it as its own content and the refraction
// shader can sample it. Static image wallpapers only (the KDE original also
// gates the live/video path behind a battery-drain toggle).
//
// GNOME 50: Clutter.Image is gone -- St.ImageContent + Cogl bytes, the same
// pattern as macos-top-panel/lib/panelBackground.js.

import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GdkPixbuf from 'gi://GdkPixbuf';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BG_SCHEMA = 'org.gnome.desktop.background';
const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';

function currentWallpaperPath() {
    const bg = new Gio.Settings({schema_id: BG_SCHEMA});
    const iface = new Gio.Settings({schema_id: INTERFACE_SCHEMA});
    const dark = iface.get_string('color-scheme') === 'prefer-dark';
    const darkUri = bg.get_string('picture-uri-dark');
    const uri = (dark && darkUri) ? darkUri : bg.get_string('picture-uri');
    if (!uri)
        return {path: null, options: 'zoom'};
    let path = uri;
    try {
        path = GLib.filename_from_uri(uri)[0];
    } catch (e) {
        // already a plain path
    }
    return {path, options: bg.get_string('picture-options') || 'zoom'};
}

// Where a monitor-local point (mx, my) lands in the source image, given how the
// wallpaper is fitted to the monitor.
function monitorToImage(mx, my, mw, mh, iw, ih, options) {
    if (options === 'stretched')
        return [mx / mw * iw, my / mh * ih];

    // zoom (cover), scaled (contain), and everything else: uniform scale, centred.
    const scale = options === 'scaled'
        ? Math.min(mw / iw, mh / ih)
        : Math.max(mw / iw, mh / ih);
    const dispW = iw * scale;
    const dispH = ih * scale;
    const offX = (dispW - mw) / 2;
    const offY = (dispH - mh) / 2;
    return [(mx + offX) / scale, (my + offY) / scale];
}

/**
 * @param {{x,y,width,height}} screenRect  the full actor rect in stage coords
 *   (glass + margin), i.e. the region to sample.
 * @param {number} texW  target texture width in px
 * @param {number} texH  target texture height in px
 * @returns {St.ImageContent|null}
 */
export function buildWallpaperTexture(screenRect, texW, texH) {
    const {path, options} = currentWallpaperPath();
    if (!path)
        return null;

    let src;
    try {
        src = GdkPixbuf.Pixbuf.new_from_file(path);
    } catch (e) {
        logError(e, '[peachos-widgets] could not load wallpaper');
        return null;
    }
    const iw = src.get_width();
    const ih = src.get_height();

    // Which monitor is this rect on?
    const monitors = Main.layoutManager.monitors;
    const cx = screenRect.x + screenRect.width / 2;
    const cy = screenRect.y + screenRect.height / 2;
    const mon = monitors.find(m =>
        cx >= m.x && cx < m.x + m.width && cy >= m.y && cy < m.y + m.height)
        || Main.layoutManager.primaryMonitor;

    const [ix0, iy0] = monitorToImage(
        screenRect.x - mon.x, screenRect.y - mon.y, mon.width, mon.height, iw, ih, options);
    const [ix1, iy1] = monitorToImage(
        screenRect.x - mon.x + screenRect.width, screenRect.y - mon.y + screenRect.height,
        mon.width, mon.height, iw, ih, options);

    // Clamp the source rect inside the image (edge-widgets get a small
    // misalignment for now; a padded fetch is the proper fix).
    const sx = Math.max(0, Math.min(iw - 1, Math.round(ix0)));
    const sy = Math.max(0, Math.min(ih - 1, Math.round(iy0)));
    const sw = Math.max(1, Math.min(iw - sx, Math.round(ix1 - ix0)));
    const sh = Math.max(1, Math.min(ih - sy, Math.round(iy1 - iy0)));

    let crop;
    try {
        crop = src.new_subpixbuf(sx, sy, sw, sh)
            .scale_simple(Math.max(1, Math.round(texW)), Math.max(1, Math.round(texH)),
                GdkPixbuf.InterpType.BILINEAR);
    } catch (e) {
        logError(e, '[peachos-widgets] wallpaper crop failed');
        return null;
    }
    if (!crop)
        return null;

    const coglContext = global.stage.context.get_backend().get_cogl_context();
    const content = St.ImageContent.new_with_preferred_size(crop.get_width(), crop.get_height());
    content.set_bytes(
        coglContext,
        crop.read_pixel_bytes(),
        crop.get_has_alpha() ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
        crop.get_width(), crop.get_height(), crop.get_rowstride());
    return content;
}
