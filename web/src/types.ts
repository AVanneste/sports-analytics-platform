export interface TacticalDriver {
  factor: string;
  detail: string;
  direction: 'positive' | 'negative' | 'neutral';
}

export interface RefereeInfo {
  name: string;
  strictness_label: string;
  avg_cards?: number;
}

export interface TeamStats {
  form?: string[];
  elo?: number;
  attack?: number;
  defense?: number;
  avg_gf_season?: number;
  avg_ga_season?: number;
  clean_sheet_pct?: number;
  btts_pct?: number;
  o25_pct?: number;
  avg_corners?: number;
  avg_cards?: number;
}

export interface RecentMatch {
  date: string;
  venue: string;
  opponent: string;
  score: string;
  res: string;
  corners?: number;
  cards?: number;
}

export interface H2HMatch {
  date: string;
  home_team: string;
  away_team: string;
  score: string;
  winner: string;
}

export interface TopPickItem {
  match: string;
  date: string;
  league: string;
  circuit?: string;
  market: string;
  selection: string;
  prob: number;
  fair_odds: number;
  bookmaker_odds?: any;
  ev?: number;
}

export interface AIAudit {
  verdict: 'GO' | 'CAUTION' | 'NO-GO';
  confidence_score: number;
  summary: string;
  pros: string[];
  risks: string[];
  tactical_angle?: string;
  source?: string;
}

export interface LeakItem {
  cohort: string;
  dimension: string;
  count: number;
  wins: number;
  win_rate_pct: number;
  total_staked: number;
  net_pnl: number;
  roi_pct: number;
  leak_severity: 'HIGH_LEAK' | 'MODERATE_LEAK' | 'HIGH_PROFIT' | 'NEUTRAL';
}

export interface LossBreakdown {
  variance_losses: number;
  structural_losses: number;
  variance_ratio_pct: number;
}

export interface LedgerDiagnostics {
  total_audited: number;
  wins_count: number;
  losses_count: number;
  loss_breakdown: LossBreakdown;
  active_leaks_count: number;
  active_leaks: LeakItem[];
  top_performers: LeakItem[];
  cohorts: {
    by_odds: LeakItem[];
    by_league: LeakItem[];
    by_market: LeakItem[];
    by_venue: LeakItem[];
  };
  recommendations: string[];
}

export interface BestPick {
  market: string;
  selection: string;
  odds: number;
  prob: number;
  ev: number;
  kelly: number;
}

export interface MarketLineItem {
  line: number;
  prob_over: number;
  prob_under: number;
  fair_odds_over: number;
  fair_odds_under: number;
  odds_over?: number;
  odds_under?: number;
  is_primary?: boolean;
}

export interface FootballMatch {
  match_id: string;
  league: string;
  league_name: string;
  flag: string;
  date: string;
  commence_time?: string;
  home_team: string;
  away_team: string;

  home_elo: number;
  away_elo: number;
  expected_goals_home: number;
  expected_goals_away: number;
  expected_total_goals?: number;
  most_likely_score: string;
  most_likely_score_prob: number;

  primary_goal_line?: number;
  primary_corner_line?: number;
  primary_card_line?: number;
  goal_lines?: MarketLineItem[];
  corner_lines?: MarketLineItem[];
  card_lines?: MarketLineItem[];

  prob_home: number;
  prob_draw: number;
  prob_away: number;
  fair_odds_home: number;
  fair_odds_draw: number;
  fair_odds_away: number;
  odds_home?: number;
  odds_draw?: number;
  odds_away?: number;

  prob_over25: number;
  prob_under25: number;
  fair_odds_over25: number;
  fair_odds_under25: number;
  odds_over25?: number;
  odds_under25?: number;
  prob_btts_yes: number;
  prob_btts_no: number;
  fair_odds_btts_yes: number;
  fair_odds_btts_no: number;
  odds_btts_yes?: number;
  odds_btts_no?: number;

  expected_corners: number;
  prob_corners_over95: number;
  prob_corners_under95: number;
  fair_odds_corners_over95: number;
  fair_odds_corners_under95: number;
  odds_corners_over95?: number;
  odds_corners_under95?: number;

  expected_cards: number;
  prob_cards_over35: number;
  prob_cards_under35: number;
  fair_odds_cards_over35: number;
  fair_odds_cards_under35: number;
  odds_cards_over35?: number;
  odds_cards_under35?: number;

  referee?: RefereeInfo;
  best_pick?: BestPick;
  has_value?: boolean;
  highest_prob_selection?: string;

  drivers?: TacticalDriver[];
  home_stats?: TeamStats;
  away_stats?: TeamStats;
  recent_matches_home?: RecentMatch[];
  recent_matches_away?: RecentMatch[];
  h2h_matches?: H2HMatch[];
  ai_audit?: AIAudit | null;
}

