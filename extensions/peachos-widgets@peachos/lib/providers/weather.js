// Weather data from Open-Meteo (no API key, plain HTTPS GET via libsoup -- the
// same Soup.Session/send_and_read_async pattern as
// macos-top-panel/lib/mediaPlayerController.js). Ported from the KDE repo's
// WeatherData.qml; location + unit come from this extension's gsettings.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const REFRESH_SECONDS = 900; // 15 min

// WMO weather-code -> label + GNOME symbolic icon name.
export function wmoInfo(code, isDay = true) {
    const night = !isDay;
    const clear = night ? 'weather-clear-night-symbolic' : 'weather-clear-symbolic';
    const map = {
        0: ['Clear', clear],
        1: ['Mostly clear', night ? 'weather-few-clouds-night-symbolic' : 'weather-few-clouds-symbolic'],
        2: ['Partly cloudy', night ? 'weather-few-clouds-night-symbolic' : 'weather-few-clouds-symbolic'],
        3: ['Overcast', 'weather-overcast-symbolic'],
        45: ['Fog', 'weather-fog-symbolic'],
        48: ['Rime fog', 'weather-fog-symbolic'],
        51: ['Light drizzle', 'weather-showers-scattered-symbolic'],
        53: ['Drizzle', 'weather-showers-scattered-symbolic'],
        55: ['Heavy drizzle', 'weather-showers-symbolic'],
        56: ['Freezing drizzle', 'weather-showers-symbolic'],
        57: ['Freezing drizzle', 'weather-showers-symbolic'],
        61: ['Light rain', 'weather-showers-scattered-symbolic'],
        63: ['Rain', 'weather-showers-symbolic'],
        65: ['Heavy rain', 'weather-showers-symbolic'],
        66: ['Freezing rain', 'weather-showers-symbolic'],
        67: ['Freezing rain', 'weather-showers-symbolic'],
        71: ['Light snow', 'weather-snow-symbolic'],
        73: ['Snow', 'weather-snow-symbolic'],
        75: ['Heavy snow', 'weather-snow-symbolic'],
        77: ['Snow grains', 'weather-snow-symbolic'],
        80: ['Rain showers', 'weather-showers-symbolic'],
        81: ['Rain showers', 'weather-showers-symbolic'],
        82: ['Violent showers', 'weather-storm-symbolic'],
        85: ['Snow showers', 'weather-snow-symbolic'],
        86: ['Snow showers', 'weather-snow-symbolic'],
        95: ['Thunderstorm', 'weather-storm-symbolic'],
        96: ['Thunderstorm', 'weather-storm-symbolic'],
        99: ['Thunderstorm', 'weather-storm-symbolic'],
    };
    return map[code] ?? ['—', 'weather-few-clouds-symbolic'];
}

export class WeatherProvider {
    constructor(settings) {
        this._settings = settings;
        this._session = new Soup.Session({timeout: 15});
        this._listeners = new Set();
        this._data = null;
        this._error = null;

        this._settings.connectObject(
            'changed::weather-latitude', () => this.refresh(),
            'changed::weather-longitude', () => this.refresh(),
            'changed::weather-unit', () => this.refresh(),
            'changed::weather-location-name', () => this._reemit(),
            this);

        this.refresh();
        this._periodicId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
            this.refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    get data() {
        return this._data;
    }

    get error() {
        return this._error;
    }

    subscribe(fn) {
        this._listeners.add(fn);
        fn(this._data, this._error);
        return () => this._listeners.delete(fn);
    }

    _emit() {
        for (const fn of this._listeners)
            fn(this._data, this._error);
    }

    _reemit() {
        if (this._data)
            this._data.name = this._settings.get_string('weather-location-name');
        this._emit();
    }

    refresh() {
        const lat = this._settings.get_double('weather-latitude');
        const lon = this._settings.get_double('weather-longitude');
        const unit = this._settings.get_string('weather-unit');

        const url = 'https://api.open-meteo.com/v1/forecast'
            + `?latitude=${lat}&longitude=${lon}`
            + '&current=temperature_2m,apparent_temperature,weather_code,is_day'
            + '&daily=weather_code,temperature_2m_max,temperature_2m_min'
            + `&temperature_unit=${unit}&timezone=auto&forecast_days=4`;

        const msg = Soup.Message.new('GET', url);
        this._session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (source, result) => {
            try {
                const bytes = source.send_and_read_finish(result);
                if (msg.get_status() !== Soup.Status.OK) {
                    this._error = `HTTP ${msg.get_status()}`;
                    this._emit();
                    return;
                }
                const json = JSON.parse(new TextDecoder().decode(bytes.get_data()));
                this._data = this._parse(json);
                this._error = null;
                this._emit();
            } catch (e) {
                logError(e, '[peachos-widgets] weather fetch failed');
                this._error = 'unavailable';
                this._emit();
            }
        });
    }

    _parse(j) {
        const unitLetter = this._settings.get_string('weather-unit') === 'celsius' ? 'C' : 'F';
        const cur = j.current ?? {};
        const daily = j.daily ?? {};
        const days = (daily.time ?? []).map((iso, i) => {
            const d = new Date(`${iso}T12:00:00`);
            return {
                label: i === 0 ? 'Today' : d.toLocaleDateString(undefined, {weekday: 'short'}),
                hi: Math.round(daily.temperature_2m_max?.[i] ?? 0),
                lo: Math.round(daily.temperature_2m_min?.[i] ?? 0),
                code: daily.weather_code?.[i] ?? 0,
            };
        });
        return {
            name: this._settings.get_string('weather-location-name'),
            temp: Math.round(cur.temperature_2m ?? 0),
            feels: Math.round(cur.apparent_temperature ?? 0),
            code: cur.weather_code ?? 0,
            isDay: cur.is_day !== 0,
            unit: unitLetter,
            days,
        };
    }

    destroy() {
        if (this._periodicId)
            GLib.source_remove(this._periodicId);
        this._periodicId = 0;
        this._settings.disconnectObject(this);
        this._session.abort();
        this._listeners.clear();
        this._data = null;
    }
}
