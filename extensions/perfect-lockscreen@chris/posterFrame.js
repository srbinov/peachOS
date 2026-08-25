import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

Gio._promisify(Gio.Subprocess.prototype, 'wait_check_async', 'wait_check_finish');

async function _run(argv) {
    const proc = Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
    );
    await proc.wait_check_async(null);
}

export async function extractPosterFrame(videoPath, destPath) {
    if (!videoPath || !destPath)
        return false;

    const dest = Gio.File.new_for_path(destPath);
    try {
        if (dest.query_exists(null))
            dest.delete(null);
    } catch (e) {
        // ignore
    }

    const ffmpeg = GLib.find_program_in_path('ffmpeg');
    const mpv = GLib.find_program_in_path('mpv');

    try {
        if (ffmpeg) {
            await _run([
                ffmpeg, '-y', '-ss', '0', '-i', videoPath,
                '-frames:v', '1', destPath,
            ]);
        } else if (mpv) {
            await _run([
                'mpv',
                '--really-quiet',
                '--ao=null',
                '--no-audio',
                '--vo=image',
                '--vo-image-format=jpg',
                '--frames=1',
                `--o=${destPath}`,
                videoPath,
            ]);
        } else {
            return false;
        }

        if (!dest.query_exists(null))
            return false;

        dest.set_attribute_uint32('unix::mode', 0o644, Gio.FileQueryInfoFlags.NONE, null);
        return true;
    } catch (e) {
        console.error(`PerfectLockScreen: poster extract failed: ${e}`);
        return false;
    }
}
