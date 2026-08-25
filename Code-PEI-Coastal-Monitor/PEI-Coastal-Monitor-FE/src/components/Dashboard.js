import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet-draw';
import 'leaflet-draw/dist/leaflet.draw.css';
import { Chart } from 'chart.js/auto';
import 'leaflet/dist/leaflet.css';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import './dashboard.css';
import westernStudyline from '../data/westernStudyline.json';
import centralStudyline from '../data/centralStudyline.json';
import easternStudyline from '../data/easternStudyline.json';
import easternMostStudyline from '../data/easternMostStudyline.json';
import westernMostStudyline from '../data/westernMostStudyline.json';

// Predefined patches: [west, south, east, north]
const PATCHES = [
  { id: 'central', name: 'Central', bbox: [-63.44409804, 45.993464200000004, -62.932614660000006, 46.554219399999995] },
  { id: 'eastern', name: 'Eastern', bbox: [-62.932614660000006, 45.893464200000004, -62.421131280000004, 46.554219399999995] },
  { id: 'easternMost', name: 'Eastern Most', bbox: [-62.421131280000004, 46.143464200000004, -61.9096479, 46.554219399999995] },
  { id: 'western', name: 'Western', bbox: [-63.95558142, 46.193464200000004, -63.44409804, 46.754219399999995] },
  { id: 'westernMost', name: 'Western Most', bbox: [-64.4670648, 46.293464200000004, -63.95558142, 47.154219399999995] }
];
const PATCH_IDS = PATCHES.map(p => p.id);

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5050';

// Earth Engine evaluates map tiles lazily. During animated zooms Leaflet's
// defaults can request several zoom levels at once, which quickly triggers GEE
// throttling when multiple imagery layers are stacked. Sentinel-2 is 10 m, so
// tiles above z14 add no source detail; let Leaflet upscale the z14 tiles.
const GEE_TILE_OPTIONS = {
  updateWhenIdle: true,
  updateWhenZooming: false,
  updateInterval: 400,
  keepBuffer: 1,
  maxNativeZoom: 14,
  maxZoom: 20,
  detectRetina: false,
  crossOrigin: true
};

const IMAGERY_LAYER_TYPES = [
  'baselineTrueColor',
  'baselineDetection',
  'comparisonTrueColor',
  'comparisonDetection',
  'imageryTrueColor',
  'imageryDetection'
];

// Browser connection limits alone are not enough to protect Earth Engine from
// a Leaflet tile burst (especially when an analysis overlay is also visible).
// Share a small queue across every GEE layer to stay below the observed 429
// throttling threshold while still loading several tiles in parallel.
const GEE_MAX_CONCURRENT_TILES = 3;
const geeTileQueue = [];
let geeTilesInFlight = 0;

const startGeeTileTask = (task) => {
  task.active = true;
  geeTilesInFlight += 1;

  const finish = (error) => {
    if (task.settled) return;
    task.settled = true;
    task.active = false;
    geeTilesInFlight = Math.max(0, geeTilesInFlight - 1);
    delete task.tile._geeTask;
    task.done(error, task.tile);
    drainGeeTileQueue();
  };

  task.cancel = () => {
    if (task.settled) return;
    task.cancelled = true;
    task.settled = true;
    task.tile.onload = null;
    task.tile.onerror = null;
    task.tile.src = L.Util.emptyImageUrl;
    if (task.active) geeTilesInFlight = Math.max(0, geeTilesInFlight - 1);
    delete task.tile._geeTask;
    drainGeeTileQueue();
  };

  task.tile.onload = () => finish(null);
  task.tile.onerror = () => finish(new Error('Earth Engine tile failed to load'));
  task.tile.src = task.layer.getTileUrl(task.coords);
};

const drainGeeTileQueue = () => {
  while (geeTilesInFlight < GEE_MAX_CONCURRENT_TILES && geeTileQueue.length > 0) {
    const task = geeTileQueue.shift();
    const tileKey = task.layer._tileCoordsToKey(task.coords);
    const liveTile = task.layer._tiles?.[tileKey]?.el;

    if (task.cancelled || !task.layer._map || liveTile !== task.tile) continue;
    startGeeTileTask(task);
  }
};

class GeeTileLayer extends L.TileLayer {
  createTile(coords, done) {
    const tile = document.createElement('img');
    tile.alt = '';
    tile.setAttribute('role', 'presentation');
    tile.decoding = 'async';

    if (this.options.crossOrigin || this.options.crossOrigin === '') {
      tile.crossOrigin = this.options.crossOrigin === true ? '' : this.options.crossOrigin;
    }

    const task = {
      layer: this,
      tile,
      coords,
      done,
      active: false,
      cancelled: false,
      settled: false,
      cancel: null
    };
    tile._geeTask = task;
    geeTileQueue.push(task);

    // Leaflet records the tile in this._tiles immediately after createTile
    // returns, so start draining on the next microtask.
    Promise.resolve().then(drainGeeTileQueue);
    return tile;
  }

  _removeTile(key) {
    this._tiles?.[key]?.el?._geeTask?.cancel?.();
    return super._removeTile(key);
  }

  _abortLoading() {
    Object.values(this._tiles || {}).forEach(({ coords, el }) => {
      if (coords.z !== this._tileZoom) el?._geeTask?.cancel?.();
    });
    return super._abortLoading();
  }
}

const createGeeTileLayer = (url, options = {}) => (
  new GeeTileLayer(url, { ...GEE_TILE_OPTIONS, ...options })
);

const STUDY_LINE_DATA = [
  { id: 'western', name: 'Western', geojson: westernStudyline },
  { id: 'central', name: 'Central', geojson: centralStudyline },
  { id: 'eastern', name: 'Eastern', geojson: easternStudyline },
  { id: 'easternMost', name: 'Eastern Most', geojson: easternMostStudyline },
  { id: 'westernMost', name: 'Western Most', geojson: westernMostStudyline }
];

const LOCAL_STUDY_AREAS = STUDY_LINE_DATA
  .map(({ id, name, geojson }) => {
    const geom = geojson?.features?.[0]?.geometry;
    return geom && (geom.type === 'Polygon' || geom.type === 'MultiPolygon')
      ? { id, name, geometry: geom }
      : null;
  })
  .filter(Boolean);

