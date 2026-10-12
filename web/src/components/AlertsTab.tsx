import React, { useState } from 'react';
import { Bell, RefreshCw, Info } from 'lucide-react';

import { AlertsData, Group, cap, pick } from '../alerts';

const ICONS: Record<string, string> = { Soccer: '⚽', Tennis: '🎾', Basketball: '🏀', Hockey: '🏒', Volleyball: '🏐', Handball: '🤾' };
const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`);
const evColor = (v: number | null | undefined) => (v == null ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : 'text-rose-400');

const Card: React.FC<{ label: string; value: string; sub?: string; color?: string }> = ({ label, value, sub, color }) => (
  <div className="bg-dark-800/80 border border-dark-700/80 rounded-xl p-3.5">
    <div className="text-slate-400 text-xs font-semibold">{label}</div>
    <div className={`mt-2 text-2xl font-bold font-mono ${color || 'text-white'}`}>{value}</div>
    {sub && <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>}
  </div>
);

const GroupTable: React.FC<{ title: string; rows: Group[] }> = ({ title, rows }) => (
  <div className="bg-dark-800/80 border border-dark-700 rounded-xl overflow-hidden">
    <div className="px-3 py-2 text-[11px] font-bold text-slate-300 uppercase tracking-wider border-b border-dark-700">{title}</div>
    <table className="w-full text-xs">
      <thead className="text-[10px] text-slate-500 uppercase"><tr>
        <th className="px-3 py-1.5 text-left" /><th className="px-3 py-1.5 text-right">Alerts</th>
        <th className="px-3 py-1.5 text-right">EV sent</th><th className="px-3 py-1.5 text-right">EV at close</th>
        <th className="px-3 py-1.5 text-right">Beat close</th>
      </tr></thead>
      <tbody className="divide-y divide-dark-700/60">
        {rows.map((r) => (
          <tr key={r.group}>
            <td className="px-3 py-1.5 text-slate-200">{cap(r.group)}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{r.alerts}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-400">{pct(r.ev_sent_pct)}</td>
            <td className={`px-3 py-1.5 text-right font-mono font-bold ${evColor(r.ev_close_pct)}`}>{pct(r.ev_close_pct)}</td>
            <td className="px-3 py-1.5 text-right font-mono text-slate-300">{r.beat_close_pct == null ? '—' : `${r.beat_close_pct.toFixed(0)}%`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const AlertsTab: React.FC<{ data: AlertsData | null; error: string | null; loading: boolean; reload: () => void; timeZone: string }> =
  ({ data, error, loading, reload: load, timeZone }) => {
  const [showHelp, setShowHelp] = useState(false);

  const when = (iso: string) => new Date(iso).toLocaleString('en-GB', { timeZone, weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

  if (error && !data) return <div className="p-6 text-sm text-slate-400 bg-dark-800 border border-dark-700 rounded-xl">{error}</div>;
  if (!data) return <div className="p-6 text-sm text-slate-400">Loading alerts…</div>;
  const s = data.summary;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <Bell className="w-4 h-4 text-emerald-400" />
        <span className="font-bold text-sm text-white">+EV & dropping-odds alerts</span>
        <span className="text-[11px] text-slate-400">Belgian books vs Pinnacle's vig-free price · updated {when(data.generated_at)}</span>
        <button onClick={load} className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
        <button onClick={() => setShowHelp(!showHelp)} className="ml-auto flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200">
          <Info className="w-3.5 h-3.5" /> What is CLV?
        </button>
      </div>
      {showHelp && (
        <div className="text-[11px] leading-relaxed text-slate-300 bg-dark-800/80 border border-dark-700 rounded-xl p-3 space-y-1">
          <p><b>EV sent</b>: the alert price against Pinnacle's vig-free price when the alert went out.</p>
          <p><b>EV at close</b> (CLV): the same price against Pinnacle's last price before kick-off. The closing price is the sharpest estimate there is, so alerts that keep beating it are real value, whatever the results of a few bets.</p>
          <p><b>EV now</b> (open alerts): against Pinnacle's latest price. If it has fallen, the market moved your way; it is still worth betting only while the book keeps the price.</p>
          <p><b>Stake</b>: quarter-Kelly share of the bankroll (capped at 5%); set your bankroll with /set bankroll 500 to see euros.</p>
          <p>Settings (EV, odds, sports, books, bankroll…) are changed by messaging the Telegram bot: /settings, /set, /reset.</p>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card label="Open alerts" value={String(data.open.length)} sub="not started yet" />
        <Card label="Closed (30 days)" value={String(s.alerts)} sub="kicked off" />
        <Card label="Avg EV sent" value={pct(s.ev_sent_pct)} color="text-slate-200" />
        <Card label="Avg EV at close" value={pct(s.ev_close_pct)} color={evColor(s.ev_close_pct)} sub="closing line value" />
        <Card label="Beat the close" value={s.beat_close_pct == null ? '—' : `${s.beat_close_pct.toFixed(0)}%`} sub="of closed alerts" />
      </div>

      <div className="bg-dark-800/80 border border-dark-700 rounded-xl overflow-hidden">
        <div className="px-4 py-2.5 text-xs font-bold text-white border-b border-dark-700">Open alerts</div>
        {data.open.length === 0 ? <div className="px-4 py-4 text-xs text-slate-400">No open alerts right now.</div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider"><tr>
                <th className="px-3 py-2 text-left">Kick-off</th><th className="px-3 py-2 text-left">Match</th>
                <th className="px-3 py-2 text-left">Pick</th><th className="px-3 py-2 text-right">Best price</th>
                <th className="px-3 py-2 text-right">Fair now</th><th className="px-3 py-2 text-right">EV sent</th>
                <th className="px-3 py-2 text-right">EV now</th><th className="px-3 py-2 text-right">Stake</th>
              </tr></thead>
              <tbody className="divide-y divide-dark-700/60">
                {data.open.map((a, i) => (
                  <tr key={i} className="hover:bg-dark-700/30">
                    <td className="px-3 py-2 font-mono text-slate-400 whitespace-nowrap">{when(a.start)}</td>
                    <td className="px-3 py-2 text-slate-200">{ICONS[a.sport] || '•'} {a.home} – {a.away}
                      <div className="text-[10px] text-slate-500">{a.league}</div></td>
                    <td className="px-3 py-2 font-semibold text-white">{pick(a)}
                      {a.dropped_from != null && <span className="ml-1.5 text-[10px] text-amber-300" title="Pinnacle's price dropped and the book has not followed">📉 drop</span>}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-200 whitespace-nowrap">{a.price.toFixed(2)} <span className="text-slate-400">{cap(a.book)}</span>
                      {a.books && Object.keys(a.books).length > 1 && (
                        <div className="text-[10px] text-slate-500">{Object.entries(a.books).filter(([b]) => b !== a.book).map(([b, p]) => `${cap(b)} ${p.toFixed(2)}`).join(' · ')}</div>)}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{a.fair_prob_now ? (1 / a.fair_prob_now).toFixed(2) : '—'}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-400">{pct(a.ev * 100)}</td>
                    <td className={`px-3 py-2 text-right font-mono font-bold ${evColor(a.ev_now)}`}>{a.ev_now == null ? '—' : pct(a.ev_now * 100)}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-400 whitespace-nowrap">
                      {data.bankroll ? `€${(a.stake * data.bankroll).toFixed(0)} ` : ''}<span className={data.bankroll ? 'text-slate-500' : ''}>{(a.stake * 100).toFixed(1)}%</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <GroupTable title="By sport" rows={data.by_sport} />
        <GroupTable title="By market" rows={data.by_market} />
        <GroupTable title="By book" rows={data.by_book} />
        <GroupTable title="By kind (EV vs Pinnacle drop)" rows={data.by_kind} />
      </div>

      <div className="bg-dark-800/80 border border-dark-700 rounded-xl overflow-hidden">
        <div className="px-4 py-2.5 text-xs font-bold text-white border-b border-dark-700">Recently closed</div>
        <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0"><tr>
              <th className="px-3 py-2 text-left">Kick-off</th><th className="px-3 py-2 text-left">Match</th>
              <th className="px-3 py-2 text-left">Pick</th><th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Closing fair</th><th className="px-3 py-2 text-right">EV sent</th>
              <th className="px-3 py-2 text-right">EV at close</th>
            </tr></thead>
            <tbody className="divide-y divide-dark-700/60">
              {data.recent.map((a, i) => (
                <tr key={i}>
                  <td className="px-3 py-1.5 font-mono text-slate-400 whitespace-nowrap">{when(a.start)}</td>
                  <td className="px-3 py-1.5 text-slate-300">{ICONS[a.sport] || '•'} {a.home} – {a.away}</td>
                  <td className="px-3 py-1.5 text-slate-200">{pick(a)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-300">{a.price.toFixed(2)} <span className="text-slate-500">{cap(a.book)}</span></td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-400">{a.close_prob ? (1 / a.close_prob).toFixed(2) : '—'}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-400">{pct(a.ev * 100)}</td>
                  <td className={`px-3 py-1.5 text-right font-mono font-bold ${evColor(a.ev_at_close)}`}>{a.ev_at_close == null ? '—' : pct(a.ev_at_close * 100)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
