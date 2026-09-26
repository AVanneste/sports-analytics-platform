import React, { useState } from 'react';
import { Flame, ChevronDown, ChevronUp, Trophy } from 'lucide-react';
import { TennisMatch } from '../types';

interface TennisMatchCardProps {
  match: TennisMatch;
}

const formatNum = (val: unknown, decimals: number = 1): string => {
  if (val === null || val === undefined || val === 'N/A' || val === 'Unranked / N/A' || val === '-') {
    return '-';
  }
  const n = typeof val === 'number' ? val : parseFloat(String(val));
  return isNaN(n) ? '-' : n.toFixed(decimals);
};

const formatPct = (val: unknown, decimals: number = 1): string => {
  const formatted = formatNum(val, decimals);
  return formatted === '-' ? '-' : `${formatted}%`;
};

export const TennisMatchCard: React.FC<TennisMatchCardProps> = ({ match: m }) => {
  const [showScorelines, setShowScorelines] = useState(false);
  const [showAllLines, setShowAllLines] = useState(false);
  const [selectedGamesLine, setSelectedGamesLine] = useState<number | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [showAbstractProfile, setShowAbstractProfile] = useState(false);
  const sg = m.sets_games;
  const ctx = m.context;

  const activeGamesLine =
    sg?.games_lines?.find((l) => l.line === (selectedGamesLine ?? sg.primary_games_line ?? sg.main_games_line?.line)) ||
    (sg?.games_lines && sg.games_lines.length > 0 ? sg.games_lines[0] : null) ||
    sg?.main_games_line;

  return (
    <div className="bg-dark-800/90 border border-dark-700 rounded-xl overflow-hidden shadow-sm hover:border-sky-500/50 transition-all">
      {/* Top Fixture Bar */}
      <div className="bg-dark-700/40 px-4 py-2.5 border-b border-dark-700 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/20 text-sky-400 border border-sky-500/30">
            {m.circuit}
          </span>
          <span className="font-bold text-slate-200">{m.tourney_name}</span>
          <span className="text-slate-500">•</span>
          <span className="font-mono text-slate-400">{m.surface} Court</span>
          <span className="text-slate-500">•</span>
          <span className="font-mono text-slate-400">{m.date}</span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400">{m.round || 'Main Draw'}</span>
        </div>

        <div className="flex items-center space-x-2">
          {m.ai_audit && (
            <span
              onClick={() => setShowAudit(!showAudit)}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-bold cursor-pointer text-[10px] uppercase border transition-all ${
                m.ai_audit.verdict === 'GO'
                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25'
                  : m.ai_audit.verdict === 'CAUTION'
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/30 hover:bg-amber-500/25'
                  : 'bg-rose-500/15 text-rose-300 border-rose-500/30 hover:bg-rose-500/25'
              }`}
            >
              <span>🧠 AI Audit: {m.ai_audit.verdict} ({formatNum(m.ai_audit.confidence_score, 0)}%)</span>
            </span>
          )}

          {m.betting?.has_value && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 font-bold border border-amber-500/30 text-[11px]">
              <Flame className="w-3 h-3 text-amber-400" />
              <span>
                Value Pick: {m.betting.recommended_pick} (+{formatNum(m.betting.best_ev, 1)}% EV)
              </span>
            </span>
          )}
          <span className="text-[11px] font-mono text-slate-400">
            Best of {m.best_of}
          </span>
        </div>
      </div>

      {/* Match Body */}
      <div className="p-4 space-y-4">
        {/* Players Head to Head Probabilities */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
          {/* Player 1 */}
          <div className="flex items-center space-x-3">
            <div className="flex-1 text-left">
              <div className="text-sm font-extrabold text-white flex flex-wrap items-center gap-1.5">
                <span>{m.p1_name}</span>
                {ctx?.p1_rank ? (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30" title={`Current ATP/WTA Rank: #${ctx.p1_rank}`}>
                    #{ctx.p1_rank}
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-500 bg-dark-900 border border-dark-700" title="Unranked / Qualifier">
                    UR
                  </span>
                )}
                {ctx?.p1_career_high && (
                  <span className="text-[10px] font-mono text-slate-400" title={`Career-High Rank: #${ctx.p1_career_high}`}>
                    (CH: #{ctx.p1_career_high})
                  </span>
                )}
                {m.predicted_winner === m.p1_name && (
                  <span className="text-emerald-400 text-xs" title="Model Predicted Winner">👑</span>
                )}
              </div>
              <div className="text-[11px] text-slate-400 font-mono flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1">
                <span>
                  Elo: <strong className="text-sky-400">{formatNum(ctx?.p1_surface_elo, 0)}</strong>
                  {ctx?.p1_provisional && (
                    <span className="ml-1 text-[9px] text-amber-400 font-normal" title={`Provisional rating based on ${ctx.p1_match_count ?? 2} tour matches`}>
                      (Prov.)
                    </span>
                  )}
                </span>
                <span>•</span>
                <span>L5: <strong className={ctx?.p1_form_5 !== null && ctx?.p1_form_5 !== undefined && ctx.p1_form_5 >= 60 ? "text-emerald-400" : "text-slate-200"}>{formatPct(ctx?.p1_form_5, 0)}</strong></span>
                <span>•</span>
                <span>{m.surface}: <strong className={ctx?.p1_surface_form !== null && ctx?.p1_surface_form !== undefined && ctx.p1_surface_form >= 60 ? "text-amber-400" : "text-slate-200"}>{formatPct(ctx?.p1_surface_form, 0)}</strong></span>
              </div>
            </div>
          </div>

          {/* Prob Bar */}
          <div className="space-y-1 text-center">
            <div className="flex justify-between text-xs font-bold font-mono">
              <span className="text-sky-400">{formatNum(m.p1_prob, 0)}%</span>
              <span className="text-slate-400">vs</span>
              <span className="text-purple-400">{formatNum(m.p2_prob, 0)}%</span>
            </div>
            <div className="w-full bg-dark-900 rounded-full h-2 overflow-hidden flex">
              <div className="bg-sky-500 h-2" style={{ width: `${Math.min(100, Math.max(0, Number(m.p1_prob) || 50))}%` }}></div>
              <div className="bg-purple-500 h-2" style={{ width: `${Math.min(100, Math.max(0, Number(m.p2_prob) || 50))}%` }}></div>
            </div>
            <div className="text-[10px] text-slate-400 font-medium">
              Anti-Symmetric Ensembling • Confidence: <strong className="text-white">{formatNum(m.confidence, 0)}%</strong>
            </div>
          </div>

          {/* Player 2 */}
          <div className="flex items-center space-x-3">
            <div className="flex-1 text-right">
              <div className="text-sm font-extrabold text-white flex flex-wrap items-center justify-end gap-1.5">
                {m.predicted_winner === m.p2_name && (
                  <span className="text-emerald-400 text-xs" title="Model Predicted Winner">👑</span>
                )}
                {ctx?.p2_career_high && (
                  <span className="text-[10px] font-mono text-slate-400" title={`Career-High Rank: #${ctx.p2_career_high}`}>
                    (CH: #{ctx.p2_career_high})
                  </span>
                )}
                {ctx?.p2_rank ? (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30" title={`Current ATP/WTA Rank: #${ctx.p2_rank}`}>
                    #{ctx.p2_rank}
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-500 bg-dark-900 border border-dark-700" title="Unranked / Qualifier">
                    UR
                  </span>
                )}
                <span>{m.p2_name}</span>
              </div>
              <div className="text-[11px] text-slate-400 font-mono flex flex-wrap items-center justify-end gap-x-2 gap-y-0.5 mt-1">
                <span>{m.surface}: <strong className={ctx?.p2_surface_form !== null && ctx?.p2_surface_form !== undefined && ctx.p2_surface_form >= 60 ? "text-amber-400" : "text-slate-200"}>{formatPct(ctx?.p2_surface_form, 0)}</strong></span>
                <span>•</span>
                <span>L5: <strong className={ctx?.p2_form_5 !== null && ctx?.p2_form_5 !== undefined && ctx.p2_form_5 >= 60 ? "text-emerald-400" : "text-slate-200"}>{formatPct(ctx?.p2_form_5, 0)}</strong></span>
                <span>•</span>
                <span>
                  Elo: <strong className="text-purple-400">{formatNum(ctx?.p2_surface_elo, 0)}</strong>
                  {ctx?.p2_provisional && (
                    <span className="ml-1 text-[9px] text-amber-400 font-normal" title={`Provisional rating based on ${ctx.p2_match_count ?? 2} tour matches`}>
                      (Prov.)
                    </span>
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Multi-Market Grid for Tennis */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          {/* 1. Sets Market */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>🎾 Sets Markets</span>
              <span className="text-[10px] text-sky-400">≥1 Set</span>
            </div>
            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between items-center py-1 border-b border-dark-800">
                <span className="text-slate-400">{m.p1_name.slice(0, 10)} ≥1 Set</span>
                <span className="text-white font-bold">{formatPct(sg?.p1_win_at_least_1_set_prob, 1)}</span>
                <span className="text-slate-400 text-[11px]">Fair: {formatNum(sg?.p1_win_at_least_1_set_odds, 2)}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-dark-800">
                <span className="text-slate-400">{m.p2_name.slice(0, 10)} ≥1 Set</span>
                <span className="text-white font-bold">{formatPct(sg?.p2_win_at_least_1_set_prob, 1)}</span>
                <span className="text-slate-400 text-[11px]">Fair: {formatNum(sg?.p2_win_at_least_1_set_odds, 2)}</span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-slate-400">Deciding Set</span>
                <span className="text-amber-400 font-bold">{formatPct(sg?.prob_deciding_set, 1)}</span>
                <span className="text-slate-400 text-[11px]">Fair: {formatNum(sg?.fair_odds_deciding_set, 2)}</span>
              </div>
            </div>
          </div>

          {/* 2. Total Games Line */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>🎯 Total Games Line</span>
              <span className="text-[10px] text-purple-400 font-mono">
                Exp: {formatNum(sg?.expected_total_games, 1) !== '-' ? formatNum(sg?.expected_total_games, 1) : '22.5'}
              </span>
            </div>

            {/* Interactive Multi-Line Selector Pills */}
            {sg?.games_lines && sg.games_lines.length > 0 && (
              <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
                {sg.games_lines.map((gl) => {
                  const isCurrent = gl.line === activeGamesLine?.line;
                  return (
                    <button
                      key={gl.line}
                      onClick={() => setSelectedGamesLine(gl.line)}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold transition-all ${
                        isCurrent
                          ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50 shadow-sm'
                          : 'bg-dark-800 text-slate-400 hover:text-white border border-dark-700/50'
                      }`}
                      title={gl.is_primary ? 'Primary Bookmaker Consensus Line' : `O/U ${gl.line}`}
                    >
                      {gl.line}{gl.is_primary ? '*' : ''}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="space-y-1.5 text-xs font-mono">
              {activeGamesLine ? (
                <>
                  <div className="flex justify-between items-center py-1 border-b border-dark-800">
                    <span className="text-slate-400">Over {activeGamesLine.line}</span>
                    <span className="text-emerald-400 font-bold">{formatPct(activeGamesLine.prob_over, 1)}</span>
                    <span className="text-slate-400 text-[11px]">Fair: {formatNum(activeGamesLine.fair_odds_over, 2)}</span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span className="text-slate-400">Under {activeGamesLine.line}</span>
                    <span className="text-sky-400 font-bold">{formatPct(activeGamesLine.prob_under, 1)}</span>
                    <span className="text-slate-400 text-[11px]">Fair: {formatNum(activeGamesLine.fair_odds_under, 2)}</span>
                  </div>
                </>
              ) : (
                <div className="text-slate-500 text-center py-2">Line awaiting bookmaker consensus</div>
              )}
            </div>
          </div>

          {/* 3. Betting Value Signal */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>💰 Betting Recommendation</span>
              <span className="text-[10px] text-slate-500">Kelly Edge</span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="text-slate-300 font-semibold">
                Pick: <span className="text-amber-400 font-bold">{m.betting?.recommended_pick || m.predicted_winner}</span>
              </div>
              <div className="flex justify-between text-slate-400 text-[11px] font-mono">
                <span>Edge:</span>
                <span className="text-emerald-400 font-bold">
                  {m.betting?.best_edge && Number(m.betting.best_edge) > 0 ? `+${formatNum(m.betting.best_edge, 1)}%` : 'Fair odds'}
                </span>
              </div>
              <div className="flex justify-between text-slate-400 text-[11px] font-mono">
                <span>Kelly Stake:</span>
                <span className="text-white font-bold">
                  {m.betting?.best_stake && Number(m.betting.best_stake) > 0 ? `${formatNum(m.betting.best_stake, 1)}% bankroll` : '1.0% flat'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-dark-700/60 text-xs">
          {m.ai_audit && (
            <button
              onClick={() => setShowAudit(!showAudit)}
              className={`px-2.5 py-1 rounded text-[11px] font-bold flex items-center space-x-1.5 transition-all ${
                m.ai_audit.verdict === 'GO'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30'
                  : m.ai_audit.verdict === 'CAUTION'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30'
              }`}
            >
              <span>🧠 AI Pre-Bet Audit ({m.ai_audit.verdict} • {formatNum(m.ai_audit.confidence_score, 0)}%)</span>
              {showAudit ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {sg?.scoreline_probabilities && Object.keys(sg.scoreline_probabilities).length > 0 && (
            <button
              onClick={() => setShowScorelines(!showScorelines)}
              className="px-2.5 py-1 rounded bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white text-[11px] font-bold flex items-center space-x-1"
            >
              <span>🎯 Set Scoreline Probabilities</span>
              {showScorelines ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {(sg?.games_market_table || (sg?.games_lines && sg.games_lines.length > 0)) && (
            <button
              onClick={() => setShowAllLines(!showAllLines)}
              className="px-2.5 py-1 rounded bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white text-[11px] font-bold flex items-center space-x-1"
            >
              <span>🔢 Multi-Line Games Table</span>
              {showAllLines ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          <button
            onClick={() => setShowAbstractProfile(!showAbstractProfile)}
            className={`px-2.5 py-1 rounded text-[11px] font-bold flex items-center space-x-1.5 transition-all ${
              showAbstractProfile
                ? 'bg-sky-500/25 text-sky-200 border border-sky-500/50 shadow-sm'
                : 'bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white'
            }`}
          >
            <Trophy className="w-3 h-3 text-sky-400" />
            <span>📊 Tennis Abstract Profiles & Form</span>
            {showAbstractProfile ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>

        {/* AI Pre-Bet Audit Expandable Panel */}
        {showAudit && m.ai_audit && (
          <div className="p-4 bg-dark-900/95 rounded-xl border border-dark-600 text-xs space-y-3 shadow-lg">
            <div className="flex items-center justify-between border-b border-dark-700/80 pb-2.5">
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-sm text-white">Pre-Bet Risk Audit</span>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-bold text-[10px] uppercase tracking-wide border ${
                    m.ai_audit.verdict === 'GO'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : m.ai_audit.verdict === 'CAUTION'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                  }`}
                >
                  {m.ai_audit.verdict} VERDICT
                </span>
              </div>
              <div className="text-[11px] font-mono text-slate-400">
                Confidence: <strong className="text-white font-bold">{formatNum(m.ai_audit.confidence_score, 0)}%</strong>
              </div>
            </div>

            <p className="text-slate-200 text-xs leading-relaxed italic bg-dark-800/80 p-3 rounded-lg border border-dark-700/60">
              "{m.ai_audit.summary}"
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
              <div className="space-y-1.5">
                <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                  <span>✓</span> <span>Key Model Angles</span>
                </div>
                <ul className="space-y-1.5 text-slate-300">
                  {(m.ai_audit.pros || []).map((p, idx) => (
                    <li key={idx} className="flex items-start space-x-2">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span className="text-[11px] leading-snug">{p}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="space-y-1.5">
                <div className="text-[11px] font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                  <span>⚠</span> <span>Qualitative Risk Traps</span>
                </div>
                <ul className="space-y-1.5 text-slate-300">
                  {(m.ai_audit.risks || []).map((r, idx) => (
                    <li key={idx} className="flex items-start space-x-2">
                      <span className="text-rose-400 font-bold">•</span>
                      <span className="text-[11px] leading-snug">{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {m.ai_audit.tactical_angle && (
              <div className="text-[11px] text-slate-400 pt-2 border-t border-dark-700/50">
                <strong className="text-slate-300">Tactical Dynamic:</strong> {m.ai_audit.tactical_angle}
              </div>
            )}
          </div>
        )}

        {showScorelines && sg?.scoreline_probabilities && (
          <div className="mt-3 p-3 bg-dark-900/90 rounded-lg border border-dark-700 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            {Object.entries(sg.scoreline_probabilities).map(([score, prob]) => (
              <div key={score} className="p-2 bg-dark-800 rounded border border-dark-700/60 flex justify-between items-center">
                <span className="text-slate-300 font-semibold">{score}</span>
                <span className="text-emerald-400 font-bold">{formatPct(Number(prob) * 100, 1)}</span>
              </div>
            ))}
          </div>
        )}

        {showAllLines && (sg?.games_lines || sg?.games_market_table) && (
          <div className="mt-3 p-3 bg-dark-900/95 rounded-xl border border-dark-700 overflow-x-auto shadow-sm">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center justify-between">
              <span>📊 Multi-Line Total Games Market Spectrum</span>
              <span className="text-[10px] text-purple-400 font-mono">Expected Total: {formatNum(sg?.expected_total_games, 1)} games</span>
            </div>
            <table className="w-full text-xs font-mono text-left">
              <thead className="bg-dark-800 text-slate-400 text-[10px] uppercase border-b border-dark-700">
                <tr>
                  <th className="p-2">Line</th>
                  <th className="p-2 text-right">P(Over)</th>
                  <th className="p-2 text-right">Fair Odds Over</th>
                  <th className="p-2 text-right">P(Under)</th>
                  <th className="p-2 text-right">Fair Odds Under</th>
                  <th className="p-2 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-800">
                {(sg.games_lines || []).map((gl) => (
                  <tr
                    key={gl.line}
                    className={`hover:bg-dark-800/60 transition-colors ${
                      gl.line === activeGamesLine?.line ? 'bg-purple-500/10' : ''
                    }`}
                  >
                    <td className="p-2 font-bold text-white">
                      O/U {gl.line} {gl.is_primary ? <span className="text-purple-400 text-[10px] ml-1">(Consensus)</span> : null}
                    </td>
                    <td className="p-2 text-right font-bold text-emerald-400">{formatPct(gl.prob_over, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatNum(gl.fair_odds_over, 2)}</td>
                    <td className="p-2 text-right font-bold text-sky-400">{formatPct(gl.prob_under, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatNum(gl.fair_odds_under, 2)}</td>
                    <td className="p-2 text-center">
                      <button
                        onClick={() => setSelectedGamesLine(gl.line)}
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          gl.line === activeGamesLine?.line
                            ? 'bg-purple-500 text-white'
                            : 'bg-dark-700 text-slate-300 hover:text-white'
                        }`}
                      >
                        {gl.line === activeGamesLine?.line ? 'Selected' : 'Select'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showAbstractProfile && (
          <div className="mt-3 p-4 bg-dark-900/95 rounded-xl border border-sky-500/40 text-xs space-y-4 shadow-xl">
            {/* Header & Source Note */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-dark-700/80 pb-2.5">
              <div className="flex items-center space-x-2">
                <Trophy className="w-4 h-4 text-amber-400" />
                <span className="font-extrabold text-sm text-white">Tennis Abstract Player Profile & Matchup Analysis</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                  Jeff Sackmann Data
                </span>
              </div>
              <div className="text-[11px] font-mono text-slate-400">
                H2H: <span className="text-white font-bold">{ctx?.h2h_p1_wins ?? 0}W</span> ({m.p1_name}) - <span className="text-white font-bold">{ctx?.h2h_p2_wins ?? 0}W</span> ({m.p2_name})
                <span className="text-slate-500 ml-1">[{ctx?.h2h_total ?? 0} total, {ctx?.h2h_surf_p1_wins ?? 0} on {m.surface}]</span>
              </div>
            </div>

            {/* Metric Comparison Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead className="bg-dark-800 text-slate-400 text-[10px] uppercase border-b border-dark-700">
                  <tr>
                    <th className="p-2 text-left w-2/5">Player Profile Metric</th>
                    <th className="p-2 text-right text-sky-300 w-[30%]">{m.p1_name}</th>
                    <th className="p-2 text-right text-purple-300 w-[30%]">{m.p2_name}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-800/80">
                  {/* Rankings & Baseline */}
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Official Tour Rank (ATP/WTA)</td>
                    <td className="p-2 text-right font-bold text-white">
                      {ctx?.p1_rank ? `#${ctx.p1_rank}` : 'Unranked'}
                    </td>
                    <td className="p-2 text-right font-bold text-white">
                      {ctx?.p2_rank ? `#${ctx.p2_rank}` : 'Unranked'}
                    </td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Career-High Rank (Peak)</td>
                    <td className="p-2 text-right text-slate-300">
                      {ctx?.p1_career_high ? `#${ctx.p1_career_high}` : '-'}
                    </td>
                    <td className="p-2 text-right text-slate-300">
                      {ctx?.p2_career_high ? `#${ctx.p2_career_high}` : '-'}
                    </td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Age</td>
                    <td className="p-2 text-right text-slate-300">{ctx?.p1_age ? `${ctx.p1_age} yrs` : '-'}</td>
                    <td className="p-2 text-right text-slate-300">{ctx?.p2_age ? `${ctx.p2_age} yrs` : '-'}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">{m.surface} Surface Elo Rating</td>
                    <td className="p-2 text-right font-bold text-sky-400">
                      {formatNum(ctx?.p1_surface_elo, 0)}
                      {ctx?.p1_provisional && (
                        <span className="text-[10px] text-amber-400 font-normal ml-1">
                          ({ctx.p1_match_count ?? 2}m prov.)
                        </span>
                      )}
                    </td>
                    <td className="p-2 text-right font-bold text-purple-400">
                      {formatNum(ctx?.p2_surface_elo, 0)}
                      {ctx?.p2_provisional && (
                        <span className="text-[10px] text-amber-400 font-normal ml-1">
                          ({ctx.p2_match_count ?? 2}m prov.)
                        </span>
                      )}
                    </td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Overall Elo Rating</td>
                    <td className="p-2 text-right text-slate-300">
                      {formatNum(ctx?.p1_elo, 0)}
                      {ctx?.p1_provisional && (
                        <span className="text-[10px] text-amber-400 font-normal ml-1">
                          ({ctx.p1_match_count ?? 2}m prov.)
                        </span>
                      )}
                    </td>
                    <td className="p-2 text-right text-slate-300">
                      {formatNum(ctx?.p2_elo, 0)}
                      {ctx?.p2_provisional && (
                        <span className="text-[10px] text-amber-400 font-normal ml-1">
                          ({ctx.p2_match_count ?? 2}m prov.)
                        </span>
                      )}
                    </td>
                  </tr>

                  {/* Form & Dominance Ratio */}
                  <tr className="hover:bg-dark-800/40 bg-dark-800/20">
                    <td className="p-2 text-slate-300 font-semibold">Dominance Ratio (DR = Ret% / SrvLost%)</td>
                    <td className="p-2 text-right font-bold text-white">{formatNum(ctx?.p1_dominance_ratio, 2)}</td>
                    <td className="p-2 text-right font-bold text-white">{formatNum(ctx?.p2_dominance_ratio, 2)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Recent Form (Last 5 Matches Win %)</td>
                    <td className="p-2 text-right font-bold text-emerald-400">{formatPct(ctx?.p1_form_5, 1)}</td>
                    <td className="p-2 text-right font-bold text-emerald-400">{formatPct(ctx?.p2_form_5, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">1-Year Surface Form ({m.surface} Win %)</td>
                    <td className="p-2 text-right font-bold text-amber-400">{formatPct(ctx?.p1_surface_form, 1)}</td>
                    <td className="p-2 text-right font-bold text-amber-400">{formatPct(ctx?.p2_surface_form, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Sets Won Ratio (Last 10 Matches)</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_sets_win_rate, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_sets_win_rate, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Games Won Ratio (Last 10 Matches)</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_games_win_rate, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_games_win_rate, 1)}</td>
                  </tr>

                  {/* Serve Statistics */}
                  <tr className="hover:bg-dark-800/40 bg-dark-800/20">
                    <td className="p-2 text-slate-300 font-semibold">Projected Match Hold %</td>
                    <td className="p-2 text-right font-bold text-sky-400">{formatPct((ctx?.projected_p1_hold_rate ?? 0) * 100, 1)}</td>
                    <td className="p-2 text-right font-bold text-purple-400">{formatPct((ctx?.projected_p2_hold_rate ?? 0) * 100, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Career Surface Hold %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_surface_hold_pct, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_surface_hold_pct, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Ace Rate % (Aces / 1st Serves)</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_ace_rate, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_ace_rate, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Double Fault Rate %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_df_rate, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_df_rate, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">1st Serve In %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_first_serve_pct, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_first_serve_pct, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">1st Serve Points Won %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_first_serve_won_pct, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_first_serve_won_pct, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Break Points Saved %</td>
                    <td className="p-2 text-right font-bold text-emerald-400">{formatPct(ctx?.p1_bp_save_pct, 1)}</td>
                    <td className="p-2 text-right font-bold text-emerald-400">{formatPct(ctx?.p2_bp_save_pct, 1)}</td>
                  </tr>

                  {/* Return Statistics */}
                  <tr className="hover:bg-dark-800/40 bg-dark-800/20">
                    <td className="p-2 text-slate-300 font-semibold">Projected Match Break %</td>
                    <td className="p-2 text-right font-bold text-sky-400">{formatPct((ctx?.projected_p1_break_rate ?? 0) * 100, 1)}</td>
                    <td className="p-2 text-right font-bold text-purple-400">{formatPct((ctx?.projected_p2_break_rate ?? 0) * 100, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Break Points Converted %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_bp_conversion_pct, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_bp_conversion_pct, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Return Points Won %</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_return_points_won_pct, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_return_points_won_pct, 1)}</td>
                  </tr>

                  {/* Clutch Records */}
                  <tr className="hover:bg-dark-800/40 bg-dark-800/20">
                    <td className="p-2 text-slate-300 font-semibold">Deciding Set Win Rate (Clutch)</td>
                    <td className="p-2 text-right font-bold text-amber-400">{formatPct(ctx?.p1_deciding_set_win_rate, 1)}</td>
                    <td className="p-2 text-right font-bold text-amber-400">{formatPct(ctx?.p2_deciding_set_win_rate, 1)}</td>
                  </tr>
                  <tr className="hover:bg-dark-800/40">
                    <td className="p-2 text-slate-300 font-semibold">Tiebreak Win Rate</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p1_tiebreak_win_rate, 1)}</td>
                    <td className="p-2 text-right text-slate-300">{formatPct(ctx?.p2_tiebreak_win_rate, 1)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Recent Matches Match Logs Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-dark-700/80">
              {/* Player 1 Recent Match Logs */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-sky-400 flex items-center gap-1.5">
                    <span>📅</span> <span>{m.p1_name} — Recent Match History</span>
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Form: {formatPct(ctx?.p1_form_5, 0)}
                  </span>
                </div>
                {ctx?.p1_recent_matches && ctx.p1_recent_matches.length > 0 ? (
                  <div className="space-y-1.5">
                    {ctx.p1_recent_matches.map((match, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-dark-800/70 border border-dark-700/60 rounded-lg flex items-center justify-between gap-2 text-xs font-mono"
                      >
                        <div className="flex items-center space-x-2">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              match.won
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            }`}
                          >
                            {match.result}
                          </span>
                          <div className="flex flex-col">
                            <span className="text-white font-semibold">{match.opponent}</span>
                            <span className="text-[10px] text-slate-400">{match.tourney} ({match.surface})</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-slate-200 font-bold">{match.score || '-'}</div>
                          <div className="text-[10px] text-slate-400">{match.date}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-slate-500 text-xs italic py-2">No recent match history available</div>
                )}
              </div>

              {/* Player 2 Recent Match Logs */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-purple-400 flex items-center gap-1.5">
                    <span>📅</span> <span>{m.p2_name} — Recent Match History</span>
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Form: {formatPct(ctx?.p2_form_5, 0)}
                  </span>
                </div>
                {ctx?.p2_recent_matches && ctx.p2_recent_matches.length > 0 ? (
                  <div className="space-y-1.5">
                    {ctx.p2_recent_matches.map((match, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-dark-800/70 border border-dark-700/60 rounded-lg flex items-center justify-between gap-2 text-xs font-mono"
                      >
                        <div className="flex items-center space-x-2">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              match.won
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            }`}
                          >
                            {match.result}
                          </span>
                          <div className="flex flex-col">
                            <span className="text-white font-semibold">{match.opponent}</span>
                            <span className="text-[10px] text-slate-400">{match.tourney} ({match.surface})</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-slate-200 font-bold">{match.score || '-'}</div>
                          <div className="text-[10px] text-slate-400">{match.date}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-slate-500 text-xs italic py-2">No recent match history available</div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
