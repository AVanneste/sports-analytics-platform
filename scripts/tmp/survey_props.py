"""Temporary: which prop markets Pinnacle and the Belgian books share (run on a GitHub runner)."""
import collections, json
from sports_common.pinnacle import pinnacle_get
from sports_common.kambi import kambi_get

for name, sid in (("Basketball", 4), ("Soccer", 29), ("Hockey", 19), ("Tennis", 33)):
    m = pinnacle_get(f"sports/{sid}/matchups")
    specials = [x for x in m if x.get("type") == "special"]
    print(f"\n== PINNACLE {name}: {len(specials)} specials")
    print("   categories:", collections.Counter((x.get("special") or {}).get("category") for x in specials).most_common(8))
    for x in specials[:4]:
        print("   ", json.dumps({k: x.get(k) for k in ("special", "participants", "parentId", "units")})[:400])
for ks in ("basketball", "football", "ice_hockey"):
    lv = kambi_get("ubbe", f"listView/{ks}/all/all/all/matches.json").get("events") or []
    ids = [str(x["event"]["id"]) for x in lv if x["event"].get("state") == "NOT_STARTED"][:20]
    bo = kambi_get("ubbe", "betoffer/event/" + ",".join(ids) + ".json").get("betOffers") or [] if ids else []
    c = collections.Counter((o["criterion"].get("englishLabel") or o["criterion"]["label"], o["betOfferType"]["name"]) for o in bo
                            if "player" in (o["betOfferType"]["name"] + str(o["criterion"])).lower() or "corner" in o["criterion"]["label"].lower())
    print(f"\n== KAMBI {ks} player/corner offers:", c.most_common(14))
