"""Player ages from the Wikidata birth-date table (data/raw/player_birthdates.csv, see birthdates.py)."""
from datetime import datetime, date
from typing import Optional

from tennis_core.data.birthdates import birthdate_for


def get_player_age(player_name: str, as_of_date: Optional[date] = None) -> Optional[int]:
    """Player's age in whole years on ``as_of_date`` (today by default); None when the birth date is unknown."""
    if not player_name:
        return None
    bdate_str = birthdate_for(player_name)
    if not bdate_str:
        return None
    ref_date = as_of_date or date.today()
    if isinstance(ref_date, datetime):
        ref_date = ref_date.date()
    born = date.fromisoformat(bdate_str)
    return ref_date.year - born.year - ((ref_date.month, ref_date.day) < (born.month, born.day))
