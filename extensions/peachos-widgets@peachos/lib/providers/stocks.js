// Stock / index / crypto quotes from Yahoo Finance's public chart endpoint
// (no key): https://query1.finance.yahoo.com/v8/finance/chart/<symbol>
// -> meta.regularMarketPrice, meta.chartPreviousClose, and an intraday close
// series for the sparkline. Symbols are fixed for now.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const REFRESH_SECONDS = 90;
const URL = s =>
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(s)}`
    + '?range=1d&interval=5m';

export const STOCK_SYMBOLS = ['SPY', 'AAPL', 'BTC-USD'];

const META = {
    'SPY': {label: 'SPY', sub: 'S&P 500 ETF'},
    'AAPL': {label: 'AAPL', sub: 'Apple Inc.'},
    'BTC-USD': {label: 'Bitcoin', sub: 'Bitcoin USD'},
};

function fmtPrice(v) {
    if (!Number.isFinite(v))
        return '--';
    return v.toLocaleString('en-US', {
        minimumFractionDigits: v >= 2000 ? 0 : 2,
        maximumFractionDigits: v >= 2000 ? 0 : 2,
    });
}

export class StocksProvider {
    constructor() {
        this._session = new Soup.Session({timeout: 15});
        this._listeners = new Set();
        this._data = new Map();     // symbol -> quote

        this.refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
            this.refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    subscribe(fn) {
        this._listeners.add(fn);
        fn();
        return () => this._listeners.delete(fn);
    }

    _emit() {
        for (const fn of this._listeners)
            fn();
    }

    /** { label, sub, price, priceText, changePct, changeText, up, spark[] } */
    get(symbol) {
        return this._data.get(symbol) ?? null;
    }

    refresh() {
        for (const symbol of STOCK_SYMBOLS)
            this._fetch(symbol);
    }

    _fetch(symbol) {
        const msg = Soup.Message.new('GET', URL(symbol));
        msg.request_headers.append('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64)');
        this._session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (src, res) => {
            try {
                const bytes = src.send_and_read_finish(res);
                if (msg.get_status() !== Soup.Status.OK)
                    return;
                const j = JSON.parse(new TextDecoder().decode(bytes.get_data()));
                const r = j?.chart?.result?.[0];
                if (!r)
                    return;
                const m = r.meta ?? {};
                const price = Number(m.regularMarketPrice);
                const prev = Number(m.chartPreviousClose ?? m.previousClose);
                if (!Number.isFinite(price) || !Number.isFinite(prev))
                    return;
                const spark = (r.indicators?.quote?.[0]?.close ?? [])
                    .filter(v => v != null);
                const pct = ((price - prev) / prev) * 100;
                const up = price >= prev;
                const meta = META[symbol] || {label: symbol, sub: ''};
                this._data.set(symbol, {
                    symbol,
                    label: meta.label,
                    sub: meta.sub,
                    price,
                    prev,
                    priceText: fmtPrice(price),
                    changePct: pct,
                    changeText: `${up ? '+' : ''}${pct.toFixed(2)}%`,
                    up,
                    spark: spark.length >= 2 ? spark : [prev, price],
                });
                this._emit();
            } catch (e) {
                logError(e, '[peachos-widgets] stock fetch failed');
            }
        });
    }

    destroy() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._session.abort();
        this._listeners.clear();
        this._data.clear();
    }
}
