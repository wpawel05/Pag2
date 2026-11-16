from src.graph import load_graph
from src.routing import znajdz_trase

# Wczytaj sieć drogową
graf = load_graph("data/torun/torun_edges.geojson")

# Współrzędne wpisuj jako: długość geograficzna, szerokość geograficzna
start_lon, start_lat = 18.60, 53.01  # tu wpisz punkt startowy
cel_lon, cel_lat = 18.66, 53.02      # tu wpisz punkt docelowy

# Znajdź w grafie najbliższe węzły sieci drogowej
start, odleglosc_start = graf.najblizszy_wezel(start_lon, start_lat)
cel, odleglosc_cel = graf.najblizszy_wezel(cel_lon, cel_lat)

if start is None or cel is None:
    print("Nie znaleziono drogi dostatecznie blisko jednego z punktów.")
else:
    # Oblicz trasę: A* i kryterium najszybszego przejazdu
    trasa = znajdz_trase(
        graf,
        start=start,
        cel=cel,
        algorytm="astar",
        kryterium="najszybsza",
    )

    if trasa is None:
        print("Nie znaleziono trasy między tymi punktami.")
    else:
        print(f"Długość trasy: {trasa.dlugosc_m:.0f} m")
        print(f"Szacowany czas: {trasa.czas_s / 60:.1f} min")
        print(f"Współrzędne trasy: {trasa.geometria}")
