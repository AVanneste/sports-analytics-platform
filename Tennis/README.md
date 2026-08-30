# 🎾 CourtVision: Tennis Outcome & Value Betting Engine (ATP & WTA)

An end-to-end tennis match outcome prediction platform and value betting engine for both **ATP** and **WTA** tours.

CourtVision models player performance dynamically across court surfaces (**Hard**, **Clay**, **Grass**), tracks head-to-head records and rolling momentum, trains calibrated gradient-boosted models, identifies market mispricings against bookmaker odds (**Expected Value** & **Kelly Staking**), and provides a **continuous post-match result tracking & feedback loop**.

---

## 🌟 Key Capabilities

### 1. 🏟️ Surface-Specific Dynamic Elo Engine
- Match-by-match dynamic ratings computed chronologically with zero lookahead bias.
- Separate Elo ratings for:
  - **Overall Elo**
  - **Hard Court Elo**
  - **Clay Court Elo**
  - **Grass Court Elo**
- **Experience-weighted surface adaptation**: dynamically blends surface Elo with overall Elo based on a player's sample size on the target surface.

### 2. ⚡ Momentum, Form & Matchup Features
- **Rolling Form**: Win % over last 5, 10, and 20 matches.
- **Surface Form (1-Year)**: Rolling 365-day win rate on the specific court surface.
- **Sets Ratio**: Percentage of sets won over recent matches.
- **Fatigue & Rest**: Days of rest since last match and 30-day match load.
- **Head-to-Head (H2H)**: Overall career H2H win rates and surface-specific H2H history.
- **Rankings**: Current ATP/WTA rank, career-high (best) rank, and log rank ratio.

### 3. 🤖 Machine Learning Modeling & Probability Calibration
- Symmetrical feature matrix pairing ($P_1$ vs $P_2$ and $P_2$ vs $P_1$) to eliminate positional bias.
- **LightGBM Classifier** with **Sigmoid Probability Calibration** to ensure unskewed, mathematically accurate probabilities for betting analysis.
- Walk-forward chronological validation (Train on past seasons, test on out-of-time subsequent seasons).

### 4. 💰 Betting Odds & Value Detection Engine
- Ingests market decimal odds and eliminates bookmaker margin (vig / overround).
- **Expected Value (EV)** calculation:
  $$\text{EV} = (P_{\text{model}} \times \text{Odds}) - 1$$
- **Fractional Kelly Criterion Staking** recommendation:
  $$f^* = \text{fraction} \times \frac{P_{\text{model}} \times (\text{Odds} - 1) - (1 - P_{\text{model}})}{\text{Odds} - 1}$$
- Visual indicators for high-value opportunities ($\text{EV} > 3\%$).

### 5. 🔄 Post-Match Result Tracking & Feedback Loop
- **Prediction Archive**: Automatically logs every prediction, snapshot odds, and timestamp.
- **Result Reconciliation**: Compares predictions against true match scores and grades outcomes (Won / Lost / PnL).
- **Realized Performance & PnL**: Tracks Out-of-Sample Accuracy, Brier Calibration Score, Cumulative Profit/Loss ($), and ROI (%) under both Kelly Staking and Flat Staking strategies.
- **Continuous Feedback**: Incrementally updates player Elo ratings and form metrics as new matches conclude.

---

## 🚀 Quick Start

### 1. Activate Environment & Install Dependencies
```bash
# In the repository root
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Pipeline (Fetch Data, Train Models & Generate Predictions)
```bash
# Run full pipeline end-to-end
python run_pipeline.py --all

# Or run individual stages:
python run_pipeline.py --fetch     # Download latest historical data & odds
python run_pipeline.py --train     # Build surface features and train LightGBM models
python run_pipeline.py --predict   # Run predictions on upcoming matches
python run_pipeline.py --reconcile # Reconcile pending bets with match outcomes
```

### 3. Launch Interactive Streamlit Dashboard
```bash
streamlit run app/main.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📱 Dashboard Overview

1. **🎾 Upcoming & Value Bets**: View upcoming week's ATP & WTA matches, predicted win %, market odds comparison, expected value tags, Kelly stake suggestions, and key match drivers.
2. **⚔️ Match Simulator**: Pick any two ATP/WTA players and simulate a matchup on Hard, Clay, or Grass with customizable market odds.
3. **📈 Betting Tracker & PnL**: View realized accuracy, Brier score, cumulative PnL curve ($), and grade pending match outcomes.
4. **👤 Player Explorer**: Look up any player's career Elo curve, surface Elo ratings (Hard, Clay, Grass), and leaderboard position.
5. **🔬 Model Performance**: Inspect LightGBM feature importances, ROC-AUC, Log-Loss, and calibration reliability.

---

## 📂 Repository Structure

```
AG_sports_data/
├── app/
│   ├── main.py             # Streamlit entry point
│   └── views/
│       ├── upcoming.py     # Upcoming matches & value bets view
│       ├── simulator.py    # Custom matchup simulator
│       ├── tracker_view.py # Graded results, PnL curve & reconciliation
│       ├── player_view.py  # Player profiles & surface Elo breakdown
│       └── performance.py  # Model metrics & feature importance
├── src/
│   ├── config.py           # Configuration, constants & paths
│   ├── data/
│   │   ├── fetcher.py      # Historical match & odds dataset downloader
│   │   ├── preprocessor.py # Data cleaning & rank standardization
│   │   └── scraper.py      # Upcoming fixtures & odds schedule
│   ├── features/
│   │   ├── elo.py          # Dynamic Surface-specific Elo Engine
│   │   ├── h2h.py          # Head-to-Head tracking
│   │   ├── form.py         # Rolling form & momentum calculator
│   │   └── builder.py      # Symmetrical training feature matrix builder
│   ├── models/
│   │   ├── train.py        # LightGBM training & probability calibration
│   │   ├── predictor.py    # Match inference wrapper
│   │   └── explain.py      # Key factor explainability
│   ├── betting/
│   │   ├── value.py        # EV, vig removal & Kelly staking
│   │   └── tracker.py      # Result reconciliation & PnL tracking
│   └── utils/
│       └── helpers.py      # Data helpers & name normalization
├── run_pipeline.py         # CLI pipeline runner
├── requirements.txt
└── README.md
```

