
"""Przypisywanie udziału terenów leśnych do krawędzi grafu drogowego.

Dane wejściowe: GeoJSON z poligonami OSM w EPSG:4326.
Geometrie są przeliczane do EPSG:2180.
"""

import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform as transform_geom, unary_union
from shapely.strtree import STRtree
from shapely import make_valid


UKLAD_ZRODLOWY = "EPSG:4326"
UKLAD_METRYCZNY = "EPSG:2180"

BUFOR_LASU_M = 9.0


def _poligony_z_geometrii(geometria):
    """Zwraca składowe typu Polygon."""
    if geometria.is_empty:
        return []

    if geometria.geom_type == "Polygon":
        return [geometria]

    if geometria.geom_type in ("MultiPolygon", "GeometryCollection"):
        wynik = []

        for skladowa in geometria.geoms:
            wynik.extend(_poligony_z_geometrii(skladowa))

        return wynik

    return []


def wczytaj_poligony_lasow(sciezka):
    """Wczytuje poligony lasów, przelicza je do EPSG:2180 i buforuje o podaną ilość metrów."""
    sciezka = Path(sciezka)

    if not sciezka.is_file():
        raise FileNotFoundError(
            f"Nie znaleziono pliku z lasami: {sciezka}"
        )

    with sciezka.open(encoding="utf-8") as plik:
        dane = json.load(plik)

    if dane.get("type") != "FeatureCollection":
        raise ValueError(
            "Plik z lasami musi być GeoJSON typu FeatureCollection."
        )

    przeksztalc = Transformer.from_crs(
        UKLAD_ZRODLOWY,
        UKLAD_METRYCZNY,
        always_xy=True
    ).transform

    poligony = []

    for cecha in dane.get("features", []):
        surowa_geometria = cecha.get("geometry")

        if not surowa_geometria:
            continue

        geometria = shape(surowa_geometria)
        geometria = transform_geom(przeksztalc, geometria)

        if not geometria.is_valid:
            geometria = make_valid(geometria)

        poligony.extend(_poligony_z_geometrii(geometria))

    if not poligony:
        raise ValueError(
            "Plik GeoJSON nie zawiera poprawnych poligonów leśnych."
        )

    # Połączenie poligonów zapobiega wielokrotnemu liczeniu
    # tych samych fragmentów dróg.
    lasy = unary_union(poligony)

    # Rozszerzenie granic lasów buforem.
    lasy_buforowane = lasy.buffer(BUFOR_LASU_M)

    wynik = _poligony_z_geometrii(lasy_buforowane)

    if not wynik:
        raise ValueError(
            "Nie udało się przygotować geometrii poligonów leśnych."
        )

    return wynik


def przypisz_udzial_lasu(graf, sciezka_geojson):
    """Oblicza i zapisuje udzial_lasu dla każdej krawędzi grafu.

    Udział oznacza stosunek długości części krawędzi znajdującej się
    w poligonach lasów rozszerzonych o 3 m do całkowitej długości krawędzi.

    Wynik zapisywany jest bezpośrednio w atrybucie udzial_lasu.
    """

    poligony = wczytaj_poligony_lasow(sciezka_geojson)
    indeks = STRtree(poligony)

    przeksztalc = Transformer.from_crs(
        UKLAD_ZRODLOWY,
        UKLAD_METRYCZNY,
        always_xy=True
    ).transform

    for krawedz in graf.krawedzie.values():
        punkty = [
            (float(p[0]), float(p[1]))
            for p in krawedz["punkty"]
        ]

        linia = LineString(punkty)
        linia = transform_geom(przeksztalc, linia)

        dlugosc_geom = linia.length

        if dlugosc_geom <= 0:
            krawedz["udzial_lasu"] = 0.0
            continue

        dlugosc_w_lesie = 0.0

        kandydaci = indeks.query(linia)

        for indeks_poligonu in kandydaci:
            poligon = poligony[int(indeks_poligonu)]

            if linia.intersects(poligon):
                dlugosc_w_lesie += linia.intersection(poligon).length

        # Zabezpieczenie przed drobnymi błędami numerycznymi.
        dlugosc_w_lesie = min(dlugosc_w_lesie, dlugosc_geom)

        udzial = dlugosc_w_lesie / dlugosc_geom

        krawedz["udzial_lasu"] = max(0.0, min(1.0, udzial))