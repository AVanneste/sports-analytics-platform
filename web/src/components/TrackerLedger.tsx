import React, { useState, useMemo, useEffect } from 'react';
import { Filter, AlertTriangle, TrendingDown, TrendingUp, ShieldCheck, CheckCircle2, Layers, HelpCircle, ShieldAlert, Zap } from 'lucide-react';
import { FootballTrackerEntry, TennisTrackerEntry, LedgerDiagnostics, LeakItem } from '../types';
import { CalendarDateRangePicker } from './CalendarDateRangePicker';

interface TrackerLedgerProps {
  sport: 'football' | 'tennis';
  footballEntries: FootballTrackerEntry[];
  tennisEntries: TennisTrackerEntry[];
  leagues: { key: string; name: string; flag: string }[];
  circuits: string[];
  diagnostics?: LedgerDiagnostics;
  valueDiagnostics?: LedgerDiagnostics;
}

export const TrackerLedger: React.FC<TrackerLedgerProps> = ({
  sport,
  footballEntries,
  tennisEntries,
  leagues,
  circuits,
  diagnostics,
  valueDiagnostics,
}) => {
  const [trackerSearch, setTrackerSearch] = useState('');
  const [trackerLeague, setTrackerLeague] = useState('ALL');
  const [trackerStatus, setTrackerStatus] = useState('ALL');
  const [trackerCategory, setTrackerCategory] = useState<'value' | '1x2' | 'goals' | 'btts' | 'corners' | 'cards' | 'score'>('value');
  const [tennisCategory, setTennisCategory] = useState<'value' | 'winner' | 'sets' | 'games' | 'decider'>('value');
  const [cohortFilter, setCohortFilter] = useState<'all' | 'value_only'>('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [sortCol, setSortCol] = useState('date');
  const [sortAsc, setSortAsc] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'diagnostics'>('table');
  const [selectedDimension, setSelectedDimension] = useState<string>('ALL');
  const [cohortSearch, setCohortSearch] = useState<string>('');

  // Active diagnostics based on cohort filter (All Matches vs Value Bets Only)
  const activeDiagnostics = useMemo(() => {
    if (sport === 'football' && cohortFilter === 'value_only' && valueDiagnostics) {
      return valueDiagnostics;
    }
    return diagnostics;
  }, [sport, cohortFilter, diagnostics, valueDiagnostics]);

  // Flatten & filter cohorts for diagnostics inspector
  const allCohorts = useMemo(() => {
    if (!activeDiagnostics?.cohorts) return [];
    const list: LeakItem[] = [
      ...(activeDiagnostics.cohorts.by_odds || []),
      ...(activeDiagnostics.cohorts.by_league || []),
      ...(activeDiagnostics.cohorts.by_market || []),
      ...(activeDiagnostics.cohorts.by_venue || []),
    ];
    return list.filter((c) => {
      const matchDim = selectedDimension === 'ALL' || c.dimension === selectedDimension;
      const matchSearch = !cohortSearch || c.cohort.toLowerCase().includes(cohortSearch.toLowerCase());
      return matchDim && matchSearch;
    });
  }, [activeDiagnostics, selectedDimension, cohortSearch]);

  // Reset league/circuit filter on sport change to prevent cross-filtering
  useEffect(() => {
    setTrackerLeague('ALL');
  }, [sport]);

  // Filtered Football entries
  const filteredFootball = useMemo(() => {
    return footballEntries.filter((t) => {
      const matchSearch = (t.home_team + ' ' + t.away_team + ' ' + t.league).toLowerCase().includes(trackerSearch.toLowerCase());
      const matchLeague = trackerLeague === 'ALL' || t.league === trackerLeague;
      const matchStatus = trackerStatus === 'ALL' || (trackerStatus === 'settled' ? t.status === 'settled' : t.status === 'pending');
      const matchCohort = cohortFilter === 'all' || Boolean(t.has_value);
      const mDate = (t.date || '').slice(0, 10);
      const matchStart = !startDate || mDate >= startDate;
      const matchEnd = !endDate || mDate <= endDate;
      return matchSearch && matchLeague && matchStatus && matchCohort && matchStart && matchEnd;
    });
  }, [footballEntries, trackerSearch, trackerLeague, trackerStatus, cohortFilter, startDate, endDate]);

  // Filtered Tennis entries
  const filteredTennis = useMemo(() => {
    return tennisEntries.filter((t) => {
      const matchSearch = (t.p1_name + ' ' + t.p2_name + ' ' + t.tourney_name + ' ' + t.circuit).toLowerCase().includes(trackerSearch.toLowerCase());
      const matchCircuit = trackerLeague === 'ALL' || t.circuit === trackerLeague;
      const matchStatus = trackerStatus === 'ALL' || (trackerStatus === 'settled' ? t.status !== 'PENDING' : t.status === 'PENDING');
      const matchCohort = cohortFilter === 'all' || Boolean(t.is_value_bet);
      const mDate = (t.date || '').slice(0, 10);
      const matchStart = !startDate || mDate >= startDate;
      const matchEnd = !endDate || mDate <= endDate;
      return matchSearch && matchCircuit && matchStatus && matchCohort && matchStart && matchEnd;
    });
  }, [tennisEntries, trackerSearch, trackerLeague, trackerStatus, cohortFilter, startDate, endDate]);

  // Column sorting handler
  const handleSort = (colKey: string) => {
    if (sortCol === colKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(colKey);
      setSortAsc(false);
    }
  };

  // Sortable Football List
  const sortedFootball = useMemo(() => {
    const list = [...filteredFootball];
    if (!sortCol) return list;
    return list.sort((a, b) => {
      let valA: any;
      let valB: any;
      switch (sortCol) {
        case 'date':
          valA = a.date || '';
          valB = b.date || '';
          break;
        case 'league':
          valA = a.league || '';
          valB = b.league || '';
          break;
        case 'match':
          valA = `${a.home_team} vs ${a.away_team}`;
          valB = `${b.home_team} vs ${b.away_team}`;
          break;
        case 'pred_1x2':
          valA = a.pred_1x2 || '';
          valB = b.pred_1x2 || '';
          break;
        case 'prob_home':
          valA = a.prob_home ?? 0;
          valB = b.prob_home ?? 0;
          break;
        case 'prob_draw':
          valA = a.prob_draw ?? 0;
          valB = b.prob_draw ?? 0;
          break;
        case 'prob_away':
          valA = a.prob_away ?? 0;
          valB = b.prob_away ?? 0;
          break;
        case 'actual_score':
          valA = a.actual_score || '';
          valB = b.actual_score || '';
          break;
        case 'actual_winner':
          valA = a.actual_winner || '';
          valB = b.actual_winner || '';
          break;
        case 'correct_1x2':
          valA = a.correct_1x2 ? 1 : 0;
          valB = b.correct_1x2 ? 1 : 0;
          break;
        case 'exp_xg':
          valA = a.exp_total_goals ?? ((a.expected_goals_home ?? a.exp_goals_home ?? 1.3) + (a.expected_goals_away ?? a.exp_goals_away ?? 1.1));
          valB = b.exp_total_goals ?? ((b.expected_goals_home ?? b.exp_goals_home ?? 1.3) + (b.expected_goals_away ?? b.exp_goals_away ?? 1.1));
          break;
        case 'pred_o25':
          valA = a.pred_over25 || '';
          valB = b.pred_over25 || '';
          break;
        case 'prob_o25':
          valA = a.prob_over25 ?? 0;
          valB = b.prob_over25 ?? 0;
          break;
        case 'actual_goals':
          valA = a.actual_goals ?? -1;
          valB = b.actual_goals ?? -1;
          break;
        case 'goal_error':
          valA = a.goal_error ?? 99;
          valB = b.goal_error ?? 99;
          break;
        case 'correct_o25':
          valA = a.correct_over25 ? 1 : 0;
          valB = b.correct_over25 ? 1 : 0;
          break;
        case 'pred_btts':
          valA = a.pred_btts || '';
          valB = b.pred_btts || '';
          break;
        case 'prob_btts_yes':
          valA = a.prob_btts_yes ?? 0;
          valB = b.prob_btts_yes ?? 0;
          break;
        case 'prob_btts_no':
          valA = a.prob_btts_no ?? 0;
          valB = b.prob_btts_no ?? 0;
          break;
        case 'actual_btts':
          valA = a.actual_btts || '';
          valB = b.actual_btts || '';
          break;
        case 'correct_btts':
          valA = a.correct_btts ? 1 : 0;
          valB = b.correct_btts ? 1 : 0;
          break;
        case 'exp_corners':
          valA = a.exp_corners ?? a.expected_corners ?? 9.5;
          valB = b.exp_corners ?? b.expected_corners ?? 9.5;
          break;
        case 'pred_corners':
          valA = a.pred_corners_o95 || '';
          valB = b.pred_corners_o95 || '';
          break;
        case 'prob_corners':
          valA = a.prob_corners_over95 ?? 0;
          valB = b.prob_corners_over95 ?? 0;
          break;
        case 'actual_corners':
          valA = a.actual_corners ?? -1;
          valB = b.actual_corners ?? -1;
          break;
        case 'corner_error':
          valA = a.corner_error ?? 99;
          valB = b.corner_error ?? 99;
          break;
        case 'correct_corners':
          valA = a.actual_corners == null ? -1 : (a.correct_corners_o95 ? 1 : 0);
          valB = b.actual_corners == null ? -1 : (b.correct_corners_o95 ? 1 : 0);
          break;
        case 'referee':
          valA = typeof a.referee === 'string' ? a.referee : ((a.referee as any)?.name || '');
          valB = typeof b.referee === 'string' ? b.referee : ((b.referee as any)?.name || '');
          break;
        case 'exp_cards':
          valA = a.exp_cards ?? a.expected_cards ?? 4.2;
          valB = b.exp_cards ?? b.expected_cards ?? 4.2;
          break;
        case 'pred_cards':
          valA = a.pred_cards_o35 || '';
          valB = b.pred_cards_o35 || '';
          break;
        case 'prob_cards':
          valA = a.prob_cards_over35 ?? 0;
          valB = b.prob_cards_over35 ?? 0;
          break;
        case 'actual_cards':
          valA = a.actual_cards ?? -1;
          valB = b.actual_cards ?? -1;
          break;
        case 'card_error':
          valA = a.card_error ?? 99;
          valB = b.card_error ?? 99;
          break;
        case 'correct_cards':
          valA = a.actual_cards == null ? -1 : (a.correct_cards_o35 ? 1 : 0);
          valB = b.actual_cards == null ? -1 : (b.correct_cards_o35 ? 1 : 0);
          break;
        case 'pred_score':
          valA = a.pred_score || '';
          valB = b.pred_score || '';
          break;
        case 'correct_score':
          valA = a.correct_score ? 1 : 0;
          valB = b.correct_score ? 1 : 0;
          break;
        case 'pick':
          valA = a.best_pick?.selection || (a.has_value ? a.pred_1x2 : '') || '';
          valB = b.best_pick?.selection || (b.has_value ? b.pred_1x2 : '') || '';
          break;
        case 'market':
          valA = a.best_pick?.market || (a.has_value ? a.market_category : '') || '';
          valB = b.best_pick?.market || (b.has_value ? b.market_category : '') || '';
          break;
        case 'odds':
          valA = a.best_pick?.odds ?? 0;
          valB = b.best_pick?.odds ?? 0;
          break;
        case 'prob':
          valA = a.best_pick?.prob ?? 0;
          valB = b.best_pick?.prob ?? 0;
          break;
        case 'ev':
          valA = a.best_pick?.ev ?? 0;
          valB = b.best_pick?.ev ?? 0;
          break;
        case 'result':
          valA = a.won === true ? 1 : a.won === false ? 0 : -1;
          valB = b.won === true ? 1 : b.won === false ? 0 : -1;
          break;
        case 'pnl':
          valA = a.flat_pnl ?? 0;
          valB = b.flat_pnl ?? 0;
          break;
        default:
          valA = (a as any)[sortCol] ?? '';
          valB = (b as any)[sortCol] ?? '';
      }
      if (typeof valA === 'number' && typeof valB === 'number') {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });
  }, [filteredFootball, sortCol, sortAsc]);

  // Sortable Tennis List
  const sortedTennis = useMemo(() => {
    const list = [...filteredTennis];
    if (!sortCol) return list;
    return list.sort((a, b) => {
      let valA: any;
      let valB: any;
      switch (sortCol) {
        case 'date':
          valA = a.date || '';
          valB = b.date || '';
          break;
        case 'circuit':
          valA = a.circuit || '';
          valB = b.circuit || '';
          break;
        case 'tournament':
          valA = a.tourney_name || '';
          valB = b.tourney_name || '';
          break;
        case 'surface':
          valA = a.surface || '';
          valB = b.surface || '';
          break;
        case 'match':
          valA = `${a.p1_name} vs ${a.p2_name}`;
          valB = `${b.p1_name} vs ${b.p2_name}`;
          break;
        case 'pick':
          valA = a.recommended_pick || '';
          valB = b.recommended_pick || '';
          break;
        case 'odds':
          valA = a.best_odds ?? 0;
          valB = b.best_odds ?? 0;
          break;
        case 'ev':
          valA = a.best_ev ?? 0;
          valB = b.best_ev ?? 0;
          break;
        case 'edge':
          valA = a.best_edge ?? 0;
          valB = b.best_edge ?? 0;
          break;
        case 'stake':
          valA = a.stake ?? a.best_stake ?? 0;
          valB = b.stake ?? b.best_stake ?? 0;
          break;
        case 'result':
          valA = a.actual_winner || '';
          valB = b.actual_winner || '';
          break;
        case 'status':
          valA = a.status || '';
          valB = b.status || '';
          break;
        case 'pnl':
          valA = a.pnl ?? 0;
          valB = b.pnl ?? 0;
          break;
        case 'p1_prob':
          valA = a.p1_prob ?? 0;
          valB = b.p1_prob ?? 0;
          break;
        case 'p2_prob':
          valA = a.p2_prob ?? 0;
          valB = b.p2_prob ?? 0;
          break;
        case 'pred_winner':
          valA = a.predicted_winner || (a.p1_prob >= a.p2_prob ? a.p1_name : a.p2_name);
          valB = b.predicted_winner || (b.p1_prob >= b.p2_prob ? b.p1_name : b.p2_name);
          break;
        case 'correct_winner':
          valA = a.correct_winner ? 1 : 0;
          valB = b.correct_winner ? 1 : 0;
          break;
        case 'sets_p1':
          valA = a.sets_games?.p1_win_at_least_1_set_prob ?? 0;
          valB = b.sets_games?.p1_win_at_least_1_set_prob ?? 0;
          break;
        case 'sets_p2':
          valA = a.sets_games?.p2_win_at_least_1_set_prob ?? 0;
          valB = b.sets_games?.p2_win_at_least_1_set_prob ?? 0;
          break;
        case 'correct_sets':
          valA = a.correct_sets_at_least_1 ? 1 : 0;
          valB = b.correct_sets_at_least_1 ? 1 : 0;
          break;
        case 'exp_games':
          valA = a.exp_total_games ?? a.sets_games?.expected_total_games ?? 0;
          valB = b.exp_total_games ?? b.sets_games?.expected_total_games ?? 0;
          break;
        case 'games_line':
          valA = a.games_line ?? a.sets_games?.main_games_line?.line ?? 0;
          valB = b.games_line ?? b.sets_games?.main_games_line?.line ?? 0;
          break;
        case 'actual_games':
          valA = a.actual_games ?? -1;
          valB = b.actual_games ?? -1;
          break;
        case 'game_error':
          valA = a.game_error ?? 99;
          valB = b.game_error ?? 99;
          break;
        case 'correct_games':
          valA = a.correct_games_ou ? 1 : 0;
          valB = b.correct_games_ou ? 1 : 0;
          break;
        case 'decider_prob':
          valA = a.sets_games?.prob_deciding_set ?? 0;
          valB = b.sets_games?.prob_deciding_set ?? 0;
          break;
        case 'correct_decider':
          valA = a.correct_deciding_set ? 1 : 0;
          valB = b.correct_deciding_set ? 1 : 0;
          break;
        default:
          valA = (a as any)[sortCol] ?? '';
          valB = (b as any)[sortCol] ?? '';
      }
      if (typeof valA === 'number' && typeof valB === 'number') {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });
  }, [filteredTennis, sortCol, sortAsc]);

  // Tennis Multi-Market Realized Accuracy Scorecard
  const tennisTrackerMetrics = useMemo(() => {
    const settled = filteredTennis.filter((t) => t.status !== 'PENDING');
    const total = settled.length;

    // 1. Model Match Winner Hit Rate (pure ML favorite accuracy)
    const winnerHits = settled.filter((t) => t.correct_winner === true || t.model_correct === true).length;
    const winnerGraded = settled.filter((t) => t.correct_winner !== undefined || t.model_correct !== undefined).length || total;
    const modelWinnerAcc = winnerGraded > 0 ? (winnerHits / winnerGraded) * 100 : 0;

    // Circuit breakdown
    const atpSettled = settled.filter((t) => t.circuit === 'ATP');
    const atpHits = atpSettled.filter((t) => t.correct_winner === true || t.model_correct === true).length;
    const atpWinRate = atpSettled.length > 0 ? (atpHits / atpSettled.length) * 100 : 0;

    const wtaSettled = settled.filter((t) => t.circuit === 'WTA');
    const wtaHits = wtaSettled.filter((t) => t.correct_winner === true || t.model_correct === true).length;
    const wtaWinRate = wtaSettled.length > 0 ? (wtaHits / wtaSettled.length) * 100 : 0;

    // 2. Multi-Market Hit Rates
    // Sets line (Win >= 1 Set)
    const setsGraded = settled.filter((t) => t.correct_sets_at_least_1 !== undefined);
    const setsHits = setsGraded.filter((t) => t.correct_sets_at_least_1 === true).length;
    const setsAcc = setsGraded.length > 0 ? (setsHits / setsGraded.length) * 100 : 0;

    // Games line O/U
    const gamesGraded = settled.filter((t) => t.correct_games_ou !== undefined);
    const gamesHits = gamesGraded.filter((t) => t.correct_games_ou === true).length;
    const gamesAcc = gamesGraded.length > 0 ? (gamesHits / gamesGraded.length) * 100 : 0;

    // Deciding Set
    const deciderGraded = settled.filter((t) => t.correct_deciding_set !== undefined);
    const deciderHits = deciderGraded.filter((t) => t.correct_deciding_set === true).length;
    const deciderAcc = deciderGraded.length > 0 ? (deciderHits / deciderGraded.length) * 100 : 0;

    // Average Game Error
    const errorEntries = settled.filter((t) => typeof t.game_error === 'number' && !isNaN(t.game_error));
    const avgGameError = errorEntries.length > 0 ? errorEntries.reduce((acc, t) => acc + (t.game_error || 0), 0) / errorEntries.length : 0;

    // 3. Disciplined Value Bets
    const valueBets = settled.filter((t) => t.is_value_bet || (t.pnl !== undefined && t.pnl !== 0));
    const valWins = valueBets.filter((t) => t.status === 'WON').length;
    const valLosses = valueBets.filter((t) => t.status === 'LOST').length;
    const valVoids = valueBets.filter((t) => t.status === 'VOID').length;
    const totalPnl = valueBets.reduce((acc, t) => acc + (t.pnl || 0), 0);
    const totalStaked = valueBets.reduce((acc, t) => acc + (t.stake || 50), 0);
    const roi = totalStaked > 0 ? (totalPnl / totalStaked) * 100 : 0;
    const valWinRate = (valWins + valLosses) > 0 ? (valWins / (valWins + valLosses)) * 100 : 0;

    return {
      totalSettled: total,
      modelWinnerAcc,
      winnerHits,
      winnerGraded,
      atpWinRate,
      atpHits,
      atpGraded: atpSettled.length,
      wtaWinRate,
      wtaHits,
      wtaGraded: wtaSettled.length,
      setsAcc,
      setsHits,
      setsGraded: setsGraded.length,
      gamesAcc,
      gamesHits,
      gamesGraded: gamesGraded.length,
      deciderAcc,
      deciderHits,
      deciderGraded: deciderGraded.length,
      avgGameError,
      valueBetsCount: valueBets.length,
      valWins,
      valLosses,
      valVoids,
      valWinRate,
      totalPnl,
      totalStaked,
      roi,
    };
  }, [filteredTennis]);

  // Scorecard metrics for Football
  const trackerMetrics = useMemo(() => {
    const settled = filteredFootball.filter((t) => t.status === 'settled');
    const total = settled.length;
    if (total === 0) {
      return {
        totalSettled: 0,
        acc1x2: 0,
        accO25: 0,
        accBtts: 0,
        accCorners: 0,
        accCards: 0,
        cornHits: 0,
        cornTotal: 0,
        cardHits: 0,
        cardTotal: 0,
        exactScores: 0,
        avgGoalErr: 0,
        avgCornerErr: 0,
        avgCardErr: 0,
        totalPnl: 0,
        totalStaked: 0,
        roi: 0,
        wins: 0,
        valMatchesCount: 0,
        valWins: 0,
        valWinRate: 0,
        valPnl: 0,
        valStaked: 0,
        valRoi: 0,
        valAvgEv: 0,
      };
    }
    const c1x2 = settled.filter((t) => t.correct_1x2).length;
    const cO25 = settled.filter((t) => t.correct_over25).length;
    const cBtts = settled.filter((t) => t.correct_btts).length;

    const cornMatches = settled.filter((t) => typeof t.actual_corners === 'number' && t.actual_corners >= 0);
    const cardMatches = settled.filter((t) => typeof t.actual_cards === 'number' && t.actual_cards >= 0);

    const cCorn = cornMatches.filter((t) => t.correct_corners_o95).length;
    const cCards = cardMatches.filter((t) => t.correct_cards_o35).length;
    const cScore = settled.filter((t) => t.correct_score).length;

    const goalErrs = settled.map((t) => t.goal_error).filter((v): v is number => typeof v === 'number');
    const cornErrs = cornMatches.map((t) => t.corner_error).filter((v): v is number => typeof v === 'number');
    const cardErrs = cardMatches.map((t) => t.card_error).filter((v): v is number => typeof v === 'number');

    const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);

    // Financial calculations
    const totalPnl = settled.reduce((acc, t) => acc + (t.flat_pnl ?? 0), 0);
    const totalStaked = settled.length * 100;
    const roi = totalStaked > 0 ? (totalPnl / totalStaked) * 100 : 0;
    const wins = settled.filter((t) => t.won).length;

    const valSettled = settled.filter((t) => Boolean(t.has_value));
    const valMatchesCount = valSettled.length;
    const valWins = valSettled.filter((t) => t.won).length;
    const valWinRate = valMatchesCount > 0 ? (valWins / valMatchesCount) * 100 : 0;
    const valPnl = valSettled.reduce((acc, t) => acc + (t.flat_pnl ?? 0), 0);
    const valStaked = valMatchesCount * 100;
    const valRoi = valStaked > 0 ? (valPnl / valStaked) * 100 : 0;
    const valEvList = valSettled.map((t) => t.best_pick?.ev ?? 0);
    const valAvgEv = valEvList.length > 0 ? (valEvList.reduce((a, b) => a + b, 0) / valEvList.length) * 100 : 0;

    return {
      totalSettled: total,
      acc1x2: (c1x2 / total) * 100,
      accO25: (cO25 / total) * 100,
      accBtts: (cBtts / total) * 100,
      accCorners: cornMatches.length > 0 ? (cCorn / cornMatches.length) * 100 : 0,
      accCards: cardMatches.length > 0 ? (cCards / cardMatches.length) * 100 : 0,
      cornHits: cCorn,
      cornTotal: cornMatches.length,
      cardHits: cCards,
      cardTotal: cardMatches.length,
      exactScores: cScore,
      avgGoalErr: avg(goalErrs),
      avgCornerErr: avg(cornErrs),
      avgCardErr: avg(cardErrs),
      totalPnl,
      totalStaked,
      roi,
      wins,
      valMatchesCount,
      valWins,
      valWinRate,
      valPnl,
      valStaked,
      valRoi,
      valAvgEv,
    };
  }, [filteredFootball]);

  // Reusable Sortable Table Header Component
  const SortTh: React.FC<{
    col: string;
    label: string;
    align?: 'left' | 'center' | 'right';
  }> = ({ col, label, align = 'left' }) => {
    const isActive = sortCol === col;
    return (
      <th
        onClick={() => handleSort(col)}
        className={`px-4 py-3 cursor-pointer select-none transition-colors hover:text-white ${
          isActive ? 'text-sky-400 font-bold bg-dark-800/80' : ''
        } ${align === 'center' ? 'text-center' : align === 'right' ? 'text-right' : 'text-left'}`}
        title={`Sort by ${label} (${isActive ? (sortAsc ? 'Ascending ▲' : 'Descending ▼') : 'Click to sort'})`}
      >
        <div
          className={`inline-flex items-center gap-1.5 ${
            align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : 'justify-start'
          }`}
        >
          <span>{label}</span>
          <span className={`text-[10px] ${isActive ? 'text-sky-400 font-bold' : 'text-slate-500'}`}>
            {isActive ? (sortAsc ? '▲' : '▼') : '↕'}
          </span>
        </div>
      </th>
    );
  };

  return (
    <div className="space-y-6">
      {/* View Switcher: Table vs Diagnostics */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-dark-800/90 border border-dark-700 p-2.5 rounded-xl shadow-md">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('table')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 ${
              viewMode === 'table'
                ? 'bg-sky-500/20 text-sky-400 border border-sky-500/40 shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <span>📋 Verified Ledger Table</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-dark-900/80 font-mono text-slate-300">
              {sport === 'football' ? filteredFootball.length : filteredTennis.length}
            </span>
          </button>
          <button
            onClick={() => setViewMode('diagnostics')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 ${
              viewMode === 'diagnostics'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <span>🔬 Post-Mortem Leak Detector</span>
            {activeDiagnostics && activeDiagnostics.active_leaks_count > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-mono font-bold border border-rose-500/30">
                {activeDiagnostics.active_leaks_count} {activeDiagnostics.active_leaks_count === 1 ? 'Leak' : 'Leaks'}
              </span>
            )}
          </button>
        </div>

        {activeDiagnostics && (
          <div className="text-[11px] text-slate-400 flex items-center gap-3">
            <span>
              Audited Bets: <strong className="text-slate-200 font-mono">{activeDiagnostics.total_audited}</strong>
            </span>
            <span className="text-slate-600">•</span>
            <span>
              Variance Losses:{' '}
              <strong className="text-teal-400 font-mono">
                {activeDiagnostics.loss_breakdown.variance_ratio_pct.toFixed(0)}%
              </strong>
            </span>
          </div>
        )}
      </div>

      {viewMode === 'table' ? (
        <>
          {/* Filter Ledger Toolbar */}
          <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-4 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <Filter className="w-4 h-4 text-sky-400" />
            <span>Filter Verification Ledger</span>
          </h3>
          <span className="text-[11px] text-slate-400">
            Showing {sport === 'football' ? filteredFootball.length : filteredTennis.length} matches
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
          <div className="lg:col-span-2">
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              Search Ledger
            </label>
            <input
              type="text"
              value={trackerSearch}
              onChange={(e) => setTrackerSearch(e.target.value)}
              placeholder="Search fixture, team, competition..."
              className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              Filter Competition
            </label>
            <select
              value={trackerLeague}
              onChange={(e) => setTrackerLeague(e.target.value)}
              className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="ALL">All Competitions</option>
              {sport === 'football'
                ? leagues.map((l) => (
                    <option key={l.key} value={l.key}>
                      {l.flag} {l.name}
                    </option>
                  ))
                : circuits.map((c) => (
                    <option key={c} value={c}>
                      {c} Tour
                    </option>
                  ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              Status Filter
            </label>
            <select
              value={trackerStatus}
              onChange={(e) => setTrackerStatus(e.target.value)}
              className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs font-semibold text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="ALL">All Statuses (Settled & Pending)</option>
              <option value="settled">Settled Matches Only</option>
              <option value="pending">Pending Matches Only</option>
            </select>
          </div>

          {sport === 'football' && (
            <div>
              <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Strategy Cohort
              </label>
              <select
                value={cohortFilter}
                onChange={(e) => setCohortFilter(e.target.value as 'all' | 'value_only')}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-xs font-semibold text-emerald-400 focus:outline-none focus:border-emerald-500"
              >
                <option value="all">📋 All Evaluated ({footballEntries.length})</option>
                <option value="value_only">⭐ +EV Value Bets Only ({footballEntries.filter(t => Boolean(t.has_value)).length})</option>
              </select>
            </div>
          )}

          <div className={sport === 'football' ? '' : 'lg:col-span-2'}>
            <CalendarDateRangePicker
              startDate={startDate}
              endDate={endDate}
              onChange={(s, e) => {
                setStartDate(s);
                setEndDate(e);
              }}
              mode="ledger"
              label="Match Date Filter"
            />
          </div>
        </div>
      </div>

      {/* Realized Model Accuracy Scorecard */}
      {sport === 'football' && (
        <div className="space-y-3">
          {/* Financial Performance & Realized PnL Bar */}
          <div className="bg-gradient-to-r from-emerald-950/40 via-dark-800 to-sky-950/40 border border-emerald-500/30 rounded-xl p-4 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5">
                    ⭐ +EV Model Financial Ledger
                  </span>
                  <span className="text-xs text-slate-400">
                    {cohortFilter === 'value_only'
                      ? 'Displaying filtered +EV picks only'
                      : `Strategy tracks ${trackerMetrics.valMatchesCount} positive expected-value opportunities across evaluated fixtures`}
                  </span>
                </div>
                <div className="text-xs text-slate-300">
                  Settled Bets: <strong className="text-white font-mono">{trackerMetrics.valMatchesCount}</strong> | 
                  Win Rate: <strong className="text-emerald-400 font-mono">{trackerMetrics.valWinRate.toFixed(1)}%</strong> ({trackerMetrics.valWins}W - {trackerMetrics.valMatchesCount - trackerMetrics.valWins}L) | 
                  Modeled Edge (EV): <strong className="text-sky-400 font-mono">+{trackerMetrics.valAvgEv.toFixed(1)}%</strong>
                </div>
              </div>
              <div className="flex items-center gap-4 divide-x divide-dark-700">
                <div className="text-right pr-4">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Total Staked (100€/bet)</div>
                  <div className="text-sm font-mono font-bold text-slate-200">{trackerMetrics.valStaked.toLocaleString()}€</div>
                </div>
                <div className="text-right px-4">
                  <div className="text-[10px] uppercase font-bold text-slate-400">+EV Realized Net Profit</div>
                  <div className={`text-lg font-mono font-extrabold ${trackerMetrics.valPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {trackerMetrics.valPnl >= 0 ? '+' : ''}{trackerMetrics.valPnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}€
                  </div>
                </div>
                <div className="text-right pl-4">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Realized ROI</div>
                  <div className={`text-lg font-mono font-extrabold ${trackerMetrics.valRoi >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {trackerMetrics.valRoi >= 0 ? '+' : ''}{trackerMetrics.valRoi.toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Verified Matches</div>
              <div className="text-xl font-mono font-bold text-white mt-1">{trackerMetrics.totalSettled}</div>
              <div className="text-[10px] text-slate-500">{filteredFootball.length} in Filter</div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">1X2 Hit Rate</div>
              <div className="text-xl font-mono font-bold text-emerald-400 mt-1">{trackerMetrics.acc1x2.toFixed(1)}%</div>
              <div className="text-[10px] text-emerald-500/80">Out-of-sample</div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">O/U 2.5 Goals</div>
              <div className="text-xl font-mono font-bold text-teal-400 mt-1">{trackerMetrics.accO25.toFixed(1)}%</div>
              <div className="text-[10px] text-teal-500/80">Poisson Dixon-Coles</div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">BTTS Hit Rate</div>
              <div className="text-xl font-mono font-bold text-sky-400 mt-1">{trackerMetrics.accBtts.toFixed(1)}%</div>
              <div className="text-[10px] text-sky-500/80">Both Teams Score</div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Corners &gt;9.5</div>
              <div className="text-xl font-mono font-bold text-purple-400 mt-1">{trackerMetrics.accCorners.toFixed(1)}%</div>
              <div className="text-[10px] text-purple-500/80">
                {trackerMetrics.cornHits}/{trackerMetrics.cornTotal} Reported
                {trackerMetrics.totalSettled > trackerMetrics.cornTotal && (
                  <span className="text-slate-500"> ({trackerMetrics.totalSettled - trackerMetrics.cornTotal} unrecorded)</span>
                )}
              </div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Cards &gt;3.5</div>
              <div className="text-xl font-mono font-bold text-amber-400 mt-1">{trackerMetrics.accCards.toFixed(1)}%</div>
              <div className="text-[10px] text-amber-500/80">
                {trackerMetrics.cardHits}/{trackerMetrics.cardTotal} Reported
                {trackerMetrics.totalSettled > trackerMetrics.cardTotal && (
                  <span className="text-slate-500"> ({trackerMetrics.totalSettled - trackerMetrics.cardTotal} unrecorded)</span>
                )}
              </div>
            </div>
          </div>

          {/* Error Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-dark-900/80 border border-dark-700/60 rounded-lg p-2.5 text-center">
              <span className="text-[10px] text-slate-400 uppercase">Avg Goal Error: </span>
              <span className="text-xs font-mono font-bold text-white">{trackerMetrics.avgGoalErr.toFixed(2)} goals</span>
            </div>
            <div className="bg-dark-900/80 border border-dark-700/60 rounded-lg p-2.5 text-center">
              <span className="text-[10px] text-slate-400 uppercase">Avg Corner Error: </span>
              <span className="text-xs font-mono font-bold text-white">{trackerMetrics.avgCornerErr.toFixed(1)} corners</span>
            </div>
            <div className="bg-dark-900/80 border border-dark-700/60 rounded-lg p-2.5 text-center">
              <span className="text-[10px] text-slate-400 uppercase">Avg Card Error: </span>
              <span className="text-xs font-mono font-bold text-white">{trackerMetrics.avgCardErr.toFixed(1)} cards</span>
            </div>
            <div className="bg-dark-900/80 border border-dark-700/60 rounded-lg p-2.5 text-center">
              <span className="text-[10px] text-slate-400 uppercase">Exact Score Hits: </span>
              <span className="text-xs font-mono font-bold text-emerald-400">{trackerMetrics.exactScores} matches</span>
            </div>
          </div>
        </div>
      )}

      {/* 6 Dedicated Category Verification Tabs for Football */}
      {sport === 'football' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1 bg-dark-800 p-1 rounded-xl border border-dark-700">
            <button
              onClick={() => setTrackerCategory('value')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'value' ? 'bg-dark-700 text-emerald-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              💰 +EV Value Bets & PnL
            </button>
            <button
              onClick={() => setTrackerCategory('1x2')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === '1x2' ? 'bg-dark-700 text-emerald-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🏆 1X2 Match Outcomes
            </button>
            <button
              onClick={() => setTrackerCategory('goals')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'goals' ? 'bg-dark-700 text-teal-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              ⚽ Goals & xG Accuracy
            </button>
            <button
              onClick={() => setTrackerCategory('btts')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'btts' ? 'bg-dark-700 text-sky-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🥅 Both Teams To Score
            </button>
            <button
              onClick={() => setTrackerCategory('corners')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'corners' ? 'bg-dark-700 text-purple-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🚩 Corners Line Accuracy
            </button>
            <button
              onClick={() => setTrackerCategory('cards')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'cards' ? 'bg-dark-700 text-amber-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🟨 Cards & Referee Disciplinary
            </button>
            <button
              onClick={() => setTrackerCategory('score')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                trackerCategory === 'score' ? 'bg-dark-700 text-rose-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🎯 Exact Scoreline Predictions
            </button>
          </div>

          {/* Sub-tab Content Tables */}
          <div className="bg-dark-800/80 border border-dark-700 rounded-xl overflow-hidden shadow-sm">
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-dark-700">
                  <tr>
                    <SortTh col="date" label="Date" />
                    <SortTh col="league" label="League" />
                    <SortTh col="match" label="Match" />

                    {trackerCategory === 'value' && (
                      <>
                        <SortTh col="pick" label="Value Selection" />
                        <SortTh col="odds" label="Odds" align="right" />
                        <SortTh col="prob" label="Model Prob" align="right" />
                        <SortTh col="ev" label="Expected Edge (EV)" align="right" />
                        <SortTh col="actual_score" label="Actual Score" align="center" />
                        <SortTh col="result" label="Result" align="center" />
                        <th className="px-4 py-3 text-right uppercase text-[10px] tracking-wider font-semibold text-slate-400">Stake</th>
                        <SortTh col="pnl" label="Net PnL" align="right" />
                      </>
                    )}

                    {trackerCategory === '1x2' && (
                      <>
                        <SortTh col="pred_1x2" label="Model Pred" />
                        <SortTh col="prob_home" label="P(Home)" />
                        <SortTh col="prob_draw" label="P(Draw)" />
                        <SortTh col="prob_away" label="P(Away)" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="actual_winner" label="Actual Winner" />
                        <SortTh col="correct_1x2" label="Verification" />
                      </>
                    )}

                    {trackerCategory === 'goals' && (
                      <>
                        <SortTh col="exp_xg" label="Projected xG" />
                        <SortTh col="pred_o25" label="Pred O/U 2.5" />
                        <SortTh col="prob_o25" label="P(Over 2.5)" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="actual_goals" label="Total Goals" />
                        <SortTh col="goal_error" label="Goal Error" />
                        <SortTh col="correct_o25" label="Verification" />
                      </>
                    )}

                    {trackerCategory === 'btts' && (
                      <>
                        <SortTh col="pred_btts" label="Model Pred" />
                        <SortTh col="prob_btts_yes" label="P(Yes)" />
                        <SortTh col="prob_btts_no" label="P(No)" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="actual_btts" label="Both Scored?" />
                        <SortTh col="correct_btts" label="Verification" />
                      </>
                    )}

                    {trackerCategory === 'corners' && (
                      <>
                        <SortTh col="exp_corners" label="Exp. Corners (λ)" />
                        <SortTh col="pred_corners" label="Pred O/U 9.5" />
                        <SortTh col="prob_corners" label="P(Over 9.5)" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="actual_corners" label="Actual Corners" />
                        <SortTh col="corner_error" label="Corner Error" />
                        <SortTh col="correct_corners" label="Verification" />
                      </>
                    )}

                    {trackerCategory === 'cards' && (
                      <>
                        <SortTh col="referee" label="Official Referee" />
                        <SortTh col="exp_cards" label="Exp. Cards (λ)" />
                        <SortTh col="pred_cards" label="Pred O/U 3.5" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="actual_cards" label="Actual Cards" />
                        <SortTh col="card_error" label="Card Error" />
                        <SortTh col="correct_cards" label="Verification" />
                      </>
                    )}

                    {trackerCategory === 'score' && (
                      <>
                        <SortTh col="pred_score" label="Predicted Score" />
                        <SortTh col="actual_score" label="Actual Score" />
                        <SortTh col="correct_score" label="Verification" />
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-700/60 font-medium">
                  {sortedFootball.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="px-4 py-16 text-center text-slate-500 italic">
                        <div className="flex flex-col items-center justify-center">
                          <CheckCircle2 className="w-8 h-8 text-slate-600 mb-2" />
                          <span className="text-slate-400 font-medium">No tracked predictions in ledger</span>
                          <span className="text-xs text-slate-600 mt-0.5">Historical predictions will appear here once verified</span>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    sortedFootball.map((t) => {
                      const isSettled = t.status === 'settled';

                    return (
                      <tr key={t.match_id} className="hover:bg-dark-700/30 transition-colors">
                        <td className="px-4 py-2.5 text-slate-400 font-mono text-[11px]">
                          {t.date?.slice(0, 10)}
                        </td>
                        <td className="px-4 py-2.5 text-slate-300 font-semibold">{t.league}</td>
                        <td className="px-4 py-2.5 font-bold text-white">
                          {t.home_team} vs {t.away_team}
                        </td>

                        {trackerCategory === 'value' && (() => {
                          const hasVal = Boolean(t.has_value);
                          const pick = t.best_pick;

                          if (!hasVal || !pick || (pick.ev ?? 0) <= 0) {
                            return (
                              <>
                                <td className="px-4 py-2.5">
                                  <div className="font-semibold text-slate-400 italic">No +EV Pick</div>
                                  <div className="text-[10px] text-slate-500 font-mono uppercase">Fair / Negative EV</div>
                                </td>
                                <td className="px-4 py-2.5 text-right font-mono text-slate-500">-</td>
                                <td className="px-4 py-2.5 text-right font-mono text-slate-500">-</td>
                                <td className="px-4 py-2.5 text-right font-mono text-slate-500">-</td>
                                <td className="px-4 py-2.5 text-center font-mono font-bold text-slate-300">
                                  {t.actual_score || '-'}
                                </td>
                                <td className="px-4 py-2.5 text-center">
                                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-dark-700 text-slate-400 border border-dark-600">
                                    NO BET
                                  </span>
                                </td>
                                <td className="px-4 py-2.5 text-right font-mono text-slate-500">0.00€</td>
                                <td className="px-4 py-2.5 text-right font-mono text-slate-500">0.00€</td>
                              </>
                            );
                          }

                          const selection = pick.selection;
                          const market = pick.market || '1X2';
                          const odds = typeof pick.odds === 'number' ? pick.odds : 0;
                          const prob = typeof pick.prob === 'number' ? pick.prob : 0;
                          const ev = pick.ev != null ? (pick.ev > 1 ? pick.ev : pick.ev * 100) : (odds * prob - 1) * 100;
                          const isWin = t.won;
                          const pnl = t.flat_pnl ?? (isSettled ? (isWin ? (odds - 1) * 100 : -100) : 0);

                          return (
                            <>
                              <td className="px-4 py-2.5">
                                <div className="font-bold text-white">{selection}</div>
                                <div className="text-[10px] text-slate-400 font-mono uppercase">{market}</div>
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono font-bold text-slate-200">
                                @{odds > 0 ? odds.toFixed(2) : '-'}
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                                {prob > 0 ? `${(prob * 100).toFixed(1)}%` : '-'}
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono font-bold">
                                <span className={ev > 0 ? 'text-emerald-400' : 'text-slate-400'}>
                                  {ev > 0 ? `+${ev.toFixed(1)}%` : `${ev.toFixed(1)}%`}
                                </span>
                              </td>
                              <td className="px-4 py-2.5 text-center font-mono font-bold text-slate-100">
                                {t.actual_score || '-'}
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                {isSettled ? (
                                  isWin ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ WON
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ LOST
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                    ⏳ PENDING
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                                100.00€
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono font-bold">
                                {isSettled ? (
                                  <span className={pnl > 0 ? 'text-emerald-400' : pnl < 0 ? 'text-rose-400' : 'text-slate-400'}>
                                    {pnl > 0 ? `+${pnl.toFixed(2)}€` : `${pnl.toFixed(2)}€`}
                                  </span>
                                ) : (
                                  <span className="text-slate-500">-</span>
                                )}
                              </td>
                            </>
                          );
                        })()}

                        {trackerCategory === '1x2' && (
                          <>
                            <td className="px-4 py-2.5 text-emerald-400 font-semibold">{t.pred_1x2 || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_home || 0.33) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_draw || 0.33) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_away || 0.33) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5 font-semibold text-slate-200">{t.actual_winner || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_winner != null && t.correct_1x2 !== null ? (
                                  t.correct_1x2 ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {trackerCategory === 'goals' && (
                          <>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {(t.exp_total_goals ?? ((t.expected_goals_home ?? t.exp_goals_home ?? 1.3) + (t.expected_goals_away ?? t.exp_goals_away ?? 1.1))).toFixed(2)}
                            </td>
                            <td className="px-4 py-2.5 text-teal-400 font-semibold">{t.pred_over25 || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_over25 || 0.5) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.actual_goals ?? '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-400">
                              {t.goal_error != null ? `${t.goal_error.toFixed(2)} goals` : '-'}
                            </td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_goals != null && t.correct_over25 !== null ? (
                                  t.correct_over25 ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {trackerCategory === 'btts' && (
                          <>
                            <td className="px-4 py-2.5 text-sky-400 font-semibold">{t.pred_btts || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_btts_yes || 0.5) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_btts_no || 0.5) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5 font-semibold text-slate-200">{t.actual_btts || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_btts != null && t.correct_btts !== null ? (
                                  t.correct_btts ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {trackerCategory === 'corners' && (
                          <>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {(t.exp_corners ?? t.expected_corners ?? 9.5).toFixed(1)}
                            </td>
                            <td className="px-4 py-2.5 text-purple-400 font-semibold">{t.pred_corners_o95 || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {((t.prob_corners_over95 || 0.5) * 100).toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.actual_corners ?? '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-400">
                              {t.corner_error != null ? `${t.corner_error.toFixed(1)} corners` : '-'}
                            </td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_corners != null && t.correct_corners_o95 !== null ? (
                                  t.correct_corners_o95 ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {trackerCategory === 'cards' && (
                          <>
                            <td className="px-4 py-2.5 text-slate-300">
                              {typeof t.referee === 'string' ? t.referee : ((t.referee as any)?.name || 'Unassigned')}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-300">
                              {(t.exp_cards ?? t.expected_cards ?? 4.2).toFixed(1)}
                            </td>
                            <td className="px-4 py-2.5 text-amber-400 font-semibold">{t.pred_cards_o35 || '-'}</td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.actual_cards ?? '-'}</td>
                            <td className="px-4 py-2.5 font-mono text-slate-400">
                              {t.card_error != null ? `${t.card_error.toFixed(1)} cards` : '-'}
                            </td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_cards != null && t.correct_cards_o35 !== null ? (
                                  t.correct_cards_o35 ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {trackerCategory === 'score' && (
                          <>
                            <td className="px-4 py-2.5 font-mono font-bold text-emerald-400">{t.pred_score || '-'}</td>
                            <td className="px-4 py-2.5 font-mono font-bold text-white">{t.actual_score || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.actual_score != null && t.correct_score !== null ? (
                                  t.correct_score ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      🎯 Exact Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  }))}
                </tbody>
              </table>
            </div>

            <div className="px-4 py-3 bg-dark-900/60 border-t border-dark-700 flex justify-between items-center text-xs text-slate-400">
              <div>
                📊 Showing <strong className="text-sky-400">{filteredFootball.length}</strong> matches (
                {trackerMetrics.totalSettled} Settled, {filteredFootball.length - trackerMetrics.totalSettled} Pending)
              </div>
              <div>⚡ PitchVision 2.4 Multi-Market Engine</div>
            </div>
          </div>
        </div>
      )}

      {/* Tennis Verified Ledger & Scorecard */}
      {sport === 'tennis' && (
        <div className="space-y-4">
          {/* Tennis Multi-Market Realized Accuracy Scorecard */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Model Winner %</div>
              <div className="text-xl font-mono font-bold text-teal-400 mt-1">
                {tennisTrackerMetrics.modelWinnerAcc.toFixed(1)}%
              </div>
              <div className="text-[10px] text-teal-500/80">
                {tennisTrackerMetrics.winnerHits}/{tennisTrackerMetrics.winnerGraded} (ATP: {tennisTrackerMetrics.atpWinRate.toFixed(1)}% | WTA: {tennisTrackerMetrics.wtaWinRate.toFixed(1)}%)
              </div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Sets ≥1 Set Hit Rate</div>
              <div className="text-xl font-mono font-bold text-sky-400 mt-1">
                {tennisTrackerMetrics.setsAcc.toFixed(1)}%
              </div>
              <div className="text-[10px] text-sky-500/80">
                {tennisTrackerMetrics.setsHits} / {tennisTrackerMetrics.setsGraded} set lines hit
              </div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Games Line O/U %</div>
              <div className="text-xl font-mono font-bold text-purple-400 mt-1">
                {tennisTrackerMetrics.gamesAcc.toFixed(1)}%
              </div>
              <div className="text-[10px] text-purple-500/80">
                {tennisTrackerMetrics.gamesHits} / {tennisTrackerMetrics.gamesGraded} lines hit
              </div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Deciding Set Rate</div>
              <div className="text-xl font-mono font-bold text-amber-400 mt-1">
                {tennisTrackerMetrics.deciderAcc.toFixed(1)}%
              </div>
              <div className="text-[10px] text-amber-500/80">
                {tennisTrackerMetrics.deciderHits} / {tennisTrackerMetrics.deciderGraded} calls correct
              </div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Avg Game Error</div>
              <div className="text-xl font-mono font-bold text-slate-200 mt-1">
                ±{tennisTrackerMetrics.avgGameError.toFixed(1)} g
              </div>
              <div className="text-[10px] text-slate-400">Mean Abs Error vs Actual</div>
            </div>

            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-3 text-center">
              <div className="text-[11px] text-slate-400 font-bold uppercase">Disciplined +EV PnL</div>
              <div className={`text-xl font-mono font-bold mt-1 ${tennisTrackerMetrics.totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {tennisTrackerMetrics.totalPnl >= 0 ? `+${tennisTrackerMetrics.totalPnl.toFixed(0)}€` : `${tennisTrackerMetrics.totalPnl.toFixed(0)}€`}
              </div>
              <div className="text-[10px] text-slate-500">
                {tennisTrackerMetrics.roi.toFixed(1)}% ROI ({tennisTrackerMetrics.valWins}W-{tennisTrackerMetrics.valLosses}L, €{tennisTrackerMetrics.totalStaked.toFixed(0)} staked)
              </div>
            </div>
          </div>

          {/* 5 Dedicated Category Verification Tabs for Tennis */}
          <div className="flex flex-wrap items-center gap-1 bg-dark-800 p-1 rounded-xl border border-dark-700">
            <button
              onClick={() => setTennisCategory('value')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                tennisCategory === 'value' ? 'bg-dark-700 text-emerald-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              💰 Disciplined +EV Bets & PnL
            </button>
            <button
              onClick={() => setTennisCategory('winner')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                tennisCategory === 'winner' ? 'bg-dark-700 text-teal-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🎾 Match Winner (Moneyline)
            </button>
            <button
              onClick={() => setTennisCategory('sets')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                tennisCategory === 'sets' ? 'bg-dark-700 text-sky-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              📊 Sets Line (≥ 1 Set)
            </button>
            <button
              onClick={() => setTennisCategory('games')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                tennisCategory === 'games' ? 'bg-dark-700 text-purple-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🔢 Total Games Multi-Line O/U
            </button>
            <button
              onClick={() => setTennisCategory('decider')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                tennisCategory === 'decider' ? 'bg-dark-700 text-amber-400 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              🔥 Deciding Set Prediction
            </button>
          </div>

          {/* Tennis Table */}
          <div className="bg-dark-800/80 border border-dark-700 rounded-xl overflow-hidden shadow-sm">
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-dark-900/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-dark-700">
                  <tr>
                    <SortTh col="date" label="Date" />
                    <SortTh col="circuit" label="Circuit" />
                    <SortTh col="tournament" label="Tournament" />
                    <SortTh col="match" label="Match" />

                    {tennisCategory === 'value' && (
                      <>
                        <SortTh col="pick" label="Value Pick" />
                        <SortTh col="p1_prob" label="Model Prob" align="right" />
                        <SortTh col="odds" label="Odds" align="right" />
                        <SortTh col="edge" label="Edge %" align="right" />
                        <SortTh col="ev" label="EV %" align="right" />
                        <SortTh col="stake" label="Stake" align="right" />
                        <SortTh col="result" label="Official Result" />
                        <SortTh col="status" label="Status" />
                        <SortTh col="pnl" label="Net PnL" align="right" />
                      </>
                    )}

                    {tennisCategory === 'winner' && (
                      <>
                        <SortTh col="p1_prob" label="P1 Win %" align="right" />
                        <SortTh col="p2_prob" label="P2 Win %" align="right" />
                        <SortTh col="pred_winner" label="Model Favorite" />
                        <SortTh col="result" label="Official Score" />
                        <SortTh col="result" label="Actual Winner" />
                        <SortTh col="correct_winner" label="Verification" />
                      </>
                    )}

                    {tennisCategory === 'sets' && (
                      <>
                        <SortTh col="sets_p1" label="P1 ≥1 Set %" align="right" />
                        <SortTh col="sets_p2" label="P2 ≥1 Set %" align="right" />
                        <SortTh col="pick" label="Favored Set Pick" />
                        <SortTh col="result" label="Actual Score" />
                        <SortTh col="correct_sets" label="Verification" />
                      </>
                    )}

                    {tennisCategory === 'games' && (
                      <>
                        <SortTh col="exp_games" label="Exp Games (λ)" align="right" />
                        <SortTh col="games_line" label="Games Line" align="right" />
                        <SortTh col="pick" label="Model Call" />
                        <SortTh col="actual_games" label="Actual Games" align="right" />
                        <SortTh col="game_error" label="Game Error" align="right" />
                        <SortTh col="correct_games" label="Verification" />
                      </>
                    )}

                    {tennisCategory === 'decider' && (
                      <>
                        <SortTh col="decider_prob" label="P(Decider) %" align="right" />
                        <SortTh col="pick" label="Decider Call" />
                        <SortTh col="result" label="Actual Score" />
                        <SortTh col="correct_decider" label="Verification" />
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-700/60 font-medium">
                  {sortedTennis.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="px-4 py-16 text-center text-slate-500 italic">
                        <div className="flex flex-col items-center justify-center">
                          <CheckCircle2 className="w-8 h-8 text-slate-600 mb-2" />
                          <span className="text-slate-400 font-medium">No tracked predictions in ledger</span>
                          <span className="text-xs text-slate-600 mt-0.5">Historical predictions will appear here once verified</span>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    sortedTennis.map((t) => {
                      const isSettled = t.status !== 'PENDING';
                    const expGames = t.exp_total_games ?? t.sets_games?.expected_total_games ?? 22.5;
                    const gamesLine = t.games_line ?? t.sets_games?.main_games_line?.line ?? 22.5;
                    const deciderProb = t.sets_games?.prob_deciding_set ?? 48.0;

                    return (
                      <tr key={t.match_id} className="hover:bg-dark-700/30 transition-colors">
                        <td className="px-4 py-2.5 text-slate-400 font-mono text-[11px]">{t.date?.slice(0, 10)}</td>
                        <td className="px-4 py-2.5 text-sky-400 font-bold">{t.circuit}</td>
                        <td className="px-4 py-2.5 text-slate-200">{t.tourney_name}</td>
                        <td className="px-4 py-2.5 font-bold text-white">
                          {t.p1_name} vs {t.p2_name}
                        </td>

                        {tennisCategory === 'value' && (
                          <>
                            <td className="px-4 py-2.5 text-amber-400 font-semibold">{t.recommended_pick || t.predicted_winner || '-'}</td>
                            <td className="px-4 py-2.5 text-right font-mono text-slate-200">
                              {(t.recommended_pick === t.p1_name ? t.p1_prob : t.p2_prob)?.toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                              {t.best_odds ? t.best_odds.toFixed(2) : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono font-bold text-teal-400">
                              {t.best_edge != null ? `+${t.best_edge.toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono font-bold text-emerald-400">
                              {t.best_ev != null ? `+${t.best_ev.toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                              {t.stake != null ? `${t.stake.toFixed(0)}€` : (t.best_stake ? `${t.best_stake.toFixed(1)}%` : '-')}
                            </td>
                            <td className="px-4 py-2.5 font-mono font-bold text-slate-100">
                              {t.actual_winner ? `${t.actual_winner} (${t.score || 'Final'})` : (t.score || '-')}
                            </td>
                            <td className="px-4 py-2.5">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  t.status === 'WON'
                                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                    : t.status === 'LOST'
                                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                                    : t.status === 'VOID'
                                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                    : 'bg-slate-700 text-slate-400'
                                }`}
                              >
                                {t.status}
                              </span>
                            </td>
                            <td
                              className={`px-4 py-2.5 text-right font-mono font-bold ${
                                (t.pnl || 0) > 0
                                  ? 'text-emerald-400'
                                  : (t.pnl || 0) < 0
                                  ? 'text-rose-400'
                                  : 'text-slate-400'
                              }`}
                            >
                              {t.pnl ? `${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(2)}€` : '-'}
                            </td>
                          </>
                        )}

                        {tennisCategory === 'winner' && (
                          <>
                            <td className="px-4 py-2.5 text-right font-mono text-sky-400 font-bold">
                              {t.p1_prob?.toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-purple-400 font-bold">
                              {t.p2_prob?.toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 text-amber-400 font-semibold">
                              {t.predicted_winner || (t.p1_prob >= t.p2_prob ? t.p1_name : t.p2_name)}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.score || '-'}</td>
                            <td className="px-4 py-2.5 font-bold text-white">{t.actual_winner || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.correct_winner != null || t.model_correct != null ? (
                                  (t.correct_winner ?? t.model_correct) ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {tennisCategory === 'sets' && (
                          <>
                            <td className="px-4 py-2.5 text-right font-mono text-sky-400 font-bold">
                              {t.sets_games?.p1_win_at_least_1_set_prob ? `${t.sets_games.p1_win_at_least_1_set_prob.toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-purple-400 font-bold">
                              {t.sets_games?.p2_win_at_least_1_set_prob ? `${t.sets_games.p2_win_at_least_1_set_prob.toFixed(1)}%` : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-slate-200">
                              {t.p1_prob >= t.p2_prob ? `${t.p1_name} ≥1 Set` : `${t.p2_name} ≥1 Set`}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.score || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.correct_sets_at_least_1 != null ? (
                                  t.correct_sets_at_least_1 ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {tennisCategory === 'games' && (
                          <>
                            <td className="px-4 py-2.5 text-right font-mono text-slate-300">
                              {expGames.toFixed(1)}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono font-bold text-sky-400">
                              O/U {gamesLine}
                            </td>
                            <td className="px-4 py-2.5 text-slate-200 font-semibold">
                              {expGames >= gamesLine ? 'Over' : 'Under'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono font-bold text-white">
                              {t.actual_games != null ? t.actual_games : '-'}
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono text-slate-400">
                              {t.game_error != null ? `±${t.game_error.toFixed(1)} g` : '-'}
                            </td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.correct_games_ou != null ? (
                                  t.correct_games_ou ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}

                        {tennisCategory === 'decider' && (
                          <>
                            <td className="px-4 py-2.5 text-right font-mono font-bold text-amber-400">
                              {deciderProb.toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 text-slate-200 font-semibold">
                              {deciderProb >= 50.0 ? 'Deciding Set (3+ sets)' : 'Straight Sets'}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-slate-200">{t.score || '-'}</td>
                            <td className="px-4 py-2.5">
                              {isSettled ? (
                                t.correct_deciding_set != null ? (
                                  t.correct_deciding_set ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                      ✅ Hit
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                                      ❌ Miss
                                    </span>
                                  )
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700/60 text-slate-400 border border-slate-600/30">
                                    ⚪ Unreported
                                  </span>
                                )
                              ) : (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-700 text-slate-400">
                                  ⏳ Pending
                                </span>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  }))}
                </tbody>
              </table>
            </div>

            <div className="px-4 py-3 bg-dark-900/60 border-t border-dark-700 flex justify-between items-center text-xs text-slate-400">
              <div>
                📊 Showing <strong className="text-sky-400">{sortedTennis.length}</strong> tennis matches ({tennisTrackerMetrics.totalSettled} Settled)
              </div>
              <div>⚡ CourtVision Anti-Symmetric Ensembling & Markov Engine</div>
            </div>
          </div>
        </div>
      )}
        </>
      ) : (
        <div className="space-y-6">
          {!activeDiagnostics || activeDiagnostics.total_audited === 0 ? (
            <div className="bg-dark-800/80 border border-dark-700 rounded-xl p-8 text-center space-y-3">
              <ShieldCheck className="w-12 h-12 text-slate-500 mx-auto" />
              <h4 className="text-sm font-bold text-slate-200">No Settled Matches in Diagnostic Ledger</h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Post-mortem diagnostics run continuously on verified, settled matches. Once fixtures conclude and are marked settled, automated leak detection will appear here.
              </p>
            </div>
          ) : (
            <>
              {/* 1. KPI Diagnostics Scorecard */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>Audited Value Bets</span>
                    <Layers className="w-4 h-4 text-sky-400" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-white mt-2">
                    {activeDiagnostics.total_audited}
                  </div>
                  <div className="flex items-center justify-between mt-2 text-[11px]">
                    <span className="text-emerald-400 font-semibold">{activeDiagnostics.wins_count} Won</span>
                    <span className="text-slate-600">•</span>
                    <span className="text-rose-400 font-semibold">{activeDiagnostics.losses_count} Lost</span>
                    <span className="text-slate-500 font-mono">
                      ({((activeDiagnostics.wins_count / activeDiagnostics.total_audited) * 100).toFixed(1)}% WR)
                    </span>
                  </div>
                </div>

                <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>Variance Losses (Unlucky +EV)</span>
                    <ShieldCheck className="w-4 h-4 text-teal-400" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-teal-400 mt-2">
                    {activeDiagnostics.loss_breakdown.variance_losses}{' '}
                    <span className="text-xs text-slate-400 font-normal">
                      ({activeDiagnostics.loss_breakdown.variance_ratio_pct.toFixed(1)}%)
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-2">
                    Sound positive-EV bets lost to natural sports randomness. Do not overfit.
                  </p>
                </div>

                <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>Structural Model Flaws</span>
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-amber-400 mt-2">
                    {activeDiagnostics.loss_breakdown.structural_losses}{' '}
                    <span className="text-xs text-slate-400 font-normal">
                      ({(100 - activeDiagnostics.loss_breakdown.variance_ratio_pct).toFixed(1)}%)
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-2">
                    Negative closing edge or market mispricing. Prime targets for model adjustment.
                  </p>
                </div>

                <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>Active Leak Cohorts</span>
                    <ShieldAlert className="w-4 h-4 text-rose-400" />
                  </div>
                  <div className="text-2xl font-bold font-mono text-rose-400 mt-2">
                    {activeDiagnostics.active_leaks_count}
                  </div>
                  <div className="flex items-center justify-between mt-2 text-[11px]">
                    <span className="text-rose-300 font-semibold">
                      {activeDiagnostics.active_leaks.length} Sub-segments
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="text-emerald-400 font-semibold">
                      {activeDiagnostics.top_performers.length} Alpha Drivers
                    </span>
                  </div>
                </div>
              </div>

              {/* 2. Automated Guardrail Recommendations */}
              <div className="bg-dark-800/90 border border-dark-700 rounded-xl p-5 shadow-sm space-y-3">
                <div className="flex items-center gap-2 text-white font-bold text-sm">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <span>Automated Guardrail Recommendations & Policy Adjustments</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  {activeDiagnostics.recommendations.map((rec, i) => {
                    const isLeak = rec.includes('Cap or exclude') || rec.includes('Increase minimum EV') || rec.includes('Review');
                    const isStrength = rec.includes('Core strength');
                    return (
                      <div
                        key={i}
                        className={`p-3 rounded-lg border text-xs leading-relaxed flex items-start gap-2.5 ${
                          isLeak
                            ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                            : isStrength
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
                            : 'bg-dark-900 border-dark-700 text-slate-300'
                        }`}
                      >
                        <span className="text-sm shrink-0 mt-0.5">
                          {isLeak ? '🛑' : isStrength ? '🚀' : '⚖️'}
                        </span>
                        <span>{rec}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* 3. Cohort Breakdown & Leak Inspector */}
              <div className="bg-dark-800/90 border border-dark-700 rounded-xl overflow-hidden shadow-sm space-y-4 p-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-bold text-white flex items-center gap-2">
                      <TrendingDown className="w-4 h-4 text-sky-400" />
                      <span>Cohort Diagnostic Inspector</span>
                    </h4>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Slice historical bets by odds bracket, competition, market type, or venue to uncover hidden negative-ROI leaks.
                    </p>
                  </div>

                  {/* Search filter for cohorts */}
                  <input
                    type="text"
                    value={cohortSearch}
                    onChange={(e) => setCohortSearch(e.target.value)}
                    placeholder="Search cohort..."
                    className="bg-dark-900 border border-dark-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 w-full sm:w-48"
                  />
                </div>

                {/* Dimension Filter Tabs */}
                <div className="flex flex-wrap gap-1.5 border-b border-dark-700 pb-3">
                  {['ALL', 'Odds Bracket', 'Competition', 'Market Type', 'Venue'].map((dim) => (
                    <button
                      key={dim}
                      onClick={() => setSelectedDimension(dim)}
                      className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                        selectedDimension === dim
                          ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                          : 'bg-dark-900 text-slate-400 hover:text-white border border-dark-700'
                      }`}
                    >
                      {dim === 'ALL' ? '🌐 All Dimensions' : dim}
                    </button>
                  ))}
                </div>

                {/* Table of Cohorts */}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-dark-900/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-dark-700 text-[10px]">
                      <tr>
                        <th className="px-4 py-2.5">Cohort / Segment</th>
                        <th className="px-3 py-2.5">Dimension</th>
                        <th className="px-3 py-2.5 text-center">Bets</th>
                        <th className="px-3 py-2.5 text-center">Hit Rate</th>
                        <th className="px-3 py-2.5 text-right">Staked</th>
                        <th className="px-3 py-2.5 text-right">Net PnL</th>
                        <th className="px-3 py-2.5 text-right">ROI %</th>
                        <th className="px-4 py-2.5 text-center">Diagnostic Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dark-700/50">
                      {allCohorts.map((cohort, idx) => {
                        const isHighLeak = cohort.leak_severity === 'HIGH_LEAK';
                        const isModLeak = cohort.leak_severity === 'MODERATE_LEAK';
                        const isProfit = cohort.leak_severity === 'HIGH_PROFIT';

                        return (
                          <tr
                            key={idx}
                            className={`transition-colors hover:bg-dark-700/40 ${
                              isHighLeak
                                ? 'bg-rose-950/20'
                                : isModLeak
                                ? 'bg-amber-950/10'
                                : isProfit
                                ? 'bg-emerald-950/10'
                                : ''
                            }`}
                          >
                            <td className="px-4 py-2.5 font-semibold text-slate-200">
                              {cohort.cohort}
                            </td>
                            <td className="px-3 py-2.5 text-slate-400">
                              {cohort.dimension}
                            </td>
                            <td className="px-3 py-2.5 text-center font-mono text-slate-300">
                              {cohort.count}
                            </td>
                            <td className="px-3 py-2.5 text-center font-mono">
                              <span className="text-slate-200">{cohort.win_rate_pct.toFixed(1)}%</span>
                              <span className="text-[10px] text-slate-500 ml-1">
                                ({cohort.wins}/{cohort.count})
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono text-slate-400">
                              {cohort.total_staked.toFixed(1)}u
                            </td>
                            <td
                              className={`px-3 py-2.5 text-right font-mono font-bold ${
                                cohort.net_pnl > 0
                                  ? 'text-emerald-400'
                                  : cohort.net_pnl < 0
                                  ? 'text-rose-400'
                                  : 'text-slate-400'
                              }`}
                            >
                              {cohort.net_pnl > 0 ? '+' : ''}
                              {cohort.net_pnl.toFixed(2)}u
                            </td>
                            <td
                              className={`px-3 py-2.5 text-right font-mono font-bold ${
                                cohort.roi_pct > 0
                                  ? 'text-emerald-400'
                                  : cohort.roi_pct < 0
                                  ? 'text-rose-400'
                                  : 'text-slate-400'
                              }`}
                            >
                              {cohort.roi_pct > 0 ? '+' : ''}
                              {cohort.roi_pct.toFixed(1)}%
                            </td>
                            <td className="px-4 py-2.5 text-center">
                              {isHighLeak ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                                  <ShieldAlert className="w-3 h-3" /> High Leak
                                </span>
                              ) : isModLeak ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                  <AlertTriangle className="w-3 h-3" /> Moderate Leak
                                </span>
                              ) : isProfit ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                  <CheckCircle2 className="w-3 h-3" /> Alpha Driver
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                                  Stable
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
