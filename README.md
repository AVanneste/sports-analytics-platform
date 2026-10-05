# Odds archive

Belgian bookmaker prices (Unibet.be and Bingoal, from Kambi's public feed) captured hourly for
matches kicking off within 75 minutes, one CSV per capture day in `snapshots/`. Written by
`.github/workflows/odds_collector.yml` on `main`; the daily run takes each match's last snapshot
before kick-off as its closing price (CLV). Kept off `main` so its history stays clean.
