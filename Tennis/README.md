# Tennis engine (`tennis_core`)

ATP and WTA match-winner models.

* `data/`: tennis-data.co.uk seasons, Jeff Sackmann serve/return statistics, ESPN schedules and
  results, The Odds API (optional, key-gated), official rankings and player profiles.
* `features/`: surface-aware Elo, form, head-to-head, serve/return dominance and leak-free rolling
  Sackmann stats; each match yields a mirrored pair of training rows.
* `models/`: calibrated LightGBM with pair-aware chronological splits, sets/games projections.
* `betting/`: value analysis (market-shrunk probabilities, EV cap) and the tennis ledger.

Setup, running and current performance: see the repository root `README.md`.
