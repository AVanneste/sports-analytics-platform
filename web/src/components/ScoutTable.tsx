import React, { useEffect, useMemo, useState } from 'react';
import { Search, Telescope, ChevronDown, ChevronUp, Info } from 'lucide-react';

interface ScoutStat { label: string; value: number | null; pct: number | null; weight: number }
interface ScoutTotals { goals: number | null; assists: number | null; xg: number | null; xa: number | null; rating: number | null }
interface ScoutTwin { id: number; name: string; team: string; league: string; age: number | null; similarity: number }
interface ScoutPlayer {
  id: number; name: string; team: string; league: string; nationality: string | null; age: number | null;
  position: string; foot: string | null; contract_end: string | null; height_cm: number | null;
  minutes: number; matches: number; market_value_eur: number | null; level: number | null;
  role_score: number; adj_score: number; level_bonus: number; stats: ScoutStat[]; totals: ScoutTotals; similar: ScoutTwin[];
}
interface ScoutData {
  generated_at: string; pool_size: number; leagues: string[]; players: ScoutPlayer[];
  level_weight: number; reference_level: number;
}

const POSITIONS: Record<string, string> = {
  ALL: 'All positions', ST: 'Striker', W: 'Winger', AM: 'Attacking mid', CM: 'Central mid', DM: 'Holding mid',
  FB: 'Full-back', CB: 'Centre-back', GK: 'Goalkeeper',
};
type SortKey = 'name' | 'team' | 'position' | 'age' | 'market_value_eur' | 'level' | 'minutes' | 'role_score' | 'adj_score';

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
  const [sortDesc, setSortDesc] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [showHelp, setShowHelp] = useState(false);

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
    const dir = sortDesc ? -1 : 1;
    return out.sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null && y == null) return 0;
      if (x == null) return 1;  // missing values last either way
      if (y == null) return -1;
      return dir * (typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number));
    });
  }, [data, position, league, maxAge, maxValue, query, sortKey, sortDesc]);

  const sortBy = (key: SortKey) => {
    if (key === sortKey) setSortDesc(!sortDesc);
    else { setSortKey(key); setSortDesc(!['name', 'team', 'position', 'age', 'market_value_eur'].includes(key)); }
  };

  if (error) return <div className="p-6 text-sm text-slate-400 bg-dark-800 border border-dark-700 rounded-xl">{error}</div>;
  if (!data) return <div className="p-6 text-sm text-slate-400">Loading scouting data…</div>;

  const header = (key: SortKey, label: string, right = true, title?: string) => (
    <th className={`px-3 py-2.5 cursor-pointer select-none hover:text-slate-200 ${right ? 'text-right' : ''} ${sortKey === key ? 'text-emerald-300' : ''}`}
        onClick={() => sortBy(key)} title={title}>
      {label}{sortKey === key ? (sortDesc ? ' ▼' : ' ▲') : ''}
    </th>
  );

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-xl overflow-hidden">
      <div className="px-4 py-3 bg-dark-700/40 border-b border-dark-700 flex flex-wrap items-center gap-3">
        <Telescope className="w-4 h-4 text-emerald-400" />
        <span className="font-bold text-xs text-white">Scout: {rows.length} of {data.players.length} shortlisted</span>
        <span className="text-[11px] text-slate-400">({data.pool_size} regulars scored in {data.leagues.length} leagues, updated {data.generated_at.slice(0, 10)})</span>
        <button onClick={() => setShowHelp(!showHelp)} className="ml-auto flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200">
          <Info className="w-3.5 h-3.5" /> How the score works
        </button>
      </div>
      {showHelp && (
        <div className="px-4 py-3 text-[11px] leading-relaxed text-slate-300 bg-dark-900/60 border-b border-dark-700 space-y-1">
          <p><b>Percentile</b>: how a player's per-90 number ranks among every regular of the same position in all {data.leagues.length} leagues (100 = best). A regular has played at least half the minutes of his league's most-used player.</p>
          <p><b>Score</b> (0-100): the weighted average of the percentiles that matter for his position (e.g. wingers: xA, chances created, dribbles, xG; centre-backs: interceptions, recoveries, progressive and long passing). Open a player to see each stat's weight and contribution.</p>
          <p><b>Level</b>: his club's Opta Power Ranking (0-100). The same numbers are harder to produce against stronger opposition, so <b>Adj. score</b> = Score + {data.level_weight} × (Level − {data.reference_level}).</p>
          <p><b>How reliable?</b> Tested out of sample (weights from 2023/24, judged on 2024/25): of players aged ≤23 worth ≤€5m, 21% doubled their market value within ~16 months; among the 100 best adjusted scores, 31% did. That is about as good as ranking by FotMob's own match rating (34%), and the per-90 stats alone add little; it works best for keepers, attacking mids, strikers and central mids, barely for holding mids and wingers. Use it as a shortlist to watch, not a verdict.</p>
        </div>
      )}

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
              {header('name', 'Player', false)}
              {header('team', 'Club · League', false)}
              {header('position', 'Pos', false)}
              {header('age', 'Age')}
              {header('market_value_eur', 'Value')}
              {header('level', 'Level', true, "Club strength: Opta Power Ranking, 0-100")}
              {header('minutes', 'Mins')}
              {header('role_score', 'Score', true, "Position score from per-90 percentiles, 0-100")}
              {header('adj_score', 'Adj. score', true, "Score + club-level bonus")}
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
                            Score breakdown · per 90 · percentile among {POSITIONS[p.position].toLowerCase()}s
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-slate-500">
                            <span className="w-32">Stat</span><span className="w-12 text-right">Per 90</span>
                            <span className="flex-1">Percentile</span><span className="w-10 text-right">Weight</span><span className="w-10 text-right">Adds</span>
                          </div>
                          {p.stats.map((s) => (
                            <div key={s.label} className="flex items-center gap-2">
                              <span className="w-32 text-slate-300">{s.label}</span>
                              <span className="w-12 text-right font-mono text-slate-200">{s.value ?? '—'}</span>
                              <div className="flex-1 h-2 bg-dark-700 rounded relative">
                                <div className={`h-2 rounded ${pctColor(s.pct)}`} style={{ width: `${s.pct ?? 0}%` }} />
                              </div>
                              <span className="w-10 text-right font-mono text-slate-400">{Math.round(s.weight * 100)}%</span>
                              <span className="w-10 text-right font-mono text-slate-200">{s.pct == null ? '—' : (s.pct * s.weight).toFixed(1)}</span>
                            </div>
                          ))}
                          <div className="border-t border-dark-700 pt-1.5 mt-1 space-y-0.5 font-mono text-[11px]">
                            <div className="flex justify-between"><span className="text-slate-400">Score (sum of "Adds")</span><span className="text-slate-200">{p.role_score.toFixed(1)}</span></div>
                            <div className="flex justify-between"><span className="text-slate-400">Club level {p.level?.toFixed(0) ?? '—'}: {data.level_weight} × ({p.level?.toFixed(0) ?? '—'} − {data.reference_level})</span><span className="text-slate-200">{p.level_bonus >= 0 ? '+' : ''}{p.level_bonus.toFixed(1)}</span></div>
                            <div className="flex justify-between font-bold"><span className="text-slate-300">Adj. score</span><span className="text-emerald-400">{p.adj_score.toFixed(1)}</span></div>
                          </div>
                          <div className="text-[11px] text-slate-400 pt-1">
                            Season: {p.matches} matches · {p.minutes} min · {p.totals?.goals ?? 0} G · {p.totals?.assists ?? 0} A
                            {p.totals?.xg != null ? ` · xG ${p.totals.xg}` : ''}{p.totals?.xa != null ? ` · xA ${p.totals.xa}` : ''}
                            {p.totals?.rating != null ? ` · FotMob rating ${p.totals.rating}` : ''}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {[p.foot && `${p.foot} foot`, p.height_cm && `${p.height_cm} cm`, p.contract_end && `contract to ${p.contract_end.slice(0, 7)}`, p.nationality].filter(Boolean).join(' · ')}
                          </div>
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
