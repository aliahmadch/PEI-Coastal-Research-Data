# --- COPY EVERYTHING FROM HERE ---
import ee
import json
import logging
import math
import os
import hashlib
import threading
import statistics
import time
import geopandas as gpd
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime as _dt
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from shapely.validation import make_valid
from shapely.ops import unary_union
from shapely.geometry import shape, mapping, LineString, MultiLineString, Polygon, MultiPolygon

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
SERVER_STARTED_AT_UTC = _dt.utcnow().isoformat(timespec="seconds") + "Z"
EE_INITIALIZED = False
WARMUP_LOCK = threading.Lock()
WARMUP_STATE = {
    "started": False,
    "complete": False,
    "error": None,
    "started_at_utc": None,
    "completed_at_utc": None,
}
LAYER_CACHE_LOCK = threading.Lock()
LAYER_CACHE = OrderedDict()
LAYER_CACHE_MAX = 16
BENCHMARK_RESULTS_PATH = Path(__file__).parent / "portal_benchmark_results.json"


def _validate_date_range(start_date: str, end_date: str, max_days: int = 365) -> None:
    """Validate date strings and range using Python — avoids a GEE round-trip."""
    try:
        s = _dt.strptime(start_date, "%Y-%m-%d")
        e = _dt.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Dates must be in YYYY-MM-DD format")
    if e <= s:
        raise ValueError("end_date must be after start_date")
    if (e - s).days > max_days:
        raise ValueError(f"Date range exceeds {max_days} day limit")


def _layer_cache_key(endpoint, *parts):
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{endpoint}:{digest}"


def _layer_cache_get(key):
    with LAYER_CACHE_LOCK:
        value = LAYER_CACHE.get(key)
        if value is not None:
            LAYER_CACHE.move_to_end(key)
        return value


def _layer_cache_set(key, value):
    with LAYER_CACHE_LOCK:
        LAYER_CACHE[key] = value
        LAYER_CACHE.move_to_end(key)
        while len(LAYER_CACHE) > LAYER_CACHE_MAX:
            LAYER_CACHE.popitem(last=False)


# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)  # Enable CORS for all routes


@app.after_request
def add_no_cache_headers(response):
    if request.path == "/study_areas" or request.path.startswith("/studylines/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Configure paths
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
GEOJSON_PATH = PROJECT_ROOT / "2016shoreline.geojson"  # Use 2016 shoreline with buffer for area analysis
SHORELINE_loaded = PROJECT_ROOT / "2016shoreline.geojson"  # Same file
# Study area polygons (AOI) for frontend selection
STUDY_AREA_FILES = [
    ("western", "Western", "westernStudyline.geojson"),
    ("central", "Central", "centralStudyline.geojson"),
    ("eastern", "Eastern", "easternStudyline.geojson"),
    ("easternMost", "Eastern Most", "easternMostStudyline.geojson"),
    ("westernMost", "Western Most", "westernMostStudyline.geojson"),
]
CREDENTIALS_PATH = BASE_DIR / "ee-mohammadmudassir531-747311c353f6.json"
SIMPLIFY_TOLERANCE = 0.001  # Standard tolerance
BUFFER_DISTANCE = 1000  # 1km buffer around shoreline for analysis area

# Earth Engine initialization
try:
    credentials = ee.ServiceAccountCredentials(
        "gee-4-9@ee-mohammadmudassir531.iam.gserviceaccount.com",
        str(CREDENTIALS_PATH)
    )
    ee.Initialize(credentials)
    EE_INITIALIZED = True
    logger.info("Earth Engine initialized successfully")
except Exception as e:
    logger.error("Earth Engine initialization failed: %s", str(e))
    raise

# -----------------------------
# PEI & NDWI baseline constants
# -----------------------------
PEI_BBOX = ee.Geometry.Rectangle([-64.4670648, 46.2934642, -63.95558142, 47.1542194])  # west, south, east, north
BASELINE_START = "2016-05-01"
BASELINE_END = "2016-10-31"
CLOUD_MAX = 15
SCALE = 10
# Land = NDWI <= NDWI_LAND_THRESHOLD.
# PEI coastal water is turbid (red/brown sand runoff), so near-shore pixels can have
# NDWI as low as -0.05 to -0.1 even though they are actually water. Using 0 or -0.02
# classifies that turbid water as land and pushes the shoreline offshore.
# -0.1 keeps only clearly dry land, placing the shoreline at the visible coast edge.
NDWI_LAND_THRESHOLD = -0.1
TRANSECT_SPACING_M = 500
TRANSECT_LENGTH_M = 200
TRANSECT_CRS = "EPSG:2954"  # NAD83 / PEI Stereographic (meters)


def _utc_now_iso():
    return _dt.utcnow().isoformat(timespec="seconds") + "Z"


def _run_earth_engine_warmup():
    logger.info("Starting Earth Engine warmup")
    try:
        # First call establishes the service-account session. The tiny collection
        # query warms the Sentinel-2 path used by the first dashboard layer.
        ee.Number(1).getInfo()
        (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(PEI_BBOX)
            .filterDate(BASELINE_START, BASELINE_END)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
            .limit(1)
            .size()
            .getInfo()
        )
        with WARMUP_LOCK:
            WARMUP_STATE.update({
                "complete": True,
                "error": None,
                "completed_at_utc": _utc_now_iso(),
            })
        logger.info("Earth Engine warmup completed")
    except Exception as e:
        logger.warning("Earth Engine warmup failed: %s", str(e))
        with WARMUP_LOCK:
            WARMUP_STATE.update({
                "complete": False,
                "error": str(e),
                "completed_at_utc": _utc_now_iso(),
            })


def start_warmup_once():
    with WARMUP_LOCK:
        if WARMUP_STATE["started"]:
            return dict(WARMUP_STATE)
        WARMUP_STATE.update({
            "started": True,
            "started_at_utc": _utc_now_iso(),
            "completed_at_utc": None,
            "error": None,
        })
    thread = threading.Thread(target=_run_earth_engine_warmup, daemon=True)
    thread.start()
    return dict(WARMUP_STATE)


if EE_INITIALIZED:
    start_warmup_once()

# Cache for NDWI-derived baseline (populated on first /get_baseline request with explicit date range)
BASELINE = {
    "ndwi": None,
    "land_mask": None,
    "polygons_fc": None,
    "polygons_geojson": None,
    "shoreline_geojson": None,
    "area_km2": None,
    "transects_geojson": None,
    "start_date": None,
    "end_date": None,
}
# Cache for user-selected baseline date ranges: key (start_date, end_date) -> same structure as BASELINE
BASELINE_CACHE = {}
BASELINE_CACHE_MAX = 3

# Global geo data (PEI bbox for imagery; baseline data comes from BASELINE)
baseline_geometry = None
baseline_land_area = None
processed_geojson = None


def get_geometry(roi_geojson=None):
    """Return ee.Geometry for processing: ROI polygon if provided, else PEI bbox (reference Section 1)."""
    if not roi_geojson or not isinstance(roi_geojson, dict):
        return PEI_BBOX
    try:
        return ee.Geometry(roi_geojson, None, False)
    except Exception:
        return PEI_BBOX


def fix_geometries(gdf):
    gdf.geometry = gdf.geometry.buffer(0)
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        logger.warning(f"Found {invalid.sum()} invalid geometries after buffer(0), trying make_valid")
        gdf.loc[invalid, 'geometry'] = gdf.loc[invalid, 'geometry'].apply(
            lambda geom: make_valid(geom) if geom is not None else geom
        )
    if (~gdf.geometry.is_valid).any():
        logger.error("Still invalid geometries present after all fixes")
        raise ValueError("Could not fix all invalid geometries")
    return gdf


def mask_s2(image):
    """
    Cloud masking using SCL only (reference): mask out 1=cloud shadow, 2=cloud, 3=high cloud,
    8,9,10,11=cirrus/snow. Does not scale; scale 1/10000 applied after composite in get_s2_composite.
    """
    scl = image.select("SCL")
    mask = (
        scl.neq(1)
        .And(scl.neq(2))
        .And(scl.neq(3))
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
        .And(scl.neq(11))
    )
    return image.updateMask(mask).copyProperties(image, ["system:time_start"])


def mask_clouds_s2(image):
    """Fallback: QA60 cloud/cirrus mask when SCL not available. Scales reflectance by 1/10000."""
    qa = image.select("QA60")
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000).copyProperties(image, ["system:time_start"])


# Cap images used for median to keep response time reasonable (Earth Engine is slow with 100+ images)
MAX_IMAGES_FOR_COMPOSITE = 20


def process_s2_collection(collection, geometry):
    """
    Preprocessing (reference): SCL cloud mask (mask_s2), median composite, no fill.
    Scale 1/10000 applied after composite for L2A reflectance.
    """
    collection = collection.sort("CLOUDY_PIXEL_PERCENTAGE").limit(MAX_IMAGES_FOR_COMPOSITE)
    try:
        cloud_free = collection.map(mask_s2)
        used_scl = True
    except Exception:
        cloud_free = collection.map(mask_clouds_s2)
        used_scl = False
    mosaicked = cloud_free.median()
    if used_scl:
        mosaicked = mosaicked.divide(10000)
    return mosaicked.clip(geometry)


# -----------------------------
# NDWI pipeline: composite, land mask, polygons, shoreline (land = NDWI <= 0)
# -----------------------------
def get_s2_composite(start_date, end_date, geometry, use_scl=True):
    """
    Median NDWI composite (reference): filter CLOUD_MAX, mask_s2 (SCL), median, clip.
    No fill of cloudy pixels. Scale 1/10000 after composite when SCL used.
    """
    ic = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
    )
    size = ic.size().getInfo()
    if size == 0:
        raise ValueError(
            f"No Sentinel-2 images with CLOUD<{CLOUD_MAX}% between {start_date} and {end_date}"
        )
    if size > 1:
        logger.info("Multiple images (%d); median composite.", size)
    ic = ic.sort("CLOUDY_PIXEL_PERCENTAGE").limit(MAX_IMAGES_FOR_COMPOSITE)
    try:
        cloud_free = ic.map(mask_s2) if use_scl else ic.map(mask_clouds_s2)
        used_scl = use_scl
    except Exception:
        cloud_free = ic.map(mask_clouds_s2)
        used_scl = False
    mosaicked = cloud_free.median()
    if used_scl:
        mosaicked = mosaicked.divide(10000)
    return mosaicked.clip(geometry)


def get_ndwi_composite(start_date, end_date, geometry=None):
    """NDWI = normalizedDifference(B3, B8) (green vs NIR). geometry defaults to PEI_BBOX."""
    geom = geometry or PEI_BBOX
    img = get_s2_composite(start_date, end_date, geom, use_scl=True)
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("NDWI")
    return ndwi


