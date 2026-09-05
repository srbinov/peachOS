// A blurred St.ImageContent of the wallpaper region behind a screen rect --
// the frosted backdrop for a glass widget. Shell.BlurEffect (BACKGROUND mode)
// does not reliably capture anything for an actor down in _backgroundGroup, so
// the frost is baked here instead: crop the wallpaper, downscale hard and
// upscale back (a cheap box blur), hand it over as actor content. Static;
// recomputed on move / wallpaper change.
//
// The crop/fit mapping matches macos-top-panel/lib/panelBackground.js.

import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GdkPixbuf from 'gi://GdkPixbuf';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BG_SCHEMA = 'org.gnome.desktop.background';
const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';

let _cachedPath = null;
let _cachedPixbuf = null;

function currentWallpaper() {
    const bg = new Gio.Settings({schema_id: BG_SCHEMA});
    const iface = new Gio.Settings({schema_id: INTERFACE_SCHEMA});
    const dark = iface.get_string('color-scheme') === 'prefer-dark';
    const darkUri = bg.get_string('picture-uri-dark');
    const uri = (dark && darkUri) ? darkUri : bg.get_string('picture-uri');
    let path = uri;
    try {
        path = GLib.filename_from_uri(uri)[0];
    } catch (e) {
        // already a plain path
    }
    return {path: path || null, options: bg.get_string('picture-options') || 'zoom'};
}

function loadWallpaper(path) {
    if (path === _cachedPath && _cachedPixbuf)
        return _cachedPixbuf;
    try {
        _cachedPixbuf = GdkPixbuf.Pixbuf.new_from_file(path);
        _cachedPath = path;
    } catch (e) {
        logError(e, '[peachos-widgets] wallpaper load failed');
        _cachedPixbuf = null;
        _cachedPath = null;
    }
    return _cachedPixbuf;
}

export function invalidateWallpaper() {
    _cachedPath = null;
    _cachedPixbuf = null;
}

function monitorToImage(mx, my, mw, mh, iw, ih, options) {
    if (options === 'stretched')
        return [mx / mw * iw, my / mh * ih];
    const scale = options === 'scaled'
        ? Math.min(mw / iw, mh / ih)
        : Math.max(mw / iw, mh / ih);
    const offX = (iw * scale - mw) / 2;
    const offY = (ih * scale - mh) / 2;
    return [(mx + offX) / scale, (my + offY) / scale];
}

/**
 * @param {{x,y,w,h}} rect  glass rect in stage coords
 * @returns {St.ImageContent|null}
 */
export function buildBlurredCrop(rect) {
    const {path, options} = currentWallpaper();
    if (!path)
        return null;
    const src = loadWallpaper(path);
    if (!src)
        return null;

    const iw = src.get_width();
    const ih = src.get_height();

    const monitors = Main.layoutManager.monitors;
    const cx = rect.x + rect.w / 2;
    const cy = rect.y + rect.h / 2;
    const mon = monitors.find(m =>
        cx >= m.x && cx < m.x + m.width && cy >= m.y && cy < m.y + m.height)
        || Main.layoutManager.primaryMonitor;

    const [ix0, iy0] = monitorToImage(rect.x - mon.x, rect.y - mon.y, mon.width, mon.height, iw, ih, options);
    const [ix1, iy1] = monitorToImage(
        rect.x - mon.x + rect.w, rect.y - mon.y + rect.h, mon.width, mon.height, iw, ih, options);

    const sx = Math.max(0, Math.min(iw - 2, Math.round(ix0)));
    const sy = Math.max(0, Math.min(ih - 2, Math.round(iy0)));
    const sw = Math.max(2, Math.min(iw - sx, Math.round(ix1 - ix0)));
    const sh = Math.max(2, Math.min(ih - sy, Math.round(iy1 - iy0)));

    // Downscale hard, upscale back == a cheap blur (~ box blur of the
    // downscale factor). Two passes for a softer, more Kawase-like result.
    const DOWN = 9;
    let pb;
    try {
        const crop = src.new_subpixbuf(sx, sy, sw, sh);
        const lowW = Math.max(2, Math.round(sw / DOWN));
        const lowH = Math.max(2, Math.round(sh / DOWN));
        pb = crop
            .scale_simple(lowW, lowH, GdkPixbuf.InterpType.BILINEAR)
            .scale_simple(Math.max(2, Math.round(lowW / 2)), Math.max(2, Math.round(lowH / 2)),
                GdkPixbuf.InterpType.BILINEAR)
            .scale_simple(Math.round(rect.w), Math.round(rect.h), GdkPixbuf.InterpType.BILINEAR);
    } catch (e) {
        logError(e, '[peachos-widgets] wallpaper crop/blur failed');
        return null;
    }
    if (!pb)
        return null;

    const coglContext = global.stage.context.get_backend().get_cogl_context();
    const content = St.ImageContent.new_with_preferred_size(pb.get_width(), pb.get_height());
    content.set_bytes(
        coglContext,
        pb.read_pixel_bytes(),
        pb.get_has_alpha() ? Cogl.PixelFormat.RGBA_8888 : Cogl.PixelFormat.RGB_888,
        pb.get_width(), pb.get_height(), pb.get_rowstride());
    return content;
}
