// News headlines from curated RSS feeds per topic (no API key). Each topic
// merges 2-4 image-carrying feeds; article images are downloaded to the cache
// so St can show them (it won't load remote http images directly).

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const REFRESH_SECONDS = 10 * 60;
const STALE_MS = 60 * 1000;
const MAX_ARTICLES = 12;

export const NEWS_TOPICS = [
    {id: 'top', name: 'Top Stories', feeds: [
        'http://feeds.bbci.co.uk/news/rss.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml',
        'https://feeds.npr.org/1001/rss.xml',
    ]},
    {id: 'world', name: 'World', feeds: [
        'http://feeds.bbci.co.uk/news/world/rss.xml',
        'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    ]},
    {id: 'us', name: 'U.S.', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/US.xml',
        'https://feeds.npr.org/1003/rss.xml',
    ]},
    {id: 'politics', name: 'Politics', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml',
        'http://feeds.bbci.co.uk/news/politics/rss.xml',
    ]},
    {id: 'business', name: 'Business', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml',
        'http://feeds.bbci.co.uk/news/business/rss.xml',
    ]},
    {id: 'tech', name: 'Technology', feeds: [
        'https://feeds.arstechnica.com/arstechnica/technology-lab',
        'https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml',
        'http://feeds.bbci.co.uk/news/technology/rss.xml',
    ]},
    {id: 'science', name: 'Science', feeds: [
        'https://feeds.arstechnica.com/arstechnica/science',
        'https://rss.nytimes.com/services/xml/rss/nyt/Science.xml',
    ]},
    {id: 'health', name: 'Health', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/Health.xml',
        'http://feeds.bbci.co.uk/news/health/rss.xml',
    ]},
    {id: 'climate', name: 'Climate', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/Climate.xml',
        'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
    ]},
    {id: 'sports', name: 'Sports', feeds: [
        'http://feeds.bbci.co.uk/sport/rss.xml',
        'https://www.cbssports.com/rss/headlines/',
    ]},
    {id: 'entertainment', name: 'Entertainment', feeds: [
        'https://variety.com/feed/',
        'http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml',
    ]},
    {id: 'gaming', name: 'Gaming', feeds: [
        'https://feeds.arstechnica.com/arstechnica/gaming',
        'https://www.polygon.com/rss/index.xml',
        'https://feeds.ign.com/ign/all',
    ]},
    {id: 'arts', name: 'Arts & Culture', feeds: [
        'https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml',
    ]},
];

export function topicName(id) {
    return NEWS_TOPICS.find(t => t.id === id)?.name ?? 'News';
}

const SOURCE_MAP = {
    'nytimes.com': 'The New York Times',
    'bbc.co.uk': 'BBC News', 'bbc.com': 'BBC News',
    'arstechnica.com': 'Ars Technica',
    'npr.org': 'NPR',
    'variety.com': 'Variety',
    'polygon.com': 'Polygon',
    'ign.com': 'IGN',
    'cbssports.com': 'CBS Sports',
};

