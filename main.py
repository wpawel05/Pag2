
from pathlib import Path
import logging

from flask import Flask, jsonify, request, send_from_directory

from src.forest import przypisz_udzial_lasu
from src.graph import load_graph
from src.routing import znajdz_trase

ROOT = Path(__file__).resolve().parent
SCIEZKA_GRAFU = ROOT / "data" / "torun" / "torun_edges.geojson"
SCIEZKA_LASOW = ROOT / "data" / "torun" / "torun_forests.geojson"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Graf drogowy i udział lasu w krawędziach są przygotowywane raz przy starcie.
graf = load_graph(str(SCIEZKA_GRAFU))
DANE_LASOW_DOSTEPNE = False
BLAD_DANYCH_LASOW = None

try:
    przypisz_udzial_lasu(graf, SCIEZKA_LASOW)
    DANE_LASOW_DOSTEPNE = True

except (FileNotFoundError, ValueError, OSError) as blad:
    BLAD_DANYCH_LASOW = str(blad)
    logger.warning(
        "Trasa leśna będzie niedostępna. Przyczyna: %s. "
        "Zobacz instrukcję w README.md.",
        blad,
    )


@app.get("/")
def strona():
    return send_from_directory(ROOT, "index.html")


@app.get("/main.js")
def javascript():
    return send_from_directory(ROOT, "main.js")


@app.get("/style.css")
def style():
    return send_from_directory(ROOT, "style.css")


@app.post("/api/route")
def wyznacz_trase():
    dane = request.get_json(silent=True) or {}
    wariant = dane.get("wariant", "najkrotsza")

    algorytm = dane.get("algorytm", "astar")

    if algorytm not in ("dijkstra", "astar"):
        return jsonify({"error": "Nieznany algorytm."}), 400

    if wariant not in ("najkrotsza", "najszybsza", "lesna"):
        return jsonify({"error": "Nieznany wariant trasy."}), 400

    if wariant == "lesna" and not DANE_LASOW_DOSTEPNE:
        return jsonify({
            "error": (
                "Dane o lasach nie są dostępne. Pobierz poligony leśne z "
                "Overpass Turbo i zapisz je jako "
                "data/torun/torun_forests.geojson. "
                "Instrukcja znajduje się w README.md."
            ),
            "forest_data_error": BLAD_DANYCH_LASOW,
        }), 503

    try:
        start_lon, start_lat = map(float, dane["start"])
        cel_lon, cel_lat = map(float, dane["cel"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Podaj start i cel jako [lon, lat]."}), 400

    start, odl_start = graf.najblizszy_wezel(start_lon, start_lat)
    cel, odl_cel = graf.najblizszy_wezel(cel_lon, cel_lat)

    if start is None or cel is None:
        return jsonify({
            "error": "Nie znaleziono drogi blisko jednego z punktów."
        }), 400

    if wariant == "lesna":

        def koszt_trasy_lesnej(krawedz, od_wezla, do_wezla):
            dlugosc = float(krawedz["dlugosc"])
            udzial_lasu = float(krawedz.get("udzial_lasu", 0.0))
            return dlugosc * (1.0 - udzial_lasu)

        trasa = znajdz_trase(
            graf,
            start=start,
            cel=cel,
            algorytm=algorytm,
            kryterium="najkrotsza",
            koszt_krawedzi=koszt_trasy_lesnej,
        )

    else:
        kryterium = (
            "najszybsza" if wariant == "najszybsza"
            else "najkrotsza"
        )

        trasa = znajdz_trase(
            graf,
            start=start,
            cel=cel,
            algorytm=algorytm,
            kryterium=kryterium,
        )

    if trasa is None:
        return jsonify({
            "error": "Nie znaleziono drogi między punktami."
        }), 404

    if len(trasa.geometria) < 2:
        return jsonify({
            "error": "Start i cel wskazują ten sam punkt sieci."
        }), 400

    wlasciwosci = {
        "dlugosc_m": trasa.dlugosc_m,
        "czas_s": trasa.czas_s,
        "odleglosc_przypiecia_start_m": odl_start,
        "odleglosc_przypiecia_cel_m": odl_cel,
        "wariant": wariant,
        "algorytm": algorytm,
    }

    if wariant == "lesna":
        dlugosc_w_lesie = sum(
            float(graf.krawedzie[eid]["dlugosc"])
            * float(graf.krawedzie[eid].get("udzial_lasu", 0.0))
            for eid in trasa.krawedzie
        )

        wlasciwosci.update({
            "dlugosc_w_lesie_m": dlugosc_w_lesie,
            "udzial_lasu_pct": (
                100.0 * dlugosc_w_lesie / trasa.dlugosc_m
                if trasa.dlugosc_m > 0 else 0.0
            ),
        })

    return jsonify({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": trasa.geometria,
            },
            "properties": wlasciwosci,
        }],
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)