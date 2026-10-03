import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { BetSummary, MarketComparison, TrackRecord } from '../types';

interface Props {
  trackRecord?: TrackRecord | null;
  sport: 'football' | 'tennis';
}

const fmtPct = (v?: number | null, digits = 1) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`;

function qualityLine(cmp?: MarketComparison): string {
  if (!cmp || !cmp.n || cmp.model_log_loss === undefined || cmp.market_log_loss === undefined) {
    return 'Not enough settled matches with bookmaker prices yet to compare the model with the market.';
  }
  const verdict = (cmp.log_loss_skill ?? 0) < 0 ? 'better than' : 'worse than';
  return `Live probability quality over ${cmp.n} priced matches: model log loss ${cmp.model_log_loss.toFixed(3)} vs market ${cmp.market_log_loss.toFixed(3)} (${verdict} the market).`;
}

function betsLine(bets?: BetSummary): string {
  if (!bets || !bets.n) return 'No settled model-edge bets yet.';
  return `${bets.n} settled model-edge bets: ROI ${fmtPct(bets.roi_pct)} while the model claimed ${fmtPct(bets.claimed_ev_pct)} EV.`;
}

/** Honest summary shown above the picks: realised results next to what the model claimed. */
export default function TrackRecordBanner({ trackRecord, sport }: Props) {
  if (!trackRecord) return null;
  const ledger = sport === 'football' ? trackRecord.football?.ledger : trackRecord.tennis?.ledger;
  if (!ledger) return null;
  const quality = sport === 'football'
    ? (trackRecord.football.ledger.match_odds_1x2)
    : (trackRecord.tennis.ledger.match_winner);
  const clv = ledger.clv?.ev_at_close;
  const losing = (ledger.bets?.roi_pct ?? 0) < 0;

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-slate-300 space-y-1">
      <div className="flex items-center gap-2 font-bold text-amber-300">
        <AlertTriangle className="w-4 h-4" />
        <span>Track record — picks are model views, not proven value</span>
      </div>
      <div className={losing ? 'text-rose-300' : 'text-slate-300'}>{betsLine(ledger.bets)}</div>
      <div>{qualityLine(quality)}</div>
      {clv && clv.n > 0 && (
        <div>
          Closing-line value: {fmtPct(clv.mean_pct, 2)} on average over {clv.n} picks ({clv.share_positive_pct?.toFixed(0)}% beat the later price).
        </div>
      )}
      <div className="text-slate-500">
        Probabilities are shrunk toward the bookmaker&apos;s vig-free price; an edge only counts once the
        track record shows it.
      </div>
    </div>
  );
}
