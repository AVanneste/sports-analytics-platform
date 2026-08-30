# ⚽ PitchVision: Football Outcome & Value Betting Engine (Top 5 European Leagues)

An end-to-end predictive analytics platform and value betting engine for Europe's top 5 football leagues:
- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 **Premier League** (`EPL` / `E0`)
- 🇪🇸 **La Liga** (`LaLiga` / `SP1`)
- 🇮🇹 **Serie A** (`SerieA` / `I1`)
- 🇩🇪 **Bundesliga** (`Bundesliga` / `D1`)
- 🇫🇷 **Ligue 1** (`Ligue1` / `F1`)

---

## 🌟 Key Architectural Pillars

### 1. 🏟️ Dynamic Football Elo Engine
- Chronological, lookahead-free rating engine.
- World Football Elo goal-difference margin multiplier:
  $$\Delta R = K \cdot G \cdot (S - E)$$
  where $G = 1$ for 0-1 GD, $1.5$ for 2 GD, and $(11 + |GD|)/8$ for $3+$ GD.
- Separate home advantage parameter ($\approx +65$ Elo points).

### 2. 🎯 Dixon-Coles & Poisson Goal Expectancy Engine
- Bivariate Poisson model with low-score correlation adjustment ($\rho$ parameter) for scorelines `0-0`, `1-0`, `0-1`, and `1-1`.
- Fits attacking strengths ($\alpha_i$) and defensive weaknesses ($\beta_j$) for each club.
- Computes complete $(6 \times 6)$ joint score probability matrices, exact scoreline distributions, Over/Under 2.5, and Both Teams to Score (BTTS).

### 3. ⚡ Rolling Form, Shot Efficiency & Rest Indices
- Rolling points per game (PPG) over 5 and 10 matches.
- Total Shots Ratio (TSR) and Shots on Target Ratio (SoTR).
- Corner differential and home/away specific venue splits.
- Rest days and schedule congestion index (matches played in prior 21 days).

### 4. 🤖 Calibrated Machine Learning Models
- Multi-class **LightGBM** (Home / Draw / Away) + **Sigmoid Probability Calibration**.
- Binary **LightGBM** for Over/Under 2.5 Goals.
- Binary **LightGBM** for Both Teams to Score (BTTS).
- Ensembled with Dixon-Coles analytical distributions for robust out-of-sample generalization.

### 5. 💰 Market Vig Removal & Value Staking Engine
- Proportional margin removal across multi-bookmaker odds.
- **Expected Value (EV)** calculation:
  $$\text{EV} = (P_{\text{model}} \times \text{Odds}) - 1$$
- **Fractional Kelly Criterion Staking**:
  $$f^* = c \times \frac{b \cdot p - q}{b}$$

### 6. 🔄 Continuous Results Tracking & Reconciliation Feedback Loop
- Full prediction ledger persisted to disk.
- One-click reconciliation against final match scorelines.
- Realized PnL ($), ROI (%), and Multi-class Brier calibration scores.

---

## 🚀 Quick Start

### 1. Activate Environment
```bash
# In the repository root
source ../.venv/bin/activate
```

### 2. Run Pipeline (Fetch Data, Train Models & Generate Predictions)
```bash
# Run full pipeline end-to-end for all 5 leagues
python run_pipeline.py --all

# Or run individual stages:
python run_pipeline.py --fetch
python run_pipeline.py --train
python run_pipeline.py --predict
```

### 3. Launch Streamlit UI
```bash
streamlit run app/main.py
```

