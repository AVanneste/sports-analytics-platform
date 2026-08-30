# 🏆 OmniVision AI: Football & Tennis Outcome Prediction & Value Engines

An all-in-one predictive machine learning platform and automated value betting system for **Football (PitchVision)** and **Tennis (CourtVision)**.

---

## 🌟 Highlights & Features

### ⚽ PitchVision (Football Engine)
- **12 European Competitions**: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Belgian Pro League, Eredivisie, Liga Portugal, Scottish Premiership, UEFA Champions League, Europa League, and Conference League.
- **Dynamic Football Elo Engine**: Continuous rating tracking with goal-difference margin multipliers and home field advantage modeling.
- **Dixon-Coles & Bivariate Poisson**: Joint score probability distributions, exact scoreline matrices, Over/Under 2.5, and Both Teams to Score (BTTS).
- **Player & Referee Disciplinary Props**: Yellow/Red cards, total fouls, and corner expectancy modeling.
- **Calibrated LightGBM Classifiers**: Multi-class match outcome and props predictions calibrated with Platt Sigmoid Scaling.
- **Kelly Criterion & Value Engine**: Multiplicative vig removal with fractional Quarter-Kelly bankroll allocation.
- **Continuous Results Reconciliation**: Full prediction ledger with automated scoreline verification and Brier calibration scores.

### 🎾 CourtVision (Tennis Engine)
- **ATP & WTA Tours**: Comprehensive coverage of Grand Slams, Masters 1000, WTA 1000, 500, 250, and Tour Finals.
- **Surface-Aware Elo Engine**: Surface-specific ratings (Hard, Clay, Grass) with tournament tier weighting.
- **Serve & Return Dominance**: Service hold %, return break %, and pressure-point conversion tracking.
- **Head-to-Head & Form Dynamics**: Surface-specific H2H metrics, fatigue indices, and rest-day adjustments.
- **Automated 48-Hour Sync**: Auto-refresh for live tournament draws, odds feeds, and rankings.
- **Interactive Match Simulator**: Custom head-to-head simulations with surface selection and Kelly staking advice.

---

## 🚀 Quick Start

### 1. Prerequisites & Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/your-username/AG_sports_data.git
cd AG_sports_data

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch Streamlit Application

```bash
streamlit run app.py
```

The unified app will open in your browser, allowing you to toggle seamlessly between **⚽ Football (PitchVision)** and **🎾 Tennis (CourtVision)** via the sidebar!

---

## ☁️ Deploying to Streamlit Community Cloud

1. Push this repository to your **GitHub** account:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Unified Football & Tennis AI Engine"
   git remote add origin https://github.com/<your-github-username>/AG_sports_data.git
   git branch -M main
   git push -u origin main
   ```

2. Navigate to [share.streamlit.io](https://share.streamlit.io/) and log in with your GitHub account.
3. Click **New app** and select:
   - **Repository**: `<your-github-username>/AG_sports_data`
   - **Branch**: `main`
   - **Main file path**: `app.py` (or `streamlit_app.py`)
4. *(Optional)* Add your `ODDS_API_KEY` under **Advanced settings -> Secrets**:
   ```toml
   ODDS_API_KEY = "your_api_key_here"
   ```
5. Click **Deploy!** 🚀

---

## 🛠️ CLI Pipeline Runners

You can also run automated data fetching, feature engineering, and model training pipelines directly from the terminal:

### Football Pipeline
```bash
python Football/run_pipeline.py --all
```

### Tennis Pipeline
```bash
python Tennis/run_pipeline.py --all
```

---

## 📂 Project Structure

```
AG_sports_data/
├── app.py                      # Unified Streamlit entrypoint
├── streamlit_app.py            # Streamlit Cloud deployment alias
├── compat.py                   # Model unpickling backwards compatibility bridge
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
├── README.md                   # Platform documentation
├── Football/                   # PitchVision Platform
│   ├── football_core/          # Core models, features, data pipelines, betting engine
│   ├── football_app/           # Streamlit view components (Upcoming, Simulator, etc.)
│   ├── models_saved/           # Pre-trained LightGBM bundles
│   ├── data/                   # Historical and processed parquet datasets
│   └── run_pipeline.py         # CLI pipeline runner
└── Tennis/                     # CourtVision Platform
    ├── tennis_core/            # Core models, features, data pipelines, betting engine
    ├── tennis_app/             # Streamlit view components (Upcoming, Simulator, etc.)
    ├── models_saved/           # Pre-trained ATP & WTA models and scalers
    ├── data/                   # Historical tournament datasets & prediction archives
    └── run_pipeline.py         # CLI pipeline runner
```

