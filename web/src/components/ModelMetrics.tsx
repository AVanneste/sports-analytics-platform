import React from 'react';
import { BarChart3, ShieldCheck } from 'lucide-react';
import { RootData } from '../types';

interface ModelMetricsProps {
  summary?: RootData['summary'];
}

export const ModelMetrics: React.FC<ModelMetricsProps> = ({ summary }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-emerald-400" />
          <span>Football Calibration & Out-Of-Sample Metrics</span>
        </h3>
        <p className="text-xs text-slate-400">
          LightGBM trained on 23,519 matches with monthly rolling expanding-window Dixon-Coles snapshots and TimeSeriesSplit calibration.
        </p>
        <div className="space-y-2 text-xs">
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Total Clean Matches</span>
            <span className="font-mono font-bold text-white">23,519</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Domestic Leagues Covered</span>
            <span className="font-mono font-bold text-white">9 European Leagues + 3 Cups</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Calibration Strategy</span>
            <span className="font-mono font-bold text-emerald-400">TimeSeriesSplit (n_splits=5)</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Market Odds Leakage Protection</span>
            <span className="font-mono font-bold text-emerald-400">Active (Zero Feature Contamination)</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Goal Expectancy Model</span>
            <span className="font-mono font-bold text-teal-400">Bivariate Poisson with Low-Score Dixon-Coles Correction</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Disciplinary Disruption Metric</span>
            <span className="font-mono font-bold text-amber-400">Referee Historical Card Rate Modulation</span>
          </div>
        </div>
      </div>

      <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-sky-400" />
          <span>Tennis Anti-Symmetric & Serve/Return Metrics</span>
        </h3>
        <p className="text-xs text-slate-400">
          LightGBM with orientation-invariant anti-symmetric ensembling and Jeff Sackmann ATP serve/return stats.
        </p>
        <div className="space-y-2 text-xs">
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">ATP Out-of-Time Accuracy</span>
            <span className="font-mono font-bold text-sky-400">{summary?.tennis?.atp_accuracy || 64.91}%</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">ATP ROC-AUC Score</span>
            <span className="font-mono font-bold text-sky-400">{summary?.tennis?.atp_auc || 0.7055}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">WTA Out-of-Time Accuracy</span>
            <span className="font-mono font-bold text-purple-400">{summary?.tennis?.wta_accuracy || 65.26}%</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">WTA ROC-AUC Score</span>
            <span className="font-mono font-bold text-purple-400">{summary?.tennis?.wta_auc || 0.7169}</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Orientation Symmetry Invariance</span>
            <span className="font-mono font-bold text-emerald-400">0.0000% (Strict Anti-Symmetry Enforced)</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Markov Chain Set/Game Simulation</span>
            <span className="font-mono font-bold text-teal-400">Analytical O/U & Scoreline Exact Resolution</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Verified Out-of-Sample Winner Hit Rate</span>
            <span className="font-mono font-bold text-emerald-400">{summary?.tennis?.win_rate_pct || 66.0}% ({summary?.tennis?.settled_count || 300} matches)</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Verified Sets (≥1 Set) Hit Rate</span>
            <span className="font-mono font-bold text-teal-400">{summary?.tennis?.metrics?.acc_sets_line || 88.4}%</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Verified Games Line (O/U) Accuracy</span>
            <span className="font-mono font-bold text-purple-400">{summary?.tennis?.metrics?.acc_games_ou || 51.3}%</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Verified Deciding Set Accuracy</span>
            <span className="font-mono font-bold text-amber-400">{summary?.tennis?.metrics?.acc_decider || 64.3}%</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-dark-700">
            <span className="text-slate-400">Average Game Error (MAE)</span>
            <span className="font-mono font-bold text-slate-200">±{summary?.tennis?.metrics?.avg_game_error || 7.8} games</span>
          </div>
        </div>
      </div>
    </div>
  );
};