export interface FootballTrackerEntry {
  match_id: string;
  date: string;
  league: string;
  home_team: string;
  away_team: string;
  status: 'settled' | 'pending';
  status_label?: string;
  is_future?: boolean;

  actual_score?: string;
  actual_winner?: string;
  actual_goals?: number;
  actual_btts?: string;
  actual_corners?: number;
  actual_cards?: number;

  correct_1x2?: boolean;
  correct_over25?: boolean;
  correct_btts?: boolean;
  correct_corners_o95?: boolean;
  correct_cards_o35?: boolean;
  correct_score?: boolean;

  goal_error?: number;
  corner_error?: number;
  card_error?: number;

  prob_home?: number;
  prob_draw?: number;
  prob_away?: number;
  prob_over25?: number;
  prob_under25?: number;
  prob_btts_yes?: number;
  prob_btts_no?: number;
  prob_corners_over95?: number;
  prob_cards_over35?: number;

  pred_1x2?: string;
  pred_over25?: string;
  pred_btts?: string;
  pred_corners_o95?: string;
  pred_cards_o35?: string;
  pred_score?: string;

  expected_goals_home?: number;
  expected_goals_away?: number;
  exp_goals_home?: number;
  exp_goals_away?: number;
  exp_total_goals?: number;
  expected_corners?: number;
  exp_corners?: number;
  expected_cards?: number;
  exp_cards?: number;
  referee?: string;

  won?: boolean;
  flat_pnl?: number;
  kelly_pnl?: number;
  best_pick?: BestPick;
  has_value?: boolean;
  stake?: number;
  market_category?: string;
  odds_home?: number;
  odds_draw?: number;
  odds_away?: number;
}

export interface TennisMatchLog {
  date: string;
  won: boolean;
  result: 'W' | 'L';
  opponent: string;
  tourney: string;
  surface: string;
  score: string;
  sets: string;
  games: string;
}

export interface TennisMatch {
  match_id: string;
  circuit: 'ATP' | 'WTA';
  tourney_name: string;
  surface: string;
  date: string;
  round?: string;
  best_of: number;
  p1_name: string;
  p2_name: string;

  p1_prob: number;
  p2_prob: number;
  predicted_winner: string;
  confidence: number;
  has_value?: boolean;
  has_odds?: boolean;
  best_ev?: number;

  betting?: {
    recommended_pick?: string;
    best_ev?: number;
    best_edge?: number;
    best_stake?: number;
    best_odds?: number;
    p1_odds?: number;
    p2_odds?: number;
    fair_model_odds_p1?: number;
    fair_model_odds_p2?: number;
    has_odds?: boolean;
    has_value?: boolean;
    bookmaker_vig_pct?: number;
    p1_kelly_pct?: number;
    p2_kelly_pct?: number;
  };

  context?: {
    p1_name?: string;
    p2_name?: string;
    surface?: string;
    p1_has_history?: boolean;
    p2_has_history?: boolean;
    p1_provisional?: boolean;
    p2_provisional?: boolean;
    p1_match_count?: number;
    p2_match_count?: number;
    p1_rank?: number | null;
    p2_rank?: number | null;
    p1_career_high?: number | null;
    p2_career_high?: number | null;
    p1_age?: number | null;
    p2_age?: number | null;
    p1_elo?: number | null;
    p2_elo?: number | null;
    p1_surface_elo?: number | null;
    p2_surface_elo?: number | null;
    p1_eff_surface_elo?: number | null;
    p2_eff_surface_elo?: number | null;
    p1_form_5?: number | null;
    p2_form_5?: number | null;
    p1_surface_form?: number | null;
    p2_surface_form?: number | null;
    p1_sets_win_rate?: number | null;
    p2_sets_win_rate?: number | null;
    p1_games_win_rate?: number | null;
    p2_games_win_rate?: number | null;
    p1_dominance_ratio?: number | null;
    p2_dominance_ratio?: number | null;
    p1_deciding_set_win_rate?: number | null;
    p2_deciding_set_win_rate?: number | null;
    p1_tiebreak_win_rate?: number | null;
    p2_tiebreak_win_rate?: number | null;
    p1_hold_pct?: number | null;
    p2_hold_pct?: number | null;
    p1_break_pct?: number | null;
    p2_break_pct?: number | null;
    p1_surface_hold_pct?: number | null;
    p2_surface_hold_pct?: number | null;
    p1_surface_break_pct?: number | null;
    p2_surface_break_pct?: number | null;
    projected_p1_hold_rate?: number;
    projected_p1_break_rate?: number;
    projected_p2_hold_rate?: number;
    projected_p2_break_rate?: number;
    h2h_p1_wins?: number;
    h2h_p2_wins?: number;
    h2h_p1_sets?: number;
    h2h_p2_sets?: number;
    h2h_p1_games?: number;
    h2h_p2_games?: number;
    h2h_total?: number;
    h2h_surf_p1_wins?: number;
    p1_recent_matches?: TennisMatchLog[];
    p2_recent_matches?: TennisMatchLog[];
    p1_ace_rate?: number | null;
    p2_ace_rate?: number | null;
    p1_df_rate?: number | null;
    p2_df_rate?: number | null;
    p1_first_serve_pct?: number | null;
    p2_first_serve_pct?: number | null;
    p1_first_serve_won_pct?: number | null;
    p2_first_serve_won_pct?: number | null;
    p1_bp_save_pct?: number | null;
    p2_bp_save_pct?: number | null;
    p1_bp_conversion_pct?: number | null;
    p2_bp_conversion_pct?: number | null;
    p1_return_points_won_pct?: number | null;
    p2_return_points_won_pct?: number | null;
  };

