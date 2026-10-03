# Football engine (`football_core`)

Domestic-league models for EPL, LaLiga, Serie A, Bundesliga, Ligue 1, Belgium, Eredivisie,
Primeira Liga and the Scottish Premiership, plus European cups and internationals.

* `data/`: football-data.co.uk seasons, ESPN fixtures/odds/results, The Odds API and API-Football
  (both optional, key-gated), and Understat xG for the top five leagues (`xg_scraper.py`).
* `features/`:
  * Elo;
  * Dixon-Coles fitted on goals blended with shots on target and xG, with time decay, ridge
    shrinkage and a below-average prior for promoted sides;
  * rolling form, head-to-head and referee profiles;
  * team count models for corners and cards (`count_model.py`).

  One `_match_features()` serves training and inference.
* `models/`:
  * calibrated LightGBM (1X2, O/U 2.5, BTTS), blended with Dixon-Coles and then with the
    vig-free market price;
  * `backtest.py`, the walk-forward accuracy harness;
  * `train_international.py`, the international model.
* `betting/tracker.py`: the football prediction ledger.

Setup, running and current performance: see the repository root `README.md`.