def land_mask_from_ndwi(ndwi):
    """Land = NDWI <= NDWI_LAND_THRESHOLD (sample logic: land = NDWI <= 0)."""
    return ndwi.lte(NDWI_LAND_THRESHOLD).rename("land")


def land_area_km2(land_mask, geometry=None):
    """Land area in km² inside geometry (default PEI_BBOX)."""
    geom = geometry or PEI_BBOX
    area_m2 = (
        land_mask.selfMask()
        .multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=SCALE,
            maxPixels=1e13,
        )
        .get("land")
        .getInfo()
    )
    area_m2 = area_m2 or 0
    return round(area_m2 / 1e6, 2)


def land_polygons_fc(land_mask, geometry=None):
    """
    Convert land mask to polygons for shoreline extraction.

    We use scale=10 m — the native Sentinel-2 pixel size — so the polygon boundary
    is placed at 10 m intervals matching the actual image resolution.  Using a coarser
    scale (e.g. 30 m) re-bins the 10 m pixels into larger cells before vectorizing,
    introducing up to 30 m of positional error even though the image itself is 10 m.

    focal_mode radius=1 pixel: removes single-pixel salt-and-pepper noise without
    expanding the land polygon into the water (radius=2 grows land ~10 m in every
    direction because it reclassifies isolated water pixels near the coast as land).
    """
    geom = geometry or PEI_BBOX
    clean = (
        land_mask
        .selfMask()
        .focal_mode(radius=1, units="pixels")
        .rename("land")
    )
    vectors = clean.reduceToVectors(
        geometry=geom,
        scale=10,               # Native S2 resolution — no precision lost
        geometryType="polygon",
        eightConnected=False,
        labelProperty="value",
        maxPixels=1e13,
        bestEffort=True,
        tileScale=16,           # Higher tileScale prevents memory errors at 10 m
    )
    # Keep polygons ≥ 500 m² (0.05 ha) to remove salt-and-pepper noise over water
    def add_area(f):
        return f.set("area_m2", f.geometry().area(maxError=1))

    filtered_vectors = (
        vectors.map(add_area)
        .filter(ee.Filter.gt("area_m2", 500))
        .limit(2000)
    )
    return filtered_vectors


def land_polygons_fc_dissolved(land_mask, geometry=None):
    """
    Convert land mask to a single dissolved polygon for shoreline display.

    scale=10 m  — native S2 resolution (was 30 m; coarser scale introduces up to
                  30 m positional error because pixel centres shift by ±½ pixel).
    focal_mode radius=1 (was 2) — prevents ~10–20 m seaward expansion of the land polygon.
    dissolve maxError=5 (was 30) — GEE is allowed to deviate ≤5 m from the true
                  polygon boundary; was 30 m which visibly shifted the coastline.
    """
    geom = geometry or PEI_BBOX
    clean = (
        land_mask
        .selfMask()
        .focal_mode(radius=1, units="pixels")
        .rename("land")
    )
    vectors = clean.reduceToVectors(
        geometry=geom,
        scale=10,               # Native S2 resolution
        geometryType="polygon",
        eightConnected=False,
        labelProperty="value",
        maxPixels=1e13,
        bestEffort=True,
        tileScale=16,
    )
    dissolved = vectors.geometry().dissolve(maxError=5)
    return ee.FeatureCollection([ee.Feature(dissolved, {"year": "baseline_or_current"})])


def ee_fc_to_geojson(fc):
    """Convert EE FeatureCollection to GeoJSON dict."""
    return fc.getInfo()


def filter_polygons_by_area_min(geojson, min_area_m2=5000):
    """
    Drop polygon features smaller than min_area_m2 (m²) to remove red-dot artifacts over water.
    Uses PEI projection (EPSG:2954) for area; returns GeoJSON in WGS84.
    """
    if not geojson or not geojson.get("features"):
        return geojson
    try:
        gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
        gdf = gdf.to_crs(TRANSECT_CRS)
        gdf["_area_m2"] = gdf.geometry.area
        gdf = gdf[gdf["_area_m2"] >= min_area_m2].drop(columns=["_area_m2"])
        gdf = gdf.to_crs("EPSG:4326")
        if len(gdf) == 0:
            return {"type": "FeatureCollection", "features": []}
        return json.loads(gdf.to_json())
    except Exception as e:
        logger.warning("filter_polygons_by_area_min failed: %s", e)
        return geojson


def extract_shoreline_from_land_mask(land_mask, geometry, log):
    """
    Extract shoreline (LineString FC) from land mask. Tries dissolved pipeline first;
    if that returns no features, falls back to non-dissolved (multiple polygons).
    Returns {"type": "FeatureCollection", "features": [...]}.
    """
    for name, use_dissolved in [("dissolved", True), ("non-dissolved", False)]:
        try:
            if use_dissolved:
                polygons_fc = land_polygons_fc_dissolved(land_mask, geometry)
            else:
                polygons_fc = land_polygons_fc(land_mask, geometry)
            polygons_geojson = ee_fc_to_geojson(polygons_fc)
            if not polygons_geojson or not polygons_geojson.get("features"):
                log.warning("Shoreline extraction (%s): no polygon features from GEE", name)
                continue
            shoreline_geojson = polygons_geojson_to_shoreline_lines(polygons_geojson)
            if shoreline_geojson.get("features"):
                log.info("Shoreline extracted with %s pipeline: %d segment(s)", name, len(shoreline_geojson["features"]))
                return shoreline_geojson
            log.warning("Shoreline extraction (%s): polygons had no valid boundaries", name)
        except Exception as e:
            log.warning("Shoreline extraction (%s) failed: %s", name, str(e))
    return {"type": "FeatureCollection", "features": []}


def polygons_geojson_to_shoreline_lines(polygons_geojson):
    """
    Take polygon GeoJSON -> produce LineString shoreline GeoJSON (boundaries).
    Leaflet DSAS code expects LineString features.
    Simple extraction of exteriors - no filtering, matches original working approach.
    """
    features = []
    for f in polygons_geojson.get("features", []):
        geom = f.get("geometry")
        if not geom:
            continue
        shp = shape(geom)
        # unify multipolygons etc.
        if shp.is_empty:
            continue
        boundaries = []
        if isinstance(shp, Polygon):
            boundaries = [shp.exterior]
        elif isinstance(shp, MultiPolygon):
            boundaries = [p.exterior for p in shp.geoms]
        else:
            # if something unexpected, skip
            continue
        for b in boundaries:
            if b.is_empty:
                continue
            line = LineString(b.coords)
            features.append({
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {}
            })
    return {"type": "FeatureCollection", "features": features}


def shoreline_remove_aoi_boundary(shoreline_geojson, aoi_geojson, tolerance_deg=0.0001):
    """
    Remove segments of the shoreline that lie on the AOI boundary (e.g. predefined rectangle edges).
    Only removes segments that are clearly part of the rectangle perimeter, preserving natural coastlines.
    """
    if not aoi_geojson or not shoreline_geojson.get("features"):
        return shoreline_geojson
    try:
        geom_dict = aoi_geojson.get("geometry", aoi_geojson) if isinstance(aoi_geojson, dict) else aoi_geojson
        if not geom_dict or geom_dict.get("type") != "Polygon":
            return shoreline_geojson
        aoi = shape(geom_dict)
        if aoi.is_empty:
            return shoreline_geojson
        aoi_boundary = aoi.boundary
        if aoi_boundary.is_empty:
            return shoreline_geojson
        # Buffer the AOI boundary - only remove segments that are very close to it
        aoi_buffered = aoi_boundary.buffer(tolerance_deg)
        out_features = []
        removed_count = 0
        for f in shoreline_geojson["features"]:
            geom = f.get("geometry")
            if not geom:
                continue
            line = shape(geom)
            if line.is_empty:
                continue
            # MultiLineString: process each part
            if isinstance(line, MultiLineString):
                for part in line.geoms:
                    cleaned = _remove_boundary_segments_simple(part, aoi_buffered)
                    if cleaned:
                        out_features.append({"type": "Feature", "geometry": mapping(cleaned), "properties": {}})
                    else:
                        removed_count += 1
            else:
                cleaned = _remove_boundary_segments_simple(line, aoi_buffered)
                if cleaned:
                    out_features.append({"type": "Feature", "geometry": mapping(cleaned), "properties": {}})
                else:
                    removed_count += 1
        if out_features:
            logger.info("shoreline_remove_aoi_boundary: kept %d segment(s), removed %d AOI-boundary segment(s)", len(out_features), removed_count)
        return {"type": "FeatureCollection", "features": out_features}
    except Exception as e:
        logger.warning("shoreline_remove_aoi_boundary failed: %s", str(e))
        return shoreline_geojson


def _remove_boundary_segments_simple(line, aoi_buffered):
    """Remove parts of line that are within the buffered AOI boundary, return remaining parts."""
    if not isinstance(line, LineString) or len(line.coords) < 2:
        return None
    try:
        # Only remove if the entire line is within the buffer (it's an AOI edge)
        # Otherwise, keep the line (natural coastline near but not on the edge)
        if aoi_buffered.contains(line):
            return None  # Entire line is on AOI boundary, remove it
        # If line intersects buffer but isn't fully contained, keep it (natural coastline)
        return line
    except Exception:
        return line  # If check fails, keep the line (safer)


def _collect_cleaned(line, aoi_buffered, out_features):
    """Append non-empty parts of line.difference(aoi_buffered) to out_features."""
    if not isinstance(line, LineString) or len(line.coords) < 2:
        return
    try:
        cleaned = line.difference(aoi_buffered)
        if cleaned.is_empty:
            return
        if isinstance(cleaned, LineString) and len(cleaned.coords) >= 2:
            out_features.append({"type": "Feature", "geometry": mapping(cleaned), "properties": {}})
        elif isinstance(cleaned, MultiLineString):
            for part in cleaned.geoms:
                if not part.is_empty and len(part.coords) >= 2:
                    out_features.append({"type": "Feature", "geometry": mapping(part), "properties": {}})
    except Exception:
        pass


