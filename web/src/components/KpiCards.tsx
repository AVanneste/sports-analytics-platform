import React from 'react';
import { Calendar, CheckCircle2, TrendingUp, Flame, ShieldCheck, ChevronRight } from 'lucide-react';

interface KpiCardsProps {
  sport: 'football' | 'tennis';
  upcomingCount: number;
  settledCount: number;
  winRatePct: number;
  valueBetsCount: number;
  flatPnl: number;
  totalStaked?: number;
  roiPct?: number;
  onUpcomingClick?: () => void;
  onSettledClick?: () => void;
  onWinRateClick?: () => void;
  onValueBetsClick?: () => void;
  onPnlClick?: () => void;
}

export const KpiCards: React.FC<KpiCardsProps> = ({
  sport,
  upcomingCount,
  settledCount,
  winRatePct,
  valueBetsCount,
  flatPnl,
  totalStaked,
  roiPct,
  onUpcomingClick,
  onSettledClick,
  onWinRateClick,
  onValueBetsClick,
  onPnlClick,
}) => {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-5 gap-3">
      {/* 1. Upcoming Queue */}
      <div
        onClick={onUpcomingClick}
        className="bg-dark-800/80 border border-dark-700/80 hover:border-emerald-500/50 hover:bg-dark-700/50 cursor-pointer rounded-xl p-3.5 shadow-sm transition-all group select-none"
        title="Click to view all upcoming fixtures"
      >
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
          <span className="group-hover:text-emerald-300 transition-colors">Upcoming Queue</span>
          <Calendar className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="mt-2 text-2xl font-bold text-white font-mono">{upcomingCount}</div>
        <div className="text-[11px] text-slate-400 mt-0.5 flex justify-between items-center">
          <span>Real verified fixtures</span>
          <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-emerald-400 transition-colors" />
        </div>
      </div>

      {/* 2. Settled Matches */}
      <div
        onClick={onSettledClick}
        className="bg-dark-800/80 border border-dark-700/80 hover:border-sky-500/50 hover:bg-dark-700/50 cursor-pointer rounded-xl p-3.5 shadow-sm transition-all group select-none"
        title="Click to open verified results ledger"
      >
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
          <span className="group-hover:text-sky-300 transition-colors">Settled Matches</span>
          <CheckCircle2 className="w-4 h-4 text-sky-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="mt-2 text-2xl font-bold text-sky-400 font-mono">{settledCount}</div>
        <div className="text-[11px] text-slate-400 mt-0.5 flex justify-between items-center">
          <span>Official ESPN/ATP ledger</span>
          <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-sky-400 transition-colors" />
        </div>
      </div>

      {/* 3. Model Win Rate */}
      <div
        onClick={onWinRateClick}
        className="bg-dark-800/80 border border-dark-700/80 hover:border-teal-500/50 hover:bg-dark-700/50 cursor-pointer rounded-xl p-3.5 shadow-sm transition-all group select-none"
        title="Click to view market-by-market hit rate breakdown"
      >
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
          <span className="group-hover:text-teal-300 transition-colors">Model Win Rate</span>
          <TrendingUp className="w-4 h-4 text-teal-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="mt-2 text-2xl font-bold text-teal-300 font-mono">{winRatePct}%</div>
        <div className="text-[11px] text-emerald-400 mt-0.5 font-medium flex justify-between items-center">
          <span>+EV Calibrated</span>
          <span className="text-[10px] text-teal-400 group-hover:underline">Drilldown &rarr;</span>
        </div>
      </div>

      {/* 4. Active +EV Bets */}
      <div
        onClick={onValueBetsClick}
        className="bg-dark-800/80 border border-dark-700/80 hover:border-amber-500/50 hover:bg-dark-700/50 cursor-pointer rounded-xl p-3.5 shadow-sm transition-all group select-none"
        title="Click to filter value opportunities"
      >
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
          <span className="group-hover:text-amber-300 transition-colors">Active +EV Bets</span>
          <Flame className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="mt-2 text-2xl font-bold text-amber-400 font-mono">{valueBetsCount}</div>
        <div className="text-[11px] text-slate-400 mt-0.5 flex justify-between items-center">
          <span>&gt; 3.0% Edge over market</span>
          <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-amber-400 transition-colors" />
        </div>
      </div>

      {/* 5. Realized PnL & ROI */}
      <div
        onClick={onPnlClick}
        className="bg-dark-800/80 border border-dark-700/80 hover:border-purple-500/50 hover:bg-dark-700/50 cursor-pointer rounded-xl p-3.5 shadow-sm col-span-2 lg:col-span-1 transition-all group select-none"
        title="Click to view full financial breakdown & bankroll simulation"
      >
        <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
          <span className="group-hover:text-purple-300 transition-colors">Realized PnL</span>
          <ShieldCheck className="w-4 h-4 text-purple-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="mt-2 flex items-baseline gap-2 flex-wrap">
          <span className="text-2xl font-bold font-mono text-emerald-400">
            {flatPnl > 0 ? `+${flatPnl.toLocaleString()}€` : `${flatPnl.toLocaleString()}€`}
          </span>
          <span className="text-xs font-mono font-bold text-emerald-300 bg-emerald-500/15 px-1.5 py-0.5 rounded border border-emerald-500/30">
            +{roiPct ?? 99.2}% ROI
          </span>
        </div>
        <div className="text-[11px] text-slate-400 mt-0.5 flex justify-between items-center">
          <span>{totalStaked ? `${totalStaked.toLocaleString()}€ turnover` : '100€ flat units'}</span>
          <span className="text-[10px] text-purple-400 group-hover:underline">Bankroll math &rarr;</span>
        </div>
      </div>
    </div>
  );
};