function bboxToPolygon(bbox) {
  const [w, s, e, n] = bbox;
  return { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

function studyAreaLabelForReport(selectedAreaMode, studyAreas) {
  if (selectedAreaMode === 'custom') return 'Custom Polygon';
  const patch = PATCHES.find((p) => p.id === selectedAreaMode);
  if (patch) return patch.name;
  if (selectedAreaMode?.startsWith('study_')) {
    const id = selectedAreaMode.replace(/^study_/, '');
    const sa = studyAreas.find((s) => String(s.id) === String(id));
    return sa?.name || 'Study area';
  }
  return '—';
}

async function buildCoastalReportPdf({
  analysisData,
  selectedAreaMode,
  studyAreas,
  baselineStartDate,
  baselineEndDate,
  comparisonStartDate,
  comparisonEndDate,
  dsasData,
  getMapEl,
  invalidateMap
}) {
  const pageW = 210;
  const pageH = 297;
  const M = 10;
  const W = pageW - 2 * M;
  const today = new Date();
  const todayStr = today.toLocaleDateString('en-CA', { year: 'numeric', month: 'long', day: 'numeric' });
  const dateShort = today.toISOString().slice(0, 10);
  const studyLabel = studyAreaLabelForReport(selectedAreaMode, studyAreas);
  const baselineKm = Number(analysisData.baseline_land_area || 0);
  const comparisonKm = Number(analysisData.comparison_land_area || 0);
  const areaChange = Number(analysisData.erosion_area || 0);
  const chgPct = Number.isFinite(Number(analysisData.change_percentage)) ? Number(analysisData.change_percentage) : null;
  const isErosion = areaChange < 0;

  const doc = new jsPDF('p', 'mm', 'a4');
  doc.setFillColor(15, 41, 66); // #0f2942
  doc.rect(0, 0, pageW, pageH, 'F');

  const cardFill = [26, 61, 92]; // #1a3d5c
  const cardBorder = [58, 91, 122];
  const sectionTeal = [78, 205, 196]; // #4ecdc4

  const drawCard = (x, y, w, h) => {
    doc.setFillColor(...cardFill);
    doc.setDrawColor(...cardBorder);
    doc.setLineWidth(0.3);
    doc.roundedRect(x, y, w, h, 2.8, 2.8, 'FD');
  };

  const drawSectionHeader = (x, y, title) => {
    doc.setDrawColor(...sectionTeal);
    doc.setLineWidth(0.8);
    doc.line(x, y - 3, x, y + 2.5);
    doc.setTextColor(...sectionTeal);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.text(title, x + 2.4, y);
  };

  // Sticky-style top header
  const headerH = 24;
  drawCard(M, M, W, headerH);
  doc.setFillColor(38, 73, 107);
  doc.roundedRect(M + 3, M + 4, 16, 16, 2, 2, 'F');
  doc.setTextColor(182, 208, 224);
  doc.setFontSize(7);
  doc.setFont('helvetica', 'bold');
  doc.text('LOGO', M + 11, M + 13, { align: 'center' });
  doc.setTextColor(230, 242, 249);
  doc.setFontSize(14);
  doc.text('PEI COASTAL EROSION REPORT', M + 22, M + 11);
  doc.setFontSize(8.5);
  doc.setFont('helvetica', 'normal');
  doc.text(`Area: ${studyLabel}`, M + 22, M + 16.3);
  doc.setFillColor(32, 95, 128);
  doc.roundedRect(M + W - 46, M + 5, 42, 10, 5, 5, 'F');
  doc.setTextColor(217, 242, 240);
  doc.setFontSize(8);
  doc.text(`Generated ${todayStr}`, M + W - 25, M + 11.5, { align: 'center' });

  // KPI cards (2 columns x 2 rows)
  const kpiY = M + headerH + 4;
  const gap = 4;
  const colW = (W - gap) / 2;
  const kpiH = 20;
  const kpiData = [
    { icon: 'B', label: 'Baseline Area', value: `${baselineKm.toFixed(2)} km2`, color: [143, 207, 245] },
    { icon: 'C', label: 'Comparison Area', value: `${comparisonKm.toFixed(2)} km2`, color: [255, 179, 132] },
    { icon: isErosion ? 'E' : 'A', label: isErosion ? 'Erosion' : 'Accretion', value: `${areaChange.toFixed(2)} km2`, color: isErosion ? [244, 114, 114] : [94, 234, 212] },
    { icon: isErosion ? 'v' : '^', label: 'Change', value: chgPct != null ? `${chgPct.toFixed(2)}%` : 'Data Pending', color: isErosion ? [248, 113, 113] : [45, 212, 191] }
  ];
  kpiData.forEach((kpi, idx) => {
    const row = Math.floor(idx / 2);
    const col = idx % 2;
    const x = M + col * (colW + gap);
    const y = kpiY + row * (kpiH + gap);
    drawCard(x, y, colW, kpiH);
    doc.setFillColor(20, 51, 78);
    doc.circle(x + 6.2, y + 6.6, 3.6, 'F');
    doc.setTextColor(...kpi.color);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.text(kpi.icon, x + 6.2, y + 7.6, { align: 'center' });
    doc.setTextColor(156, 200, 216);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.text(kpi.label, x + 12, y + 7);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...kpi.color);
    doc.setFontSize(11);
    doc.text(kpi.value, x + 12, y + 13.6);
  });

  // Two-column section zone
  const bodyTop = kpiY + (kpiH * 2) + gap + 5;
  const panelH = 72;
  const leftX = M;
  const rightX = M + colW + gap;

  // Enhanced bar chart panel (drawn in PDF with polished styling)
  drawCard(leftX, bodyTop, colW, panelH);
  drawSectionHeader(leftX + 4, bodyTop + 8, 'Enhanced Bar Chart');
  const cx = leftX + 6;
  const cy = bodyTop + 14;
  const cw = colW - 12;
  const ch = panelH - 20;
  doc.setDrawColor(108, 141, 163);
  doc.setLineWidth(0.2);
  for (let i = 0; i <= 4; i++) {
    const gy = cy + (ch / 4) * i;
    doc.line(cx, gy, cx + cw, gy);
  }
  const vmax = Math.max(baselineKm, comparisonKm, 0.01);
  const padTop = 6;
  const baseY = cy + ch - 4;
  const usable = ch - padTop - 9;
  const b1 = (baselineKm / vmax) * usable;
  const b2 = (comparisonKm / vmax) * usable;
  const bw = 11;
  const bgap = 17;
  const bx1 = cx + cw / 2 - (bw + bgap / 2);
  const bx2 = bx1 + bw + bgap;

  // Dashed reference line at baseline
  doc.setDrawColor(143, 207, 245);
  doc.setLineDashPattern([1.4, 1.2], 0);
  doc.line(cx + 1, baseY - b1, cx + cw - 1, baseY - b1);
  doc.setLineDashPattern([], 0);

  doc.setFillColor(74, 172, 184);
  doc.roundedRect(bx1, baseY - b1, bw, b1, 1.4, 1.4, 'F');
  doc.setFillColor(214, 112, 78);
  doc.roundedRect(bx2, baseY - b2, bw, b2, 1.4, 1.4, 'F');
  doc.setTextColor(198, 230, 241);
  doc.setFontSize(7.5);
  doc.text(`${baselineKm.toFixed(2)}`, bx1 + bw / 2, baseY - b1 - 1.8, { align: 'center' });
  doc.text(`${comparisonKm.toFixed(2)}`, bx2 + bw / 2, baseY - b2 - 1.8, { align: 'center' });
  doc.setTextColor(160, 198, 213);
  doc.text('Baseline', bx1 + bw / 2, baseY + 4.2, { align: 'center' });
  doc.text('Comparison', bx2 + bw / 2, baseY + 4.2, { align: 'center' });

  // Study information panel
  drawCard(rightX, bodyTop, colW, panelH);
  drawSectionHeader(rightX + 4, bodyTop + 8, 'Study Information');
  const tx = rightX + 6;
  let ty = bodyTop + 16;
  doc.setTextColor(164, 203, 219);
  doc.setFontSize(8);
  doc.setFont('helvetica', 'normal');
  doc.text(`Area: ${studyLabel}`, tx, ty);
  ty += 6.5;
  doc.text(`Baseline: ${baselineStartDate} to ${baselineEndDate}`, tx, ty);
  ty += 6.5;
  doc.text(`Comparison: ${comparisonStartDate} to ${comparisonEndDate}`, tx, ty);
  ty += 6.5;
  doc.text(`Change Type: ${isErosion ? 'Erosion' : 'Accretion'}`, tx, ty);

  // Map section
  const mapY = bodyTop + panelH + 5;
  const mapH = pageH - mapY - 20;
  drawCard(M, mapY, W, mapH);
  drawSectionHeader(M + 4, mapY + 8, 'Shoreline Comparison Map');

  invalidateMap();
  // Wait for Leaflet tiles to fully paint before capturing
  await new Promise((r) => setTimeout(r, 900));
  const mapEl = getMapEl();
  if (!mapEl) throw new Error('Map container not found');
  // Force a second invalidation + settle so all tile images are loaded
  invalidateMap();
  await new Promise((r) => setTimeout(r, 600));
  const mapCanvas = await html2canvas(mapEl, {
    scale: 1.2,
    useCORS: true,
    allowTaint: true,
    logging: false,
    backgroundColor: '#e8f4f8',
    imageTimeout: 15000,
    onclone: (clonedDoc) => {
      // Ensure the cloned map container keeps its dimensions
      const clonedMap = clonedDoc.querySelector('.dashboard-map-container') || clonedDoc.getElementById('map');
      if (clonedMap) {
        clonedMap.style.overflow = 'visible';
      }
    }
  });
  const mapData = mapCanvas.toDataURL('image/jpeg', 0.88);
  const imgX = M + 4;
  const imgY = mapY + 11;
  const imgW = W - 8;
  const rawH = (mapCanvas.height / mapCanvas.width) * imgW;
  const imgH = Math.min(rawH, mapH - 22);

  doc.setDrawColor(79, 112, 138);
  doc.setLineWidth(0.4);
  doc.roundedRect(imgX, imgY, imgW, imgH, 2, 2, 'S');
  doc.addImage(mapData, 'JPEG', imgX, imgY, imgW, imgH);

  // Legend overlay
  const lgW = 36;
  const lgH = 14;
  const lgX = imgX + imgW - lgW - 3;
  const lgY = imgY + 3;
  doc.setFillColor(22, 47, 72);
  doc.setDrawColor(89, 121, 146);
  doc.roundedRect(lgX, lgY, lgW, lgH, 1.8, 1.8, 'FD');
  doc.setFontSize(7);
  doc.setTextColor(219, 235, 243);
  doc.setFillColor(74, 172, 184);
  doc.rect(lgX + 2.3, lgY + 3, 2.8, 2.8, 'F');
  doc.text('Accretion', lgX + 6.1, lgY + 5.5);
  doc.setFillColor(181, 83, 66);
  doc.rect(lgX + 2.3, lgY + 8, 2.8, 2.8, 'F');
  doc.text('Erosion', lgX + 6.1, lgY + 10.5);

  // Caption
  doc.setTextColor(156, 192, 208);
  doc.setFontSize(8);
  doc.setFont('helvetica', 'italic');
  doc.text(
    `${studyLabel} PEI — Baseline ${baselineStartDate?.slice(0, 4) || 'N/A'} vs Comparison ${comparisonStartDate?.slice(0, 4) || 'N/A'}`,
    M + 5,
    imgY + imgH + 5
  );

  // Footer
  doc.setDrawColor(57, 89, 114);
  doc.line(M, pageH - 11.5, pageW - M, pageH - 11.5);
  doc.setTextColor(146, 184, 201);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.text(`PEI Coastal Erosion Monitoring System | Generated ${todayStr}`, pageW / 2, pageH - 7.4, { align: 'center' });

  doc.save(`pei-coastal-report-${dateShort}.pdf`);
}

const Dashboard = () => {
  const location = useLocation();
  const [baselineStartDate, setBaselineStartDate] = useState('2019-05-01');
  const [baselineEndDate, setBaselineEndDate] = useState('2019-10-31');
  const [comparisonStartDate, setComparisonStartDate] = useState('2020-05-01');
  const [comparisonEndDate, setComparisonEndDate] = useState('2020-10-31');
  const [errorMessage, setErrorMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [loadingSlow, setLoadingSlow] = useState(false);
  const [activeLayers, setActiveLayers] = useState(new Set(['studyLines'])); // studyLines on by default so study lines show
  const [analysisData, setAnalysisData] = useState(null);
  const [drawnPolygon, setDrawnPolygon] = useState(null);
  const [baselineData, setBaselineData] = useState(null);
  const [comparisonBoundaryGeo, setComparisonBoundaryGeo] = useState(null);
  const [dsasData, setDsasData] = useState(null);
  const [selectedAreaMode, setSelectedAreaMode] = useState(''); // '' | 'custom' | patch id | 'study_<id>'
  const [studyAreas] = useState(LOCAL_STUDY_AREAS); // bundled study polygons; available immediately on dashboard load
  const [bottomTab, setBottomTab] = useState('charts'); // 'charts' | 'reports'
  const [workflowStep, setWorkflowStep] = useState(0); // 0:none, 1:baseline, 2:comparison, 3:erosion, 4:dsas
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [showBenchmarkModal, setShowBenchmarkModal] = useState(false);
  const [showLayersPanel, setShowLayersPanel] = useState(false);
  const [loadingDownload,setLoadingDownload] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mapRef = useRef(null);
  const barChartRef = useRef(null);
  const barChartInstance = useRef(null);
  const drawControlRef = useRef(null);
  const drawControlOnMapRef = useRef(true); // track if draw control is currently on map
  const drawnLayerRef = useRef(null);
  const patchLayersRef = useRef({});
  const studyAreaLayersRef = useRef({});
  const studyAreaLayerGroupRef = useRef(null);
  const loadingSlowTimerRef = useRef(null);

  const layers = useRef({
    baseMap: null,
    userPolygon: null,
    baselineImagery: { trueColor: null, ndwi: null },
    baselineBoundary: null,
    comparisonImagery: { trueColor: null, ndwi: null },
    comparisonBoundary: null,
    imagery: { trueColor: null, ndwi: null },  // Reference: get_imagery with roi
    transects: null,
    change: { erosion: null },
    baselineDetectionPEI: null,
    currentShorelineDetection: null
  });

  useEffect(() => {
    if (loadingSlowTimerRef.current) {
      clearTimeout(loadingSlowTimerRef.current);
      loadingSlowTimerRef.current = null;
    }

    if (!loading) {
      setLoadingSlow(false);
      return undefined;
    }

    setLoadingSlow(false);
    loadingSlowTimerRef.current = setTimeout(() => {
      setLoadingSlow(true);
    }, 180000);

    return () => {
      if (loadingSlowTimerRef.current) {
        clearTimeout(loadingSlowTimerRef.current);
        loadingSlowTimerRef.current = null;
      }
    };
  }, [loading]);

  useEffect(() => {
    initializeMap();
    return () => {
      if (mapRef.current) mapRef.current.remove();
    };
  }, []);

  // Add dashboard-page class to html and body to prevent scrollbars
  // Only when we're actually on the dashboard route
  useEffect(() => {
    const isDashboard = location.pathname === '/dashboard';
    
    if (isDashboard) {
      document.documentElement.classList.add('dashboard-page');
      document.body.classList.add('dashboard-page');
      const raf1 = requestAnimationFrame(() => {
        const raf2 = requestAnimationFrame(() => {
          if (mapRef.current) {
            mapRef.current.invalidateSize({ animate: false });
          }
        });
        return () => cancelAnimationFrame(raf2);
      });

      return () => {
        cancelAnimationFrame(raf1);
        document.documentElement.classList.remove('dashboard-page');
        document.body.classList.remove('dashboard-page');
      };
    } else {
      document.documentElement.classList.remove('dashboard-page');
      document.body.classList.remove('dashboard-page');
    }
    
    return () => {
      document.documentElement.classList.remove('dashboard-page');
      document.body.classList.remove('dashboard-page');
    };
  }, [location.pathname]);

  useEffect(() => {
    if (!mapRef.current || !studyAreaLayerGroupRef.current || studyAreas.length === 0) return;
    studyAreaLayerGroupRef.current.clearLayers();
    studyAreaLayersRef.current = {};
    const fc = {
      type: 'FeatureCollection',
      features: studyAreas.map((s) => ({
        type: 'Feature',
        properties: { id: s.id, name: s.name },
        geometry: s.geometry
      }))
    };
    L.geoJSON(fc, {
      onEachFeature: (feature, layer) => {
        const id = feature.properties.id;
        studyAreaLayersRef.current[id] = layer;
        layer.on('click', () => setSelectedAreaMode('study_' + id));
        layer.bindTooltip(feature.properties.name + ' (study line)', { permanent: false });
        layer.setStyle({ weight: 2, color: '#9c27b0', fillOpacity: 0.2, fillColor: '#9c27b0' });
        studyAreaLayerGroupRef.current.addLayer(layer);
      }
    });
    if (typeof studyAreaLayerGroupRef.current.bringToFront === 'function') {
      studyAreaLayerGroupRef.current.bringToFront();
    }
    // Keep study areas visible by default even when this async effect runs with stale activeLayers.
    const shouldShowStudyLines = activeLayers.has('studyLines') || activeLayers.size === 0;
    if (mapRef.current && shouldShowStudyLines && studyAreaLayerGroupRef.current.getLayers().length > 0 && !mapRef.current.hasLayer(studyAreaLayerGroupRef.current)) {
      studyAreaLayerGroupRef.current.addTo(mapRef.current);
    }
  }, [studyAreas, activeLayers]);

  // Fetch PEI-wide shoreline baseline in the background after map is ready (deferred to avoid blocking initial load)
  useEffect(() => {
    if (!mapRef.current || !baselineStartDate || !baselineEndDate) return;
    const t = setTimeout(() => {
      const params = new URLSearchParams({ start_date: baselineStartDate, end_date: baselineEndDate });
      fetch(`${API_BASE}/get_baseline?${params}`)
        .then((res) => res.ok ? res.json() : Promise.reject(new Error('get_baseline failed')))
        .then((data) => {
          if (!mapRef.current) return;
          const shoreline = data.shoreline_geojson;
          const geojson = (shoreline && shoreline.features?.length) ? shoreline : data.geojson;
          if (!geojson || !geojson.features?.length) return;
          if (layers.current.baselineDetectionPEI && mapRef.current.hasLayer(layers.current.baselineDetectionPEI)) {
            mapRef.current.removeLayer(layers.current.baselineDetectionPEI);
          }
          const start = data.baseline_start || baselineStartDate;
          const end = data.baseline_end || baselineEndDate;
          const isShoreline = shoreline && shoreline.features?.length;
          layers.current.baselineDetectionPEI = L.geoJSON(geojson, {
            style: {
              color: '#e74c3c',
              weight: isShoreline ? 3 : 2,
              dashArray: '8,4',
              fillOpacity: isShoreline ? 0 : 0.1,
              fillColor: '#e74c3c'
            },
            onEachFeature: (feature, layer) => {
              layer.bindPopup(
                '<div style="font-family: Arial, sans-serif;">' +
                '<h4 style="margin: 0 0 8px 0; color: #e74c3c;">Baseline Shoreline</h4>' +
                '<p style="margin: 0; font-size: 12px;">' + start + ' to ' + end + '. Shoreline detection layer.</p>' +
                '</div>'
              );
            }
          });
        })
        .catch((err) => console.warn('PEI baseline load:', err.message));
    }, 1200);
    return () => clearTimeout(t);
  }, [baselineStartDate, baselineEndDate]);

  useEffect(() => {
    if (analysisData && !loading) updateChart();
  }, [analysisData, loading]);

  useEffect(() => {
    if (showResultsModal && analysisData) {
      // Small delay to ensure modal is rendered
      setTimeout(() => {
        updateChart();
      }, 100);
    }
  }, [showResultsModal]);

  const getActivePolygon = () => {
    if (PATCH_IDS.includes(selectedAreaMode)) {
      const patch = PATCHES.find(p => p.id === selectedAreaMode);
      return patch ? bboxToPolygon(patch.bbox) : null;
    }
    if (selectedAreaMode && selectedAreaMode.startsWith('study_')) {
      const id = selectedAreaMode.replace(/^study_/, '');
      const sa = studyAreas.find(s => s.id === id);
      return sa ? sa.geometry : null;
    }
    if (selectedAreaMode === 'custom') return drawnPolygon || null;
    return null;
  };

  /** Reference: ROI for API (get_imagery, get_shoreline_data, analyze_change). */
  const getRoiForApi = () => getActivePolygon();

  const hasActiveArea = selectedAreaMode === 'custom'
    ? !!drawnPolygon
    : PATCH_IDS.includes(selectedAreaMode) || (selectedAreaMode && selectedAreaMode.startsWith('study_') && studyAreas.some(s => 'study_' + s.id === selectedAreaMode));

  useEffect(() => {
    if (!mapRef.current || !patchLayersRef.current) return;
    const isCustom = selectedAreaMode === 'custom';
    const isStudy = selectedAreaMode && selectedAreaMode.startsWith('study_');
    const isPatch = PATCH_IDS.includes(selectedAreaMode);
    const showMyPolygon = activeLayers.has('myPolygon');

    // When an AOI is selected, "My polygon" controls visibility of that AOI outline
    if (hasActiveArea && !showMyPolygon) {
      PATCHES.forEach(({ id }) => {
        const layer = patchLayersRef.current[id];
        if (layer && mapRef.current.hasLayer(layer)) mapRef.current.removeLayer(layer);
      });
      if (studyAreaLayerGroupRef.current) studyAreaLayerGroupRef.current.clearLayers();
      if (isCustom && drawnLayerRef.current && mapRef.current.hasLayer(drawnLayerRef.current)) {
        mapRef.current.removeLayer(drawnLayerRef.current);
      }
      return;
    }

    // Patches: show only the selected patch when a patch is selected; show all when nothing selected; hide all when custom or study
    PATCHES.forEach(({ id }) => {
      const layer = patchLayersRef.current[id];
      if (!layer) return;
      if (isCustom || isStudy) {
        if (mapRef.current.hasLayer(layer)) mapRef.current.removeLayer(layer);
      } else if (isPatch) {
        if (selectedAreaMode === id) {
          if (!mapRef.current.hasLayer(layer)) layer.addTo(mapRef.current);
          layer.setStyle({ weight: 4, color: '#1565c0', fillOpacity: 0.25, fillColor: '#1565c0' });
        } else {
          if (mapRef.current.hasLayer(layer)) mapRef.current.removeLayer(layer);
        }
      } else {
        if (!mapRef.current.hasLayer(layer)) layer.addTo(mapRef.current);
        layer.setStyle({ weight: 2, color: '#666', fillOpacity: 0.12, fillColor: '#1565c0' });
      }
    });

    // Study lines: show only the selected study line when one is selected; show all when nothing selected; hide all when patch or custom
    if (studyAreaLayerGroupRef.current) {
      const showStudyLines = activeLayers.has('studyLines');
      if (mapRef.current.hasLayer(studyAreaLayerGroupRef.current) && !showStudyLines) {
        mapRef.current.removeLayer(studyAreaLayerGroupRef.current);
      }
      studyAreaLayerGroupRef.current.clearLayers();
      if (isStudy) {
        const id = selectedAreaMode.replace(/^study_/, '');
        const layer = studyAreaLayersRef.current[id];
        if (layer) {
          studyAreaLayerGroupRef.current.addLayer(layer);
          layer.setStyle({ weight: 4, color: '#7b1fa2', fillOpacity: 0.25, fillColor: '#9c27b0' });
        }
      } else if (!isPatch && !isCustom) {
        Object.keys(studyAreaLayersRef.current).forEach((sid) => {
          const layer = studyAreaLayersRef.current[sid];
          if (layer) {
            studyAreaLayerGroupRef.current.addLayer(layer);
            layer.setStyle({ weight: 2, color: '#9c27b0', fillOpacity: 0.2, fillColor: '#9c27b0' });
          }
        });
      }
      if (showStudyLines && studyAreaLayerGroupRef.current.getLayers().length > 0 && !mapRef.current.hasLayer(studyAreaLayerGroupRef.current)) {
        studyAreaLayerGroupRef.current.addTo(mapRef.current);
      }
      if (showStudyLines && mapRef.current.hasLayer(studyAreaLayerGroupRef.current) && typeof studyAreaLayerGroupRef.current.bringToFront === 'function') {
        studyAreaLayerGroupRef.current.bringToFront();
      }
    }

    // Drawn polygon (custom AOI): show when custom selected and myPolygon is on
    if (isCustom && drawnLayerRef.current) {
      if (!mapRef.current.hasLayer(drawnLayerRef.current)) drawnLayerRef.current.addTo(mapRef.current);
    }

    if (isPatch) {
      const layer = patchLayersRef.current[selectedAreaMode];
      if (layer) mapRef.current.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 12 });
    } else if (isStudy) {
      const id = selectedAreaMode.replace(/^study_/, '');
      const layer = studyAreaLayersRef.current[id];
      if (layer) mapRef.current.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 12 });
    }
  }, [selectedAreaMode, activeLayers, hasActiveArea, studyAreas.length]);

  useEffect(() => {
    if (hasActiveArea && !activeLayers.has('myPolygon')) {
      setActiveLayers(prev => new Set([...prev, 'myPolygon']));
    }
  }, [selectedAreaMode, drawnPolygon]);

  // Reset workflow when baseline inputs/AOI change
  useEffect(() => {
    setWorkflowStep(0);
  }, [selectedAreaMode, drawnPolygon, baselineStartDate, baselineEndDate]);

  // Reset downstream workflow when comparison date range changes
  useEffect(() => {
    setWorkflowStep(prev => Math.min(prev, 1));
  }, [comparisonStartDate, comparisonEndDate]);

  // When an AOI (patch) or study line is selected, hide the draw-polygon control so it doesn't appear
  useEffect(() => {
    if (!mapRef.current || !drawControlRef.current) return;
    const isPatchOrStudy = PATCH_IDS.includes(selectedAreaMode) || (selectedAreaMode && selectedAreaMode.startsWith('study_'));
    if (isPatchOrStudy && drawControlOnMapRef.current) {
      mapRef.current.removeControl(drawControlRef.current);
      drawControlOnMapRef.current = false;
    } else if (!isPatchOrStudy && !drawControlOnMapRef.current) {
      mapRef.current.addControl(drawControlRef.current);
      drawControlOnMapRef.current = true;
    }
  }, [selectedAreaMode]);

  const normalizeBoundaryToFeatureCollection = (geo) => {
    if (!geo || !geo.type) return null;
    if (geo.type === 'FeatureCollection' && Array.isArray(geo.features)) return geo;
    if (geo.type === 'Feature' && geo.geometry) {
      return { type: 'FeatureCollection', features: [geo] };
    }
    if (geo.type === 'Polygon' || geo.type === 'MultiPolygon' || geo.type === 'LineString' || geo.type === 'MultiLineString') {
      return {
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: geo, properties: {} }]
      };
    }
    return null;
  };

  const initializeMap = () => {
    mapRef.current = L.map('map').setView([46.5107, -63.4168], 10);
    
    // Pane for boundary layers so they always appear on top of imagery
    if (!mapRef.current.getPane('boundaryPane')) {
      mapRef.current.createPane('boundaryPane');
    }
    mapRef.current.getPane('boundaryPane').style.zIndex = 650;
    
    // Base map — updateWhenIdle/keepBuffer reduce tile thrashing and lag when panning
    layers.current.baseMap = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap, © CartoDB',
      subdomains: 'abcd',
      maxZoom: 20,
      updateWhenIdle: true,
      keepBuffer: 3
    }).addTo(mapRef.current);

    // Recompute map size after layout — use rAF so the browser has painted
    // the grid/flex layout before Leaflet measures the container.
    // A second rAF pass is added as a safety net for slower devices.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (mapRef.current) mapRef.current.invalidateSize({ animate: false });
      });
    });
    // Fallback for cases where the container is still hidden (display:none nav)
    setTimeout(() => {
      if (mapRef.current) mapRef.current.invalidateSize({ animate: false });
    }, 500);

    // Predefined patch rectangles (click to select)
    PATCHES.forEach(({ id, name, bbox }) => {
      const [w, s, e, n] = bbox;
      const bounds = L.latLngBounds([s, w], [n, e]);
      const layer = L.rectangle(bounds, {
        weight: 2,
        color: '#666',
        fillOpacity: 0.12,
        fillColor: '#1565c0'
      });
      layer.on('click', () => setSelectedAreaMode(id));
      layer.bindTooltip(name, { permanent: false, direction: 'center' });
      layer.addTo(mapRef.current);
      patchLayersRef.current[id] = layer;
    });

    // Study areas layer group (populated when studyAreas loads; added to map when "Study lines" layer is on)
    studyAreaLayerGroupRef.current = L.layerGroup();

    // Add drawing controls
    const drawControl = new L.Control.Draw({
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          drawError: {
            color: '#e1e100',
            message: '<strong>Oh snap!</strong> you can\'t draw that!'
          },
          shapeOptions: {
            color: '#97009c',
            fillColor: '#97009c',
            fillOpacity: 0.2
          }
        },
        polyline: false,
        circle: false,
        rectangle: false,
        marker: false,
        circlemarker: false
      },
      edit: {
        featureGroup: drawnLayerRef.current || new L.FeatureGroup(),
        remove: true
      }
    });

    mapRef.current.addControl(drawControl);
    drawControlRef.current = drawControl;
    drawControlOnMapRef.current = true;

    // Handle polygon drawing
    mapRef.current.on(L.Draw.Event.CREATED, (e) => {
      const { layer } = e;
      let geoJson = layer.toGeoJSON();
      
      try {
        // Fix polygon geometry: ensure coordinates are properly formatted
        // Leaflet.draw creates GeoJSON with [lon, lat] format (GeoJSON standard)
        if (geoJson.geometry && geoJson.geometry.type === 'Polygon' && geoJson.geometry.coordinates) {
          if (geoJson.geometry.coordinates.length === 0) {
            throw new Error('Polygon has no coordinate rings');
          }
          
          const coords = geoJson.geometry.coordinates[0];
          if (!Array.isArray(coords) || coords.length < 3) {
            throw new Error('Polygon must have at least 3 vertices');
          }
          
          // Validate and clean coordinates
          const validCoords = [];
          for (let i = 0; i < coords.length; i++) {
            const coord = coords[i];
            if (!Array.isArray(coord) || coord.length < 2) {
              console.warn(`Skipping invalid coordinate at index ${i}:`, coord);
              continue;
            }
            
            const lon = parseFloat(coord[0]);
            const lat = parseFloat(coord[1]);
            
            if (isNaN(lon) || isNaN(lat)) {
              console.warn(`Skipping invalid coordinate at index ${i}:`, coord);
              continue;
            }
            
            // Validate longitude and latitude ranges
            if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
              console.warn(`Coordinate out of range at index ${i}:`, [lon, lat]);
              continue;
            }
            
            validCoords.push([lon, lat]);
          }
          
          if (validCoords.length < 3) {
            throw new Error(`Polygon must have at least 3 valid vertices (found ${validCoords.length})`);
          }
          
          // Ensure polygon is closed (first and last point must be the same)
          const first = validCoords[0];
          const last = validCoords[validCoords.length - 1];
          
          // Check if polygon is already closed (with small tolerance)
          const isClosed = Math.abs(first[0] - last[0]) < 0.0000001 && 
                          Math.abs(first[1] - last[1]) < 0.0000001;
          
          if (!isClosed) {
            // Close the polygon by adding the first point at the end
            validCoords.push([first[0], first[1]]);
          }
          
          // Update the coordinates
          geoJson.geometry.coordinates[0] = validCoords;
          
          // Validate the final GeoJSON structure
          if (!geoJson.geometry.coordinates[0] || geoJson.geometry.coordinates[0].length < 4) {
            throw new Error('Invalid polygon after processing');
          }
          
          console.log(`Polygon validated: ${validCoords.length} coordinates`);
          
          // Extract just the geometry from the Feature (Leaflet.draw returns a Feature)
          // Earth Engine expects just the geometry, not the full Feature
          const polygonGeometry = {
            type: geoJson.geometry.type,
            coordinates: geoJson.geometry.coordinates
          };
          
          // Remove previous polygon if exists
          if (drawnLayerRef.current) {
            mapRef.current.removeLayer(drawnLayerRef.current);
          }
          
          drawnLayerRef.current = layer;
          mapRef.current.addLayer(layer);
          setDrawnPolygon(polygonGeometry);
          setSelectedAreaMode('custom');
          setActiveLayers(prev => new Set([...prev, 'drawnPolygon']));
        } else {
          throw new Error('Invalid polygon geometry type');
        }
        
        mapRef.current.fitBounds(layer.getBounds());
        showError('Polygon drawn successfully! Select baseline dates and load baseline.');
      } catch (error) {
        console.error('Polygon validation error:', error);
        showError(`Error processing polygon: ${error.message}`);
        // Remove the invalid layer
        mapRef.current.removeLayer(layer);
      }
    });

    // Handle polygon editing — extract geometry only (same as CREATED path) so the
    // backend receives a plain Polygon, not a GeoJSON Feature wrapper
    mapRef.current.on(L.Draw.Event.EDITED, (e) => {
      e.layers.eachLayer((layer) => {
        const geoJson = layer.toGeoJSON();
        // Extract just the geometry (Polygon), not the Feature wrapper
        const geometry = geoJson?.geometry || geoJson;
        if (geometry && geometry.type === 'Polygon' && geometry.coordinates?.length) {
          setDrawnPolygon(geometry);
          // Zoom to the edited polygon just like after initial draw
          if (layer.getBounds) mapRef.current.fitBounds(layer.getBounds());
        }
      });
    });

    // Handle polygon deletion
    mapRef.current.on(L.Draw.Event.DELETED, () => {
      setDrawnPolygon(null);
      drawnLayerRef.current = null;
      if (selectedAreaMode === 'custom') setSelectedAreaMode('');
      clearAllAnalysis();
    });
  };

  const clearAllAnalysis = () => {
    if (mapRef.current) {
      Object.values(layers.current.comparisonImagery).forEach(layer => {
        if (layer) mapRef.current.removeLayer(layer);
      });
      if (layers.current.comparisonBoundary) mapRef.current.removeLayer(layers.current.comparisonBoundary);
      Object.values(layers.current.baselineImagery).forEach(layer => {
        if (layer) mapRef.current.removeLayer(layer);
      });
      if (layers.current.baselineBoundary) mapRef.current.removeLayer(layers.current.baselineBoundary);
      Object.values(layers.current.imagery).forEach(layer => {
        if (layer) mapRef.current.removeLayer(layer);
      });
      if (layers.current.transects) mapRef.current.removeLayer(layers.current.transects);
      if (layers.current.change.erosion) mapRef.current.removeLayer(layers.current.change.erosion);
      if (layers.current.baselineDetectionPEI && mapRef.current.hasLayer(layers.current.baselineDetectionPEI)) {
        mapRef.current.removeLayer(layers.current.baselineDetectionPEI);
      }
      if (layers.current.currentShorelineDetection && mapRef.current.hasLayer(layers.current.currentShorelineDetection)) {
        mapRef.current.removeLayer(layers.current.currentShorelineDetection);
      }
    }
    // Reset all analysis state + workflow
    setAnalysisData(null);
    setBaselineData(null);
    setComparisonBoundaryGeo(null);
    setDsasData(null);
    setBenchmarkData(null);
    setWorkflowStep(0);
    setActiveLayers(new Set(['studyLines']));
  };

  const handleClearAnalysis = () => {
    if (!baselineData && !analysisData && !dsasData) {
      showError('Nothing to clear.');
      return;
    }
    clearAllAnalysis();
    showError('Analysis cleared. Select an area and dates to start again.');
  };

  const loadBaseline2016 = async () => {
    const polygon = getActivePolygon();
    if (!polygon) {
      showError('Please select a patch (click on map) or draw a custom polygon.');
      return;
    }
    if (!baselineStartDate || !baselineEndDate) {
      showError('Please select baseline start and end dates.');
      return;
    }

    try {
      setLoading(true);
      setLoadingMessage('Loading baseline imagery…');
      clearAllAnalysis();

      const response = await fetch(`${API_BASE}/load_baseline_2016`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          polygon,
          start_date: baselineStartDate,
          end_date: baselineEndDate
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.baseline_imagery?.true_color) {
        if (layers.current.baselineImagery.trueColor) {
          mapRef.current.removeLayer(layers.current.baselineImagery.trueColor);
        }
        layers.current.baselineImagery.trueColor = createGeeTileLayer(data.baseline_imagery.true_color).addTo(mapRef.current);
      }

      if (data.baseline_imagery?.ndwi) {
        if (layers.current.baselineImagery.ndwi) {
          mapRef.current.removeLayer(layers.current.baselineImagery.ndwi);
        }
        // Keep NDWI ready, but detached until the user explicitly enables it.
        layers.current.baselineImagery.ndwi = createGeeTileLayer(data.baseline_imagery.ndwi);
      }

      // Baseline boundary (red, dashed) on dedicated pane so it stays on top
      if (data.boundary && data.boundary.features && data.boundary.features.length > 0) {
        if (layers.current.baselineBoundary) {
          mapRef.current.removeLayer(layers.current.baselineBoundary);
        }
        const baselineBoundaryGeo = normalizeBoundaryToFeatureCollection(data.boundary);
        if (baselineBoundaryGeo) {
          layers.current.baselineBoundary = L.geoJSON(baselineBoundaryGeo, {
            pane: 'boundaryPane',
            style: {
              color: '#c0392b',
              weight: 5,
              opacity: 1,
              dashArray: '10, 8',
              fillOpacity: 0.08,
              fillColor: '#c0392b'
            }
          });
          // Only add to map if the baseline boundary layer toggle is on
          if (activeLayers.has('baselineBoundary')) {
            layers.current.baselineBoundary.addTo(mapRef.current);
            layers.current.baselineBoundary.bringToFront();
          }
        }
      }

      setBaselineData(data);
      // Never force-enable boundary layers — respect whatever checkbox state the user has set
      setActiveLayers(prev => new Set([
        ...[...prev].filter(layer => !IMAGERY_LAYER_TYPES.includes(layer)),
        'baselineTrueColor'
      ]));
      showError('Baseline loaded successfully!');
      return true;
    } catch (err) {
      showError(err.message || 'Failed to load baseline');
      console.error('Baseline loading error:', err);
      return false;
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const loadCurrentShoreline = async () => {
    const start = comparisonStartDate || baselineStartDate;
    const end = comparisonEndDate || baselineEndDate;
    if (!start || !end) {
      showError('Please set comparison (or baseline) date range first.');
      return;
    }
    const body = { start_date: start, end_date: end };
    if (getRoiForApi()) body.roi = getRoiForApi();
    try {
      setLoading(true);
      setLoadingMessage('Loading current shoreline…');
      const response = await fetch(`${API_BASE}/get_shoreline_data`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || 'Failed to load current shoreline');
      }
      const data = await response.json();
      if (!data.shoreline?.features?.length) throw new Error('No shoreline features returned');
      if (layers.current.currentShorelineDetection && mapRef.current.hasLayer(layers.current.currentShorelineDetection)) {
        mapRef.current.removeLayer(layers.current.currentShorelineDetection);
      }
      layers.current.currentShorelineDetection = L.geoJSON(data.shoreline, {
        style: { color: '#2ecc71', weight: 3, opacity: 0.8 },
        onEachFeature: (feature, layer) => {
          layer.bindPopup(
            '<div style="font-family: Arial, sans-serif;">' +
            '<h4 style="margin: 0 0 8px 0; color: #2ecc71;">Current Shoreline</h4>' +
            '<p style="margin: 0; font-size: 12px;">Shoreline detection for ' + start + ' to ' + end + '.</p>' +
            '</div>'
          );
        }
      });
      // Only add to map if the user has the layer toggled on; do not force-enable it
      if (activeLayers.has('currentShorelineDetection')) {
        layers.current.currentShorelineDetection.addTo(mapRef.current);
      }
      showError('Current shoreline loaded successfully.');
      return true;
    } catch (err) {
      showError(err.message || 'Failed to load current shoreline');
      return false;
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  /** Reference: loadImagery POST get_imagery with roi: getRoiForApi(). S2 + mask_s2 + median, clip to geom; true colour min 500 max 2500. */
  const loadImagery = async () => {
    const roi = getRoiForApi();
    if (!roi) {
      showError('Select a patch or draw a polygon first.');
      return;
    }
    const start = comparisonStartDate || baselineStartDate;
    const end = comparisonEndDate || baselineEndDate;
    if (!start || !end) {
      showError('Set start and end dates first.');
      return;
    }
    try {
      setLoading(true);
      setLoadingMessage('Loading imagery (ROI)…');
      Object.values(layers.current.imagery).forEach(layer => {
        if (layer && mapRef.current.hasLayer(layer)) mapRef.current.removeLayer(layer);
      });
      layers.current.imagery.trueColor = null;
      layers.current.imagery.ndwi = null;
      const response = await fetch(`${API_BASE}/get_imagery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_date: start, end_date: end, roi })
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || 'Failed to load imagery');
      }
      const data = await response.json();
      IMAGERY_LAYER_TYPES.forEach(removeLayer);
      layers.current.imagery.trueColor = createGeeTileLayer(data.true_color).addTo(mapRef.current);
      layers.current.imagery.ndwi = createGeeTileLayer(data.ndwi);
      setActiveLayers(prev => new Set([
        ...[...prev].filter(layer => !IMAGERY_LAYER_TYPES.includes(layer)),
        'imageryTrueColor'
      ]));
      showError('Imagery loaded with shoreline detection layer.');
    } catch (err) {
      showError(err.message || 'Failed to load imagery');
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const loadComparisonImagery = async () => {
    const polygon = getActivePolygon();
    if (!polygon) {
      showError('Please select a patch (click on map) or draw a custom polygon.');
      return;
    }

    try {
      setLoading(true);
      setLoadingMessage('Loading comparison imagery…');
      
      Object.values(layers.current.comparisonImagery).forEach(layer => {
        if (layer) mapRef.current.removeLayer(layer);
      });
      if (layers.current.comparisonBoundary) {
        mapRef.current.removeLayer(layers.current.comparisonBoundary);
        layers.current.comparisonBoundary = null;
      }
      setComparisonBoundaryGeo(null);

      const response = await fetch(`${API_BASE}/load_comparison_imagery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          polygon,
          start_date: comparisonStartDate,
          end_date: comparisonEndDate
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();

      if (data.true_color) {
        // Display one imagery raster at a time to avoid duplicate GEE tile bursts.
        IMAGERY_LAYER_TYPES.forEach(removeLayer);
        layers.current.comparisonImagery.trueColor = createGeeTileLayer(data.true_color).addTo(mapRef.current);
      }

      if (data.ndwi) {
        // NDWI is opt-in through the Detection checkbox.
        layers.current.comparisonImagery.ndwi = createGeeTileLayer(data.ndwi);
      }

      // Comparison boundary (green, solid) on dedicated pane
      if (data.boundary && data.boundary.features && data.boundary.features.length > 0) {
        setComparisonBoundaryGeo(data.boundary);
        const comparisonBoundaryFC = normalizeBoundaryToFeatureCollection(data.boundary);
        if (comparisonBoundaryFC) {
          layers.current.comparisonBoundary = L.geoJSON(comparisonBoundaryFC, {
            pane: 'boundaryPane',
            style: {
              color: '#27ae60',
              weight: 5,
              opacity: 1,
              fillOpacity: 0.08,
              fillColor: '#27ae60'
            }
          });
          // Only add to map if the comparison boundary layer toggle is on
          if (activeLayers.has('comparisonBoundary')) {
            layers.current.comparisonBoundary.addTo(mapRef.current);
            layers.current.comparisonBoundary.bringToFront();
          }
        }
      } else {
        setComparisonBoundaryGeo(null);
      }

      // Never force-enable boundary layers — respect whatever checkbox state the user has set
      setActiveLayers(prev => new Set([
        ...[...prev].filter(layer => !IMAGERY_LAYER_TYPES.includes(layer)),
        'comparisonTrueColor'
      ]));
      showError('Comparison imagery loaded successfully!');
      return true;
    } catch (err) {
      showError(err.message || 'Failed to load comparison imagery');
      console.error('Comparison imagery loading error:', err);
      return false;
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const analyzeErosion = async () => {
    const polygon = getActivePolygon();
    if (!polygon || !baselineData) {
      showError(!polygon ? 'Please select a patch or draw a polygon.' : 'Please load baseline first!');
      return;
    }

    try {
      setLoading(true);
      setLoadingMessage('Running erosion analysis…');
      
      if (layers.current.change.erosion) {
        mapRef.current.removeLayer(layers.current.change.erosion);
      }

      const response = await fetch(`${API_BASE}/analyze_erosion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          polygon,
          baseline_start_date: baselineStartDate,
          baseline_end_date: baselineEndDate,
          comparison_start_date: comparisonStartDate,
          comparison_end_date: comparisonEndDate
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();

      if (data.erosion_tiles) {
        layers.current.change.erosion = createGeeTileLayer(data.erosion_tiles, { opacity: 0.7 }).addTo(mapRef.current);
      }

      setAnalysisData(data);
      setActiveLayers(prev => new Set([...prev, 'erosion']));
      setShowResultsModal(true);
      showError('Erosion analysis completed!');
      return true;
    } catch (err) {
      showError(err.message || 'Erosion analysis failed');
      console.error('Erosion analysis error:', err);
      return false;
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  /** Reference: analyze_change POST with start_date, end_date, roi; baseline area = land_area_km2(BASELINE, geom) for ROI. */
  const runAnalyzeChange = async () => {
    const roi = getRoiForApi();
    if (!roi) {
      showError('Select a patch or draw a polygon first.');
      return;
    }
    const start = comparisonStartDate || baselineStartDate;
    const end = comparisonEndDate || baselineEndDate;
    if (!start || !end) {
      showError('Set start and end dates first.');
      return;
    }
    try {
      setLoading(true);
      setLoadingMessage('Running change analysis (ROI)…');
      if (layers.current.change.erosion) mapRef.current.removeLayer(layers.current.change.erosion);
      const response = await fetch(`${API_BASE}/analyze_change`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_date: start, end_date: end, roi })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Change analysis failed');
      if (data.erosion_tiles) {
        layers.current.change.erosion = createGeeTileLayer(data.erosion_tiles, { opacity: 0.7 }).addTo(mapRef.current);
      }
      setAnalysisData({
        baseline_land_area: data.baseline_land_area,
        current_land_area: data.current_land_area,
        erosion_area: data.erosion_area,
        change_percentage: data.change_percentage,
        comparison_land_area: data.current_land_area
      });
      setActiveLayers(prev => new Set([...prev, 'erosion']));
      setShowResultsModal(true);
      showError('Change analysis (ROI) completed.');
    } catch (err) {
      showError(err.message || 'Change analysis failed');
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const runTransects = async () => {
    const polygon = getActivePolygon();
    if (!polygon || !baselineData) {
      showError(!polygon ? 'Please select a patch or draw a polygon.' : 'Please load baseline first!');
      return;
    }

    try {
      setLoading(true);
      setLoadingMessage('Generating change transects…');

      if (layers.current.transects) {
        mapRef.current.removeLayer(layers.current.transects);
      }

      const response = await fetch(`${API_BASE}/generate_dsas_transects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          polygon,
          baseline_start_date: baselineStartDate,
          baseline_end_date: baselineEndDate,
          comparison_start_date: comparisonStartDate,
          comparison_end_date: comparisonEndDate
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();

      if (!data.transects?.features?.length) {
        throw new Error("No transects generated");
      }

      layers.current.transects = L.geoJSON(data.transects, {
        style: {
          color: '#3498db',
          weight: 2,
          opacity: 0.8,
          dashArray: '6,4'
        },
        renderer: L.canvas(),
        onEachFeature: function (feature, layer) {
          const transectId = data.transects.features.indexOf(feature);
          const polygon = getActivePolygon();

          layer.bindTooltip('Click to see shoreline change', {
            permanent: false,
            direction: 'top',
            opacity: 0.95,
            className: 'transect-tooltip'
          });

          layer.on('mouseover', function () {
            layer.setStyle({ weight: 6, opacity: 1 });
            layer.bringToFront();
          });
          layer.on('mouseout', function () {
            layer.setStyle({ weight: 2, opacity: 0.8 });
          });

          layer.on('click', async function (e) {
            L.DomEvent.stopPropagation(e);
            const popup = L.popup().setLatLng(e.latlng);
            popup.setContent(
              '<div style="font-family: Arial, sans-serif; min-width: 200px;">' +
              '<h4 style="margin: 0 0 8px 0; color: #3498db;">Transect #' + (transectId + 1) + '</h4>' +
              '<p style="margin: 0; font-size: 12px; color: #7f8c8d;">Loading shoreline change…</p></div>'
            );
            popup.openOn(mapRef.current);

            if (!polygon) {
              popup.setContent(
                '<div style="font-family: Arial, sans-serif;"><h4 style="margin: 0 0 8px 0; color: #3498db;">Transect #' + (transectId + 1) + '</h4>' +
                '<p style="color: #c0392b;">No area selected. Draw or select a polygon first.</p></div>'
              );
              return;
            }

            try {
              const res = await fetch(`${API_BASE}/get_transect_change`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  transect: feature.geometry,
                  polygon,
                  baseline_start_date: baselineStartDate,
                  baseline_end_date: baselineEndDate,
                  comparison_start_date: comparisonStartDate,
                  comparison_end_date: comparisonEndDate
                })
              });
              const changeData = await res.json();
              if (!res.ok) {
                popup.setContent(
                  '<div style="font-family: Arial, sans-serif;"><h4 style="margin: 0 0 8px 0; color: #3498db;">Transect #' + (transectId + 1) + '</h4>' +
                  '<p style="color: #c0392b;">' + (changeData.error || 'Failed to load change') + '</p></div>'
                );
                return;
              }
              const sc = changeData.shoreline_change;
              const cr = changeData.change_rate;
              const info = changeData.info;
              const scColor = sc == null ? '#7f8c8d' : (sc < 0 ? '#c0392b' : '#27ae60');
              const scLabel = sc == null ? '' : (sc > 0 ? '+' : '') + sc.toFixed(1) + ' m (' + (sc < 0 ? 'Erosion ↙ landward' : 'Accretion ↗ seaward') + ')';
              const rows = [
                sc != null ? '<p><strong>Shoreline change:</strong> <span style="color:' + scColor + '">' + scLabel + '</span></p>' : '',
                cr != null ? '<p><strong>Change rate:</strong> ' + Math.abs(cr).toFixed(1) + ' m/year ' + (cr < 0 ? '(eroding)' : '(accreting)') + '</p>' : ''
              ].filter(Boolean).join('');
              const body = rows || '<p style="color: #7f8c8d;">' + (info || 'No change data for this transect.') + '</p>';
              popup.setContent(
                '<div style="font-family: Arial, sans-serif; min-width: 220px;">' +
                '<h4 style="margin: 0 0 8px 0; color: #3498db;">Transect #' + (transectId + 1) + '</h4>' +
                '<div style="font-size: 12px; line-height: 1.6;">' + body + '</div></div>'
              );
            } catch (err) {
              popup.setContent(
                '<div style="font-family: Arial, sans-serif;"><h4 style="margin: 0 0 8px 0; color: #3498db;">Transect #' + (transectId + 1) + '</h4>' +
                '<p style="color: #c0392b;">Error: ' + (err.message || 'Could not load change') + '</p></div>'
              );
            }
          });
        }
      });

      layers.current.transects.addTo(mapRef.current);
      setDsasData(data);
      setActiveLayers(prev => new Set([...prev, 'transects']));
      showError(`Transect analysis completed! ${data.transects.features.length} transects generated.`);
      return true;
    } catch (err) {
      showError('Transect analysis failed: ' + err.message);
      console.error(err);
      return false;
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const handleLoadBaseline = async () => {
    const polygon = getActivePolygon();
    if (!polygon || !baselineStartDate || !baselineEndDate) {
      showError('Select baseline dates and study area first');
      return;
    }
    const ok = await loadBaseline2016();
    if (ok) setWorkflowStep(1);
  };

  const handleLoadComparisonAndShoreline = async () => {
    if (workflowStep < 1) return;
    if (!comparisonStartDate || !comparisonEndDate) {
      showError('Select comparison dates first');
      return;
    }
    const comparisonOk = await loadComparisonImagery();
    if (!comparisonOk) return;
    const shorelineOk = await loadCurrentShoreline();
    if (shorelineOk) setWorkflowStep(2);
  };

  const handleAnalyzeErosion = async () => {
    if (workflowStep < 2) return;
    const ok = await analyzeErosion();
    if (ok) setWorkflowStep(3);
  };

  const handleRunTransects = async () => {
    if (workflowStep < 3) return;
    const ok = await runTransects();
    if (ok) setWorkflowStep(4);
  };

  const handleResearchBenchmark = async () => {
    const polygon = getActivePolygon();
    if (workflowStep < 4 || !polygon) {
      showError('Complete Steps 1–4 for a selected area before running the benchmark.');
      return;
    }
    try {
      setLoading(true);
      setLoadingMessage('Running reviewer benchmark: 5 uncached repetitions of imagery, shoreline, and DSAS processing…');
      const response = await fetch(`${API_BASE}/research_benchmark`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          polygon,
          area_name: studyAreaLabelForReport(selectedAreaMode, studyAreas),
          baseline_start_date: baselineStartDate,
          baseline_end_date: baselineEndDate,
          comparison_start_date: comparisonStartDate,
          comparison_end_date: comparisonEndDate,
          runs: 5
        })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || `Server error: ${response.status}`);
      setBenchmarkData(result);
      setShowBenchmarkModal(true);
      showError('Reviewer benchmark completed and saved successfully.');
    } catch (err) {
      showError(`Benchmark failed: ${err.message}`);
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  const ensureBoundaryLayerExists = (layerType) => {
    if (!mapRef.current) return;
    if (layerType === 'baselineBoundary' && !layers.current.baselineBoundary && baselineData?.boundary) {
      ensureBoundaryPane();
      const fc = normalizeBoundaryToFeatureCollection(baselineData.boundary);
      if (fc) {
        layers.current.baselineBoundary = L.geoJSON(fc, {
          pane: 'boundaryPane',
          style: { color: '#c0392b', weight: 5, opacity: 1, dashArray: '10, 8', fillOpacity: 0.08, fillColor: '#c0392b' }
        });
      }
    }
    if (layerType === 'comparisonBoundary' && !layers.current.comparisonBoundary && comparisonBoundaryGeo) {
      ensureBoundaryPane();
      const fc = normalizeBoundaryToFeatureCollection(comparisonBoundaryGeo);
      if (fc) {
        layers.current.comparisonBoundary = L.geoJSON(fc, {
          pane: 'boundaryPane',
          style: { color: '#27ae60', weight: 5, opacity: 1, fillOpacity: 0.08, fillColor: '#27ae60' }
        });
      }
    }
  };

  const toggleLayer = (layerType) => {
    const newLayers = new Set(activeLayers);
    if (newLayers.has(layerType)) {
      newLayers.delete(layerType);
      removeLayer(layerType);
    } else {
      // Imagery controls behave exclusively even though they are rendered as
      // checkboxes: hidden raster layers must not keep fetching GEE tiles.
      if (IMAGERY_LAYER_TYPES.includes(layerType)) {
        IMAGERY_LAYER_TYPES.forEach(otherLayer => {
          if (otherLayer !== layerType) {
            newLayers.delete(otherLayer);
            removeLayer(otherLayer);
          }
        });
      }
      if (layerType === 'baselineBoundary' || layerType === 'comparisonBoundary') {
        ensureBoundaryLayerExists(layerType);
      }
      const hasLayer = (layerType === 'studyLines' && studyAreaLayerGroupRef.current && studyAreaLayerGroupRef.current.getLayers().length > 0) ||
        (layerType === 'baselineBoundary' && layers.current.baselineBoundary) ||
        (layerType === 'comparisonBoundary' && layers.current.comparisonBoundary) ||
        (layerType === 'baselineDetectionPEI' && layers.current.baselineDetectionPEI) ||
        (layerType === 'currentShorelineDetection' && layers.current.currentShorelineDetection) ||
        !['studyLines', 'baselineBoundary', 'comparisonBoundary', 'baselineDetectionPEI', 'currentShorelineDetection'].includes(layerType);
      if (hasLayer) {
        newLayers.add(layerType);
        addLayer(layerType);
      }
    }
    setActiveLayers(newLayers);
  };

  const ensureBoundaryPane = () => {
    if (!mapRef.current) return;
    if (!mapRef.current.getPane('boundaryPane')) {
      mapRef.current.createPane('boundaryPane');
      mapRef.current.getPane('boundaryPane').style.zIndex = 650;
    }
  };

  const addLayer = (layerType) => {
    if (!mapRef.current) return;
    switch (layerType) {
      case 'studyLines':
        if (studyAreaLayerGroupRef.current && studyAreaLayerGroupRef.current.getLayers().length > 0 && !mapRef.current.hasLayer(studyAreaLayerGroupRef.current)) {
          studyAreaLayerGroupRef.current.addTo(mapRef.current);
        }
        break;
      case 'drawnPolygon':
        if (drawnLayerRef.current && !mapRef.current.hasLayer(drawnLayerRef.current)) {
          drawnLayerRef.current.addTo(mapRef.current);
        }
        break;
      case 'baselineTrueColor':
        if (layers.current.baselineImagery.trueColor) layers.current.baselineImagery.trueColor.addTo(mapRef.current);
        break;
      case 'baselineDetection':
        if (layers.current.baselineImagery.ndwi) layers.current.baselineImagery.ndwi.addTo(mapRef.current);
        break;
      case 'baselineBoundary':
        if (layers.current.baselineBoundary) {
          ensureBoundaryPane();
          layers.current.baselineBoundary.addTo(mapRef.current);
          if (layers.current.baselineBoundary.getLayers) {
            layers.current.baselineBoundary.getLayers().forEach((l) => l.bringToFront && l.bringToFront());
          }
          layers.current.baselineBoundary.bringToFront();
          mapRef.current.invalidateSize();
        }
        break;
      case 'comparisonTrueColor':
        if (layers.current.comparisonImagery.trueColor) layers.current.comparisonImagery.trueColor.addTo(mapRef.current);
        break;
      case 'comparisonDetection':
        if (layers.current.comparisonImagery.ndwi) layers.current.comparisonImagery.ndwi.addTo(mapRef.current);
        break;
      case 'comparisonBoundary':
        if (layers.current.comparisonBoundary) {
          ensureBoundaryPane();
          layers.current.comparisonBoundary.addTo(mapRef.current);
          if (layers.current.comparisonBoundary.getLayers) {
            layers.current.comparisonBoundary.getLayers().forEach((l) => l.bringToFront && l.bringToFront());
          }
          layers.current.comparisonBoundary.bringToFront();
          mapRef.current.invalidateSize();
        }
        break;
      case 'erosion':
        if (layers.current.change.erosion) layers.current.change.erosion.addTo(mapRef.current);
        break;
      case 'transects':
        if (layers.current.transects) layers.current.transects.addTo(mapRef.current);
        break;
      case 'baselineDetectionPEI':
        if (layers.current.baselineDetectionPEI) layers.current.baselineDetectionPEI.addTo(mapRef.current);
        break;
      case 'currentShorelineDetection':
        if (layers.current.currentShorelineDetection) layers.current.currentShorelineDetection.addTo(mapRef.current);
        break;
      case 'imageryTrueColor':
        if (layers.current.imagery.trueColor) layers.current.imagery.trueColor.addTo(mapRef.current);
        break;
      case 'imageryDetection':
        if (layers.current.imagery.ndwi) layers.current.imagery.ndwi.addTo(mapRef.current);
        break;
      default:
        break;
    }
  };

  const removeLayer = (layerType) => {
    if (!mapRef.current) return;
    switch (layerType) {
      case 'studyLines':
        if (studyAreaLayerGroupRef.current && mapRef.current.hasLayer(studyAreaLayerGroupRef.current)) {
          mapRef.current.removeLayer(studyAreaLayerGroupRef.current);
        }
        break;
      case 'drawnPolygon':
        if (drawnLayerRef.current && mapRef.current.hasLayer(drawnLayerRef.current)) {
          mapRef.current.removeLayer(drawnLayerRef.current);
        }
        break;
      case 'baselineTrueColor':
        if (layers.current.baselineImagery.trueColor) mapRef.current.removeLayer(layers.current.baselineImagery.trueColor);
        break;
      case 'baselineDetection':
        if (layers.current.baselineImagery.ndwi) mapRef.current.removeLayer(layers.current.baselineImagery.ndwi);
        break;
      case 'baselineBoundary':
        if (layers.current.baselineBoundary) mapRef.current.removeLayer(layers.current.baselineBoundary);
        break;
      case 'comparisonTrueColor':
        if (layers.current.comparisonImagery.trueColor) mapRef.current.removeLayer(layers.current.comparisonImagery.trueColor);
        break;
      case 'comparisonDetection':
        if (layers.current.comparisonImagery.ndwi) mapRef.current.removeLayer(layers.current.comparisonImagery.ndwi);
        break;
      case 'comparisonBoundary':
        if (layers.current.comparisonBoundary) mapRef.current.removeLayer(layers.current.comparisonBoundary);
        break;
      case 'erosion':
        if (layers.current.change.erosion) mapRef.current.removeLayer(layers.current.change.erosion);
        break;
      case 'transects':
        if (layers.current.transects) mapRef.current.removeLayer(layers.current.transects);
        break;
      case 'baselineDetectionPEI':
        if (layers.current.baselineDetectionPEI) mapRef.current.removeLayer(layers.current.baselineDetectionPEI);
        break;
      case 'currentShorelineDetection':
        if (layers.current.currentShorelineDetection) mapRef.current.removeLayer(layers.current.currentShorelineDetection);
        break;
      case 'imageryTrueColor':
        if (layers.current.imagery.trueColor) mapRef.current.removeLayer(layers.current.imagery.trueColor);
        break;
      case 'imageryDetection':
        if (layers.current.imagery.ndwi) mapRef.current.removeLayer(layers.current.imagery.ndwi);
        break;
      default:
        break;
    }
  };

  const updateChart = () => {
    if (barChartInstance.current) barChartInstance.current.destroy();

    if (!(barChartRef.current && analysisData)) return;

    const baseline = Number(analysisData.baseline_land_area || 0);
    const comparison = Number(analysisData.comparison_land_area || 0);
    const labels = [`Baseline (${baselineStartDate})`, `${comparisonStartDate} Land`];
    const sharedScales = {
      x: {
        grid: { color: 'rgba(160, 140, 110, 0.15)' },
        ticks: {
          color: '#AE9E84',
          autoSkip: false,
          maxRotation: 20
        }
      },
      y: {
        beginAtZero: true,
        grid: { color: 'rgba(160, 140, 110, 0.15)' },
        ticks: {
          color: '#AE9E84',
          callback: (value) => `${Number(value).toFixed(2)} km²`
        }
      }
    };
    const sharedTooltip = {
      backgroundColor: '#4A3A28',
      titleColor: '#F5EDD6',
      bodyColor: '#E0D8C0',
      callbacks: {
        label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.raw || 0).toFixed(2)} km²`
      }
    };

    const barCtx = barChartRef.current.getContext('2d');
    barChartInstance.current = new Chart(barCtx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Baseline',
            data: [baseline, null],
            backgroundColor: '#4AACB8',
            borderColor: '#4AACB8',
            borderRadius: 4
          },
          {
            label: 'Comparison',
            data: [null, comparison],
            backgroundColor: '#E8924A',
            borderColor: '#E8924A',
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: sharedTooltip },
        scales: sharedScales
      }
    });

  };

  const handleDownloadReportPdf = async () => {
    setLoadingDownload(true);
    if (!analysisData) {
      window.alert('Run analysis first');
      return;
    }
    try {
      await buildCoastalReportPdf({
        analysisData,
        selectedAreaMode,
        studyAreas,
        baselineStartDate,
        baselineEndDate,
        comparisonStartDate,
        comparisonEndDate,
        dsasData,
        getMapEl: () => document.querySelector('.dashboard-map-container') || document.getElementById('map'),
        invalidateMap: () => {
          if (mapRef.current) mapRef.current.invalidateSize();
        }
      });
    } catch (err) {
      console.error(err);
      window.alert(`Could not generate PDF: ${err.message || 'Unknown error'}`);
    }
    finally{
      setLoadingDownload(false);
    }
  };

  const showError = (message) => {
    setErrorMessage(message);
    setTimeout(() => setErrorMessage(''), 5000);
  };

  return (
    <div className="dashboard-layout">
      {/* Mobile menu toggle button */}
      <button
        className="mobile-menu-toggle"
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        aria-label="Toggle menu"
      >
        {mobileMenuOpen ? '✕' : '☰'}
      </button>

      {/* Mobile sidebar backdrop */}
      {mobileMenuOpen && (
        <div
          className="mobile-sidebar-backdrop active"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <div className="dashboard-body">
        <aside className={`sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
          {/* Mobile close button */}
          <button
            className="mobile-menu-toggle"
            style={{ position: 'absolute', top: '12px', right: '12px', left: 'auto' }}
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
          >
            ✕
          </button>

          <div className="sidebar-aoi-block" style={{ marginTop: "10px" }}>
            <label className="sidebar-aoi-label">Area of Interest</label>
            <select
              value={selectedAreaMode}
              onChange={(e) => setSelectedAreaMode(e.target.value)}
              className="sidebar-select"
            >
              <option value="">— Select or draw —</option>
              <option value="" disabled>— Patch polygons —</option>
              {PATCHES.map(({ id, name }) => (
                <option key={id} value={id}>{name} (patch)</option>
              ))}
              {studyAreas.length > 0 && (
                <>
                  <option value="" disabled>— Study polygons —</option>
                  {studyAreas.map((s) => (
                    <option key={s.id} value={'study_' + s.id}>{s.name} (study polygon)</option>
                  ))}
                </>
              )}
              <option value="custom">Custom (draw polygon)</option>
            </select>
            {hasActiveArea && (
              <p style={{ fontSize: '10px', color: '#4ade80', marginTop: '4px', marginBottom: 0 }}>
                {selectedAreaMode === 'custom' && '✓ Custom polygon'}
                {PATCH_IDS.includes(selectedAreaMode) && `✓ ${PATCHES.find(p => p.id === selectedAreaMode)?.name}`}
                {selectedAreaMode?.startsWith('study_') && `✓ ${studyAreas.find(s => 'study_' + s.id === selectedAreaMode)?.name}`}
              </p>
            )}
          </div>

          <div className="date-range-section">
            <span className="date-range-section-title">Date Ranges</span>
            <div className="date-range-compact">
              <div className="date-compact-row">
                <span className="date-compact-label">Baseline</span>
                <input
                  type="date"
                  className="date-input-compact"
                  value={baselineStartDate}
                  onChange={(e) => setBaselineStartDate(e.target.value)}
                />
                <input
                  type="date"
                  className="date-input-compact"
                  value={baselineEndDate}
                  onChange={(e) => setBaselineEndDate(e.target.value)}
                  min={baselineStartDate}
                />
              </div>
              <div className="date-compact-row">
                <span className="date-compact-label">Comparison</span>
                <input
                  type="date"
                  className="date-input-compact"
                  value={comparisonStartDate}
                  onChange={(e) => setComparisonStartDate(e.target.value)}
                />
                <input
                  type="date"
                  className="date-input-compact"
                  value={comparisonEndDate}
                  onChange={(e) => setComparisonEndDate(e.target.value)}
                  min={comparisonStartDate}
                />
              </div>
            </div>
          </div>

          <div className="actions">
            <button onClick={() => { handleLoadBaseline(); setMobileMenuOpen(false); }} className={`btn-sidebar btn-primary workflow-btn${workflowStep >= 1 ? ' step-done' : ''}`} title="Step 1 — Load baseline imagery">
              <span className="step-badge">1</span>
              Load Baseline
              {workflowStep >= 1 && <span className="step-check">✓</span>}
            </button>
            <button
              onClick={() => { handleLoadComparisonAndShoreline(); setMobileMenuOpen(false); }}
              className={`btn-sidebar btn-secondary workflow-btn${workflowStep >= 2 ? ' step-done' : ''}`}
              disabled={workflowStep < 1}
              title="Step 2 — Load comparison imagery and current shoreline"
            >
              <span className="step-badge">2</span>
              Load Comparison
              {workflowStep >= 2 && <span className="step-check">✓</span>}
            </button>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button onClick={() => { handleAnalyzeErosion(); setMobileMenuOpen(false); }} className={`btn-sidebar btn-small workflow-btn${workflowStep >= 3 ? ' step-done' : ''}`} disabled={workflowStep < 2} title="Step 3 — Run erosion analysis">
                <span className="step-badge">3</span>
                Erosion
                {workflowStep >= 3 && <span className="step-check">✓</span>}
              </button>
              <button onClick={() => { handleRunTransects(); setMobileMenuOpen(false); }} className={`btn-sidebar btn-small workflow-btn${workflowStep >= 4 ? ' step-done' : ''}`} disabled={workflowStep < 3} title="Step 4 — Generate change transects">
                <span className="step-badge">4</span>
                Transects
                {workflowStep >= 4 && <span className="step-check">✓</span>}
              </button>
            </div>
            <button
              type="button"
              onClick={() => { handleResearchBenchmark(); setMobileMenuOpen(false); }}
              className="btn-sidebar benchmark-launch-btn"
              disabled={workflowStep < 4 || loading}
              title="Run five uncached repetitions and calculate reviewer R3.25 performance metrics"
            >
              <span className="benchmark-launch-icon">R3.25</span>
              Reviewer Benchmark
            </button>
            {benchmarkData && (
              <button
                type="button"
                className="benchmark-reopen-btn"
                onClick={() => setShowBenchmarkModal(true)}
              >
                View saved benchmark results
              </button>
            )}
          </div>

          <div className="sidebar-layers-compact">
            <h3 className="sidebar-layers-heading-compact">Quick Layers</h3>
            <div className="layers-grid-compact">
              <label className="layer-toggle-compact" title="Baseline True Color">
                <input type="checkbox" checked={activeLayers.has('baselineTrueColor')} onChange={() => toggleLayer('baselineTrueColor')} />
                <span>Baseline</span>
              </label>
              <label className="layer-toggle-compact" title="Comparison True Color">
                <input type="checkbox" checked={activeLayers.has('comparisonTrueColor')} onChange={() => toggleLayer('comparisonTrueColor')} />
                <span>Comparison</span>
              </label>
              <label className="layer-toggle-compact" title="Erosion Analysis">
                <input type="checkbox" checked={activeLayers.has('erosion')} onChange={() => toggleLayer('erosion')} />
                <span>Erosion</span>
              </label>
              <label className="layer-toggle-compact" title="Change Transects">
                <input type="checkbox" checked={activeLayers.has('transects')} onChange={() => toggleLayer('transects')} />
                <span>Transects</span>
              </label>
            </div>
            <button 
              className="btn-more-layers"
              onClick={() => setShowLayersPanel(!showLayersPanel)}
            >
              {showLayersPanel ? '− Less Layers' : '+ More Layers'}
            </button>
          </div>
        </aside>

        <main className="main-content">
          {errorMessage && (
            <div className="error-message" style={{
              position: 'absolute',
              top: '10px',
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 1001,
              backgroundColor: errorMessage.includes('successfully') ? '#e8f5e9' : '#ffebee',
              color: errorMessage.includes('successfully') ? '#2e7d32' : '#c62828',
              padding: '10px 20px',
              borderRadius: '8px',
              border: `1px solid ${errorMessage.includes('successfully') ? '#a5d6a7' : '#ef9a9a'}`,
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
            }}>
              {errorMessage}
            </div>
          )}
          
          <div
            id="map"
            className="dashboard-map-container"
          />
          
          {/* Layers Control Panel
          <button
            type="button"
            className="layers-toggle-btn"
            onClick={() => setShowLayersPanel(!showLayersPanel)}
            title="Toggle layers panel"
          >
            <span style={{ fontSize: '18px' }}>☰</span> Layers
          </button> */}

          {showLayersPanel && ( 
            <div className="layers-panel">
              <div className="layers-panel-header">
                <h4>Map Layers</h4>
                <button onClick={() => setShowLayersPanel(false)} className="layers-panel-close">×</button>
              </div>
              <div className="layers-panel-content">
                <div className="layer-section-panel">
                  <span className="layer-section-title-panel">Imagery</span>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('baselineTrueColor')} onChange={() => toggleLayer('baselineTrueColor')} /> Baseline</label>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('comparisonTrueColor')} onChange={() => toggleLayer('comparisonTrueColor')} /> Comparison</label>
                </div>
                <div className="layer-section-panel">
                  <span className="layer-section-title-panel">Detection</span>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('baselineDetection')} onChange={() => toggleLayer('baselineDetection')} /> Baseline Detection</label>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('comparisonDetection')} onChange={() => toggleLayer('comparisonDetection')} /> Comparison Detection</label>
                </div>
                <div className="layer-section-panel">
                  <span className="layer-section-title-panel">Analysis</span>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('erosion')} onChange={() => toggleLayer('erosion')} /> Erosion</label>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('transects')} onChange={() => toggleLayer('transects')} /> Transects</label>
                </div>
                <div className="layer-section-panel">
                  <span className="layer-section-title-panel">Other</span>
                  {hasActiveArea && (
                    <label className="checkbox-item-panel">
                      <input type="checkbox" checked={activeLayers.has('myPolygon')} onChange={() => toggleLayer('myPolygon')} />
                      My Polygon
                    </label>
                  )}
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('baselineBoundary')} onChange={() => toggleLayer('baselineBoundary')} /> Baseline Boundary</label>
                  <label className="checkbox-item-panel"><input type="checkbox" checked={activeLayers.has('comparisonBoundary')} onChange={() => toggleLayer('comparisonBoundary')} /> Comparison Boundary</label>
                </div>
              </div>
            </div>
          )}

          {(baselineData || analysisData || dsasData) && (
            <button
              type="button"
              className="map-clear-btn"
              onClick={handleClearAnalysis}
              title="Clear all analysis layers and reset workflow"
            >
              <span className="map-clear-icon">⟳</span>
              Clear analysis
            </button>
          )}

          {loading && (
            <div className="loading-overlay" role="status" aria-live="polite" aria-label="Processing">
              <div className="loading-overlay-card">
                <div className="loading-overlay-spinner">
                  <div className="loading-ring"></div>
                  <div className="loading-ring loading-ring-2"></div>
                  <div className="loading-ring loading-ring-3"></div>
                </div>
                <h3 className="loading-overlay-title">Processing</h3>
                <p className="loading-overlay-message">{loadingMessage || 'Please wait…'}</p>
                <p className="loading-overlay-hint">
                  {loadingSlow
                    ? 'The dashboard is doing heavy cloud computing at run time. This is taking more than usual; keep it running in the background and return in a few minutes.'
                    : 'This may take a minute depending on the area and dates.'}
                </p>
              </div>
            </div>
          )}
          
          {analysisData && (
            <button
              type="button"
              onClick={() => setShowResultsModal(true)}
              style={{
                position: 'absolute',
                bottom: '20px',
                right: '20px',
                zIndex: 1000,
                padding: '12px 24px',
                background: 'linear-gradient(135deg, #2563eb, #1e40af)',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontSize: '15px',
                fontWeight: '600',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(37, 99, 235, 0.4)',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 6px 16px rgba(37, 99, 235, 0.5)';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(37, 99, 235, 0.4)';
              }}
            >
              View Results
            </button>
          )}

          {showResultsModal && analysisData && (
            <div 
              className="results-modal-overlay"
              onClick={() => setShowResultsModal(false)}
            >
              <div 
                className="results-modal"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  className="results-modal-close"
                  onClick={() => setShowResultsModal(false)}
                  aria-label="Close"
                >
                  ×
                </button>
                
                <div className="results-modal-content">
                  <div className="bottom-tabs">
                    <button type="button" className={`tab ${bottomTab === 'charts' ? 'active' : ''}`} onClick={() => setBottomTab('charts')}>
                      Graphs &amp; Charts
                    </button>
                    <button type="button" className={`tab ${bottomTab === 'reports' ? 'active' : ''}`} onClick={() => setBottomTab('reports')}>
                      Reports
                    </button>
                  </div>
                  
                  <div className="tab-content">
                    <div className="tab-pane" style={{ display: bottomTab === 'charts' ? 'block' : 'none' }}>
                      <div className="results-summary-wrapper">
                        <div className="metric-summary-row">
                          <div className="change-summary-card">
                            <div className="change-summary-header">
                              <span className="change-summary-title">Area change</span>
                            </div>
                            <div className="change-summary-value" style={{ color: (analysisData.erosion_area || 0) < 0 ? '#E8924A' : '#4AACB8' }}>
                              {(analysisData.erosion_area || 0) > 0 ? '+' : ''}{(analysisData.erosion_area || 0).toFixed(2)} km²
                            </div>
                            <div className="change-summary-label">
                              {analysisData.change_percentage != null ? `${analysisData.change_percentage > 0 ? '+' : ''}${Number(analysisData.change_percentage).toFixed(2)}%` : '—'}
                            </div>
                          </div>
                          <div className="change-summary-card">
                            <div className="change-summary-header">
                              <span className="change-summary-title">Change type</span>
                            </div>
                            <div className="change-summary-value" style={{ color: (analysisData.erosion_area || 0) < 0 ? '#E8924A' : '#4AACB8' }}>
                              {(analysisData.erosion_area || 0) < 0 ? 'Erosion' : 'Accretion'}
                            </div>
                            <div className="change-summary-label">Classification</div>
                          </div>
                        </div>
                        <div className="chart-card">
                          <h3 className="chart-card-title">Coastal change analysis</h3>
                          <div className="chart-canvas-wrap bar-wrap">
                            <canvas ref={barChartRef} />
                          </div>
                        </div>
                        <div className="results-summary">
                          <h3 className="results-summary-heading">Analysis Summary</h3>
                          <div className="summary-item">
                            <span>Area</span>
                            <span>{selectedAreaMode === 'custom' ? 'Custom polygon' : (PATCHES.find(p => p.id === selectedAreaMode)?.name || '—')}</span>
                          </div>
                          <div className="summary-item">
                            <span>Baseline Date</span>
                            <span>{baselineStartDate} to {baselineEndDate}</span>
                          </div>
                          <div className="summary-item">
                            <span>Comparison Date</span>
                            <span>{comparisonStartDate} to {comparisonEndDate}</span>
                          </div>
                          <div className="summary-item">
                            <span>Baseline Land Area</span>
                            <span>{(analysisData.baseline_land_area || 0).toFixed(2)} km²</span>
                          </div>
                          <div className="summary-item">
                            <span>Comparison Land Area</span>
                            <span>{(analysisData.comparison_land_area || 0).toFixed(2)} km²</span>
                          </div>
                          <div className="summary-item highlight">
                            <span>Area Change</span>
                            <span style={{ color: (analysisData.erosion_area || 0) < 0 ? '#E8924A' : '#4AACB8' }}>
                              {(analysisData.erosion_area || 0) > 0 ? '+' : ''}{(analysisData.erosion_area || 0).toFixed(2)} km²
                              {analysisData.change_percentage != null ? ` (${analysisData.change_percentage > 0 ? '+' : ''}${Number(analysisData.change_percentage).toFixed(2)}%)` : ''}
                            </span>
                          </div>
                          <div className="summary-item">
                            <span>Change Type</span>
                            <span className={(analysisData.erosion_area || 0) < 0 ? 'change-type-badge erosion' : 'change-type-badge accretion'}>
                              {(analysisData.erosion_area || 0) < 0 ? 'Erosion' : 'Accretion'}
                            </span>
                          </div>
                          <p className="results-summary-note">
                            <strong>Boundary:</strong> The area used for these stats is the one you selected on the map (patch or drawn polygon). Turn on <strong>Polygon</strong>, <strong>Baseline Boundary</strong>, or <strong>Comparison Boundary</strong> in the Layers panel to view it above.
                          </p>
                          <div className="results-summary-interp">
                            <strong>Interpreting large changes:</strong> Big area differences over a few years can be due to (1) the size of your selected area (larger regions show larger absolute km² change), (2) different seasons or water levels between baseline and comparison dates, and (3) cloud or composite differences. For more comparable results, use similar seasons (e.g. both summer) and check that the boundary on the map matches the area you intend to analyze.
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="tab-pane" style={{ display: bottomTab === 'reports' ? 'block' : 'none' }}>
                      <div className="reports-panel">
                       <button
  type="button"
  disabled={loadingDownload}
  className="report-btn"
  onClick={handleDownloadReportPdf}
>
  {loadingDownload ? (
    <span className="custom-loader"></span>
  ) : (
    <i className="icon-download" aria-hidden>
      ⬇
    </i>
  )}
  {' '}Download PDF
</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {showBenchmarkModal && benchmarkData && (
            <div className="benchmark-modal-overlay" onClick={() => setShowBenchmarkModal(false)}>
              <section className="benchmark-modal" onClick={(e) => e.stopPropagation()} aria-label="Reviewer benchmark results">
                <button className="benchmark-modal-close" onClick={() => setShowBenchmarkModal(false)} aria-label="Close benchmark results">×</button>
                <header className="benchmark-header">
                  <div>
                    <span className="benchmark-eyebrow">Reviewer R3.25 · Reproducibility benchmark</span>
                    <h2>Portal Performance Profile</h2>
                    <p>{benchmarkData.test_case.area_name} · {benchmarkData.test_case.comparison_range}</p>
                  </div>
                  <div className="benchmark-run-stamp">
                    <strong>{benchmarkData.processing_time_seconds.runs}</strong>
                    <span>uncached runs</span>
                  </div>
                </header>

                <div className="benchmark-kpi-strip">
                  <div><span>AOI area</span><strong>{benchmarkData.test_case.aoi_area_km2.toLocaleString()} km²</strong></div>
                  <div><span>Eligible scenes</span><strong>{benchmarkData.data_volume.eligible_sentinel2_scenes}</strong></div>
                  <div><span>Scenes used</span><strong>{benchmarkData.data_volume.scenes_used_in_composite}</strong></div>
                  <div><span>Transects</span><strong>{benchmarkData.dsas.median_transect_count}</strong></div>
                </div>

                <div className="benchmark-grid">
                  <article className="benchmark-card">
                    <h3>Computational environment</h3>
                    <div className="benchmark-metric"><span>Logical CPU count</span><strong>{benchmarkData.computational_environment.logical_cpu_count ?? '—'}</strong></div>
                    <div className="benchmark-metric"><span>Total RAM</span><strong>{benchmarkData.computational_environment.total_ram_gb != null ? `${benchmarkData.computational_environment.total_ram_gb} GB` : '—'}</strong></div>
                    <p className="benchmark-note">{benchmarkData.computational_environment.note}</p>
                  </article>

                  <article className="benchmark-card">
                    <h3>Raster data volume</h3>
                    <div className="benchmark-metric"><span>Nominal 10 m grid cells</span><strong>{benchmarkData.data_volume.nominal_10m_grid_cells.toLocaleString()}</strong></div>
                    <div className="benchmark-metric"><span>Valid pixels after masking</span><strong>{benchmarkData.data_volume.valid_pixels_after_masking.toLocaleString()}</strong></div>
                    <div className="benchmark-metric"><span>Valid-data coverage</span><strong>{benchmarkData.data_volume.valid_coverage_km2.toLocaleString()} km²</strong></div>
                    <div className="benchmark-metric"><span>Composite scene cap</span><strong>{benchmarkData.data_volume.scene_cap}</strong></div>
                  </article>

                  <article className="benchmark-card benchmark-timing-card">
                    <h3>Processing performance</h3>
                    <div className="benchmark-timing-head"><span>Workflow</span><span>Median</span><span>IQR</span></div>
                    <div className="benchmark-timing-row"><strong>Imagery + NDWI</strong><span>{benchmarkData.processing_time_seconds.imagery_ndwi_median.toFixed(2)} s</span><span>{benchmarkData.processing_time_seconds.imagery_ndwi_iqr.toFixed(2)} s</span></div>
                    <div className="benchmark-timing-row"><strong>Shoreline vectorization</strong><span>{benchmarkData.processing_time_seconds.shoreline_median.toFixed(2)} s</span><span>{benchmarkData.processing_time_seconds.shoreline_iqr.toFixed(2)} s</span></div>
                    <div className="benchmark-timing-row"><strong>DSAS-style transects</strong><span>{benchmarkData.processing_time_seconds.dsas_median.toFixed(2)} s</span><span>{benchmarkData.processing_time_seconds.dsas_iqr.toFixed(2)} s</span></div>
                  </article>
                </div>

                <footer className="benchmark-footer">
                  <span>Cloud filter &lt; {benchmarkData.test_case.cloud_filter_percent}%</span>
                  <span>{benchmarkData.test_case.spatial_resolution_m} m spatial resolution</span>
                  <span>Generated {new Date(benchmarkData.generated_at_utc).toLocaleString()}</span>
                </footer>
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default Dashboard;
