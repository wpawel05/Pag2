
import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.6.0/dist/maplibre-gl.mjs';

const STYLE_OSM = 'https://tiles.openfreemap.org/styles/liberty';
const STYLE_CIEMNY = 'https://tiles.openfreemap.org/styles/dark';

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
  layers: [{
    id: 'satelite-layer',
    type: 'raster',
    source: 'satelite-tiles'
  }]
};

const STYLES = {
  osm: STYLE_OSM,
  ciemny: STYLE_CIEMNY,
  satelite: STYLE_SATELITA
};

const KOLORY_TRAS = {
  najkrotsza: '#1769ff',
  najszybsza: '#e99b32',
  lesna: '#2e9e5b'
};

const NAZWY_WARIANTOW = {
  najkrotsza: 'najkrótszą',
  najszybsza: 'najszybszą',
  lesna: 'leśną'
};

const map = new maplibregl.Map({
  container: 'map',
  style: STYLES.osm,
  center: [18.60, 53.01],
  zoom: 12
});

map.addControl(new maplibregl.NavigationControl(), 'top-right');

const status = document.getElementById('route-status');
const clearButton = document.getElementById('clear-route');

const buttons = {
  najkrotsza: document.getElementById('shortest-route'),
  najszybsza: document.getElementById('fastest-route'),
  lesna: document.getElementById('forest-route')
};

const emptyRoute = {
  type: 'FeatureCollection',
  features: []
};

let currentRoute = emptyRoute;
let currentRouteVariant = 'najkrotsza';
let shortestRoute = null;
let startPoint = null;
let endPoint = null;
let startMarker = null;
let endMarker = null;
let requestNumber = 0;

function ustawAktywnyPrzycisk(wariant) {
  Object.entries(buttons).forEach(([nazwa, button]) => {
    const aktywny = nazwa === wariant;

    button.classList.toggle('active', aktywny);
    button.setAttribute('aria-pressed', String(aktywny));
  });
}

function ustawDostepnoscPrzyciskow(dostepne) {
  Object.values(buttons).forEach((button) => {
    button.disabled = !dostepne;
  });
}

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
        'line-color': KOLORY_TRAS[currentRouteVariant],
        'line-width': 6
      }
    });
  }
}

// Warstwa z prostokątem przedstawiającym obszar, w którym można wyznaczyć trasy.
map.on('style.load', () => {
  if (!map.getSource('bbox')) {
    map.addSource('bbox', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [18.45, 52.95],
            [18.75, 52.95],
            [18.75, 53.10],
            [18.45, 53.10],
            [18.45, 52.95]
          ]]
        }
      }
    });
  }

  if (!map.getLayer('bbox-line')) {
    map.addLayer({
      id: 'bbox-line',
      type: 'line',
      source: 'bbox',
      paint: {
        'line-color': '#1769ff',
        'line-width': 2
      }
    });
  }
});

// Warstwa trasy jest dodawana ponownie po każdej zmianie podkładu.
map.on('style.load', addRouteLayer);

function ustawDaneTrasy(dane, wariant = currentRouteVariant) {
  currentRoute = dane;
  currentRouteVariant = wariant;

  const source = map.getSource('route');
  if (source) {
    source.setData(currentRoute);
  }

  if (map.getLayer('route-line')) {
    map.setPaintProperty(
      'route-line',
      'line-color',
      KOLORY_TRAS[currentRouteVariant]
    );
  }

  ustawAktywnyPrzycisk(wariant);
}

function dopasujWidokDoTrasy(dane) {
  const feature = dane.features[0];
  const bounds = new maplibregl.LngLatBounds();

  feature.geometry.coordinates.forEach((coord) => {
    bounds.extend(coord);
  });

  const menu = document.getElementById('sidebar').getBoundingClientRect();

  map.fitBounds(bounds, {
    padding: { top: 60, bottom: 60, right: 60, left: menu.right + 40 },
    maxZoom: 16
  });
}

function tekstCzasu(czasSekundy) {
  const calkowityCzas = Math.round(czasSekundy);
  const minuty = Math.floor(calkowityCzas / 60);
  const sekundy = calkowityCzas % 60;

  if (minuty === 0) return `${sekundy} s`;
  if (sekundy === 0) return `${minuty} min`;

  return `${minuty} min ${sekundy} s`;
}

