import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.6.0/dist/maplibre-gl.mjs';

const STYLE_OSM = 'https://tiles.openfreemap.org/styles/liberty';

const STYLE_SATELITA = {
  version: 8,
  sources: {
    'satelite-tiles': {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 512,
      attribution: 'Imagery &copy; Esri'
    }
  },
  layers: [{ id: 'satelite-layer', type: 'raster', source: 'satelite-tiles' }]
};

const STYLES = { osm: STYLE_OSM, satelite: STYLE_SATELITA };

const map = new maplibregl.Map({
  container: 'map',
  style: STYLES.osm,
  center: [18, 53],
  zoom: 6
});

map.addControl(new maplibregl.NavigationControl(), 'top-right');

const status = document.getElementById('route-status');
const clearButton = document.getElementById('clear-route');

const emptyRoute = {
  type: 'FeatureCollection',
  features: []
};

let currentRoute = emptyRoute;
let startPoint = null;
let endPoint = null;
let startMarker = null;
let endMarker = null;

function addRouteLayer() {
  if (!map.getSource('route')) {
    map.addSource('route', {
      type: 'geojson',
      data: currentRoute
    });
  }

  if (!map.getLayer('route-line')) {
    map.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: {
        'line-cap': 'round',
        'line-join': 'round'
      },
      paint: {
        'line-color': '#1769ff',
        'line-width': 6
      }
    });
  }
}

// Warstwa jest dodawana również po zmianie podkładu mapy.
map.on('style.load', addRouteLayer);

function clearRoute() {
  startPoint = null;
  endPoint = null;
  currentRoute = emptyRoute;

  if (startMarker) startMarker.remove();
  if (endMarker) endMarker.remove();

  startMarker = null;
  endMarker = null;

  const source = map.getSource('route');
  if (source) source.setData(currentRoute);

  status.textContent = 'Kliknij mapę, aby wybrać start.';
}

clearButton.addEventListener('click', clearRoute);

map.on('click', async (event) => {
  const point = [event.lngLat.lng, event.lngLat.lat];

  // Pierwsze kliknięcie wybiera start. Po wyznaczonej trasie
  // następne kliknięcie rozpoczyna wybór nowej trasy.
  if (!startPoint || endPoint) {
    clearRoute();

    startPoint = point;
    startMarker = new maplibregl.Marker({ color: '#22a06b' })
      .setLngLat(point)
      .addTo(map);

    status.textContent = 'Start wybrany. Kliknij mapę, aby wybrać cel.';
    return;
  }

  endPoint = point;
  endMarker = new maplibregl.Marker({ color: '#d14343' })
    .setLngLat(point)
    .addTo(map);

  status.textContent = 'Wyznaczam trasę…';

  try {
    const response = await fetch('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start: startPoint, cel: endPoint })
    });

    const dane = await response.json();

    if (!response.ok) {
      throw new Error(dane.error || 'Nie udało się wyznaczyć trasy.');
    }

    currentRoute = dane;
    map.getSource('route').setData(currentRoute);

    const feature = dane.features[0];
    const bounds = new maplibregl.LngLatBounds();
    feature.geometry.coordinates.forEach((coord) => bounds.extend(coord));
    map.fitBounds(bounds, { padding: 60, maxZoom: 16 });

    const km = (feature.properties.dlugosc_m / 1000).toFixed(2);
    const min = (feature.properties.czas_s / 60).toFixed(1);
    status.textContent = `Trasa: ${km} km, około ${min} min.`;
  } catch (error) {
    status.textContent = error.message;
  }
});

document.getElementById('select-style').addEventListener('change', (e) => {
  map.setStyle(STYLES[e.target.value]);
});