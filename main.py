from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from src.graph import load_graph
from src.routing import znajdz_trase

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)

# Graf wczytujemy raz przy uruchomieniu serwera.
graf = load_graph(str(ROOT / "data" / "torun" / "torun_edges.geojson"))


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

    try:
        start_lon, start_lat = map(float, dane["start"])
        cel_lon, cel_lat = map(float, dane["cel"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Podaj start i cel jako [lon, lat]."}), 400

    start, odl_start = graf.najblizszy_wezel(start_lon, start_lat)
    cel, odl_cel = graf.najblizszy_wezel(cel_lon, cel_lat)

    if start is None or cel is None:
        return jsonify({"error": "Nie znaleziono drogi blisko jednego z punktów."}), 400

    trasa = znajdz_trase(
        graf,
        start=start,
        cel=cel,
        algorytm="astar",
        kryterium="najkrotsza",
    )

    if trasa is None:
        return jsonify({"error": "Nie znaleziono drogi między punktami."}), 404

    if len(trasa.geometria) < 2:
        return jsonify({"error": "Start i cel wskazują ten sam punkt sieci."}), 400

    return jsonify({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": trasa.geometria,
            },
            "properties": {
                "dlugosc_m": trasa.dlugosc_m,
                "czas_s": trasa.czas_s,
                "odleglosc_przypiecia_start_m": odl_start,
                "odleglosc_przypiecia_cel_m": odl_cel,
            },
        }],
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)