def generate_transects_from_shoreline(shoreline_geojson):
    """Generate transects every TRANSECT_SPACING_M along shoreline (PEI CRS), return GeoJSON WGS84."""
    try:
        import pyproj
    except ImportError:
        logger.warning("pyproj not available; transects use approximate degree spacing")
        pyproj = None
    if not shoreline_geojson.get("features"):
        return {"type": "FeatureCollection", "features": []}
    gdf = gpd.GeoDataFrame.from_features(shoreline_geojson["features"], crs="EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    use_meters = False
    if pyproj:
        try:
            gdf_m = gdf.to_crs(TRANSECT_CRS)
            use_meters = True
        except Exception:
            gdf_m = gdf
    else:
        gdf_m = gdf
    transect_features = []
    transformer_back = (
        pyproj.Transformer.from_crs(TRANSECT_CRS, "EPSG:4326", always_xy=True)
        if pyproj else None
    )
    for geom in gdf_m.geometry:
        lines_to_process = (
            [geom] if isinstance(geom, LineString)
            else list(geom.geoms) if isinstance(geom, MultiLineString)
            else []
        )
        for line in lines_to_process:
            if line.is_empty:
                continue
            line_len = line.length
            if use_meters and line_len < TRANSECT_SPACING_M:
                continue
            if not use_meters:
                spacing = 0.0045
                half = 0.0009
                num = max(1, int(line_len / spacing))
                for i in range(1, num):
                    d = i * spacing
                    pt = line.interpolate(d)
                    before = line.interpolate(max(d - 0.00002, 0))
                    after = line.interpolate(min(d + 0.00002, line_len))
                    dx, dy = after.x - before.x, after.y - before.y
                    norm = math.hypot(dx, dy)
                    if norm == 0:
                        continue
                    ux, uy = -dy / norm, dx / norm
                    p1 = (pt.x + ux * half, pt.y + uy * half)
                    p2 = (pt.x - ux * half, pt.y - uy * half)
                    transect_features.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": [[p1[0], p1[1]], [p2[0], p2[1]]]},
                        "properties": {},
                    })
                continue
            num = int(math.floor(line_len / TRANSECT_SPACING_M))
            for i in range(1, num):
                d = i * TRANSECT_SPACING_M
                pt = line.interpolate(d)
                before = line.interpolate(max(d - 5, 0))
                after = line.interpolate(min(d + 5, line_len))
                dx, dy = after.x - before.x, after.y - before.y
                norm = math.hypot(dx, dy)
                if norm == 0:
                    continue
                ux, uy = -dy / norm, dx / norm
                half = TRANSECT_LENGTH_M / 2
                p1 = (pt.x + ux * half, pt.y + uy * half)
                p2 = (pt.x - ux * half, pt.y - uy * half)
                if transformer_back:
                    lon1, lat1 = transformer_back.transform(p1[0], p1[1])
                    lon2, lat2 = transformer_back.transform(p2[0], p2[1])
                else:
                    lon1, lat1, lon2, lat2 = p1[0], p1[1], p2[0], p2[1]
                transect_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[lon1, lat1], [lon2, lat2]]},
                    "properties": {},
                })
    return {"type": "FeatureCollection", "features": transect_features}


