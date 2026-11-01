import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.6.0/dist/maplibre-gl.mjs';

const mapa = new maplibregl.Map({
  container: 'mapa',
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [18, 52],
  zoom: 6
});

mapa.addControl(new maplibregl.NavigationControl(), 'top-right');