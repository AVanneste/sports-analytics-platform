"""Export consolidated sports analytics payload for the modern web frontend."""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WebExporter")


def load_json_safe(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error reading {path}: {e}")
        return default


def build_web_payload() -> Dict[str, Any]:
    """Generate a clean, high-performance JSON payload for the Next.js / React frontend."""
    logger.info("Building consolidated web payload...")

    # 1. Pipeline Run Metadata
    meta_path = PROJECT_ROOT / "cache" / "pipeline_run_meta.json"
    meta = load_json_safe(meta_path, {})

    # 2. Football Tracker & Upcoming
    fb_tracker_path = PROJECT_ROOT / "Football" / "data" / "cache" / "predictions_tracker.json"
    fb_raw_tracker = load_json_safe(fb_tracker_path, [])
    fb_tracker = fb_raw_tracker if isinstance(fb_raw_tracker, list) else fb_raw_tracker.get("predictions", [])

    fb_upcoming_path = PROJECT_ROOT / "Football" / "data" / "cache" / "live_upcoming_fixtures.json"
    fb_upcoming_raw = load_json_safe(fb_upcoming_path, {})
    fb_upcoming = fb_upcoming_raw.get("matches", []) if isinstance(fb_upcoming_raw, dict) else (fb_upcoming_raw or [])

    # Compute Football KPI summary
    fb_settled = [m for m in fb_tracker if m.get("status") == "settled"]
    fb_pending = [m for m in fb_tracker if m.get("status") in ("pending", "Pending")]
    fb_wins = sum(1 for m in fb_settled if m.get("won"))
    fb_total_settled = len(fb_settled)
    fb_flat_pnl = sum(float(m.get("flat_pnl", 0.0)) for m in fb_settled)
    fb_kelly_pnl = sum(float(m.get("kelly_pnl", 0.0)) for m in fb_settled)
    fb_win_rate = round((fb_wins / fb_total_settled * 100), 1) if fb_total_settled > 0 else 0.0

    # 3. Tennis Tracker & Upcoming
    tn_archive_path = PROJECT_ROOT / "Tennis" / "data" / "tracker" / "predictions_archive.json"
    tn_tracker = load_json_safe(tn_archive_path, [])

    tn_upcoming_path = PROJECT_ROOT / "Tennis" / "data" / "upcoming" / "upcoming_matches.json"
    tn_upcoming = load_json_safe(tn_upcoming_path, [])

    tn_metrics_path = PROJECT_ROOT / "Tennis" / "data" / "processed" / "model_metrics.json"
    tn_metrics = load_json_safe(tn_metrics_path, {})

    # Compute Tennis KPI summary
    tn_settled = [m for m in tn_tracker if m.get("status") in ("WON", "LOST", "SETTLED")]
    tn_pending = [m for m in tn_tracker if m.get("status") == "PENDING"]
    tn_wins = sum(1 for m in tn_settled if m.get("status") == "WON")
    tn_total_settled = len(tn_settled)
    tn_pnl = sum(float(m.get("pnl", 0.0)) for m in tn_settled)
    tn_win_rate = round((tn_wins / tn_total_settled * 100), 1) if tn_total_settled > 0 else 0.0

    # 4. Value Bet Highlights
    fb_value_bets = [m for m in fb_upcoming if m.get("has_value") or (m.get("best_pick", {}).get("ev", 0) > 0.03)]
    tn_value_bets = [m for m in tn_upcoming if m.get("has_value") or m.get("best_ev", 0) > 3.0]

    payload = {
        "timestamp": datetime.now().isoformat(),
        "generated_at_unix": time.time(),
        "summary": {
            "overall_status": meta.get("status", "HEALTHY"),
            "last_pipeline_run": meta.get("last_run_timestamp"),
            "football": {
                "settled_count": fb_total_settled,
                "pending_count": len(fb_pending),
                "upcoming_count": len(fb_upcoming),
                "win_rate_pct": fb_win_rate,
                "flat_pnl": round(fb_flat_pnl, 2),
                "kelly_pnl": round(fb_kelly_pnl, 2),
                "value_bets_count": len(fb_value_bets),
            },
            "tennis": {
                "settled_count": tn_total_settled,
                "pending_count": len(tn_pending),
                "upcoming_count": len(tn_upcoming),
                "win_rate_pct": tn_win_rate,
                "total_pnl": round(tn_pnl, 2),
                "atp_accuracy": tn_metrics.get("atp", {}).get("accuracy"),
                "atp_auc": tn_metrics.get("atp", {}).get("roc_auc"),
                "wta_accuracy": tn_metrics.get("wta", {}).get("accuracy"),
                "wta_auc": tn_metrics.get("wta", {}).get("roc_auc"),
                "value_bets_count": len(tn_value_bets),
            }
        },
        "football": {
            "upcoming": fb_upcoming,
            "tracker": fb_tracker[:150],  # Latest 150 for snappy mobile load
            "value_bets": fb_value_bets,
        },
        "tennis": {
            "upcoming": tn_upcoming,
            "tracker": tn_tracker[:150],
            "metrics": tn_metrics,
            "value_bets": tn_value_bets,
        }
    }

    # Save to public data destinations
    out_paths = [
        PROJECT_ROOT / "cache" / "sports_web_data.json",
    ]

    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info(f"Saved {p.name} ({p.stat().st_size / 1024:.1f} KB)")

    return payload


if __name__ == "__main__":
    build_web_payload()