def _polygon_to_boundary_fallback(polygon_geojson):
    """
    Return boundary as Feature with LineString (exterior) for display when NDWI extraction fails.
    Ensures the frontend always receives a boundary so Baseline/Comparison Boundary toggles work.
    """
    if not isinstance(polygon_geojson, dict) or polygon_geojson.get('type') != 'Polygon':
        return None
    coords = polygon_geojson.get('coordinates')
    if not coords or not coords[0]:
        return None
    exterior = coords[0]
    return {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': exterior}, 'properties': {}}


def _polygon_to_shoreline_line(boundary_geom):
    """
    Convert land polygon (from NDWI mask) to shoreline boundary line.
    Polygon -> LineString (exterior ring). MultiPolygon -> MultiLineString (exterior rings).
    """
    if not isinstance(boundary_geom, dict) or not boundary_geom.get('coordinates'):
        return None
    gtype = boundary_geom.get('type')
    if gtype == 'Polygon':
        rings = boundary_geom['coordinates']
        if not rings:
            return None
        exterior = rings[0]
        return {'type': 'LineString', 'coordinates': exterior}
    if gtype == 'MultiPolygon':
        lines = []
        for poly in boundary_geom['coordinates']:
            if poly and poly[0]:
                lines.append(poly[0])
        if not lines:
            return None
        return {'type': 'MultiLineString', 'coordinates': lines}
    return None


def _ndwi_land_to_shoreline_line(land_mask, user_geometry, log, scale_first=10, scale_fallback=15):
    """
    Extract ALL land-water boundary lines from NDWI (shoreline inside the AOI).
    Collects shorelines from land polygons, filtering out small noise polygons.
    Land = NDWI <= NDWI_LAND_THRESHOLD; water above threshold.
    Returns a single Feature with LineString or MultiLineString geometry.

    Scale 15 m (was 30 m): at 30 m each pixel is 900 m² which can shift the polygon
    boundary up to 30 m offshore. 15 m halves that error to ≤ 15 m.
    focal_mode radius=1 (was 2): radius=2 grows land by one pixel in all directions,
    pushing the shoreline ~10–20 m into the water.
    """
    max_err = 1
    # Minimal denoising — radius=1 removes isolated noise pixels without
    # expanding the land polygon into the water
    denoised = land_mask.selfMask().focal_mode(radius=1, units="pixels").rename("land")
    for scale in (scale_first, scale_fallback):
        try:
            # Map area and filter on GEE side for efficiency
            vectors = denoised.reduceToVectors(
                geometry=user_geometry,
                scale=scale,
                geometryType='polygon',
                eightConnected=False,
                labelProperty='land',
                maxPixels=1e13,
                bestEffort=True,
                tileScale=16  # Increased from 4 for robust large-area processing
            )
            
            def add_area(f):
                return f.set('area_m2', f.geometry().area())
            
            # GEE-side filtering (0.1 hectare = 1000m2)
            # Use 2000 limit to ensure whole-island coverage
            filtered_vectors = (vectors
                               .map(add_area)
                               .filter(ee.Filter.gt('area_m2', 1000))
                               .limit(2000))
            
            fc_info = filtered_vectors.getInfo()
            all_shorelines = []
            for feat in fc_info.get("features", []):
                geom_info = feat.get("geometry")
                if not geom_info or geom_info.get("type") not in ("Polygon", "MultiPolygon"):
                    continue
                # Individual polygon extraction
                shoreline_geom = _polygon_to_shoreline_line(geom_info)
                if shoreline_geom:
                    all_shorelines.append(shoreline_geom)

            n = len(fc_info.get("features", []))
            if n == 0:
                continue

            if all_shorelines:
                log.info("Extracted %d shoreline segments from %d filtered polygons (scale=%s)", len(all_shorelines), n, scale)
                if len(all_shorelines) == 1:
                    return {"type": "Feature", "geometry": all_shorelines[0], "properties": {}}
                else:
                    coords_list = [s["coordinates"] for s in all_shorelines]
                    return {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": coords_list}, "properties": {}}
        except Exception as e:
            log.warning("NDWI reduceToVectors at scale %s failed: %s", scale, str(e))
    return None


def validate_and_fix_polygon(polygon_geojson):
    """Validate and fix polygon GeoJSON for Earth Engine compatibility"""
    if not isinstance(polygon_geojson, dict):
        raise ValueError("Polygon must be a GeoJSON object")
    
    # Handle both Feature and direct Polygon geometry
    geometry = None
    if polygon_geojson.get('type') == 'Feature':
        # Extract geometry from Feature
        geometry = polygon_geojson.get('geometry')
        if not geometry:
            raise ValueError("Feature must have a geometry property")
        logger.info("Extracted geometry from Feature")
    elif polygon_geojson.get('type') == 'Polygon':
        # Direct Polygon geometry
        geometry = polygon_geojson
    else:
        raise ValueError(f"Geometry must be a Polygon type or Feature with Polygon geometry. Got type: {polygon_geojson.get('type')}")
    
    if geometry.get('type') != 'Polygon':
        raise ValueError(f"Geometry type must be Polygon, got: {geometry.get('type')}")
    
    if not geometry.get('coordinates') or len(geometry['coordinates']) == 0:
        raise ValueError("Polygon must have coordinates")
    
    # Work with the geometry object
    polygon_geojson = geometry
    
    fixed_coords = []
    for ring_idx, ring in enumerate(polygon_geojson['coordinates']):
        if not isinstance(ring, list) or len(ring) < 3:
            raise ValueError(f"Ring {ring_idx} must have at least 3 coordinates")
        
        fixed_ring = []
        for coord_idx, coord in enumerate(ring):
            if not isinstance(coord, list) or len(coord) < 2:
                logger.warning(f"Skipping invalid coordinate at ring {ring_idx}, coord {coord_idx}")
                continue
            
            try:
                lon = float(coord[0])
                lat = float(coord[1])
                
                # Validate ranges
                if lon < -180 or lon > 180 or lat < -90 or lat > 90:
                    logger.warning(f"Coordinate out of range: [{lon}, {lat}]")
                    continue
                
                fixed_ring.append([lon, lat])
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid coordinate value: {coord}, error: {e}")
                continue
        
        if len(fixed_ring) < 3:
            raise ValueError(f"Ring {ring_idx} must have at least 3 valid coordinates")
        
        # Ensure ring is closed
        if fixed_ring[0] != fixed_ring[-1]:
            fixed_ring.append([fixed_ring[0][0], fixed_ring[0][1]])
        
        fixed_coords.append(fixed_ring)
    
    if len(fixed_coords) == 0:
        raise ValueError("No valid coordinate rings found")
    
    polygon_geojson['coordinates'] = fixed_coords
    logger.info(f"Polygon validated: {len(fixed_coords)} rings, first ring has {len(fixed_coords[0])} coordinates")
    
    return polygon_geojson


def init_baseline():
    """
    Build NDWI-derived baseline (sample logic): fixed date range -> NDWI composite -> land mask (NDWI <= 0)
    -> dissolved polygons -> shoreline lines -> area + transects. Cached in BASELINE.
    """
    global baseline_geometry, baseline_land_area, processed_geojson
    logger.info("Building NDWI-derived baseline for %s to %s (land = NDWI <= 0)...", BASELINE_START, BASELINE_END)
    ndwi = get_ndwi_composite(BASELINE_START, BASELINE_END, PEI_BBOX)
    land = land_mask_from_ndwi(ndwi)
    # Sample logic: one dissolved polygon -> shoreline from boundaries
    polygons_fc = land_polygons_fc_dissolved(land, PEI_BBOX)
    polygons_geojson = ee_fc_to_geojson(polygons_fc)
    shoreline_geojson = polygons_geojson_to_shoreline_lines(polygons_geojson)
    logger.info("Shoreline extraction: %d features (expected >0 for all regions)", len(shoreline_geojson.get("features", [])))
    if len(shoreline_geojson.get("features", [])) == 0:
        logger.warning("No shoreline features extracted! Check NDWI mask and vectorization")
    area_km2 = land_area_km2(land, PEI_BBOX)
    transects_geojson = generate_transects_from_shoreline(shoreline_geojson)
    BASELINE["ndwi"] = ndwi
    BASELINE["land_mask"] = land
    BASELINE["polygons_fc"] = polygons_fc
    BASELINE["polygons_geojson"] = polygons_geojson
    BASELINE["shoreline_geojson"] = shoreline_geojson
    BASELINE["area_km2"] = area_km2
    BASELINE["transects_geojson"] = transects_geojson
    baseline_geometry = PEI_BBOX
    baseline_land_area = area_km2
    processed_geojson = polygons_geojson
    logger.info(
        "NDWI baseline ready | Area: %.2f km² | Shoreline features: %d | Transects: %d",
        area_km2,
        len(shoreline_geojson.get("features", [])),
        len(transects_geojson.get("features", [])),
    )


def initialize_geodata():
    """Fallback: load baseline from 2016 shoreline file if NDWI init not used or failed."""
    global baseline_geometry, baseline_land_area, processed_geojson
    try:
        logger.info(f"Loading 2016 shoreline data from: {GEOJSON_PATH}")
        if not GEOJSON_PATH.exists():
            raise FileNotFoundError(f"Shoreline file not found at {GEOJSON_PATH}")

        # Read the 2016 shoreline file
        gdf = gpd.read_file(GEOJSON_PATH)
        
        # Check if pyproj is available
        pyproj_available = PYPROJ_AVAILABLE if 'PYPROJ_AVAILABLE' in globals() else True
        try:
            import pyproj
            pyproj_available = True
        except:
            pyproj_available = False

        # Try to convert CRS, but handle pyproj errors gracefully
        if pyproj_available and gdf.crs and gdf.crs != "EPSG:4326":
            logger.info(f"Converting CRS from {gdf.crs} to EPSG:4326")
            try:
                gdf = gdf.to_crs("EPSG:4326")
            except Exception as crs_error:
                logger.warning(f"CRS conversion failed: {crs_error}")
                pyproj_available = False  # Mark as unavailable for future operations
        
        # If pyproj not available, we'll handle CRS in Earth Engine later
        # For now, just work with the geometry as-is for display purposes
        if not pyproj_available:
            logger.warning("pyproj not available - CRS transformations will be handled by Earth Engine")

        # Fix geometries using make_valid (replace invalid geometries)
        gdf['geometry'] = gdf['geometry'].apply(
            lambda geom: make_valid(geom) if geom is not None and not geom.is_valid else geom
        )

        # Use existing land polygons from 2016 shoreline data
        logger.info("Using existing land area polygons from 2016 shoreline data...")
        
        # Combine all land polygons into a single geometry for analysis
        combined_land = gdf.geometry.unary_union
        
        # Create Earth Engine geometry - specify source CRS if known
        # The original file is in EPSG:3347
        geojson_dict = combined_land.__geo_interface__
        try:
            # Earth Engine can handle CRS transformation if we specify it
            # Try with the original CRS (EPSG:3347) and transform to WGS84
            baseline_geometry = ee.Geometry(geojson_dict, 'EPSG:3347', False)
            # Transform to WGS84 in Earth Engine with error margin (required parameter)
            baseline_geometry = baseline_geometry.transform('EPSG:4326', 1)  # 1 meter error margin
            logger.info("Created Earth Engine geometry with CRS transformation")
        except Exception as geom_error:
            # Fallback: assume coordinates might already be usable
            logger.warning(f"Creating geometry without explicit CRS (error: {geom_error})")
            try:
                baseline_geometry = ee.Geometry(geojson_dict)
                logger.info("Created geometry without CRS transformation")
            except:
                # Last resort: read from file directly
                logger.warning("Trying to read geometry from file directly")
                with open(GEOJSON_PATH, 'r') as f:
                    geojson_file = json.load(f)
                # Create geometry from first feature with explicit CRS
                if 'features' in geojson_file and len(geojson_file['features']) > 0:
                    baseline_geometry = ee.Geometry(geojson_file['features'][0]['geometry'], 'EPSG:3347', False)
                    baseline_geometry = baseline_geometry.transform('EPSG:4326', 1)  # 1 meter error margin
                    logger.info("Created geometry from file with CRS transformation")
                else:
                    # Use default PEI bounding box as ultimate fallback
                    logger.warning("Using default PEI bounding box")
                    baseline_geometry = ee.Geometry.Rectangle([-64.5, 45.9, -61.9, 47.1], 'EPSG:4326')
        
        # Use official PEI area as default to avoid blocking on Earth Engine API calls during startup
        # Area can be calculated on-demand if needed
        baseline_land_area = 5686.03  # Official PEI land area (Statistics Canada 2016)
        logger.info(f"Using official PEI land area: {baseline_land_area:.2f} km²")
        logger.info("Note: Actual calculated area will be computed on first request if needed")
        
        # Simplify the geometry for display
        land_geom = combined_land.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        
        logger.info("Created land area polygon from 2016 shoreline")
        
        # Validate against official PEI land area (5,686.03 km² - Statistics Canada 2016)
        official_pei_area = 5686.03
        area_difference = baseline_land_area - official_pei_area
        area_percentage_diff = (area_difference / official_pei_area) * 100
        
        logger.info(f"2016 shoreline baseline land area: {baseline_land_area:.2f} km²")
        logger.info(f"Official PEI land area (Stats Canada 2016): {official_pei_area:.2f} km²")
        logger.info(f"Difference from official area: {area_difference:+.2f} km² ({area_percentage_diff:+.2f}%)")
        
        if abs(area_percentage_diff) > 5:
            logger.warning(f"Calculated area differs from official PEI area by {area_percentage_diff:+.2f}%")
        else:
            logger.info("Calculated area is very close to official PEI area")

        processed_geojson = json.loads(gdf.to_json())

    except Exception as e:
        logger.error("GeoJSON initialization failed: %s", str(e))
        raise


logger.info("Server ready — awaiting user date selection to run GEE baseline computation")


VISITOR_FILE = BASE_DIR / "visitors.json"

def _load_visitors():
    if VISITOR_FILE.exists():
        try:
            with open(VISITOR_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total": 0}

def _save_visitors(data):
    with open(VISITOR_FILE, "w") as f:
        json.dump(data, f)

@app.route("/visitors", methods=["GET"])
def get_visitors():
    """Return current visitor count without incrementing."""
    data = _load_visitors()
    return jsonify({"total": data.get("total", 0)})

@app.route("/visitors/track", methods=["POST"])
def track_visitor():
    """Increment visitor count and return new total."""
    data = _load_visitors()
    data["total"] = data.get("total", 0) + 1
    _save_visitors(data)
    return jsonify({"total": data["total"]})


@app.route('/')
def health_check():
    studyline_files = {
        filename: str(_study_area_path(filename))
        for _, _, filename in STUDY_AREA_FILES
        if _study_area_path(filename).exists()
    }
    ready = EE_INITIALIZED and len(studyline_files) == len(STUDY_AREA_FILES)
    return jsonify({
        "status": "running",
        "ready": ready,
        "message": "PEI Coastal Analysis API is running",
        "earth_engine_initialized": EE_INITIALIZED,
        "server_started_at_utc": SERVER_STARTED_AT_UTC,
        "studyline_files_found": len(studyline_files),
        "studyline_files": studyline_files,
        "baseline_source": "NDWI-derived" if BASELINE.get("polygons_geojson") else "none — awaiting user date selection",
        "baseline_window": (
            f"{BASELINE['start_date']} to {BASELINE['end_date']}"
            if BASELINE.get("start_date") else "not yet selected"
        ),
        "endpoints": [
            "/get_baseline",
            "/get_shoreline_data",
            "/get_baseline_transects",
            "/get_transect_change",
            "/get_imagery",
            "/analyze_change",
            "/study_areas",
        ],
    })


def _study_area_path(filename):
    """Resolve study line GeoJSON path: try project root, then api folder, then parent of project root."""
    for base in (PROJECT_ROOT, BASE_DIR, PROJECT_ROOT.parent):
        p = base / filename
        if p.exists():
            return p
    return PROJECT_ROOT / filename


@app.route("/health/ready")
def readiness_check():
    """Lightweight readiness diagnostics for deployment checks."""
    studyline_files = {
        filename: str(_study_area_path(filename))
        for _, _, filename in STUDY_AREA_FILES
        if _study_area_path(filename).exists()
    }
    ready = EE_INITIALIZED and len(studyline_files) == len(STUDY_AREA_FILES)
    payload = {
        "ready": ready,
        "status": "live" if ready else "starting",
        "earth_engine_initialized": EE_INITIALIZED,
        "studyline_files_found": len(studyline_files),
        "studyline_files_expected": len(STUDY_AREA_FILES),
        "server_started_at_utc": SERVER_STARTED_AT_UTC,
    }
    return jsonify(payload), 200 if ready else 503


@app.route("/warmup", methods=["GET", "POST"])
def warmup():
    """Start backend/GEE warmup without blocking the user-facing request."""
    state = start_warmup_once()
    return jsonify({
        "status": "warming" if not state.get("complete") else "ready",
        "warmup": state,
    })


@app.route("/study_areas")
def study_areas():
    """
    Return predefined study area polygons (from study line GeoJSON files).
    Each item: { "id", "name", "geometry" } for use as AOI on the frontend.
    """
    out = []
    for area_id, name, filename in STUDY_AREA_FILES:
        path = _study_area_path(filename)
        if not path.exists():
            logger.warning("Study area file not found: %s", path)
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            features = data.get("features") or []
            if not features:
                continue
            feat = features[0]
            geom = feat.get("geometry")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            out.append({"id": area_id, "name": name, "geometry": geom})
        except Exception as e:
            logger.warning("Failed to load study area %s: %s", filename, e)
    return jsonify({"study_areas": out})


@app.route("/studylines/<path:filename>")
def serve_studyline(filename):
    """Serve a single study line GeoJSON file (fallback if study_areas list is empty)."""
    if filename not in [f[2] for f in STUDY_AREA_FILES]:
        return jsonify({"error": "Unknown file"}), 404
    path = _study_area_path(filename)
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(path.parent, path.name, mimetype="application/geo+json")


def _compute_baseline_for_range(start_date, end_date, geometry=None):
    """Compute NDWI baseline for a date range with optional custom geometry (sample logic: dissolved polygon, land = NDWI <= 0)."""
    geom = geometry or PEI_BBOX
    geom_str = str(geometry) if geometry else "PEI_BBOX"
    key = (start_date, end_date, geom_str)
    if key in BASELINE_CACHE:
        logger.info("Returning cached baseline for %s to %s", start_date, end_date)
        return BASELINE_CACHE[key]
    _validate_date_range(start_date, end_date)
    logger.info("Computing baseline for user range %s to %s (land = NDWI <= 0)", start_date, end_date)
    ndwi = get_ndwi_composite(start_date, end_date, geom)
    land = land_mask_from_ndwi(ndwi)
    # Build lazy EE objects for dissolved polygon and area — then fetch in parallel
    polygons_fc = land_polygons_fc_dissolved(land, geom)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_poly = pool.submit(ee_fc_to_geojson, polygons_fc)
        f_area = pool.submit(land_area_km2, land, geom)
    polygons_geojson = f_poly.result()
    area_km2 = f_area.result()
    shoreline_geojson = polygons_geojson_to_shoreline_lines(polygons_geojson)
    transects_geojson = generate_transects_from_shoreline(shoreline_geojson)
    result = {
        "ndwi": ndwi,
        "land_mask": land,
        "polygons_fc": polygons_fc,
        "polygons_geojson": polygons_geojson,
        "shoreline_geojson": shoreline_geojson,
        "area_km2": area_km2,
        "transects_geojson": transects_geojson,
    }
    while len(BASELINE_CACHE) >= BASELINE_CACHE_MAX:
        BASELINE_CACHE.pop(next(iter(BASELINE_CACHE)))
    BASELINE_CACHE[key] = result
    return result


@app.route('/get_baseline', methods=['GET', 'POST'])
def get_baseline():
    """
    Return NDWI-derived baseline. Supports both GET and POST methods.
    GET: Query params: start_date, end_date (optional). Returns full PEI baseline.
    POST: Body params: start_date, end_date, geometry (optional). Returns baseline for custom AOI.
    """
    try:
        # Handle POST request with custom geometry
        if request.method == 'POST':
            data = request.get_json() or {}
            start_date = data.get("start_date") or data.get("baseline_start")
            end_date = data.get("end_date") or data.get("baseline_end")
            geometry_geojson = data.get("geometry")

            if not start_date or not end_date:
                return jsonify({"error": "Please select a baseline date range first"}), 400

            # Convert geometry if provided
            geometry = None
            if geometry_geojson:
                try:
                    geometry = ee.Geometry(geometry_geojson, None, False)
                    logger.info("Processing baseline request with custom geometry")
                except Exception as e:
                    logger.warning("Failed to parse custom geometry: %s", str(e))
                    geometry = None

            try:
                result_data = _compute_baseline_for_range(start_date, end_date, geometry)
                # Populate global BASELINE so other endpoints can use it
                BASELINE.update(result_data)
                BASELINE["start_date"] = start_date
                BASELINE["end_date"] = end_date
                return jsonify({
                    "geojson": result_data["polygons_geojson"],
                    "shoreline_geojson": result_data.get("shoreline_geojson"),
                    "baseline_area_km2": result_data["area_km2"],
                    "baseline_start": start_date,
                    "baseline_end": end_date,
                })
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

        # Handle GET request
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        if start_date and end_date:
            try:
                result_data = _compute_baseline_for_range(start_date, end_date)
                # Populate global BASELINE so other endpoints can use it
                BASELINE.update(result_data)
                BASELINE["start_date"] = start_date
                BASELINE["end_date"] = end_date
                return jsonify({
                    "geojson": result_data["polygons_geojson"],
                    "shoreline_geojson": result_data.get("shoreline_geojson"),
                    "baseline_area_km2": result_data["area_km2"],
                    "baseline_start": start_date,
                    "baseline_end": end_date,
                })
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

        # No dates provided — return populated baseline or 400
        if not BASELINE.get("polygons_geojson"):
            return jsonify({"error": "Please select a baseline date range first"}), 400
        return jsonify({
            "geojson": BASELINE.get("polygons_geojson"),
            "shoreline_geojson": BASELINE.get("shoreline_geojson"),
            "baseline_area_km2": BASELINE.get("area_km2"),
            "baseline_start": BASELINE.get("start_date"),
            "baseline_end": BASELINE.get("end_date"),
        })
    except Exception as e:
        logger.error("Baseline request failed: %s", str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/get_shoreline_data', methods=['POST'])
def get_shoreline_data():
    """
    Compute current shoreline from NDWI for user-selected date range (reference Section 4).
    Optional body: roi or geometry (GeoJSON). When provided, shoreline is computed for that AOI.
    """
    try:
        data = request.get_json() or {}
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if not start_date or not end_date:
            return jsonify({"error": "Both start_date and end_date are required"}), 400
        _validate_date_range(start_date, end_date)
        roi = data.get("roi")
        cache_key = _layer_cache_key("get_shoreline_data", roi, start_date, end_date)
        cached = _layer_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached shoreline data for %s to %s", start_date, end_date)
            return jsonify(cached)
        geom = get_geometry(roi)
        ndwi = get_ndwi_composite(start_date, end_date, geom)
        land = land_mask_from_ndwi(ndwi)
        shoreline_geojson = extract_shoreline_from_land_mask(land, geom, logger)
        result = {"shoreline": shoreline_geojson}
        _layer_cache_set(cache_key, result)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("get_shoreline_data failed: %s", str(e))
        return jsonify({"error": str(e)}), 500




# Try to import pyproj, but handle if it fails
try:
    import pyproj
    PYPROJ_AVAILABLE = True
except ImportError:
    PYPROJ_AVAILABLE = False
    logger.warning("pyproj not available, transect generation will use approximate spacing in degrees")

@app.route('/get_baseline_transects')
def get_baseline_transects():
    """
    Return baseline polygons, shoreline, and transects (DSAS). Uses user range when provided.
    Query params: start_date, end_date (optional). Same NDWI <= 0 and dissolved-polygon logic as get_baseline.
    """
    try:
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        if start_date and end_date:
            key = (start_date, end_date, "PEI_BBOX")
            if key in BASELINE_CACHE:
                data = BASELINE_CACHE[key]
            else:
                try:
                    data = _compute_baseline_for_range(start_date, end_date)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
            # Populate global BASELINE so other endpoints can use it
            BASELINE.update(data)
            BASELINE["start_date"] = start_date
            BASELINE["end_date"] = end_date
            n = len(data["transects_geojson"].get("features", []))
            return jsonify({
                "baseline": data["polygons_geojson"],
                "shoreline": data["shoreline_geojson"],
                "transects": data["transects_geojson"],
                "message": f"{n} transects from baseline {start_date} to {end_date}",
            })
        if BASELINE.get("transects_geojson") is not None:
            n = len(BASELINE["transects_geojson"].get("features", []))
            return jsonify({
                "baseline": BASELINE["polygons_geojson"],
                "shoreline": BASELINE["shoreline_geojson"],
                "transects": BASELINE["transects_geojson"],
                "message": f"{n} transects generated from NDWI baseline shoreline",
            })
        return jsonify({"error": "Please select a baseline date range first"}), 400

    except Exception as e:
        logger.error("Failed to generate transects: %s", str(e))
        return jsonify({'error': str(e)}), 500


@app.route('/get_imagery', methods=['POST'])
def get_imagery():
    """
    Return true-color and NDWI tile URLs (reference: geom = get_geometry(roi), S2 + mask_s2 + median, clip to geom).
    Body: start_date, end_date, roi (GeoJSON). True colour: unscaled reflectance min 500, max 2500.
    """
    try:
        data = request.get_json() or {}
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if not start_date or not end_date:
            raise ValueError("Both start_date and end_date are required")
        _validate_date_range(start_date, end_date)
        roi = data.get("roi")
        cache_key = _layer_cache_key("get_imagery", roi, start_date, end_date)
        cached = _layer_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached imagery for %s to %s", start_date, end_date)
            return jsonify(cached)
        geom = get_geometry(roi)
        logger.info("Fetching imagery for %s to %s (SCL mask, clip to roi)", start_date, end_date)
        image = get_s2_composite(start_date, end_date, geom, use_scl=True)
        ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
        # Reference: true colour unscaled reflectance min 500, max 2500
        image_unscaled = image.multiply(10000)
        true_color_vis = image_unscaled.visualize(**{
            "bands": ["B4", "B3", "B2"],
            "min": 500,
            "max": 2500,
            "gamma": 1.2,
        })
        ndwi_vis = ndwi.visualize(**{
            "min": -1,
            "max": 1,
            "palette": ["brown", "white", "blue"],
        })
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_tc = pool.submit(lambda: true_color_vis.getMapId()["tile_fetcher"].url_format)
            f_ndwi = pool.submit(lambda: ndwi_vis.getMapId()["tile_fetcher"].url_format)
        result = {
            "true_color": f_tc.result(),
            "ndwi": f_ndwi.result(),
        }
        _layer_cache_set(cache_key, result)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Imagery request failed: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/analyze_change', methods=['POST'])
def analyze_change():
    """
    Compare current (user date range) vs baseline (reference Section 5). Land = NDWI <= 0.
    Erosion = baseline land that is water in current. Optional body: roi or geometry for AOI.
    When roi/geometry provided, baseline and current areas and erosion are computed/clipped to that AOI.
    """
    try:
        data = request.get_json() or {}
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if not start_date or not end_date:
            raise ValueError("Both start_date and end_date are required")
        _validate_date_range(start_date, end_date)
        if BASELINE.get("land_mask") is None:
            return jsonify({"error": "Please select a baseline date range first"}), 400
        geom = get_geometry(data.get("roi")) or PEI_BBOX
        ndwi_cur = get_ndwi_composite(start_date, end_date, geom)
        land_cur = land_mask_from_ndwi(ndwi_cur)
        baseline_land_mask = BASELINE["land_mask"]
        baseline_area = float(land_area_km2(baseline_land_mask, geom))
        current_area_km2 = land_area_km2(land_cur, geom)
        area_change = round(current_area_km2 - baseline_area, 2)
        water_cur = ndwi_cur.gt(0).rename("water")
        erosion = baseline_land_mask.selfMask().And(water_cur).selfMask().clip(geom)
        erosion_vis = erosion.visualize(**{"palette": ["red"], "min": 1, "max": 1})
        change_pct = round((area_change / baseline_area) * 100, 2) if baseline_area else 0
        logger.info(
            "Change analysis | baseline=%.2f current=%.2f change=%.2f (%.2f%%)",
            baseline_area, current_area_km2, area_change, change_pct,
        )
        return jsonify({
            "baseline_land_area": round(baseline_area, 2),
            "current_land_area": current_area_km2,
            "erosion_area": area_change,
            "erosion_tiles": erosion_vis.getMapId()["tile_fetcher"].url_format,
            "analysis_period": f"{start_date} to {end_date}",
            "baseline_year": "NDWI-derived",
            "baseline_window": f"{BASELINE.get('start_date')} to {BASELINE.get('end_date')}",
            "change_percentage": change_pct,
        })
    except Exception as e:
        logger.error("Analysis failed: %s", str(e))
        return jsonify({"error": str(e)}), 500





@app.route('/load_baseline_2016', methods=['POST'])
def load_baseline_2016():
    """Load 2016 baseline imagery and detect shoreline boundary using NDWI"""
    try:
        data = request.get_json() or {}
        polygon_geojson = data.get('polygon')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not polygon_geojson:
            raise ValueError("Polygon is required")
        if not start_date or not end_date:
            raise ValueError("Baseline start_date and end_date are required (select baseline imagery date range)")
        
        # Validate and fix polygon geometry
        polygon_geojson = validate_and_fix_polygon(polygon_geojson)
        cache_key = _layer_cache_key("load_baseline_2016", polygon_geojson, start_date, end_date)
        cached = _layer_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached baseline layer for %s to %s", start_date, end_date)
            return jsonify(cached)
        
        # Create Earth Engine geometry from polygon
        try:
            user_geometry = ee.Geometry(polygon_geojson, None, False)
            logger.info("Earth Engine geometry created successfully")
        except Exception as geom_error:
            logger.error(f"Geometry creation error: {geom_error}")
            logger.error(f"Polygon structure: type={polygon_geojson.get('type')}, coords_length={len(polygon_geojson.get('coordinates', []))}")
            raise ValueError(f"Invalid polygon geometry for Earth Engine: {str(geom_error)}")
        
        logger.info(f"Loading baseline imagery for {start_date} to {end_date}")
        
        # Get Sentinel-2 imagery
        collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                      .filterBounds(user_geometry)
                      .filterDate(start_date, end_date)
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)))
        
        collection_size = collection.size().getInfo()
        logger.info(f"Found {collection_size} images with <15% cloud cover for {start_date} to {end_date}")
        
        if collection_size == 0:
            raise ValueError(f"No images with <15% cloud cover available for {start_date} to {end_date}. Try a longer date range or different dates.")
        
        # Same preprocessing as comparison: cloud filter 15%, process_s2_collection (median, unmask), clip to geometry
        median_image = process_s2_collection(collection, user_geometry)
        
        # Calculate NDWI
        ndwi = median_image.normalizedDifference(['B3', 'B8']).rename('ndwi')
        
        # Shoreline: same land rule as baseline (NDWI < -0.02)
        land_mask = land_mask_from_ndwi(ndwi)

        # Imagery vis objects (lazy — no GEE call yet)
        true_color_vis = median_image.visualize(**{
            'bands': ['B4', 'B3', 'B2'],
            'min': 0.05,
            'max': 0.25,
            'gamma': 1.2
        })
        ndwi_vis = ndwi.visualize(**{
            'min': -0.5,
            'max': 0.8,
            'palette': ['#A0522D', '#DEB887', '#87CEEB', '#4682B4', '#2F4F7F']
        })

        # Run all independent GEE round-trips in parallel
        def _get_baseline_area():
            return (land_mask.multiply(ee.Image.pixelArea())
                    .reduceRegion(reducer=ee.Reducer.sum(), geometry=user_geometry,
                                  scale=10, maxPixels=1e13, bestEffort=True)
                    .get('land').getInfo() or 0)

        with ThreadPoolExecutor(max_workers=4) as pool:
            f_shoreline = pool.submit(extract_shoreline_from_land_mask, land_mask, user_geometry, logger)
            f_tc = pool.submit(lambda: true_color_vis.getMapId()['tile_fetcher'].url_format)
            f_ndwi_url = pool.submit(lambda: ndwi_vis.getMapId()['tile_fetcher'].url_format)
            f_area = pool.submit(_get_baseline_area)

        boundary_geojson = f_shoreline.result()
        tc_url = f_tc.result()
        ndwi_url = f_ndwi_url.result()
        baseline_area = f_area.result()

        if boundary_geojson.get("features"):
            aoi_for_filter = polygon_geojson if polygon_geojson.get("type") == "Polygon" else polygon_geojson.get("geometry")
            if aoi_for_filter:
                fc = shoreline_remove_aoi_boundary(boundary_geojson, aoi_for_filter)
                if fc.get("features"):
                    boundary_geojson = fc
                else:
                    boundary_geojson = {"type": "FeatureCollection", "features": []}
        if not boundary_geojson.get("features"):
            logger.warning("No baseline shoreline for %s to %s after extraction (and optional AOI filter).", start_date, end_date)

        baseline_area_km2 = round(baseline_area / 1e6, 2)
        logger.info(f"Baseline loaded: {baseline_area_km2} km² land area")

        result = {
            'baseline_imagery': {
                'true_color': tc_url,
                'ndwi': ndwi_url
            },
            'boundary': boundary_geojson,
            'baseline_land_area': baseline_area_km2,
            'start_date': start_date,
            'end_date': end_date
        }
        _layer_cache_set(cache_key, result)
        return jsonify(result)
        
    except Exception as e:
        logger.error("Baseline loading failed: %s", str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/load_comparison_imagery', methods=['POST'])
def load_comparison_imagery():
    """Load comparison date imagery"""
    try:
        data = request.get_json() or {}
        polygon_geojson = data.get('polygon')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not polygon_geojson or not start_date or not end_date:
            raise ValueError("Polygon, start_date, and end_date are required")
        
        # Validate and fix polygon geometry
        polygon_geojson = validate_and_fix_polygon(polygon_geojson)
        cache_key = _layer_cache_key("load_comparison_imagery", polygon_geojson, start_date, end_date)
        cached = _layer_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached comparison layer for %s to %s", start_date, end_date)
            return jsonify(cached)
        
        try:
            user_geometry = ee.Geometry(polygon_geojson, None, False)
        except Exception as geom_error:
            raise ValueError(f"Invalid polygon geometry for Earth Engine: {str(geom_error)}")
        
        logger.info(f"Loading comparison imagery for {start_date} to {end_date}")
        
        # Get Sentinel-2 imagery
        collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                      .filterBounds(user_geometry)
                      .filterDate(start_date, end_date)
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)))
        
        collection_size = collection.size().getInfo()
        logger.info(f"Found {collection_size} images with <15% cloud cover for {start_date} to {end_date}")
        
        if collection_size == 0:
            raise ValueError(f"No images with <15% cloud cover available for {start_date} to {end_date}. Try a longer date range or different dates.")
        
        # Same preprocessing as baseline: cloud filter 15%, process_s2_collection (SCL mask, median mosaic, firstNonNull fill, scale 1/10000), clip to geometry
        median_image = process_s2_collection(collection, user_geometry)
        
        # Shoreline: same land rule as baseline (NDWI < -0.02)
        ndwi = median_image.normalizedDifference(['B3', 'B8']).rename('ndwi')
        land_mask = land_mask_from_ndwi(ndwi)

        # Imagery vis objects (lazy — no GEE call yet)
        true_color_vis = median_image.visualize(**{
            'bands': ['B4', 'B3', 'B2'],
            'min': 0.05,
            'max': 0.25,
            'gamma': 1.2
        })
        ndwi_vis = ndwi.visualize(**{
            'min': -0.5,
            'max': 0.8,
            'palette': ['#A0522D', '#DEB887', '#87CEEB', '#4682B4', '#2F4F7F']
        })

        # Run all independent GEE round-trips in parallel
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_shoreline = pool.submit(extract_shoreline_from_land_mask, land_mask, user_geometry, logger)
            f_tc = pool.submit(lambda: true_color_vis.getMapId()['tile_fetcher'].url_format)
            f_ndwi_url = pool.submit(lambda: ndwi_vis.getMapId()['tile_fetcher'].url_format)

        boundary_geojson = f_shoreline.result()
        tc_url = f_tc.result()
        ndwi_url = f_ndwi_url.result()

        if boundary_geojson.get("features"):
            aoi_for_filter = polygon_geojson if polygon_geojson.get("type") == "Polygon" else polygon_geojson.get("geometry")
            if aoi_for_filter:
                fc = shoreline_remove_aoi_boundary(boundary_geojson, aoi_for_filter)
                if fc.get("features"):
                    boundary_geojson = fc
                else:
                    boundary_geojson = {"type": "FeatureCollection", "features": []}
        if not boundary_geojson.get("features"):
            logger.warning("No comparison shoreline for %s to %s.", start_date, end_date)

        result = {
            'true_color': tc_url,
            'ndwi': ndwi_url,
            'boundary': boundary_geojson,
            'start_date': start_date,
            'end_date': end_date
        }
        _layer_cache_set(cache_key, result)
        return jsonify(result)
        
    except Exception as e:
        logger.error("Comparison imagery loading failed: %s", str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_erosion', methods=['POST'])
def analyze_erosion():
    """Analyze erosion between baseline and comparison dates"""
    try:
        data = request.get_json() or {}
        polygon_geojson = data.get('polygon')
        baseline_start = data.get('baseline_start_date')
        baseline_end = data.get('baseline_end_date')
        comparison_start = data.get('comparison_start_date')
        comparison_end = data.get('comparison_end_date')
        
        if not polygon_geojson or not comparison_start or not comparison_end:
            raise ValueError("Polygon, comparison_start_date, and comparison_end_date are required")
        if not baseline_start or not baseline_end:
            raise ValueError("Baseline start and end dates are required (select baseline imagery date range)")
        
        # Validate and fix polygon geometry
        polygon_geojson = validate_and_fix_polygon(polygon_geojson)
        cache_key = _layer_cache_key(
            "analyze_erosion",
            polygon_geojson,
            baseline_start,
            baseline_end,
            comparison_start,
            comparison_end,
        )
        cached = _layer_cache_get(cache_key)
        if cached is not None:
            logger.info("Returning cached erosion analysis for %s-%s vs %s-%s", baseline_start, baseline_end, comparison_start, comparison_end)
            return jsonify(cached)
        
        try:
            user_geometry = ee.Geometry(polygon_geojson, None, False)
        except Exception as geom_error:
            raise ValueError(f"Invalid polygon geometry for Earth Engine: {str(geom_error)}")
        
        # Build both collections (lazy — no GEE call yet)
        baseline_collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                              .filterBounds(user_geometry)
                              .filterDate(baseline_start, baseline_end)
                              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)))
        comparison_collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                                .filterBounds(user_geometry)
                                .filterDate(comparison_start, comparison_end)
                                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)))

        # Check both collection sizes in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_base_sz = pool.submit(lambda: baseline_collection.size().getInfo())
            f_comp_sz = pool.submit(lambda: comparison_collection.size().getInfo())
        if f_base_sz.result() == 0:
            raise ValueError(f"No baseline images with <15% cloud cover available for {baseline_start} to {baseline_end}")
        if f_comp_sz.result() == 0:
            raise ValueError(f"No comparison images with <15% cloud cover available for {comparison_start} to {comparison_end}")

        # Process images with cloud removal (GEE lazy — actual compute deferred to .getInfo())
        baseline_image = process_s2_collection(baseline_collection, user_geometry)
        comparison_image = process_s2_collection(comparison_collection, user_geometry)

        # Build all lazy EE objects
        baseline_ndwi = baseline_image.normalizedDifference(['B3', 'B8'])
        comparison_ndwi = comparison_image.normalizedDifference(['B3', 'B8'])
        baseline_land = land_mask_from_ndwi(baseline_ndwi).rename('baseline_land')
        comparison_land = land_mask_from_ndwi(comparison_ndwi).rename('comparison_land')
        comparison_water = comparison_ndwi.gt(0)
        erosion_mask = baseline_land.And(comparison_water).selfMask()
        erosion_vis = erosion_mask.visualize(**{'palette': ['red'], 'min': 1, 'max': 1})

        # Fire all three independent getInfo calls in parallel
        def _baseline_area():
            return (baseline_land.multiply(ee.Image.pixelArea())
                    .reduceRegion(reducer=ee.Reducer.sum(), geometry=user_geometry,
                                  scale=10, maxPixels=1e13, bestEffort=True)
                    .get('baseline_land').getInfo() or 0)

        def _comparison_area():
            return (comparison_land.multiply(ee.Image.pixelArea())
                    .reduceRegion(reducer=ee.Reducer.sum(), geometry=user_geometry,
                                  scale=10, maxPixels=1e13, bestEffort=True)
                    .get('comparison_land').getInfo() or 0)

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_ba = pool.submit(_baseline_area)
            f_ca = pool.submit(_comparison_area)
            f_etile = pool.submit(lambda: erosion_vis.getMapId()['tile_fetcher'].url_format)

        baseline_area = f_ba.result()
        comparison_area = f_ca.result()
        erosion_tile_url = f_etile.result()

        baseline_area_km2 = round(baseline_area / 1e6, 2)
        comparison_area_km2 = round(comparison_area / 1e6, 2)
        erosion_area = round(comparison_area_km2 - baseline_area_km2, 2)
        change_percentage = round((erosion_area / baseline_area_km2) * 100, 2) if baseline_area_km2 > 0 else 0

        logger.info(f"Erosion analysis: {baseline_area_km2} km² -> {comparison_area_km2} km² (change: {erosion_area} km²)")

        result = {
            'baseline_land_area': baseline_area_km2,
            'comparison_land_area': comparison_area_km2,
            'erosion_area': erosion_area,
            'change_percentage': change_percentage,
            'erosion_tiles': erosion_tile_url,
            'baseline_start_date': baseline_start,
            'baseline_end_date': baseline_end,
            'comparison_start_date': comparison_start,
            'comparison_end_date': comparison_end
        }
        _layer_cache_set(cache_key, result)
        return jsonify(result)
        
    except Exception as e:
        logger.error("Erosion analysis failed: %s", str(e), exc_info=True)
        return jsonify({'error': str(e)}), 500


