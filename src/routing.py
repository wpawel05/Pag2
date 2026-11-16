"""Wyszukiwanie tras w grafie z :mod:`src.graph`.

Moduł oddziela algorytm wyszukiwania od modelu kosztu krawędzi. Dzięki temu
można później dodać np. trasę widokową, rowerową albo kary za wybrane drogi,
bez kopiowania implementacji Dijkstry i A*.

Przykład::

    from src.graph import load_graph
    from src.routing import znajdz_trase

    graf = load_graph("data/torun/torun_edges.geojson")
    trasa = znajdz_trase(graf, start=12, cel=87,
                         algorytm="astar", kryterium="najszybsza")
    if trasa is not None:
        print(trasa.dlugosc_m, trasa.czas_s)
"""
from dataclasses import dataclass
import heapq
import itertools
import math
from typing import Callable, Dict, List, Optional, Tuple

from .graph import haversine


# Przybliżone prędkości w km/h używane, gdy OSM nie podaje maxspeed.
# Można przekazać własny słownik do znajdz_trase, np. dostosowany do regionu.
DOMYSLNE_PREDKOSCI_KMH = {
    "motorway": 100.0,
    "motorway_link": 50.0,
    "trunk": 80.0,
    "trunk_link": 40.0,
    "primary": 50.0,
    "primary_link": 35.0,
    "secondary": 50.0,
    "secondary_link": 35.0,
    "tertiary": 40.0,
    "tertiary_link": 30.0,
    "unclassified": 30.0,
    "residential": 30.0,
    "living_street": 10.0,
    "service": 15.0,
}
DOMYSLNA_PREDKOSC_KMH = 30.0


@dataclass
class Trasa:
    """Wynik wyszukiwania.

    ``wezly`` zawiera wszystkie węzły od startu do celu, a ``krawedzie``
    identyfikatory odcinków w tej samej kolejności. ``geometria`` to lista
    współrzędnych [lon, lat] gotowa do opakowania w GeoJSON.
    """

    algorytm: str
    kryterium: str
    wezly: List[object]
    krawedzie: List[str]
    dlugosc_m: float
    czas_s: float
    koszt: float
    geometria: list


KosztKrawedzi = Callable[[dict, object, object], float]
Heurystyka = Callable[[object, object, object], float]


def _predkosc_kmh(krawedz, od_wezla, predkosci_domyslne):
    """Prędkość dla konkretnego kierunku przejazdu krawędzi."""
    if od_wezla == krawedz["u"]:
        predkosc = krawedz.get("maxspeed_fwd")
    else:
        predkosc = krawedz.get("maxspeed_bwd")
    if not predkosc:
        predkosc = krawedz.get("maxspeed")
    if not predkosc:
        predkosc = predkosci_domyslne.get(krawedz.get("klasa"))
    if not predkosc:
        predkosc = DOMYSLNA_PREDKOSC_KMH
    return float(predkosc)


def _koszt_wbudowany(krawedz, od_wezla, kryterium, predkosci_domyslne):
    dlugosc = float(krawedz["dlugosc"])
    if not math.isfinite(dlugosc) or dlugosc < 0:
        raise ValueError("Długości krawędzi muszą być skończone i nieujemne.")
    if kryterium == "najkrotsza":
        return dlugosc
    predkosc_m_s = _predkosc_kmh(krawedz, od_wezla, predkosci_domyslne) / 3.6
    if not math.isfinite(predkosc_m_s) or predkosc_m_s <= 0:
        raise ValueError("Prędkości dróg muszą być skończone i większe od zera.")
    return dlugosc / predkosc_m_s


def _heurystyka_wbudowana(graf, wezel, cel, kryterium, maks_predkosc_kmh):
    """Dolne ograniczenie kosztu do celu (bezpieczne dla A*)."""
    odleglosc = haversine(graf.wspolrzedne[wezel], graf.wspolrzedne[cel])
    if kryterium == "najkrotsza":
        return odleglosc
    # Nawet przy założeniu jazdy z maksymalną prędkością, czas nie będzie
    # krótszy niż odległość w linii prostej / maksymalna prędkość.
    return odleglosc / (maks_predkosc_kmh / 3.6)


