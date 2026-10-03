# Football engine (`football_core`)

Domestic-league models for EPL, LaLiga, Serie A, Bundesliga, Ligue 1, Belgium, Eredivisie,
Primeira Liga and the Scottish Premiership, plus European cups and internationals.

* `data/`: football-data.co.uk seasons, ESPN fixtures/odds/results, The Odds API and API-Football
  (both optional, key-gated), Understat xG.
* `features/`: Elo, regularised Dixon-Coles, rolling form, head-to-head, referee profiles and
  shared corners/cards projections; one `_match_features()` serves training and inference.
* `models/`: calibrated LightGBM (1X2, O/U 2.5, BTTS) blended with Dixon-Coles and then with the
  vig-free market price; the international model lives in `train_international.py`.
* `betting/tracker.py`: the football prediction ledger.

Setup, running and current performance: see the repository root `README.md`.