function hostOf(url) {
    return (url || '').replace(/^https?:\/\/(www\.)?/, '').split(/[/?#]/)[0].toLowerCase();
}

function sourceName(link, feedUrl) {
    const h = hostOf(link) || hostOf(feedUrl);
    for (const k in SOURCE_MAP) {
        if (h === k || h.endsWith(`.${k}`))
            return SOURCE_MAP[k];
    }
    const parts = h.split('.');
    const base = parts.length >= 2 ? parts[parts.length - 2] : h;
    return base.charAt(0).toUpperCase() + base.slice(1);
}

const ENTITIES = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", '#39': "'", '#x27': "'", nbsp: ' ', mdash: '—', ndash: '–', hellip: '…', rsquo: '’', lsquo: '‘', ldquo: '“', rdquo: '”'};

function decode(s) {
    if (!s)
        return '';
    return s
        .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
        .replace(/<[^>]+>/g, '')
        .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
        .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d))
        .replace(/&([a-z0-9#x]+);/gi, (m, e) => ENTITIES[e] ?? ENTITIES[e.toLowerCase()] ?? m)
        .replace(/\s+/g, ' ')
        .trim();
}

function tag(block, name) {
    const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`, 'i'));
    return m ? m[1] : '';
}

function imageIn(block) {
    let m = block.match(/<(?:media:content|media:thumbnail)[^>]*\burl=["']([^"']+\.(?:jpe?g|png|webp|avif)[^"']*)["']/i);
    if (m)
        return m[1];
    m = block.match(/<enclosure[^>]*\burl=["']([^"']+)["'][^>]*type=["']image/i);
    if (m)
        return m[1];
    m = block.match(/<media:content[^>]*medium=["']image["'][^>]*\burl=["']([^"']+)["']/i);
    if (m)
        return m[1];
    m = block.match(/<img[^>]+src=["'](https?:\/\/[^"']+)["']/i);
    return m ? m[1] : '';
}

function parseFeed(xml, feedUrl) {
    const blocks = xml.match(/<(item|entry)\b[\s\S]*?<\/\1>/gi) || [];
    const out = [];
    for (const b of blocks) {
        const title = decode(tag(b, 'title'));
        if (!title)
            continue;
        let link = decode(tag(b, 'link'));
        if (!link) {
            const lm = b.match(/<link[^>]*\bhref=["']([^"']+)["']/i);
            link = lm ? lm[1] : '';
        }
        const dateStr = tag(b, 'pubDate') || tag(b, 'published') || tag(b, 'updated') ||
            tag(b, 'dc:date');
        const ts = dateStr ? Date.parse(decode(dateStr)) : NaN;
        out.push({
            title,
            link,
            source: sourceName(link, feedUrl),
            date: Number.isFinite(ts) ? ts : Date.now(),
            imageUrl: imageIn(b),
            imagePath: null,
        });
    }
    return out;
}

export class NewsProvider {
    constructor() {
        this._session = new Soup.Session({timeout: 20});
        this._topics = new Map();   // id -> {articles, listeners, lastFetch, fetching}
        this._cacheDir = GLib.build_filenamev(
            [GLib.get_user_cache_dir(), 'peachos-widgets', 'news']);
        GLib.mkdir_with_parents(this._cacheDir, 0o755);

        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, REFRESH_SECONDS, () => {
            for (const id of this._topics.keys())
                this._fetchTopic(id);
            return GLib.SOURCE_CONTINUE;
        });
    }

    subscribe(topicId, fn) {
        const t = this._ensure(topicId);
        t.listeners.add(fn);
        fn(t.articles);
        if (Date.now() - t.lastFetch > STALE_MS)
            this._fetchTopic(topicId);
        return () => t.listeners.delete(fn);
    }

    get(topicId) {
        return this._topics.get(topicId)?.articles ?? [];
    }

    refreshNow() {
        for (const id of this._topics.keys())
            this._fetchTopic(id, true);
    }

    _ensure(id) {
        if (!this._topics.has(id))
            this._topics.set(id, {articles: [], listeners: new Set(), lastFetch: 0, fetching: false});
        return this._topics.get(id);
    }

    _emit(id) {
        const t = this._topics.get(id);
        if (t)
            for (const fn of t.listeners)
                fn(t.articles);
    }

    _fetchTopic(id, force = false) {
        const topic = NEWS_TOPICS.find(x => x.id === id);
        const t = this._ensure(id);
        if (!topic || (t.fetching && !force))
            return;
        t.fetching = true;
        t.lastFetch = Date.now();

        let pending = topic.feeds.length;
        let merged = [];
        for (const url of topic.feeds) {
            const msg = Soup.Message.new('GET', url);
            msg.request_headers.append('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64)');
            this._session.send_and_read_async(msg, GLib.PRIORITY_LOW, null, (src, res) => {
                try {
                    const bytes = src.send_and_read_finish(res);
                    if (msg.get_status() === Soup.Status.OK) {
                        const xml = new TextDecoder().decode(bytes.get_data());
                        merged = merged.concat(parseFeed(xml, url));
                    }
                } catch (e) {
                    // skip this feed
                }
                if (--pending === 0)
                    this._finish(id, merged);
            });
        }
    }

    _finish(id, merged) {
        const t = this._topics.get(id);
        t.fetching = false;

        // newest first, dedupe by normalised title
        const seen = new Set();
        const articles = merged
            .sort((a, b) => b.date - a.date)
            .filter(a => {
                const k = a.title.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 40);
                if (seen.has(k))
                    return false;
                seen.add(k);
                return true;
            })
            .slice(0, MAX_ARTICLES);

        t.articles = articles;
        this._emit(id);
        this._pruneCache(articles);
        for (const a of articles)
            this._cacheImage(id, a);
    }

    _cacheImage(id, article) {
        if (!article.imageUrl || article.imagePath)
            return;
        const ext = (article.imageUrl.match(/\.(jpe?g|png|webp|avif)/i)?.[1] || 'jpg')
            .toLowerCase();
        const name = GLib.compute_checksum_for_string(
            GLib.ChecksumType.MD5, article.imageUrl, -1) + '.' + ext;
        const path = GLib.build_filenamev([this._cacheDir, name]);
        if (GLib.file_test(path, GLib.FileTest.EXISTS)) {
            article.imagePath = path;
            this._emit(id);
            return;
        }
        const msg = Soup.Message.new('GET', article.imageUrl);
        msg.request_headers.append('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64)');
        this._session.send_and_read_async(msg, GLib.PRIORITY_LOW, null, (src, res) => {
            try {
                const bytes = src.send_and_read_finish(res);
                if (msg.get_status() !== Soup.Status.OK)
                    return;
                GLib.file_set_contents(path, bytes.get_data());
                article.imagePath = path;
                this._emit(id);
            } catch (e) {
                // no image
            }
        });
    }

    _pruneCache(keepArticles) {
        try {
            const keep = new Set();
            for (const a of keepArticles) {
                if (!a.imageUrl)
                    continue;
                const ext = (a.imageUrl.match(/\.(jpe?g|png|webp|avif)/i)?.[1] || 'jpg').toLowerCase();
                keep.add(GLib.compute_checksum_for_string(
                    GLib.ChecksumType.MD5, a.imageUrl, -1) + '.' + ext);
            }
            const dir = Gio.File.new_for_path(this._cacheDir);
            const en = dir.enumerate_children('standard::name,time::modified',
                Gio.FileQueryInfoFlags.NONE, null);
            let info;
            const cutoff = Date.now() / 1000 - 3 * 24 * 3600;
            while ((info = en.next_file(null))) {
                const nm = info.get_name();
                if (keep.has(nm))
                    continue;
                if (info.get_modification_date_time()?.to_unix() < cutoff)
                    dir.get_child(nm).delete(null);
            }
        } catch (e) {
            // best effort
        }
    }

    destroy() {
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        this._session.abort();
        this._topics.clear();
    }
}
