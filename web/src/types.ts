export interface SportSummary {
  settled_count: number;
  pending_count: number;
  upcoming_count: number;
  win_rate_pct: number;
  flat_pnl?: number;
  kelly_pnl?: number;
  total_pnl?: number;
  atp_accuracy?: number;
  atp_auc?: number;
  wta_accuracy?: number;
  wta_auc?: number;
  value_bets_count: number;
}

export interface RootData {
  timestamp: string;
  generated_at_unix: number;
  summary: {
    overall_status: string;
    last_pipeline_run: string;
    football: SportSummary;
    tennis: SportSummary;
  };
  football: {
    upcoming: FootballMatch[];
    tracker: FootballTrackerEntry[];
    value_bets: FootballMatch[];
  };
  tennis: {
    upcoming: TennisMatch[];
    tracker: TennisTrackerEntry[];
    metrics: Record<string, any>;
    value_bets: TennisMatch[];
  };
}

export interface FootballMatch {
  match_id: string;
  league_name: string;
  league_key: string;
  flag: string;
  date: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  odds_home?: number;
  odds_draw?: number;
  odds_away?: number;
  odds_over25?: number;
  odds_under25?: number;
  odds_btts_yes?: number;
  prob_home?: number;
  prob_draw?: number;
  prob_away?: number;
  prob_over25?: number;
  prob_under25?: number;
  prob_btts_yes?: number;
  prob_corners_over95?: number;
  prob_cards_over35?: number;
  expected_corners?: number;
  expected_cards?: number;
  most_likely_score?: string;
  has_value?: boolean;
  best_pick?: {
    market: string;
    selection: string;
    odds: number;
    prob: number;
    ev: number;
    kelly: number;
  };
}

export interface FootballTrackerEntry {
  match_id: string;
  date: string;
  league: string;
  league_name: string;
  home_team: string;
  away_team: string;
  status: 'settled' | 'pending';
  actual_score?: string;
  actual_winner?: string;
  won?: boolean;
  flat_pnl?: number;
  kelly_pnl?: number;
  prob_home: number;
  prob_draw: number;
  prob_away: number;
  pred_1x2?: string;
  pred_score?: string;
  best_pick?: Record<string, any>;
}

export interface TennisMatch {
  match_id: string;
  circuit: 'ATP' | 'WTA';
  tourney_name: string;
  surface: string;
  date: string;
  p1_name: string;
  p2_name: string;
  p1_odds?: number;
  p2_odds?: number;
  p1_prob?: number;
  p2_prob?: number;
  predicted_winner?: string;
  confidence?: number;
  has_value?: boolean;
  best_ev?: number;
  best_edge?: number;
  best_stake?: number;
  best_odds?: number;
  recommended_pick?: string;
}

export interface TennisTrackerEntry {
  match_id: string;
  date: string;
  circuit: string;
  tourney_name: string;
  surface: string;
  p1_name: string;
  p2_name: string;
  p1_prob: number;
  p2_prob: number;
  status: 'WON' | 'LOST' | 'PENDING' | 'CANCELLED';
  actual_winner?: string;
  score?: string;
  pnl?: number;
  recommended_pick?: string;
}