def znajdz_trase(
    graf,
    start,
    cel,
    algorytm="astar",
    kryterium="najkrotsza",
    *,
    predkosci_domyslne=None,
    koszt_krawedzi: Optional[KosztKrawedzi] = None,
    heurystyka: Optional[Heurystyka] = None,
) -> Optional[Trasa]:
    """Znajduje trasę Dijkstrą lub A*.

    Args:
        graf: obiekt ``Graf`` z ``src.graph``.
        start, cel: identyfikatory węzłów grafu.
        algorytm: ``"dijkstra"`` albo ``"astar"``.
        kryterium: ``"najkrotsza"`` (metry) albo ``"najszybsza"`` (sekundy).
        predkosci_domyslne: opcjonalne nadpisanie prędkości dla klas dróg.
        koszt_krawedzi: opcjonalna funkcja ``(krawedz, od, do) -> koszt``.
            Pozwala dodać później inne cele, np. trasę widokową. Koszt musi
            być nieujemny. Przy własnym koszcie A* używa heurystyki zerowej,
            jeśli nie podano własnej, więc nadal daje poprawny wynik (jak
            Dijkstra, ale bez przyspieszenia A*).
        heurystyka: opcjonalna funkcja ``(graf, wezel, cel) -> dolne ograniczenie``.
            Dla optymalnego wyniku musi nigdy nie zawyżać pozostałego kosztu.

    Returns:
        ``Trasa`` albo ``None``, gdy celu nie da się osiągnąć z danego startu.

    Raises:
        ValueError: dla nieznanego algorytmu/kryterium, nieistniejących węzłów
            albo ujemnego/niefinitywnego kosztu krawędzi.
    """
    algorytm = algorytm.lower()
    if algorytm not in ("dijkstra", "astar"):
        raise ValueError("algorytm musi mieć wartość 'dijkstra' albo 'astar'.")
    if kryterium not in ("najkrotsza", "najszybsza"):
        raise ValueError("kryterium musi mieć wartość 'najkrotsza' albo 'najszybsza'.")
    if start not in graf.sasiedzi or cel not in graf.sasiedzi:
        raise ValueError("Węzeł startowy i końcowy muszą istnieć w grafie.")

    predkosci = dict(DOMYSLNE_PREDKOSCI_KMH)
    if predkosci_domyslne:
        predkosci.update(predkosci_domyslne)

    # Największa prędkość dostępna na dowolnym skierowanym odcinku. Użycie
    # maksimum sprawia, że heurystyka czasu nie przeszacowuje kosztu.
    maks_predkosc = DOMYSLNA_PREDKOSC_KMH
    if kryterium == "najszybsza" and koszt_krawedzi is None:
        for od, sasiedzi in graf.sasiedzi.items():
            for _, eid in sasiedzi:
                maks_predkosc = max(
                    maks_predkosc,
                    _predkosc_kmh(graf.krawedzie[eid], od, predkosci),
                )

    def koszt(od, do, eid):
        krawedz = graf.krawedzie[eid]
        wartosc = (
            koszt_krawedzi(krawedz, od, do)
            if koszt_krawedzi is not None
            else _koszt_wbudowany(krawedz, od, kryterium, predkosci)
        )
        wartosc = float(wartosc)
        if not math.isfinite(wartosc) or wartosc < 0:
            raise ValueError("Koszt każdej krawędzi musi być skończony i nieujemny.")
        return wartosc

    def h(wezel):
        if algorytm == "dijkstra":
            return 0.0
        if heurystyka is not None:
            wartosc = float(heurystyka(graf, wezel, cel))
            if not math.isfinite(wartosc) or wartosc < 0:
                raise ValueError("Heurystyka musi być skończona i nieujemna.")
            return wartosc
        if koszt_krawedzi is not None:
            return 0.0
        return _heurystyka_wbudowana(graf, wezel, cel, kryterium, maks_predkosc)

    # Kolejka przechowuje (g + h, licznik, g, węzeł). Licznik rozstrzyga
    # remisy bez wymagania, by identyfikatory węzłów dało się porównywać.
    licznik = itertools.count()
    kolejka = [(h(start), next(licznik), 0.0, start)]
    najlepszy_koszt: Dict[object, float] = {start: 0.0}
    poprzednik: Dict[object, Tuple[object, str]] = {}

    while kolejka:
        _, _, koszt_do_wezla, wezel = heapq.heappop(kolejka)
        if koszt_do_wezla != najlepszy_koszt.get(wezel):
            continue  # w kolejce został starszy, gorszy wpis
        if wezel == cel:
            break

        for sasiad, eid in graf.sasiedzi.get(wezel, ()):
            nowy_koszt = koszt_do_wezla + koszt(wezel, sasiad, eid)
            if nowy_koszt < najlepszy_koszt.get(sasiad, float("inf")):
                najlepszy_koszt[sasiad] = nowy_koszt
                poprzednik[sasiad] = (wezel, eid)
                heapq.heappush(
                    kolejka,
                    (nowy_koszt + h(sasiad), next(licznik), nowy_koszt, sasiad),
                )

    if cel not in najlepszy_koszt:
        return None

    # Odtworzenie ścieżki od celu do startu.
    wezly = [cel]
    krawedzie = []
    biezacy = cel
    while biezacy != start:
        poprzedni, eid = poprzednik[biezacy]
        krawedzie.append(eid)
        wezly.append(poprzedni)
        biezacy = poprzedni
    wezly.reverse()
    krawedzie.reverse()

    dlugosc_m = sum(float(graf.krawedzie[eid]["dlugosc"]) for eid in krawedzie)
    czas_s = sum(
        float(graf.krawedzie[eid]["dlugosc"])
        / (_predkosc_kmh(graf.krawedzie[eid], od, predkosci) / 3.6)
        for od, eid in zip(wezly, krawedzie)
    )
    geometria = graf.geometria(wezly[:-1], krawedzie) if krawedzie else []

    return Trasa(
        algorytm=algorytm,
        kryterium=kryterium if koszt_krawedzi is None else "wlasny_koszt",
        wezly=wezly,
        krawedzie=krawedzie,
        dlugosc_m=dlugosc_m,
        czas_s=czas_s,
        koszt=najlepszy_koszt[cel],
        geometria=geometria,
    )

