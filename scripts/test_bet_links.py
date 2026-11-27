"""One-off: which link formats open each bookmaker's bet slip with a selection already on it?

    python scripts/test_bet_links.py [--send]

Picks an upcoming soccer home-win price at Unibet, Bingoal, Napoleon, Golden Palace and Ladbrokes and
prints (or sends to Telegram with --send) labelled candidate links. Tap each on the phone you bet with;
the formats that open a pre-filled slip are wired into the alerts (sports_common/belgian_board.py).
Kambi's coupon parameter (single|<outcome>|<stake>|replace) is used by other Kambi books; the Napoleon,
Golden Palace and Ladbrokes candidates are guesses (no published format).
"""
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

from sports_common.belgian_board import fetch_altenar_board, fetch_eurobet_board, fetch_kambi_board, fetch_superbet_list, parse_superbet_event


def pick(rows: List[Dict], book: str, now: datetime) -> Optional[Dict]:
    """The earliest home-win price at ``book`` kicking off 12 to 40 hours from now (time to test), with an outcome id."""
    when = lambda r: datetime.fromisoformat(str(r["start"]).replace("Z", "+00:00"))
    ok = [r for r in rows if r["book"] == book and r["market"] == "moneyline" and r["period"] == 0 and r["selection"] == "home"
          and r.get("outcome_id") not in (None, "") and now + timedelta(hours=12) <= when(r) <= now + timedelta(hours=40)]
    return min(ok, key=when) if ok else None


def candidates(row: Dict) -> List[tuple]:
    """(code, description, link) to try for one price row."""
    book, url, oid = row["book"], row["url"], row["outcome_id"]
    if book == "unibet":
        return [("U1", "coupon, plain |", f"{url}?coupon=single|{oid}||replace"),
                ("U2", "coupon, | encoded", f"{url}?coupon=" + quote(f"single|{oid}||replace", safe="")),
                ("U3", "coupon with a 1 EUR stake", f"{url}?coupon=single|{oid}|1|append"),
                # Unibet's iPhone app claims /betting/sports/event/live/* (not the pre-match path): may open the app
                ("U4", "app route (live path)", url.replace("/betting/sports/event/", "/betting/sports/event/live/") + f"?coupon=single|{oid}||replace")]
    if book == "bingoal":
        event = str(row["event_id"])
        return [("B1", "coupon, plain |", f"{url}?coupon=single|{oid}||replace"),
                ("B2", "coupon, | encoded", f"{url}?coupon=" + quote(f"single|{oid}||replace", safe="")),
                ("B3", "hash route", f"https://www.bingoalsport.be/fr/Sports#event/{event}?coupon=single|{oid}|")]
    if book == "napoleon":
        bet = quote(f"{row['event_id']},{oid},{row.get('sbv') or ''},0,{row.get('odd_uuid')}", safe="")
        return [("N1", "betslip page", f"https://napoleonsports.be/en-be/betslip?bets[]={bet}"),
                ("N2", "match page + bet", f"{url}&bets[]={bet}")]
    if book == "goldenpalace":
        return [("G1", "selection on the match page", f"{url}?selection={oid}"),
                ("G2", "betslip route", f"https://www.goldenpalacesports.be/fr#/betslip/{oid}"),
                # the app claims /mobile_app/* ("path for redirection to a mobile app")
                ("G3", "app route", url.replace("goldenpalacesports.be/fr#", "goldenpalacesports.be/mobile_app/fr#"))]
    if book == "ladbrokes":
        return [("L1", "selection on the match page", f"{url}?selection=" + quote(str(oid), safe=""))]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--send", action="store_true", help="send the links to Telegram instead of printing them")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    rows = fetch_kambi_board("Soccer", within_hours=40, now=now)
    rows += [r for e in fetch_superbet_list(within_hours=40, now=now) if e.get("sportId") == 5 for r in parse_superbet_event(e, e.get("odds") or [])]
    rows += fetch_altenar_board("Soccer", within_hours=40, now=now) + fetch_eurobet_board("Soccer", within_hours=40, now=now)
    lines = ["🔗 Bet-slip link test. Tap each link: does the bookmaker open with the pick already on the slip?",
             "Reply in the Claude chat with the codes that work (e.g. U1 B3), and say which ones opened the app. Nothing is bet: you only look.",
             "Tip: turn off Telegram's in-app browser first (Telegram settings, Chat Settings / Data and Storage, 'In-App Browser' or 'Open links in'), otherwise no link can open an app."]
    for book in ("unibet", "bingoal", "napoleon", "goldenpalace", "ladbrokes"):
        row = pick(rows, book, now)
        if row is None:
            lines.append(f"\n{book.capitalize()}: no upcoming soccer price found")
            continue
        lines.append(f"\n{book.capitalize()}: {row['home']} – {row['away']}, {row['home']} to win @ {row['price']:.2f}")
        lines += [f"{code} ({what}):\n{link}" for code, what, link in candidates(row)]
    text = "\n".join(lines)
    if args.send:
        from sports_common.notify import send
        print("sent" if send([text]) else "Telegram send failed")
    else:
        print(text)


if __name__ == "__main__":
    main()