  sets_games?: {
    expected_total_games: number;
    main_games_line?: {
      line: number;
      prob_over: number;
      prob_under: number;
      fair_odds_over: number;
      fair_odds_under: number;
    };
    primary_games_line?: number;
    games_lines?: {
      line: number;
      prob_over: number;
      prob_under: number;
      fair_odds_over: number;
      fair_odds_under: number;
      is_primary?: boolean;
    }[];
    p1_win_at_least_1_set_prob: number;
    p2_win_at_least_1_set_prob: number;
    p1_win_at_least_1_set_odds: number;
    p2_win_at_least_1_set_odds: number;
    prob_deciding_set: number;
    fair_odds_deciding_set: number;
    scoreline_probabilities?: Record<string, number>;
    games_market_table?: any[];
  };
  ai_audit?: AIAudit | null;
}

export interface TennisTrackerMetrics {
  acc_winner: number;
  acc_sets_line: number;
  acc_games_ou: number;
  acc_decider: number;
  avg_game_error: number;
  total_graded: number;
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
  status: 'WON' | 'LOST' | 'PENDING' | 'VOID' | 'CANCELLED';
  actual_winner?: string;
  score?: string;
  pnl?: number;
  flat_pnl?: number;
  recommended_pick?: string;
  best_odds?: number;
  best_ev?: number;
  best_edge?: number;
  best_stake?: number;
  stake?: number;
  is_value_bet?: boolean;
  model_correct?: boolean;
  predicted_winner?: string;
  confidence?: number;
  actual_games?: number;
  exp_total_games?: number;
  game_error?: number;
  correct_winner?: boolean;
  correct_sets_at_least_1?: boolean;
  correct_games_ou?: boolean;
  correct_deciding_set?: boolean;
  games_line?: number;
  sets_games?: any;
}

export interface FootballTrackerMetrics {
  total_settled: number;
  acc_1x2: number;
  acc_o25: number;
  acc_btts: number;
  acc_corners: number;
  acc_cards: number;
  exact_score_hits: number;
  avg_goal_error: number;
}

export interface RootData {
  timestamp: string;
  generated_at_unix: number;
  summary: {
    overall_status: string;
    last_pipeline_run: string;
    football: {
      settled_count: number;
      pending_count: number;
      future_count?: number;
      upcoming_count: number;
      value_bets_count?: number;
      win_rate_pct: number;
      flat_pnl: number;
      kelly_pnl: number;
      total_staked?: number;
      roi_pct?: number;
      value_bets?: {
        settled_count: number;
        wins: number;
        losses: number;
        win_rate_pct: number;
        flat_pnl: number;
        total_staked: number;
        roi_pct: number;
        avg_odds?: number;
        avg_ev_pct: number;
        expected_pnl: number;
      };
      metrics?: FootballTrackerMetrics;
    };
    tennis: {
      settled_count: number;
      pending_count: number;
      upcoming_count: number;
      value_bets_count?: number;
      win_rate_pct: number;
      total_pnl: number;
      total_staked?: number;
      roi_pct?: number;
      atp_accuracy?: number;
      atp_auc?: number;
      wta_accuracy?: number;
      wta_auc?: number;
      metrics?: TennisTrackerMetrics;
      value_bets?: {
        settled_count: number;
        wins: number;
        losses: number;
        win_rate_pct: number;
        total_pnl: number;
        total_staked: number;
        roi_pct: number;
      };
    };
  };
  football: {
    upcoming: FootballMatch[];
    top_picks: TopPickItem[];
    tracker: FootballTrackerEntry[];
    metrics: FootballTrackerMetrics;
    diagnostics?: LedgerDiagnostics;
    value_diagnostics?: LedgerDiagnostics;
  };
  tennis: {
    upcoming: TennisMatch[];
    top_picks: TopPickItem[];
    tracker: TennisTrackerEntry[];
    metrics: Record<string, any>;
    diagnostics?: LedgerDiagnostics;
  };
}
