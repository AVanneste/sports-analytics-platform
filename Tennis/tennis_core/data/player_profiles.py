"""Player demographics and birth date registry for age computation."""
from datetime import datetime, date
from typing import Dict, Optional
from tennis_core.utils.helpers import strip_accents, match_player_to_database

# Known birth dates (YYYY-MM-DD) for ATP and WTA players
PLAYER_BIRTHDATES: Dict[str, str] = {
    # ATP Top Players & Active Competitors
    "Sinner J.": "2001-08-16",
    "Alcaraz C.": "2003-05-05",
    "Djokovic N.": "1987-05-22",
    "Zverev A.": "1997-04-20",
    "Medvedev D.": "1996-02-11",
    "Fritz T.": "1997-10-28",
    "De Minaur A.": "1999-02-17",
    "Rublev A.": "1997-10-20",
    "Ruud C.": "1998-12-22",
    "Dimitrov G.": "1991-05-16",
    "Tsitsipas S.": "1998-08-12",
    "Hurkacz H.": "1997-02-11",
    "Paul T.": "1997-05-17",
    "Shelton B.": "2002-10-09",
    "Tiafoe F.": "1998-01-20",
    "Fils A.": "2004-06-12",
    "Musetti L.": "2002-03-03",
    "Baez S.": "2000-12-28",
    "Darderi L.": "2002-02-14",
    "Machac T.": "2000-10-13",
    "Lehecka J.": "2001-11-08",
    "Auger-Aliassime F.": "2000-08-08",
    "Shapovalov D.": "1999-04-15",
    "Berrettini M.": "1996-04-12",
    "Carreno Busta P.": "1991-07-12",
    "Norrie C.": "1995-08-23",
    "Struff J.L.": "1990-04-25",
    "Monfils G.": "1986-09-01",
    "Wawrinka S.": "1985-03-28",
    "Nishikori K.": "1989-12-29",
    "Fucsovics M.": "1992-02-08",
    "Rinderknech A.": "1995-07-23",
    "Sonego L.": "1995-05-11",
    "Munar J.": "1997-05-05",
    "Van De Zandschulp B.": "1995-10-04",
    "Van Assche L.": "2004-05-03",
    "Shang J.": "2005-02-02",
    "Michelsen A.": "2004-08-25",
    "Mensik J.": "2005-09-01",
    "Cazaux A.": "2002-08-23",
    "Fonseca J.": "2006-08-21",
    "Prizmic D.": "2005-08-05",
    "Shevchenko A.": "2000-11-29",
    "Wu Y.": "1999-10-14",
    "Zhang Z.": "1996-10-16",
    "Kovacevic A.": "1998-08-29",
    "Marozsan F.": "1999-10-08",
    "Kecmanovic M.": "1999-08-31",
    "Halys Q.": "1996-10-26",
    "Hijikata R.": "2001-02-23",
    "Walton A.": "1999-04-17",
    "Majchrzak K.": "1996-01-13",
    "Medjedovic H.": "2003-07-18",
    "Guerrieri A.": "1998-12-03",

    # WTA Top Players & Active Competitors
    "Swiatek I.": "2001-05-31",
    "Sabalenka A.": "1998-05-05",
    "Gauff C.": "2004-03-13",
    "Rybakina E.": "1999-06-17",
    "Pegula J.": "1994-02-24",
    "Paolini J.": "1996-01-04",
    "Zheng Q.": "2002-10-08",
    "Navarro E.": "2001-05-18",
    "Krejcikova B.": "1995-12-18",
    "Ostapenko J.": "1997-06-08",
    "Collins D.": "1993-12-13",
    "Kasatkina D.": "1997-05-07",
    "Samsonova L.": "1998-11-11",
    "Shnaider D.": "2004-04-02",
    "Kostyuk M.": "2002-06-28",
    "Vekic D.": "1996-06-28",
    "Haddad Maia B.": "1996-05-30",
    "Alexandrova E.": "1994-11-15",
    "Keys M.": "1995-02-17",
    "Badosa P.": "1997-11-15",
    "Fernandez L.": "2002-09-06",
    "Noskova L.": "2004-11-17",
    "Tauson C.": "2002-12-25",
    "Azarenka V.": "1989-07-31",
    "Svitolina E.": "1994-09-12",
    "Andreeva M.": "2007-04-29",
    "Andreeva E.": "2004-06-24",
    "Raducanu E.": "2002-11-13",
    "Andreescu B.": "2000-06-16",
    "Osaka N.": "1997-10-16",
    "Wozniacki C.": "1990-07-11",
    "Bucsa C.": "1998-01-01",
    "Bondar A.": "1997-05-27",
    "Joint M.": "2006-04-16",
    "Parry D.": "2002-09-01",
    "Potapova A.": "2001-03-30",
    "Parks A.": "2000-12-31",
    "Zhang S.": "1989-01-21",
}


def get_player_age(player_name: str, as_of_date: Optional[date] = None) -> Optional[int]:
    """
    Calculate player's exact age in years based on their birth date.
    Returns None if birth date is not recorded.
    """
    if not player_name:
        return None

    ref_date = as_of_date or date.today()
    if isinstance(ref_date, datetime):
        ref_date = ref_date.date()

    # Match player name to registry
    matched_key = match_player_to_database(player_name, list(PLAYER_BIRTHDATES.keys()))
    bdate_str = PLAYER_BIRTHDATES.get(matched_key) or PLAYER_BIRTHDATES.get(player_name)
    
    if not bdate_str:
        return None

    try:
        b_year, b_month, b_day = map(int, bdate_str.split("-"))
        born = date(b_year, b_month, b_day)
        age = ref_date.year - born.year - ((ref_date.month, ref_date.day) < (born.month, born.day))
        return age
    except Exception:
        return None

