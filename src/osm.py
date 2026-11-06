"""Zamiana drogowego GeoJSON-a z OSM (Overpass Turbo) na sieć w formacie z data/README.md.

W pliku z Overpassa jedna cecha to cała droga (way), często przez kilka skrzyżowań.
Graf potrzebuje odcinków między skrzyżowaniami, więc:
  1. punkt, który występuje w dwóch miejscach (w różnych drogach albo dwa razy w jednej)
     albo jest końcem drogi, jest węzłem,
  2. każdą drogę tniemy w węzłach; wierzchołki pośrednie zostają w geometrii odcinka,
  3. kierunek i prędkości przepisujemy z tagów (dane OSM są już topologicznie spójne,
     więc nie trzeba sklejać luk jak w BDOT10k).

Użycie:  python -m src.osm data/raw/drogi.geojson data/torun/torun_edges.geojson
"""
import json
import sys
from collections import Counter

from .graph import _parsuj_maxspeed, haversine


def kierunek(tagi):
    """Kierunek względem kolejności punktów linii: forward / backward / both."""
    o = tagi.get("oneway")
    if o in ("yes", "true", "1"):
        return "forward"
    if o in ("-1", "reverse"):
        return "backward"
    if o in ("no", "false", "0"):
        return "both"
    if tagi.get("junction") == "roundabout" or tagi.get("highway") in ("motorway", "motorway_link"):
        return "forward"
    return "both"


def predkosci(tagi):
    """(maxspeed, maxspeed_fwd, maxspeed_bwd) w km/h albo None.

    Wartości nieliczbowe ('PL:urban', 'none', '50 mph') są pomijane, wtedy model
    weźmie prędkość z klasy drogi.
    """
    ogolna = _parsuj_maxspeed(tagi.get("maxspeed"))
    fwd = _parsuj_maxspeed(tagi.get("maxspeed:forward"))
    bwd = _parsuj_maxspeed(tagi.get("maxspeed:backward"))
    return ogolna, fwd, bwd


def przejezdna(tagi):
    """Czy droga jest dla samochodów. Odrzucamy tylko zakaz (no), drogi prywatne zostają."""
    if not tagi.get("highway"):
        return False
    if tagi.get("access") == "no" and tagi.get("motor_vehicle") not in ("yes", "permissive"):
        return False
    return tagi.get("motor_vehicle") != "no"


def _idy_osm(cecha):
    surowe = str(cecha.get("properties", {}).get("@id") or cecha.get("id") or "")
    return "w" + surowe.split("/")[-1] if surowe else None


def przetworz(dane):
    """GeoJSON z Overpassa -> (GeoJSON krawędzi, statystyki)."""
    drogi = []
    pominiete = 0
    for numer, cecha in enumerate(dane["features"]):
        g = cecha.get("geometry") or {}
        tagi = cecha.get("properties", {})
        if g.get("type") != "LineString" or not przejezdna(tagi):
            pominiete += 1
            continue
        punkty = []
        for p in g["coordinates"]:
            p = (p[0], p[1])
            if not punkty or p != punkty[-1]:        # powtórzony punkt = odcinek o długości 0
                punkty.append(p)
        if len(punkty) < 2:
            pominiete += 1
            continue
        drogi.append((_idy_osm(cecha) or f"x{numer}", tagi, punkty))

    wystapienia = Counter(p for _, _, punkty in drogi for p in punkty)
    numery_wezlow = {}

    def wezel(p):
        return numery_wezlow.setdefault(p, len(numery_wezlow))

    cechy = []
    for id_drogi, tagi, punkty in drogi:
        ogolna, fwd, bwd = predkosci(tagi)
        kier = kierunek(tagi)
        poczatek, k = 0, 0
        for i in range(1, len(punkty)):
            if i == len(punkty) - 1 or wystapienia[punkty[i]] >= 2:
                odcinek = punkty[poczatek:i + 1]
                dlugosc = sum(haversine(a, b) for a, b in zip(odcinek, odcinek[1:]))
                cechy.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [list(p) for p in odcinek]},
                    "properties": {
                        "id": f"{id_drogi}_{k}",
                        "u": wezel(odcinek[0]), "v": wezel(odcinek[-1]),
                        "dlugosc_m": round(dlugosc, 2),
                        "highway": tagi.get("highway"),
                        "maxspeed": ogolna, "maxspeed_fwd": fwd, "maxspeed_bwd": bwd,
                        "surface": tagi.get("surface"),
                        "oneway": kier,
                    },
                })
                poczatek, k = i, k + 1

    statystyki = {"drog": len(drogi), "pominietych": pominiete,
                  "krawedzi": len(cechy), "wezlow": len(numery_wezlow)}
    return {"type": "FeatureCollection", "features": cechy}, statystyki


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 1
    with open(argv[1], encoding="utf-8") as f:
        dane = json.load(f)
    wynik, st = przetworz(dane)
    with open(argv[2], "w", encoding="utf-8") as f:
        json.dump(wynik, f, ensure_ascii=False)
    print(f"Drogi: {st['drog']} (pominięte: {st['pominietych']}) -> "
          f"krawędzie: {st['krawedzi']}, węzły: {st['wezlow']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))