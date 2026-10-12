import React, { useEffect, useMemo, useState } from 'react';
import { Search, Telescope, ChevronDown, ChevronUp } from 'lucide-react';

interface ScoutStat { label: string; value: number | null; pct: number | null }
interface ScoutTwin { id: number; name: string; team: string; league: string; age: number | null; similarity: number }
interface ScoutPlayer {
  id: number; name: string; team: string; league: string; nationality: string | null; age: number | null;
  position: string; foot: string | null; contract_end: string | null; height_cm: number | null;
  minutes: number; matches: number; market_value_eur: number | null; level: number | null;
  role_score: number; adj_score: number; stats: ScoutStat[]; similar: ScoutTwin[];
}
interface ScoutData { generated_at: string; pool_size: number; leagues: string[]; players: ScoutPlayer[] }

const POSITIONS: Record<string, string> = {
  ALL: 'All positions', ST: 'Striker', W: 'Winger', AM: 'Attacking mid', CM: 'Central mid', DM: 'Holding mid',
  FB: 'Full-back', CB: 'Centre-back', GK: 'Goalkeeper',
};
type SortKey = 'adj_score' | 'role_score' | 'age' | 'market_value_eur';

const money = (v: number | null) =>
  v == null ? '—' : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${Math.round(v / 1e3)}k`;

const pctColor = (p: number | null) =>
  p == null ? 'bg-slate-600' : p >= 80 ? 'bg-emerald-500' : p >= 60 ? 'bg-sky-500' : p >= 40 ? 'bg-slate-500' : 'bg-rose-500/70';

export const ScoutTable: React.FC = () => {
  const [data, setData] = useState<ScoutData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState('ALL');
  const [league, setLeague] = useState('ALL');
  const [maxAge, setMaxAge] = useState(23);
  const [maxValue, setMaxValue] = useState(5);
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('adj_score');
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    fetch('./data/scout.json')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(`Scouting data unavailable (${e.message}). It is built weekly by scripts/update_scout.py.`));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    const out = data.players.filter((p) =>
      (position === 'ALL' || p.position === position) &&
      (league === 'ALL' || p.league === league) &&
      (p.age == null || p.age <= maxAge) &&
      (maxValue >= 50 || p.market_value_eur == null || p.market_value_eur <= maxValue * 1e6) &&
      (!q || p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q)));
    const dir = sortKey === 'age' || sortKey === 'market_value_eur' ? 1 : -1;
    return out.sort((a, b) => dir * (((a[sortKey] as number) ?? Infinity) - ((b[sortKey] as number) ?? Infinity)));
  }, [data, position, league, maxAge, maxValue, query, sortKey]);

  if (error) return <div className="p-6 text-sm text-slate-400 bg-dark-800 border border-dark-700 rounded-xl">{error}</div>;
  if (!data) return <div className="p-6 text-sm text-slate-400">Loading scouting data…</div>;

  const header = (key: SortKey, label: string) => (
    <th className="px-3 py-2.5 text-right cursor-pointer select-none hover:text-slate-200" onClick={() => setSortKey(key)}>
      {label}{sortKey === key ? ' •' : ''}
    </th>
  );

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
      <div className="px-4 py-3 bg-dark-700/40 border-b border-dark-700 flex flex-wrap items-center gap-3">
        <Telescope className="w-4 h-4 text-emerald-400" />
        <span className="font-bold text-xs text-white">Scout: {rows.length} of {data.players.length} shortlisted</span>
        <span className="text-[11px] text-slate-400">({data.pool_size} regulars scored in {data.leagues.length} leagues, updated {data.generated_at.slice(0, 10)})</span>
      </div>

      <div className="px-4 py-3 flex flex-wrap gap-3 items-center text-xs border-b border-dark-700">
        <select value={position} onChange={(e) => setPosition(e.target.value)} className="bg-dark-900 border border-dark-700 rounded-lg px-2 py-1.5 text-slate-200">
          {Object.entries(POSITIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={league} onChange={(e) => setLeague(e.target.value)} className="bg-dark-900 border border-dark-700 rounded-lg px-2 py-1.5 text-slate-200 max-w-[14rem]">
          <option value="ALL">All leagues</option>
          {data.leagues.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <label className="flex items-center gap-2 text-slate-400">
          Max age <input type="range" min={17} max={26} value={maxAge} onChange={(e) => setMaxAge(+e.target.value)} />
          <span className="font-mono text-slate-200 w-5">{maxAge}</span>
        </label>
        <label className="flex items-center gap-2 text-slate-400">
          Max value <input type="range" min={0.5} max={50} step={0.5} value={maxValue} onChange={(e) => setMaxValue(+e.target.value)} />
          <span className="font-mono text-slate-200 w-12">{maxValue >= 50 ? 'any' : `€${maxValue}m`}</span>
        </label>
        <label className="flex items-center gap-2 bg-dark-900 border border-dark-700 rounded-lg px-2 py-1.5">
          <Search className="w-3.5 h-3.5 text-slate-500" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Player or club" className="bg-transparent outline-none text-slate-200 w-32" />
        </label>
      </div>

      <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-dark-700 z-10">
            <tr>
              <th className="px-3 py-2.5">Player</th>
              <th className="px-3 py-2.5">Club · League</th>
              <th className="px-3 py-2.5">Pos</th>
              {header('age', 'Age')}
              {header('market_value_eur', 'Value')}
              <th className="px-3 py-2.5 text-right" title="Club strength (Opta Power Ranking, 0-100)">Level</th>
              <th className="px-3 py-2.5 text-right">Mins</th>
              {header('role_score', 'Score')}
              {header('adj_score', 'Adj. score')}
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-700/60">
            {rows.slice(0, 300).map((p) => (
              <React.Fragment key={p.id}>
                <tr className="hover:bg-dark-700/30 cursor-pointer" onClick={() => setOpen(open === p.id ? null : p.id)}>
                  <td className="px-3 py-2 font-semibold text-white">{p.name}<span className="ml-1 text-[10px] text-slate-500">{p.nationality}</span></td>
                  <td className="px-3 py-2 text-slate-300">{p.team}<div className="text-[10px] text-slate-500">{p.league}</div></td>
                  <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded bg-dark-900 border border-dark-700 text-[10px] font-bold text-slate-300">{p.position}</span></td>
                  <td className="px-3 py-2 text-right font-mono text-slate-200">{p.age ?? '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-200">{money(p.market_value_eur)}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-400">{p.level?.toFixed(0) ?? '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-400">{p.minutes}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{p.role_score.toFixed(0)}</td>
                  <td className="px-3 py-2 text-right font-mono font-bold text-emerald-400">{p.adj_score.toFixed(0)}</td>
                  <td className="px-3 py-2 text-slate-500">{open === p.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}</td>
                </tr>
                {open === p.id && (
                  <tr className="bg-dark-900/50">
                    <td colSpan={10} className="px-4 py-3">
                      <div className="grid md:grid-cols-2 gap-6">
                        <div className="space-y-1.5">
                          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
                            Per 90 · percentile among {POSITIONS[p.position].toLowerCase()}s
                            {p.foot ? ` · ${p.foot} foot` : ''}{p.height_cm ? ` · ${p.height_cm} cm` : ''}
                            {p.contract_end ? ` · contract to ${p.contract_end.slice(0, 7)}` : ''}
                          </div>
                          {p.stats.map((s) => (
                            <div key={s.label} className="flex items-center gap-2">
                              <span className="w-36 text-slate-300">{s.label}</span>
                              <span className="w-12 text-right font-mono text-slate-200">{s.value ?? '—'}</span>
                              <div className="flex-1 h-2 bg-dark-700 rounded">
                                <div className={`h-2 rounded ${pctColor(s.pct)}`} style={{ width: `${s.pct ?? 0}%` }} />
                              </div>
                              <span className="w-8 text-right font-mono text-slate-400">{s.pct ?? '—'}</span>
                            </div>
                          ))}
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Closest profiles (any age, any league)</div>
                          {p.similar.map((t) => (
                            <div key={t.id} className="flex justify-between py-0.5">
                              <span className="text-slate-200">{t.name}<span className="text-slate-500"> · {t.team} · {t.league}{t.age ? ` · ${t.age}` : ''}</span></span>
                              <span className="font-mono text-slate-400">{t.similarity}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {rows.length > 300 && <div className="px-4 py-2 text-[11px] text-slate-500">Showing the first 300: narrow the filters to see the rest.</div>}
      </div>
    </div>
  );
};
