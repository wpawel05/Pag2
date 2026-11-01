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

document.getElementById('select-style').addEventListener('change', (e) => {
  map.setStyle(STYLES[e.target.value]);
});