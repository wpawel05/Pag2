"""Graf drogowy wczytywany z GeoJSON (eksport z ArcPy / OSM)."""
import json
import math

R_ZIEMI_M = 6371008.8
ROZMIAR_KOMORKI_STOPNIE = 0.005


def haversine(a, b):
    """Odległość po kuli w metrach między punktami (lon, lat)."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * R_ZIEMI_M * math.asin(math.sqrt(h))


def _parsuj_maxspeed(wartosc):
    """maxspeed z OSM bywa liczbą, tekstem '50' albo śmieciem ('PL:urban', 'none')."""
    if isinstance(wartosc, (int, float)):
        return float(wartosc) if wartosc > 0 else None
    if isinstance(wartosc, str) and wartosc.strip().isdigit():
        return float(wartosc.strip()) or None
    return None


class Graf:
    def __init__(self):
        self.sasiedzi = {}        # węzeł -> [(sąsiad, id_krawędzi)], z uwzględnieniem kierunkowości
        self.krawedzie = {}       # id_krawędzi -> słownik atrybutów
        self.wspolrzedne = {}     # węzeł -> (lon, lat)
        self._siatka = {}
        self._min_komorka_m = 1.0

    #  budowa
    def dodaj_krawedz(self, eid, u, v, punkty, dlugosc, oneway="both", **atrybuty):
        self.krawedzie[eid] = {"id": eid, "u": u, "v": v, "punkty": punkty,
                               "dlugosc": float(dlugosc), "oneway": oneway, **atrybuty}
        self.wspolrzedne.setdefault(u, tuple(punkty[0]))
        self.wspolrzedne.setdefault(v, tuple(punkty[-1]))
        self.sasiedzi.setdefault(u, [])
        self.sasiedzi.setdefault(v, [])
        if oneway in ("both", "forward"):
            self.sasiedzi[u].append((v, eid))
        if oneway in ("both", "backward"):
            self.sasiedzi[v].append((u, eid))

    def zakoncz(self):
        """Wywołaj po dodaniu wszystkich krawędzi: buduje indeks przestrzenny węzłów."""
        szer = [c[1] for c in self.wspolrzedne.values()] or [0.0]
        srednia_szer = sum(szer) / len(szer)
        self._min_komorka_m = (ROZMIAR_KOMORKI_STOPNIE * 111320
                               * math.cos(math.radians(srednia_szer)))
        self._siatka = {}
        for w in self.wspolrzedne:
            self._siatka.setdefault(self._komorka(*self.wspolrzedne[w]), []).append(w)

    #  zapytania
    def _komorka(self, lon, lat):
        return (math.floor(lon / ROZMIAR_KOMORKI_STOPNIE),
                math.floor(lat / ROZMIAR_KOMORKI_STOPNIE))

    def najblizszy_wezel(self, lon, lat, maks_m=3000):
        """Najbliższy węzeł grafu. Zwraca (węzeł, odległość_m) albo (None, None)."""
        cx, cy = self._komorka(lon, lat)
        najlepszy, najlepsza = None, float("inf")
        r = 0
        while r * self._min_komorka_m <= maks_m:
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    for w in self._siatka.get((cx + dx, cy + dy), ()):
                        d = haversine((lon, lat), self.wspolrzedne[w])
                        if d < najlepsza:
                            najlepszy, najlepsza = w, d
            # każdy węzeł bliższy niż r*komórka został już sprawdzony
            if najlepszy is not None and najlepsza <= r * self._min_komorka_m:
                break
            r += 1
        if najlepszy is None or najlepsza > maks_m:
            return None, None
        return najlepszy, najlepsza

    def geometria(self, wezly, ids):
        """Sklejona linia trasy po prawdziwych wierzchołkach odcinków ([lon, lat, ...])."""
        linia = []
        for wezel, eid in zip(wezly, ids):
            e = self.krawedzie[eid]
            p = e["punkty"]
            if e["u"] != wezel:            # odcinek przejechany od końca do początku
                p = p[::-1]
            linia.extend(p if not linia else p[1:])
        return linia

    def bbox(self):
        lon = [c[0] for c in self.wspolrzedne.values()]
        lat = [c[1] for c in self.wspolrzedne.values()]
        return [min(lon), min(lat), max(lon), max(lat)]


def load_graph(sciezka_krawedzi, sciezka_ciekawosc=None):
    """Wczytuje graf z GeoJSON i (opcjonalnie) dołącza składowe ciekawosc po id krawędzi."""
    with open(sciezka_krawedzi, encoding="utf-8") as f:
        dane = json.load(f)

    ciekawosc = {}
    if sciezka_ciekawosc:
        with open(sciezka_ciekawosc, encoding="utf-8") as f:
            ciekawosc = json.load(f)

    graf = Graf()
    for cecha in dane["features"]:
        p = cecha["properties"]
        eid = str(p["id"])
        graf.dodaj_krawedz(
            eid, p["u"], p["v"], cecha["geometry"]["coordinates"], p["dlugosc_m"],
            oneway=p.get("oneway", "both"),
            klasa=p.get("highway"),
            maxspeed=_parsuj_maxspeed(p.get("maxspeed")),
            maxspeed_fwd=_parsuj_maxspeed(p.get("maxspeed_fwd")),
            maxspeed_bwd=_parsuj_maxspeed(p.get("maxspeed_bwd")),
            nawierzchnia=p.get("surface"),
            ciekawosc=ciekawosc.get(eid, {}),
        )
    graf.zakoncz()
    return graf


def skladowe_ciekawosci(graf):
    """Nazwy składowych ciekawosc obecnych w danych (do zbudowania suwaków w UI)."""
    nazwy = set()
    for e in graf.krawedzie.values():
        nazwy.update(e["ciekawosc"].keys())
    return sorted(nazwy)