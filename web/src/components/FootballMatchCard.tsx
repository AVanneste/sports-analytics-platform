import React, { useState } from 'react';
import { Flame, ChevronDown, ChevronUp, BarChart3 } from 'lucide-react';
import { FootballMatch } from '../types';

interface FootballMatchCardProps {
  match: FootballMatch;
}

export const FootballMatchCard: React.FC<FootballMatchCardProps> = ({ match: m }) => {
  const [showDrivers, setShowDrivers] = useState(false);
  const [showH2H, setShowH2H] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [showAllLines, setShowAllLines] = useState(false);

  const [selectedGoalLine, setSelectedGoalLine] = useState<number>(m.primary_goal_line ?? 2.5);
  const [selectedCornerLine, setSelectedCornerLine] = useState<number>(m.primary_corner_line ?? 9.5);
  const [selectedCardLine, setSelectedCardLine] = useState<number>(m.primary_card_line ?? 3.5);

  const activeGoal = m.goal_lines?.find((g) => g.line === selectedGoalLine) ?? {
    line: 2.5,
    prob_over: m.prob_over25,
    prob_under: m.prob_under25,
    fair_odds_over: m.fair_odds_over25,
    fair_odds_under: m.fair_odds_under25,
  };

  const activeCorner = m.corner_lines?.find((c) => c.line === selectedCornerLine) ?? {
    line: 9.5,
    prob_over: m.prob_corners_over95,
    prob_under: m.prob_corners_under95,
    fair_odds_over: m.fair_odds_corners_over95,
    fair_odds_under: m.fair_odds_corners_under95,
  };

  const activeCard = m.card_lines?.find((k) => k.line === selectedCardLine) ?? {
    line: 3.5,
    prob_over: m.prob_cards_over35,
    prob_under: m.prob_cards_under35,
    fair_odds_over: m.fair_odds_cards_over35,
    fair_odds_under: m.fair_odds_cards_under35,
  };

  return (
    <div className="bg-dark-800/90 border border-dark-700 rounded-xl overflow-hidden shadow-sm hover:border-emerald-500/50 transition-all">
      {/* Top Fixture Bar */}
      <div className="bg-dark-700/40 px-4 py-2.5 border-b border-dark-700 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center space-x-2">
          <span className="text-base">{m.flag}</span>
          <span className="font-bold text-slate-200">{m.league_name}</span>
          <span className="text-slate-500">•</span>
          <span className="font-mono text-slate-400">{m.date}</span>
          {m.referee && (
            <>
              <span className="text-slate-500">•</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-dark-900 text-amber-300 border border-dark-700">
                Ref: {typeof m.referee.name === 'string' ? m.referee.name : ((m.referee.name as any)?.name || 'Official')} ({typeof m.referee.strictness_label === 'string' ? m.referee.strictness_label : 'League Avg'})
              </span>
            </>
          )}
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
              <span>🧠 AI Audit: {m.ai_audit.verdict} ({m.ai_audit.confidence_score}%)</span>
            </span>
          )}

          {m.best_pick && (m.best_pick.ev > 0 || m.has_value) && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 font-bold border border-amber-500/30 text-[11px]">
              <Flame className="w-3 h-3 text-amber-400" />
              <span>
                Value Pick: {m.best_pick.selection} {typeof m.best_pick.odds === 'number' ? `@ ${m.best_pick.odds.toFixed(2)}` : ''} (+{((m.best_pick.ev || 0) * 100).toFixed(1)}% EV)
              </span>
            </span>
          )}
          <span className="text-[11px] font-mono text-slate-400">
            Exp Goals: <strong className="text-white font-bold">{m.most_likely_score}</strong>
          </span>
        </div>
      </div>

      {/* Match Body */}
      <div className="p-4 space-y-4">
        {/* Teams Header & Elo Bar */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
          {/* Home Team */}
          <div className="flex items-center space-x-3">
            <div className="flex-1 text-left">
              <div className="text-sm font-extrabold text-white">{m.home_team}</div>
              <div className="text-[11px] text-slate-400 font-mono">
                Elo: <span className="text-emerald-400 font-semibold">{m.home_elo}</span> | xG:{' '}
                <span className="text-slate-200 font-semibold">{m.expected_goals_home.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Center Prob Bar */}
          <div className="space-y-1 text-center">
            <div className="flex justify-between text-[11px] font-bold font-mono">
              <span className="text-emerald-400">{((m.prob_home || 0.33) * 100).toFixed(1)}%</span>
              <span className="text-slate-400">Draw {((m.prob_draw || 0.33) * 100).toFixed(1)}%</span>
              <span className="text-sky-400">{((m.prob_away || 0.33) * 100).toFixed(1)}%</span>
            </div>
            <div className="w-full bg-dark-900 rounded-full h-2 overflow-hidden flex">
              <div
                className="bg-emerald-500 h-2"
                style={{ width: `${(m.prob_home || 0.33) * 100}%` }}
              ></div>
              <div
                className="bg-slate-500 h-2"
                style={{ width: `${(m.prob_draw || 0.33) * 100}%` }}
              ></div>
              <div
                className="bg-sky-500 h-2"
                style={{ width: `${(m.prob_away || 0.33) * 100}%` }}
              ></div>
            </div>
            <div className="text-[10px] text-slate-400 font-medium">Calibrated ML + Dixon-Coles Poisson</div>
          </div>

          {/* Away Team */}
          <div className="flex items-center space-x-3">
            <div className="flex-1 text-right">
              <div className="text-sm font-extrabold text-white">{m.away_team}</div>
              <div className="text-[11px] text-slate-400 font-mono">
                Elo: <span className="text-sky-400 font-semibold">{m.away_elo}</span> | xG:{' '}
                <span className="text-slate-200 font-semibold">{m.expected_goals_away.toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 4 Multi-Market Columns Grid (Full Parity with Streamlit) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
          {/* 1. 1X2 Match Outcomes */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>🏆 1X2 Moneyline</span>
              <span className="text-[10px] text-slate-500">Fair / Cons</span>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between items-center py-1 border-b border-dark-800">
                <span className="text-slate-400">1 ({m.home_team.slice(0, 8)})</span>
                <span className="font-mono text-emerald-400 font-bold">{m.fair_odds_home.toFixed(2)}</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded">
                  {m.odds_home?.toFixed(2) || '-'}
                </span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-dark-800">
                <span className="text-slate-400">X (Draw)</span>
                <span className="font-mono text-slate-300 font-bold">{m.fair_odds_draw.toFixed(2)}</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded">
                  {m.odds_draw?.toFixed(2) || '-'}
                </span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-slate-400">2 ({m.away_team.slice(0, 8)})</span>
                <span className="font-mono text-sky-400 font-bold">{m.fair_odds_away.toFixed(2)}</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded">
                  {m.odds_away?.toFixed(2) || '-'}
                </span>
              </div>
            </div>
          </div>

          {/* 2. Total Goals Multi-Line */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
                <span>⚽ Goals</span>
                <span className="font-mono text-[10px] text-slate-400 font-normal">
                  λ={(m.expected_total_goals ?? (m.expected_goals_home + m.expected_goals_away)).toFixed(1)}
                </span>
              </div>
              <span className="text-[10px] text-emerald-400 font-bold">{m.most_likely_score}</span>
            </div>

            {/* Goal Line Selector Pills */}
            <div className="flex items-center space-x-1 bg-dark-950/60 p-0.5 rounded-md border border-dark-800">
              {[1.5, 2.5, 3.5, 4.5].map((lineVal) => {
                const isPrimary = lineVal === (m.primary_goal_line ?? 2.5);
                const isSelected = lineVal === selectedGoalLine;
                return (
                  <button
                    key={lineVal}
                    type="button"
                    onClick={() => setSelectedGoalLine(lineVal)}
                    className={`flex-1 py-0.5 text-[10px] font-bold rounded transition-all ${
                      isSelected
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-xs'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                    }`}
                    title={isPrimary ? 'Model Primary Expectancy Line' : undefined}
                  >
                    {lineVal}
                    {isPrimary && <span className="text-[8px] ml-0.5 text-amber-400">★</span>}
                  </button>
                );
              })}
            </div>

            <div className="space-y-1 text-xs">
              <div className="flex justify-between items-center py-0.5 border-b border-dark-800/80">
                <span className="text-slate-400 text-[11px]">Over {selectedGoalLine}</span>
                <span className="font-mono text-slate-200 font-semibold">{(activeGoal.prob_over * 100).toFixed(1)}%</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded text-[11px]">
                  {selectedGoalLine === 2.5 && m.odds_over25 ? m.odds_over25.toFixed(2) : `@${activeGoal.fair_odds_over.toFixed(2)}`}
                </span>
              </div>
              <div className="flex justify-between items-center py-0.5">
                <span className="text-slate-400 text-[11px]">Under {selectedGoalLine}</span>
                <span className="font-mono text-slate-200 font-semibold">{(activeGoal.prob_under * 100).toFixed(1)}%</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded text-[11px]">
                  {selectedGoalLine === 2.5 && m.odds_under25 ? m.odds_under25.toFixed(2) : `@${activeGoal.fair_odds_under.toFixed(2)}`}
                </span>
              </div>
            </div>
          </div>

          {/* 3. Both Teams To Score (BTTS) */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>🥅 Both Teams Score</span>
              <span className="text-[10px] text-slate-500">BTTS</span>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between items-center py-1 border-b border-dark-800">
                <span className="text-slate-400">BTTS Yes</span>
                <span className="font-mono text-slate-200">{(m.prob_btts_yes * 100).toFixed(1)}%</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded">
                  {m.odds_btts_yes?.toFixed(2) || (typeof m.fair_odds_btts_yes === 'number' ? m.fair_odds_btts_yes.toFixed(2) : '-')}
                </span>
              </div>
              <div className="flex justify-between items-center py-1">
                <span className="text-slate-400">BTTS No</span>
                <span className="font-mono text-slate-200">{(m.prob_btts_no * 100).toFixed(1)}%</span>
                <span className="font-mono text-white font-bold bg-dark-800 px-1.5 py-0.5 rounded">
                  {m.odds_btts_no?.toFixed(2) || (typeof m.fair_odds_btts_no === 'number' ? m.fair_odds_btts_no.toFixed(2) : '-')}
                </span>
              </div>
            </div>
          </div>

          {/* 4. Corners & Disciplinary Cards Multi-Line */}
          <div className="bg-dark-900/90 border border-dark-700/80 rounded-lg p-3 space-y-2">
            <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>🚩 Corners & Cards</span>
              <span className="text-[10px] text-amber-400 font-normal">λ Multi-Line</span>
            </div>

            {/* Corners Sub-row */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400 font-medium">Corners</span>
                {/* Corner Line Selector Pills */}
                <div className="flex items-center space-x-0.5 bg-dark-950/60 p-0.5 rounded border border-dark-800">
                  {[8.5, 9.5, 10.5, 11.5].map((lVal) => {
                    const isPrimary = lVal === (m.primary_corner_line ?? 9.5);
                    const isSelected = lVal === selectedCornerLine;
                    return (
                      <button
                        key={lVal}
                        type="button"
                        onClick={() => setSelectedCornerLine(lVal)}
                        className={`px-1.5 py-0.5 text-[9px] font-bold rounded transition-all ${
                          isSelected
                            ? 'bg-amber-500/25 text-amber-300 border border-amber-500/40'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                        }`}
                        title={isPrimary ? 'Primary Model Expectancy' : undefined}
                      >
                        {lVal}{isPrimary ? '★' : ''}
                      </button>
                    );
                  })}
                </div>
                <span className="font-mono text-slate-400 text-[10px]">λ={m.expected_corners?.toFixed(1) || '9.5'}</span>
              </div>
              <div className="flex justify-between items-center py-0.5 text-xs">
                <span className="text-slate-400 text-[11px]">&gt;{selectedCornerLine}: <b className="text-slate-200">{(activeCorner.prob_over * 100).toFixed(1)}%</b></span>
                <span className="font-mono text-[10px] text-slate-300 bg-dark-800 px-1 py-0.5 rounded">
                  {selectedCornerLine === 9.5 && m.odds_corners_over95 ? m.odds_corners_over95.toFixed(2) : `@${activeCorner.fair_odds_over.toFixed(2)}`}
                </span>
                <span className="text-slate-400 text-[11px]">&lt;{selectedCornerLine}: <b className="text-slate-200">{(activeCorner.prob_under * 100).toFixed(1)}%</b></span>
                <span className="font-mono text-[10px] text-slate-300 bg-dark-800 px-1 py-0.5 rounded">
                  {selectedCornerLine === 9.5 && m.odds_corners_under95 ? m.odds_corners_under95.toFixed(2) : `@${activeCorner.fair_odds_under.toFixed(2)}`}
                </span>
              </div>
            </div>

            {/* Cards Sub-row */}
            <div className="space-y-1 pt-1 border-t border-dark-800/80">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400 font-medium">Cards</span>
                {/* Cards Line Selector Pills */}
                <div className="flex items-center space-x-0.5 bg-dark-950/60 p-0.5 rounded border border-dark-800">
                  {[2.5, 3.5, 4.5, 5.5].map((lVal) => {
                    const isPrimary = lVal === (m.primary_card_line ?? 3.5);
                    const isSelected = lVal === selectedCardLine;
                    return (
                      <button
                        key={lVal}
                        type="button"
                        onClick={() => setSelectedCardLine(lVal)}
                        className={`px-1.5 py-0.5 text-[9px] font-bold rounded transition-all ${
                          isSelected
                            ? 'bg-amber-500/25 text-amber-300 border border-amber-500/40'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                        }`}
                        title={isPrimary ? 'Primary Model Expectancy' : undefined}
                      >
                        {lVal}{isPrimary ? '★' : ''}
                      </button>
                    );
                  })}
                </div>
                <span className="font-mono text-slate-400 text-[10px]">λ={m.expected_cards?.toFixed(1) || '4.2'}</span>
              </div>
              <div className="flex justify-between items-center py-0.5 text-xs">
                <span className="text-slate-400 text-[11px]">&gt;{selectedCardLine}: <b className="text-slate-200">{(activeCard.prob_over * 100).toFixed(1)}%</b></span>
                <span className="font-mono text-[10px] text-slate-300 bg-dark-800 px-1 py-0.5 rounded">
                  {selectedCardLine === 3.5 && m.odds_cards_over35 ? m.odds_cards_over35.toFixed(2) : `@${activeCard.fair_odds_over.toFixed(2)}`}
                </span>
                <span className="text-slate-400 text-[11px]">&lt;{selectedCardLine}: <b className="text-slate-200">{(activeCard.prob_under * 100).toFixed(1)}%</b></span>
                <span className="font-mono text-[10px] text-slate-300 bg-dark-800 px-1 py-0.5 rounded">
                  {selectedCardLine === 3.5 && m.odds_cards_under35 ? m.odds_cards_under35.toFixed(2) : `@${activeCard.fair_odds_under.toFixed(2)}`}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Collapsible Tactical Key Drivers & Form Buttons */}
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
              <span>🧠 AI Pre-Bet Audit ({m.ai_audit.verdict} • {m.ai_audit.confidence_score}%)</span>
              {showAudit ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {m.drivers && m.drivers.length > 0 && (
            <button
              onClick={() => setShowDrivers(!showDrivers)}
              className="px-2.5 py-1 rounded bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white text-[11px] font-bold flex items-center space-x-1"
            >
              <span>⚡ Tactical Drivers ({m.drivers.length})</span>
              {showDrivers ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {m.h2h_matches && m.h2h_matches.length > 0 && (
            <button
              onClick={() => setShowH2H(!showH2H)}
              className="px-2.5 py-1 rounded bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white text-[11px] font-bold flex items-center space-x-1"
            >
              <span>⚔️ Head to Head ({m.h2h_matches.length})</span>
              {showH2H ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {((m.goal_lines && m.goal_lines.length > 0) || (m.corner_lines && m.corner_lines.length > 0)) && (
            <button
              onClick={() => setShowAllLines(!showAllLines)}
              className="px-2.5 py-1 rounded bg-dark-700/60 hover:bg-dark-700 text-slate-300 hover:text-white text-[11px] font-bold flex items-center space-x-1"
            >
              <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
              <span>📊 Multi-Line Matrix</span>
              {showAllLines ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}
        </div>

        {/* AI Pre-Bet Risk Audit Expandable Panel */}
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
                Confidence: <strong className="text-white font-bold">{m.ai_audit.confidence_score}%</strong>
              </div>
            </div>

            <p className="text-slate-200 text-xs leading-relaxed italic bg-dark-800/80 p-3 rounded-lg border border-dark-700/60">
              "{m.ai_audit.summary}"
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
              {/* Pros / Angles */}
              <div className="space-y-1.5">
                <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                  <span>✓</span> <span>Key Model Angles</span>
                </div>
                <ul className="space-y-1.5 text-slate-300">
                  {m.ai_audit.pros.map((p, idx) => (
                    <li key={idx} className="flex items-start space-x-2">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span className="text-[11px] leading-snug">{p}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Risks / Traps */}
              <div className="space-y-1.5">
                <div className="text-[11px] font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                  <span>⚠</span> <span>Qualitative Risk Traps</span>
                </div>
                <ul className="space-y-1.5 text-slate-300">
                  {m.ai_audit.risks.map((r, idx) => (
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

        {/* Tactical Drivers Expandable Panel */}
        {showDrivers && m.drivers && (
          <div className="p-3 bg-dark-900/80 rounded-lg border border-dark-700 text-xs space-y-1.5">
            <div className="font-bold text-slate-300 text-[11px] mb-1">Key Match Influencing Drivers:</div>
            {m.drivers.map((d, i) => (
              <div key={i} className="flex items-start space-x-2 text-slate-300">
                <span className="text-emerald-400 font-bold">•</span>
                <div>
                  <strong className="text-white">{d.factor}:</strong> {d.detail}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* H2H Expandable Panel */}
        {showH2H && m.h2h_matches && (
          <div className="p-3 bg-dark-900/80 rounded-lg border border-dark-700 text-xs space-y-1.5">
            <div className="font-bold text-slate-300 text-[11px] mb-1">Recent Head to Head Encounters:</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {m.h2h_matches.map((h, i) => (
                <div key={i} className="p-2 bg-dark-800 rounded border border-dark-700/60 flex justify-between items-center">
                  <span className="text-slate-400 font-mono text-[10px]">{h.date}</span>
                  <span className="font-semibold text-white text-xs">
                    {h.home_team} {h.score} {h.away_team}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Multi-Line Distribution Matrix Expandable Panel */}
        {showAllLines && (
          <div className="p-3 bg-dark-900/90 rounded-lg border border-dark-700 text-xs space-y-3">
            <div className="flex items-center justify-between pb-1 border-b border-dark-800">
              <span className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4 text-cyan-400" />
                Comprehensive Multi-Line Expectancy Matrix
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                Goals: λ={(m.expected_total_goals ?? (m.expected_goals_home + m.expected_goals_away)).toFixed(1)} • Corners: λ={m.expected_corners.toFixed(1)} • Cards: λ={m.expected_cards.toFixed(1)}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Goals Lines Table */}
              <div className="bg-dark-800/80 rounded-lg p-2.5 border border-dark-700/60">
                <div className="font-bold text-[11px] text-emerald-400 mb-1.5 flex items-center justify-between">
                  <span>⚽ Total Goals Lines</span>
                  <span className="text-[9px] text-slate-400 font-mono">Primary: {m.primary_goal_line ?? 2.5}</span>
                </div>
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="text-slate-400 border-b border-dark-700">
                      <th className="py-1 text-left">Line</th>
                      <th className="py-1 text-right">Over</th>
                      <th className="py-1 text-right">Under</th>
                      <th className="py-1 text-right">Fair O/U</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-700/40">
                    {(m.goal_lines || []).map((gl) => (
                      <tr key={gl.line} className={gl.is_primary ? 'bg-emerald-500/10 font-bold' : ''}>
                        <td className="py-1 text-white font-mono">
                          {gl.line} {gl.is_primary ? '★' : ''}
                        </td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(gl.prob_over * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(gl.prob_under * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-400 font-mono">
                          {gl.fair_odds_over.toFixed(2)} / {gl.fair_odds_under.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Corners Lines Table */}
              <div className="bg-dark-800/80 rounded-lg p-2.5 border border-dark-700/60">
                <div className="font-bold text-[11px] text-amber-400 mb-1.5 flex items-center justify-between">
                  <span>🚩 Corner Lines</span>
                  <span className="text-[9px] text-slate-400 font-mono">Primary: {m.primary_corner_line ?? 9.5}</span>
                </div>
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="text-slate-400 border-b border-dark-700">
                      <th className="py-1 text-left">Line</th>
                      <th className="py-1 text-right">Over</th>
                      <th className="py-1 text-right">Under</th>
                      <th className="py-1 text-right">Fair O/U</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-700/40">
                    {(m.corner_lines || []).map((cl) => (
                      <tr key={cl.line} className={cl.is_primary ? 'bg-amber-500/10 font-bold' : ''}>
                        <td className="py-1 text-white font-mono">
                          {cl.line} {cl.is_primary ? '★' : ''}
                        </td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(cl.prob_over * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(cl.prob_under * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-400 font-mono">
                          {cl.fair_odds_over.toFixed(2)} / {cl.fair_odds_under.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Cards Lines Table */}
              <div className="bg-dark-800/80 rounded-lg p-2.5 border border-dark-700/60">
                <div className="font-bold text-[11px] text-amber-300 mb-1.5 flex items-center justify-between">
                  <span>🟨 Cards Lines</span>
                  <span className="text-[9px] text-slate-400 font-mono">Primary: {m.primary_card_line ?? 3.5}</span>
                </div>
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="text-slate-400 border-b border-dark-700">
                      <th className="py-1 text-left">Line</th>
                      <th className="py-1 text-right">Over</th>
                      <th className="py-1 text-right">Under</th>
                      <th className="py-1 text-right">Fair O/U</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-700/40">
                    {(m.card_lines || []).map((kdl) => (
                      <tr key={kdl.line} className={kdl.is_primary ? 'bg-amber-500/10 font-bold' : ''}>
                        <td className="py-1 text-white font-mono">
                          {kdl.line} {kdl.is_primary ? '★' : ''}
                        </td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(kdl.prob_over * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-200 font-mono">{(kdl.prob_under * 100).toFixed(1)}%</td>
                        <td className="py-1 text-right text-slate-400 font-mono">
                          {kdl.fair_odds_over.toFixed(2)} / {kdl.fair_odds_under.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
