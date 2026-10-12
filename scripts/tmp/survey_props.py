"""Temporary: basketball player-prop formats at Pinnacle and Kambi (run on a GitHub runner)."""
import collections, json, re
from sports_common.pinnacle import pinnacle_get
from sports_common.kambi import kambi_get

m = pinnacle_get("sports/4/matchups")
props = [x for x in m if x.get("type") == "special" and (x.get("special") or {}).get("category") == "Player Props"]
print("PIN prop descriptions (stat part):", collections.Counter(re.sub(r"^.*?(Total|Points|Rebounds|Assists|3 Point|Threes|Pts)", r"\1", x["special"]["description"]) for x in props).most_common(15))
mk = pinnacle_get("sports/4/markets/straight")
ids = {x["id"] for x in props}
sample = [r for r in mk if r.get("matchupId") in ids][:2]
print("PIN prop market rows:", json.dumps(sample)[:900])
print("PIN prop matchup:", json.dumps({k: props[0].get(k) for k in ("id", "parentId", "special", "participants", "startTime", "league")})[:800])
parent = next((x for x in m if x.get("id") == props[0].get("parentId")), None)
print("PIN parent:", parent and [p["name"] for p in parent.get("participants", [])])
lv = kambi_get("ubbe", "listView/basketball/all/all/all/matches.json").get("events") or []
ids = [str(x["event"]["id"]) for x in lv if x["event"].get("state") == "NOT_STARTED"][:30]
bo = kambi_get("ubbe", "betoffer/event/" + ",".join(ids) + ".json").get("betOffers") or []
pl = [o for o in bo if o["betOfferType"]["name"] == "Player Occurrence Line" and "by the player" in (o["criterion"].get("englishLabel") or "")]
print("KAMBI labels:", collections.Counter(o["criterion"].get("englishLabel") for o in pl).most_common(12))
print("KAMBI sample:", json.dumps(pl[0])[:1200] if pl else None)