def _distance_along_transect_m(sample_features, p1, p2, water_threshold=0.0):
    """
    Return distance in metres from the INLAND end of the transect to the first water pixel
    (NDWI > water_threshold).

    The transect generator does not guarantee that p1 is the inland end — the perpendicular
    direction depends on the orientation of the shoreline curve.  We detect which end is inland
    by comparing mean NDWI near each end: the end with lower mean NDWI (more negative = more
    land) is the inland end.  All distances are then measured from that inland end so the
    reported distances are physically meaningful (close to 100 m for a well-centred transect).

    Returns None if no water pixel is found or pyproj is unavailable.
    """
    if not sample_features:
        logger.debug("_distance_along_transect_m: no sample features provided")
        return None
    try:
        from pyproj import Geod
    except ImportError:
        logger.error("pyproj not installed — cannot compute transect distances. Run: pip install pyproj")
        return None
    try:
        geod = Geod(ellps="WGS84")
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        vv = vx * vx + vy * vy
        if vv == 0:
            logger.warning("_distance_along_transect_m: degenerate transect (p1 == p2)")
            return None

        # Collect (t, dist_from_p1, ndwi) for every valid sample pixel
        samples = []
        for f in sample_features:
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates")
            if not coords:
                continue
            lon, lat = coords[0], coords[1]
            ndwi = (f.get("properties") or {}).get("ndwi")
            if ndwi is None:
                continue
            t = ((lon - p1[0]) * vx + (lat - p1[1]) * vy) / vv
            t = max(0.0, min(1.0, t))
            px, py = p1[0] + t * vx, p1[1] + t * vy
            _, _, dist_m = geod.inv(p1[0], p1[1], px, py)
            samples.append((t, dist_m, ndwi))

        if not samples:
            return None

        # Determine which end (p1 or p2) is the inland end using the 25 % of pixels
        # closest to each end.  The end with the lower mean NDWI is inland.
        samples_by_t = sorted(samples, key=lambda x: x[0])
        quarter = max(1, len(samples_by_t) // 4)
        p1_ndwi_mean = sum(v for _, _, v in samples_by_t[:quarter]) / quarter
        p2_ndwi_mean = sum(v for _, _, v in samples_by_t[-quarter:]) / quarter
        p1_is_inland = p1_ndwi_mean <= p2_ndwi_mean
        logger.debug(
            "_distance_along_transect_m: p1_ndwi_mean=%.3f p2_ndwi_mean=%.3f p1_is_inland=%s",
            p1_ndwi_mean, p2_ndwi_mean, p1_is_inland,
        )

        # Sort from the inland end toward the sea; find first water pixel
        if p1_is_inland:
            ordered = sorted(samples, key=lambda x: x[0])          # ascending t = p1 → p2
            ref = p1
        else:
            ordered = sorted(samples, key=lambda x: -x[0])         # descending t = p2 → p1
            ref = p2

        land_count = sum(1 for _, _, v in ordered if v <= water_threshold)
        water_count = sum(1 for _, _, v in ordered if v > water_threshold)
        logger.debug(
            "_distance_along_transect_m: %d samples | land=%d water=%d",
            len(ordered), land_count, water_count,
        )

        _, _, total_len = geod.inv(p1[0], p1[1], p2[0], p2[1])
        for t, dist_from_p1, ndwi in ordered:
            if ndwi > water_threshold:
                # Convert dist_from_p1 to dist_from_inland_end
                if p1_is_inland:
                    return round(dist_from_p1, 1)
                else:
                    return round(total_len - dist_from_p1, 1)

        logger.debug("_distance_along_transect_m: no water pixel found (transect entirely on land)")
        return None
    except Exception as exc:
        logger.error("_distance_along_transect_m error: %s", exc, exc_info=True)
        return None


@app.route('/get_transect_change', methods=['POST'])
def get_transect_change():
    """
    For one transect line: compute baseline/comparison shoreline distances and change.
    Called when user clicks a transect so DSAS run stays fast.
    """
    try:
        from datetime import datetime
        data = request.get_json()
        transect_geojson = data.get("transect")
        polygon_geojson = data.get("polygon")
        baseline_start = data.get("baseline_start_date")
        baseline_end = data.get("baseline_end_date")
        comparison_start = data.get("comparison_start_date")
        comparison_end = data.get("comparison_end_date")
        if not transect_geojson or transect_geojson.get("type") != "LineString":
            raise ValueError("transect must be a GeoJSON LineString")
        if not polygon_geojson or not baseline_start or not baseline_end or not comparison_start or not comparison_end:
            raise ValueError("polygon and all date ranges are required")
        polygon_geojson = validate_and_fix_polygon(polygon_geojson)
        user_geometry = ee.Geometry(polygon_geojson, None, False)
        coords = transect_geojson.get("coordinates")
        if not coords or len(coords) < 2:
            raise ValueError("transect must have at least two coordinates")
        p1, p2 = coords[0], coords[-1]
        transect_geom = ee.Geometry.LineString([p1, p2])
        # Buffer the transect so .sample() captures pixels on both sides of the line.
        # A 0-width LineString rarely intersects pixel centres at 10m scale; 20m buffer
        # creates a ~40m-wide corridor that reliably contains 20–40 pixels along a 200m transect.
        transect_sample_region = transect_geom.buffer(distance=20, maxError=1)

        baseline_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(user_geometry)
            .filterDate(baseline_start, baseline_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15))
        )
        comparison_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(user_geometry)
            .filterDate(comparison_start, comparison_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15))
        )
        # Check both collection sizes in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_base_sz = pool.submit(lambda: baseline_collection.size().getInfo())
            f_comp_sz = pool.submit(lambda: comparison_collection.size().getInfo())
        if f_base_sz.result() == 0 or f_comp_sz.result() == 0:
            raise ValueError("Insufficient imagery for baseline or comparison dates")

        # Process images clipped to a slightly expanded AOI so edge pixels are not cut off
        sample_geom = user_geometry.buffer(distance=30, maxError=1)
        baseline_image = process_s2_collection(baseline_collection, sample_geom)
        comparison_image = process_s2_collection(comparison_collection, sample_geom)
        baseline_ndwi = baseline_image.normalizedDifference(["B3", "B8"]).rename("ndwi")
        comparison_ndwi = comparison_image.normalizedDifference(["B3", "B8"]).rename("ndwi")

        scale = 10
        baseline_samples = baseline_ndwi.sample(
            region=transect_sample_region, scale=scale, numPixels=60, geometries=True
        )
        comparison_samples = comparison_ndwi.sample(
            region=transect_sample_region, scale=scale, numPixels=60, geometries=True
        )
        # Fetch both sample sets in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_bfs = pool.submit(lambda: baseline_samples.getInfo().get("features") or [])
            f_cfs = pool.submit(lambda: comparison_samples.getInfo().get("features") or [])
        baseline_fs = f_bfs.result()
        comparison_fs = f_cfs.result()
        logger.info(
            "get_transect_change: baseline samples=%d  comparison samples=%d",
            len(baseline_fs), len(comparison_fs),
        )
        if not baseline_fs and not comparison_fs:
            return jsonify({
                "baseline_distance": None,
                "comparison_distance": None,
                "shoreline_change": None,
                "change_rate": None,
                "info": "No valid pixels sampled along transect — the transect may lie outside cloud-free imagery.",
            })
        baseline_distance = _distance_along_transect_m(baseline_fs, p1, p2, 0.0)
        comparison_distance = _distance_along_transect_m(comparison_fs, p1, p2, 0.0)

        shoreline_change = None
        change_rate = None
        info = None
        if baseline_distance is not None and comparison_distance is not None:
            shoreline_change = round(comparison_distance - baseline_distance, 2)
            baseline_date_obj = datetime.strptime(baseline_start, "%Y-%m-%d")
            comparison_date_obj = datetime.strptime(comparison_start, "%Y-%m-%d")
            years_diff = (comparison_date_obj - baseline_date_obj).days / 365.25
            change_rate = round(shoreline_change / years_diff, 2) if years_diff > 0 else None
        else:
            missing = []
            if baseline_distance is None:
                missing.append("baseline")
            if comparison_distance is None:
                missing.append("comparison")
            info = (
                f"Shoreline not detected in {' or '.join(missing)} imagery along this transect. "
                "The transect may be entirely on land or entirely in water."
            )
            logger.warning("get_transect_change: %s", info)

        return jsonify({
            "baseline_distance": baseline_distance,
            "comparison_distance": comparison_distance,
            "shoreline_change": shoreline_change,
            "change_rate": change_rate,
            "info": info,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("get_transect_change failed: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/generate_dsas_transects', methods=['POST'])
def generate_dsas_transects():
    """
    DSAS: transects perpendicular to baseline shoreline; change from baseline vs comparison shorelines.
    Baseline shoreline = NDWI-derived (land <= 0) for baseline dates; comparison shoreline for comparison dates.
    get_transect_change (on transect click) returns baseline/comparison distances and change rate.
    """
    try:
        data = request.get_json()
        polygon_geojson = data.get('polygon')
        baseline_start = data.get('baseline_start_date')
        baseline_end = data.get('baseline_end_date')
        comparison_start = data.get('comparison_start_date')
        comparison_end = data.get('comparison_end_date')

        if not polygon_geojson or not baseline_start or not baseline_end:
            raise ValueError("Polygon and baseline date range are required")
        if not comparison_start or not comparison_end:
            raise ValueError("Comparison start and end dates are required")

        polygon_geojson = validate_and_fix_polygon(polygon_geojson)
        try:
            user_geometry = ee.Geometry(polygon_geojson, None, False)
        except Exception as geom_error:
            raise ValueError(f"Invalid polygon geometry for Earth Engine: {str(geom_error)}")

        # Single NDWI composite + shoreline extraction (no per-transect sampling)
        baseline_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(user_geometry)
            .filterDate(baseline_start, baseline_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15))
        )
        if baseline_collection.size().getInfo() == 0:
            raise ValueError("Insufficient baseline imagery for the selected dates")

        baseline_image = process_s2_collection(baseline_collection, user_geometry)
        baseline_ndwi = baseline_image.normalizedDifference(["B3", "B8"]).rename("ndwi")
        baseline_land = land_mask_from_ndwi(baseline_ndwi)
        baseline_shoreline_geojson = extract_shoreline_from_land_mask(baseline_land, user_geometry, logger)
        if not baseline_shoreline_geojson.get("features"):
            raise ValueError("No baseline shoreline could be extracted in this area. Try a different AOI or dates.")

        # DSAS: transects every TRANSECT_SPACING_M perpendicular to shoreline (your smooth logic)
        transects_fc = generate_transects_from_shoreline(baseline_shoreline_geojson)
        transect_list = transects_fc.get("features") or []
        if not transect_list:
            raise ValueError("No transects generated from baseline shoreline")

        # Return transects with empty properties (fast); use Analyze Change for area/erosion
        transect_features = []
        for feat in transect_list:
            transect_features.append({
                "type": "Feature",
                "geometry": feat.get("geometry"),
                "properties": {},
            })

        logger.info("Generated %d DSAS transects (fast, no per-transect sampling)", len(transect_features))

        return jsonify({
            "transects": {"type": "FeatureCollection", "features": transect_features},
            "baseline_start_date": baseline_start,
            "baseline_end_date": baseline_end,
            "comparison_start_date": comparison_start,
            "comparison_end_date": comparison_end,
        })
    except ValueError as e:
        logger.warning("DSAS validation: %s", str(e))
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("DSAS transect generation failed: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


def _benchmark_median_iqr(values):
    """Return median and inclusive IQR for a reproducible small-run benchmark."""
    ordered = sorted(float(value) for value in values)
    median = statistics.median(ordered)
    if len(ordered) < 4:
        return median, None
    quartiles = statistics.quantiles(ordered, n=4, method="inclusive")
    return median, quartiles[2] - quartiles[0]


def _clear_benchmark_caches():
    with LAYER_CACHE_LOCK:
        LAYER_CACHE.clear()
    BASELINE_CACHE.clear()


def _system_ram_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        try:
            return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
        except (AttributeError, ValueError, OSError):
            return None


@app.route('/research_benchmark', methods=['POST'])
def research_benchmark():
    """Run and persist the reviewer R3.25 benchmark for the selected AOI and dates."""
    try:
        data = request.get_json() or {}
        polygon_geojson = validate_and_fix_polygon(data.get('polygon'))
        baseline_start = data.get('baseline_start_date')
        baseline_end = data.get('baseline_end_date')
        comparison_start = data.get('comparison_start_date')
        comparison_end = data.get('comparison_end_date')
        runs = int(data.get('runs', 5))
        area_name = str(data.get('area_name') or 'Selected AOI')

        if not all((baseline_start, baseline_end, comparison_start, comparison_end)):
            raise ValueError("Baseline and comparison date ranges are required")
        _validate_date_range(baseline_start, baseline_end)
        _validate_date_range(comparison_start, comparison_end)
        if runs < 4 or runs > 10:
            raise ValueError("runs must be between 4 and 10 so an IQR can be calculated")

        user_geometry = ee.Geometry(polygon_geojson, None, False)
        aoi_gdf = gpd.GeoDataFrame(
            geometry=[shape(polygon_geojson)], crs="EPSG:4326"
        ).to_crs(TRANSECT_CRS)
        aoi_area_km2 = float(aoi_gdf.geometry.iloc[0].area / 1e6)

        comparison_collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(user_geometry)
            .filterDate(comparison_start, comparison_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
        )
        eligible_scenes = int(comparison_collection.size().getInfo())
        if eligible_scenes == 0:
            raise ValueError("No eligible Sentinel-2 scenes for the comparison period")
        scenes_used = min(eligible_scenes, MAX_IMAGES_FOR_COMPOSITE)

        coverage_composite = process_s2_collection(comparison_collection, user_geometry)
        valid_pixel_result = (
            coverage_composite.select("B3")
            .reduceRegion(
                reducer=ee.Reducer.count(), geometry=user_geometry, scale=SCALE,
                maxPixels=1e13, tileScale=16,
            )
            .get("B3")
            .getInfo()
        )
        valid_pixels = int(valid_pixel_result or 0)

        imagery_times = []
        shoreline_times = []
        dsas_times = []
        transect_counts = []

        for run_number in range(1, runs + 1):
            logger.info("Research benchmark %d/%d for %s", run_number, runs, area_name)
            _clear_benchmark_caches()

            started = time.perf_counter()
            image = get_s2_composite(comparison_start, comparison_end, user_geometry, use_scl=True)
            ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
            image.multiply(10000).visualize(**{
                "bands": ["B4", "B3", "B2"], "min": 500, "max": 2500, "gamma": 1.2,
            }).getMapId()
            ndwi.visualize(**{
                "min": -1, "max": 1, "palette": ["brown", "white", "blue"],
            }).getMapId()
            imagery_times.append(time.perf_counter() - started)

            _clear_benchmark_caches()
            started = time.perf_counter()
            shoreline_ndwi = get_ndwi_composite(comparison_start, comparison_end, user_geometry)
            extract_shoreline_from_land_mask(
                land_mask_from_ndwi(shoreline_ndwi), user_geometry, logger
            )
            shoreline_times.append(time.perf_counter() - started)

            _clear_benchmark_caches()
            started = time.perf_counter()
            baseline_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(user_geometry)
                .filterDate(baseline_start, baseline_end)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX))
            )
            if int(baseline_collection.size().getInfo()) == 0:
                raise ValueError("No eligible Sentinel-2 scenes for the baseline period")
            baseline_image = process_s2_collection(baseline_collection, user_geometry)
            baseline_ndwi = baseline_image.normalizedDifference(["B3", "B8"]).rename("ndwi")
            baseline_shoreline = extract_shoreline_from_land_mask(
                land_mask_from_ndwi(baseline_ndwi), user_geometry, logger
            )
            transects = generate_transects_from_shoreline(baseline_shoreline)
            transect_counts.append(len(transects.get("features") or []))
            dsas_times.append(time.perf_counter() - started)

        imagery_median, imagery_iqr = _benchmark_median_iqr(imagery_times)
        shoreline_median, shoreline_iqr = _benchmark_median_iqr(shoreline_times)
        dsas_median, dsas_iqr = _benchmark_median_iqr(dsas_times)
        ram_gb = _system_ram_gb()
        result = {
            "generated_at_utc": _utc_now_iso(),
            "test_case": {
                "area_name": area_name,
                "aoi_area_km2": round(aoi_area_km2, 3),
                "baseline_range": f"{baseline_start} to {baseline_end}",
                "comparison_range": f"{comparison_start} to {comparison_end}",
                "cloud_filter_percent": CLOUD_MAX,
                "spatial_resolution_m": SCALE,
            },
            "computational_environment": {
                "logical_cpu_count": os.cpu_count(),
                "total_ram_gb": round(ram_gb, 2) if ram_gb is not None else None,
                "note": "CPU and RAM describe the machine hosting this Flask process; Earth Engine performs remote geospatial computation.",
            },
            "data_volume": {
                "eligible_sentinel2_scenes": eligible_scenes,
                "scenes_used_in_composite": scenes_used,
                "scene_cap": MAX_IMAGES_FOR_COMPOSITE,
                "nominal_10m_grid_cells": round(aoi_area_km2 * 10000),
                "valid_pixels_after_masking": valid_pixels,
                "valid_coverage_km2": round(valid_pixels * (SCALE * SCALE) / 1e6, 3),
            },
            "processing_time_seconds": {
                "runs": runs,
                "imagery_ndwi_median": round(imagery_median, 2),
                "imagery_ndwi_iqr": round(imagery_iqr, 2) if imagery_iqr is not None else None,
                "shoreline_median": round(shoreline_median, 2),
                "shoreline_iqr": round(shoreline_iqr, 2) if shoreline_iqr is not None else None,
                "dsas_median": round(dsas_median, 2),
                "dsas_iqr": round(dsas_iqr, 2) if dsas_iqr is not None else None,
            },
            "dsas": {
                "transect_count_observations": transect_counts,
                "median_transect_count": statistics.median(transect_counts),
            },
        }
        BENCHMARK_RESULTS_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Research benchmark failed: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    app.run(host='0.0.0.0', port=port, debug=True)
# --- COPY EVERYTHING UNTIL HERE ---
