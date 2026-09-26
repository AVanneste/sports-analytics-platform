import React, { useState } from 'react';
import { Flame, ChevronDown, ChevronUp } from 'lucide-react';
import { TopPickItem } from '../types';

interface TopPicksTableProps {
  picks: TopPickItem[];
  sport: 'football' | 'tennis';
}

export const TopPicksTable: React.FC<TopPicksTableProps> = ({ picks, sport }) => {
  const [isOpen, setIsOpen] = useState(true);
  const [selectedMarket, setSelectedMarket] = useState<string>('All');

  if (!picks || picks.length === 0) return null;

  // Filter out any past games (< today) to guarantee active upcoming fixtures only
  const todayStr = new Date().toISOString().slice(0, 10);
  const activePicks = picks.filter((p) => {
    if (!p.date || p.date === '-' || p.date === 'Today' || p.date === 'Upcoming') return true;
    return p.date.slice(0, 10) >= todayStr;
  });

  if (activePicks.length === 0) return null;

  const availableMarkets = ['All', ...Array.from(new Set(activePicks.map((p) => p.market).filter(Boolean)))];
  const displayedPicks = selectedMarket === 'All'
    ? activePicks
    : activePicks.filter((p) => p.market === selectedMarket);

  return (
    <div className="bg-gradient-to-r from-dark-800 via-dark-800/90 to-dark-800 border border-dark-700 rounded-xl overflow-hidden shadow-sm">
      <div
        className="px-4 py-3 bg-dark-700/40 border-b border-dark-700 flex items-center justify-between cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center space-x-2">
          <Flame className="w-4 h-4 text-amber-400" />
          <span className="font-bold text-xs text-white">
            ⭐ Highest Probability Confidence Picks Across All Markets
          </span>
          <span className="text-[11px] text-slate-400">({displayedPicks.length} picks)</span>
        </div>
        <button className="text-slate-400 hover:text-white text-xs flex items-center space-x-1 font-semibold">
          <span>{isOpen ? 'Hide Table' : 'Show Table'}</span>
          {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {isOpen && (
        <>
          {availableMarkets.length > 2 && (
            <div className="flex items-center space-x-1.5 px-4 py-2 bg-dark-900/60 border-b border-dark-700/60 overflow-x-auto text-xs">
              <span className="text-[11px] font-bold text-slate-400 mr-1">Market:</span>
              {availableMarkets.map((mkt) => {
                const isSelected = selectedMarket === mkt;
                return (
                  <button
                    key={mkt}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedMarket(mkt);
                    }}
                    className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold transition-all ${
                      isSelected
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-xs'
                        : 'text-slate-400 hover:text-white bg-dark-800 border border-dark-700'
                    }`}
                  >
                    {mkt === 'Goals' ? '⚽ Goals' : mkt === 'Corners' ? '🚩 Corners' : mkt === 'Cards' ? '🟨 Cards' : mkt === 'BTTS' ? '🥅 BTTS' : mkt}
                  </button>
                );
              })}
            </div>
          )}

          <div className="overflow-x-auto max-h-72 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-dark-700 z-10">
                <tr>
                  <th className="px-4 py-2.5">Date</th>
                  <th className="px-4 py-2.5">Competition</th>
                  <th className="px-4 py-2.5">Match</th>
                  <th className="px-4 py-2.5">Market</th>
                  <th className="px-4 py-2.5">Model Selection</th>
                  <th className="px-4 py-2.5 text-right">Probability</th>
                  <th className="px-4 py-2.5 text-right">Fair Odds</th>
                  <th className="px-4 py-2.5 text-right">Consensus Odds</th>
                  <th className="px-4 py-2.5 text-right">EV (%)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-700/60 font-medium">
                {displayedPicks.slice(0, 25).map((p, idx) => {
                  const probDisplay = p.prob > 1 ? p.prob : p.prob * 100;
                  // Guard against double multiplication: if p.ev is already in percent (> 1.0), use it directly
                  const evDisplay = typeof p.ev === 'number' ? (Math.abs(p.ev) > 1.0 ? p.ev : p.ev * 100) : null;

                return (
                  <tr key={idx} className="hover:bg-dark-700/30 transition-colors">
                    <td className="px-4 py-2 text-slate-400 font-mono text-[11px]">{p.date}</td>
                    <td className="px-4 py-2 text-slate-300">{p.league || p.circuit || '-'}</td>
                    <td className="px-4 py-2 font-semibold text-white">{p.match}</td>
                    <td className="px-4 py-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-dark-900 text-slate-300 border border-dark-700">
                        {p.market}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-bold text-emerald-400">{p.selection}</td>
                    <td className="px-4 py-2 text-right font-mono font-bold text-white">
                      {(probDisplay || 0).toFixed(1)}%
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{p.fair_odds?.toFixed(2) || '-'}</td>
                    <td className="px-4 py-2 text-right font-mono font-semibold text-slate-200">
                      {typeof p.bookmaker_odds === 'number' ? `@${p.bookmaker_odds.toFixed(2)}` : (p.bookmaker_odds || '-')}
                    </td>
                    <td className="px-4 py-2 text-right font-mono font-bold">
                      {evDisplay !== null ? (
                        <span className={evDisplay > 0 ? 'text-emerald-400' : 'text-slate-400'}>
                          {evDisplay > 0 ? `+${evDisplay.toFixed(1)}%` : `${evDisplay.toFixed(1)}%`}
                        </span>
                      ) : (
                        <span className="text-slate-500">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </>
      )}
    </div>
  );
};
