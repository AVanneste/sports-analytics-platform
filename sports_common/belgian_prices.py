"""Which Belgian book's price a selection uses: Napoleon first (the book bets are placed at),
else the best of Unibet and Bingoal; and when another book pays clearly more."""
from typing import Dict, Tuple

PREFERRED_BOOK = "napoleon"
BETTER_ELSEWHERE_MIN = 0.03  # another book paying at least 3% more is worth a note
BOOK_NAMES = {"napoleon": "Napoleon", "unibet": "Unibet", "bingoal": "Bingoal"}


def choose_prices(books: Dict[str, Dict[str, float]]) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, Dict]]:
    """(price per field, book per field, better_elsewhere per field) from {book: {field: price}}."""
    prices, sources, better = {}, {}, {}
    fields = {f for odds in books.values() for f, v in odds.items() if v}
    for field in fields:
        offers = {book: odds[field] for book, odds in books.items() if odds.get(field)}
        if PREFERRED_BOOK in offers:
            book = PREFERRED_BOOK
        else:
            book = max(offers, key=offers.get)
        prices[field], sources[field] = offers[book], book
        rival = max((b for b in offers if b != book), key=offers.get, default=None)
        if book == PREFERRED_BOOK and rival and offers[rival] >= offers[book] * (1 + BETTER_ELSEWHERE_MIN):
            better[field] = {"book": rival, "odds": offers[rival]}
    return prices, sources, better


def price_label(sources: Dict[str, str], main_field: str) -> str:
    """'Napoleon' when the main market is Napoleon's price, else the books it came from."""
    if sources.get(main_field) == PREFERRED_BOOK:
        return BOOK_NAMES[PREFERRED_BOOK]
    others = sorted({BOOK_NAMES.get(b, b) for b in sources.values() if b != PREFERRED_BOOK})
    return f"Best of {', '.join(others)} (not on Napoleon)" if others else BOOK_NAMES[PREFERRED_BOOK]


FOOTBALL_SELECTION_FIELDS = {
    "Home Win": "odds_home", "Draw": "odds_draw", "Away Win": "odds_away",
    "Over 2.5 Goals": "odds_over25", "Under 2.5 Goals": "odds_under25", "BTTS Yes": "odds_btts_yes",
    "BTTS No": "odds_btts_no", "Over 9.5 Corners": "odds_corners_over95", "Under 9.5 Corners": "odds_corners_under95",
}


def pick_note(fixture: Dict, field: str) -> Dict:
    """{book: where the selection's price is, better_elsewhere: 'Unibet pays 1.98'} (keys only when known)."""
    note = {}
    book = (fixture.get("price_books") or {}).get(field)
    if book:
        note["book"] = BOOK_NAMES.get(book, book)
    better = (fixture.get("better_elsewhere") or {}).get(field)
    if better:
        note["better_elsewhere"] = f"{BOOK_NAMES.get(better['book'], better['book'])} pays {better['odds']:.2f}"
    return note


def annotate_football_pick(pick, fixture: Dict):
    """The pick with its book and any better price elsewhere (unchanged when not a priced selection)."""
    if not isinstance(pick, dict):
        return pick
    field = FOOTBALL_SELECTION_FIELDS.get(str(pick.get("selection")))
    return {**pick, **pick_note(fixture, field)} if field else pick


def tennis_pick_note(fixture: Dict, pick: str, p1_names: tuple, p2_names: tuple) -> Dict:
    """Book note for a tennis pick, given the names player 1 and player 2 may go by."""
    field = "p1_odds" if pick in p1_names else "p2_odds" if pick in p2_names else None
    return pick_note(fixture, field) if (field and pick) else {}