function wyczyscTrase() {
  // Unieważnia ewentualne odpowiedzi żądań, które nadal są w toku.
  requestNumber += 1;

  startPoint = null;
  endPoint = null;
  shortestRoute = null;

  if (startMarker) startMarker.remove();
  if (endMarker) endMarker.remove();

  startMarker = null;
  endMarker = null;

  ustawDaneTrasy(emptyRoute, 'najkrotsza');
  ustawDostepnoscPrzyciskow(false);

  status.textContent = 'Kliknij mapę, aby wybrać start.';
}

async function pobierzTrase(wariant) {
  if (!startPoint || !endPoint) {
    status.textContent = 'Najpierw wybierz punkt początkowy i końcowy.';
    return;
  }

  if (!buttons[wariant]) return;

  const numerZadania = ++requestNumber;

  ustawDostepnoscPrzyciskow(false);

  status.textContent = `Wyznaczam trasę ${NAZWY_WARIANTOW[wariant]}…`;

  try {
    const response = await fetch('/api/route', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        start: startPoint,
        cel: endPoint,
        wariant
      })
    });

    const dane = await response.json();

    if (!response.ok) {
      throw new Error(dane.error || 'Nie udało się wyznaczyć trasy.');
    }

    // Nie pokazuj odpowiedzi dla wcześniejszego zestawu punktów lub wariantu.
    if (numerZadania !== requestNumber) return;

    ustawDaneTrasy(dane, wariant);
    dopasujWidokDoTrasy(dane);

    const feature = dane.features[0];
    const props = feature.properties;

    const km = (props.dlugosc_m / 1000).toFixed(2);
    const czas = tekstCzasu(props.czas_s);

    if (wariant === 'lesna') {
      const udzialLasu = Number(props.udzial_lasu_pct || 0);

      let komunikat =
        `Trasa leśna: ${km} km, około ${czas}. ` +
        `Udział lasu: ${udzialLasu.toFixed(1)}%.`;

      if (shortestRoute?.features?.length) {
        const dlugoscNajkrotszej =
          shortestRoute.features[0].properties.dlugosc_m;

        if (dlugoscNajkrotszej > 0) {
          const mnoznik = props.dlugosc_m / dlugoscNajkrotszej;

          komunikat +=
            ` Długość: ${mnoznik.toFixed(2)}× trasy najkrótszej.`;

          if (mnoznik > 2) {
            komunikat += ' Trasa przekracza umowny próg 2×.';
          }
        }
      }

      if (udzialLasu < 1) {
        komunikat +=
          ' Udział lasu jest niewielki — w tej okolicy może brakować dróg leśnych.';
      }

      status.textContent = komunikat;

    } else if (wariant === 'najszybsza') {
      status.textContent =
        `Trasa najszybsza: ${km} km, około ${czas}.`;

    } else {
      // Zapamiętujemy najkrótszą trasę do późniejszego porównania.
      shortestRoute = dane;

      status.textContent =
        `Trasa najkrótsza: ${km} km, około ${czas}.`;
    }

  } catch (error) {
    if (numerZadania !== requestNumber) return;

    status.textContent = error.message;

  } finally {
    if (numerZadania === requestNumber) {
      ustawDostepnoscPrzyciskow(Boolean(startPoint && endPoint));
    }
  }
}

clearButton.addEventListener('click', wyczyscTrase);

buttons.najkrotsza.addEventListener('click', () => {
  pobierzTrase('najkrotsza');
});

buttons.najszybsza.addEventListener('click', () => {
  pobierzTrase('najszybsza');
});

buttons.lesna.addEventListener('click', () => {
  pobierzTrase('lesna');
});

map.on('click', async (event) => {
  const point = [event.lngLat.lng, event.lngLat.lat];

  // Pierwsze kliknięcie wybiera start. Po wyznaczonej trasie następne
  // kliknięcie rozpoczyna wybór nowej pary punktów.
  if (!startPoint || endPoint) {
    wyczyscTrase();

    startPoint = point;

    startMarker = new maplibregl.Marker({
      color: '#22a06b'
    })
      .setLngLat(point)
      .addTo(map);

    status.textContent =
      'Start wybrany. Kliknij mapę, aby wybrać cel.';

    return;
  }

  endPoint = point;

  endMarker = new maplibregl.Marker({
    color: '#d14343'
  })
    .setLngLat(point)
    .addTo(map);

  ustawDostepnoscPrzyciskow(true);

  await pobierzTrase('najkrotsza');
});

document.getElementById('select-style').addEventListener('change', (event) => {
  map.setStyle(STYLES[event.target.value]);
});