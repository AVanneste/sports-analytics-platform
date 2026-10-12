import React from 'react';

// Written every few minutes by scripts/odds_alerts.py to the odds-archive branch (public repo), so
// alerts are live without redeploying the site.
export const ALERTS_URL = 'https://raw.githubusercontent.com/AVanneste/sports-analytics-platform/odds-archive/web/alerts.json';

export interface OpenAlert {
  sport: string; league: string | null; start: string; home: string; away: string; market: string; period: number;
  units: string | null; side: string | null; line: number | null; selection: string; book: string; price: number;
  books: Record<string, number> | null; fair_prob: number; ev: number; stake: number; limit: number | null;
  dropped_from: number | null; captured_at: string; fair_prob_now: number | null; ev_now: number | null;
}
export interface ClosedAlert extends Omit<OpenAlert, 'fair_prob_now' | 'ev_now' | 'books'> { close_prob: number | null; ev_at_close: number | null }
export interface Summary { alerts: number; ev_sent_pct?: number; ev_close_pct?: number; beat_close_pct?: number }
export interface Group extends Summary { group: string }
export interface AlertsData {
  generated_at: string; bankroll?: number; open: OpenAlert[]; summary: Summary; recent: ClosedAlert[];
  by_sport: Group[]; by_market: Group[]; by_book: Group[]; by_kind: Group[];
}

export const fetchAlerts = (): Promise<AlertsData> =>
  fetch(`${ALERTS_URL}?t=${Date.now()}`).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "Genk +0.5", "Over 2.5 (corners)", "Union SG", "Draw": the same wording as the Telegram alerts. */
export function pick(a: { home: string; away: string; market: string; side: string | null; selection: string; line: number | null; units: string | null; period: number }) {
  if (a.market === 'player_prop') {
    const player = (a.side || '').replace(/\b\w/g, (c) => c.toUpperCase());
    return `${player} ${cap(a.selection)} ${a.line} ${a.units}`;
  }
  const who = ({ home: a.home, away: a.away } as Record<string, string>)[a.side || a.selection] ?? cap(a.selection);
  let text = who;
  if (a.market === 'spread' && a.line != null) text = `${who} ${a.line >= 0 ? '+' : ''}${a.line}`;
  else if (a.market === 'total' || a.market === 'team_total') text = `${a.side ? who + ' ' : ''}${cap(a.selection)} ${a.line}`;
  const scope = [a.units && a.units.toLowerCase(), a.period === 1 ? '1st half' : a.period === 6 ? 'regular time' : null].filter(Boolean).join(', ');
  return scope ? `${text} (${scope})` : text;
}

const NOISE = new Set(['fc', 'cf', 'sc', 'afc', 'ac', 'as', 'sv', 'sk', 'kv', 'krc', 'club', 'de', 'the', 'royal', 'cd', 'fk', 'bk', 'if']);
const words = (name: string) =>
  new Set(name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2 && !NOISE.has(w)));
const shares = (a: string, b: string) => { const wb = words(b); return [...words(a)].some((w) => wb.has(w)); };

/** Open alerts on this match: same day (UTC) and both names sharing a word, either way round
 * (Pinnacle's names differ from the fixtures': "KRC Genk" / "Genk", "Qinwen Zheng" / "Zheng Qinwen"). */
export function alertsFor(alerts: OpenAlert[] | undefined, home: string, away: string, date: string): OpenAlert[] {
  if (!alerts?.length) return [];
  const day = (date || '').slice(0, 10);
  return alerts.filter((a) => a.start.slice(0, 10) === day &&
    ((shares(a.home, home) && shares(a.away, away)) || (shares(a.home, away) && shares(a.away, home))))
    .sort((x, y) => (y.ev_now ?? y.ev) - (x.ev_now ?? x.ev));
}

/** The best open alert on a match card, with a count of the others. */
export const AlertBadge: React.FC<{ alerts: OpenAlert[] }> = ({ alerts }) => {
  if (!alerts.length) return null;
  const a = alerts[0];
  const ev = a.ev_now ?? a.ev;
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 font-bold border border-emerald-500/30 text-[11px]"
          title={alerts.map((x) => `${pick(x)} @ ${x.price.toFixed(2)} ${cap(x.book)} (EV now ${((x.ev_now ?? x.ev) * 100).toFixed(1)}%)`).join('\n')}>
      🔔 {pick(a)} @ {a.price.toFixed(2)} {cap(a.book)} ({ev >= 0 ? '+' : ''}{(ev * 100).toFixed(1)}%)
      {alerts.length > 1 ? <span className="text-emerald-400/70 font-normal">+{alerts.length - 1}</span> : null}
    </span>
  );
};


export interface TeamNews { text: string; sources: { title: string | null; url: string | null }[]; fetched_at: string }

/** Pre-match team news from Gemini (Google Search grounded), with its sources; collapsed by default. */
export const TeamNewsBox: React.FC<{ news?: TeamNews }> = ({ news }) => {
  const [open, setOpen] = React.useState(false);
  if (!news?.text) return null;
  return (
    <div className="mt-2 text-[11px] border border-dark-700 rounded-lg bg-dark-900/50">
      <button onClick={() => setOpen(!open)} className="w-full text-left px-3 py-1.5 text-slate-300 hover:text-white font-semibold">
        📰 Team news {open ? '▾' : '▸'} <span className="text-slate-500 font-normal">(AI summary of recent news, {news.fetched_at.slice(0, 10)})</span>
      </button>
      {open && (
        <div className="px-3 pb-2 space-y-1">
          <div className="whitespace-pre-line text-slate-300">{news.text.replace(/\*\*/g, '')}</div>
          {news.sources.length > 0 && (
            <div className="text-slate-500">Sources: {news.sources.map((s, i) => (
              <a key={i} href={s.url || '#'} target="_blank" rel="noreferrer" className="underline hover:text-slate-300 mr-2">{s.title || 'link'}</a>
            ))}</div>
          )}
        </div>
      )}
    </div>
  );
};
