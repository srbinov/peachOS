// Weather data from Open-Meteo (no API key, plain HTTPS GET via libsoup -- the
// same Soup.Session/send_and_read_async pattern as
// macos-top-panel/lib/mediaPlayerController.js). Ported from the KDE repo's
// WeatherData.qml; location + unit come from this extension's gsettings.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const REFRESH_SECONDS = 900; // 15 min

function windCompass(deg) {
    const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    return dirs[Math.round(deg / 45) % 8];
}

// WMO code -> KDE icon-set basename (icons/weather/*.png).
export function wmoIconName(code, isDay = true) {
    const night = !isDay;
    if (code === 0)
        return night ? 'clearnight' : 'sunny';
    if (code === 1 || code === 2)
        return night ? 'partlycloudynight' : 'partlysunny';
    if (code === 3)
        return 'cloudy';
    if (code === 45 || code === 48)
        return 'fog';
    if (code >= 51 && code <= 57)
        return night ? 'nightdrizzle' : 'drizzle';
    if (code === 61 || code === 63 || code === 66)
        return 'rain';
    if (code === 65 || code === 67)
        return 'heavyrain';
    if (code === 71 || code === 73 || code === 75 || code === 85 || code === 86)
        return 'snow';
    if (code === 77)
        return 'scatteredsnow';
    if (code === 80 || code === 81)
        return 'rain';
    if (code === 82)
        return 'heavyrain';
    if (code >= 95)
        return 'thunderbolt';
    return night ? 'clearnight' : 'sunny';
}

// WMO code -> human condition label (ported from WeatherData.qml).
export function wmoCondition(code) {
    const map = {
        0: 'Clear', 1: 'Mostly Clear', 2: 'Partly Cloudy', 3: 'Cloudy',
        45: 'Fog', 48: 'Rime Fog',
        51: 'Light Drizzle', 53: 'Drizzle', 55: 'Heavy Drizzle',
        56: 'Freezing Drizzle', 57: 'Freezing Drizzle',
        61: 'Light Rain', 63: 'Rain', 65: 'Heavy Rain',
        66: 'Freezing Rain', 67: 'Freezing Rain',
        71: 'Light Snow', 73: 'Snow', 75: 'Heavy Snow', 77: 'Snow Grains',
        80: 'Rain Showers', 81: 'Rain Showers', 82: 'Violent Showers',
        85: 'Snow Showers', 86: 'Snow Showers',
        95: 'Thunderstorm', 96: 'Thunderstorm with Hail', 99: 'Heavy Thunderstorm',
    };
    return map[code] ?? '—';
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
            + '&current=temperature_2m,apparent_temperature,weather_code,is_day,'
            + 'precipitation,wind_speed_10m,wind_direction_10m'
            + '&hourly=temperature_2m,weather_code'
            + '&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'
            + `&temperature_unit=${unit}&wind_speed_unit=mph&timezone=auto&forecast_days=5`;

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
        const hourly = j.hourly ?? {};
        const days = (daily.time ?? []).map((iso, i) => {
            const d = new Date(`${iso}T12:00:00`);
            return {
                label: i === 0 ? 'Today' : d.toLocaleDateString(undefined, {weekday: 'short'}),
                hi: Math.round(daily.temperature_2m_max?.[i] ?? 0),
                lo: Math.round(daily.temperature_2m_min?.[i] ?? 0),
                code: daily.weather_code?.[i] ?? 0,
                precipProb: daily.precipitation_probability_max?.[i] ?? null,
            };
        });

        // Next 6 hourly slots from now.
        const nowMs = Date.now();
        const hours = [];
        const times = hourly.time ?? [];
        for (let i = 0; i < times.length && hours.length < 6; i++) {
            const t = new Date(times[i]).getTime();
            if (t < nowMs - 3600000)
                continue;
            hours.push({
                hour: new Date(times[i]).toLocaleTimeString(undefined, {hour: 'numeric'}),
                temp: Math.round(hourly.temperature_2m?.[i] ?? 0),
                code: hourly.weather_code?.[i] ?? 0,
            });
        }

        return {
            name: this._settings.get_string('weather-location-name'),
            temp: Math.round(cur.temperature_2m ?? 0),
            feels: Math.round(cur.apparent_temperature ?? 0),
            code: cur.weather_code ?? 0,
            isDay: cur.is_day !== 0,
            unit: unitLetter,
            wind: Math.round(cur.wind_speed_10m ?? 0),
            windDir: windCompass(cur.wind_direction_10m ?? 0),
            precip: cur.precipitation ?? 0,
            precipProb: days[0]?.precipProb ?? null,
            hi: days[0]?.hi ?? 0,
            lo: days[0]?.lo ?? 0,
            days,
            hours,
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
