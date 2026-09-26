"""Refresh and purge expired fixtures from upcoming datasets."""
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def update_dates():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Current Date UTC: {today}")

    # 1. Prune expired football fixtures from live_upcoming_fixtures.json
    fb_path = PROJECT_ROOT / "Football" / "data" / "cache" / "live_upcoming_fixtures.json"
    if fb_path.exists():
        with open(fb_path, "r", encoding="utf-8") as f:
            fb_data = json.load(f)
        matches = fb_data.get("matches", []) if isinstance(fb_data, dict) else fb_data
        active_fb = [m for m in matches if (m.get("date") or "")[:10] >= today]
        
        # Save back pruned cache
        out_payload = {
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "date": today,
            "matches": active_fb
        }
        with open(fb_path, "w", encoding="utf-8") as f:
            json.dump(out_payload, f, indent=2)
        print(f"Football: Pruned {len(matches) - len(active_fb)} past fixtures. Retained {len(active_fb)} active upcoming matches (>= {today}).")

    # 2. Prune expired Tennis fixtures (do not alter dates or invent rounds)
    tn_path = PROJECT_ROOT / "Tennis" / "data" / "upcoming" / "upcoming_matches.json"
    if tn_path.exists():
        with open(tn_path, "r", encoding="utf-8") as f:
            tn_matches = json.load(f)
        active_tn = [m for m in tn_matches if (m.get("date") or "")[:10] >= today]
        with open(tn_path, "w", encoding="utf-8") as f:
            json.dump(active_tn, f, indent=2)
        print(f"Tennis: Pruned {len(tn_matches) - len(active_tn)} past fixtures. Retained {len(active_tn)} active upcoming matches (>= {today}).")

if __name__ == "__main__":
    update_dates()

