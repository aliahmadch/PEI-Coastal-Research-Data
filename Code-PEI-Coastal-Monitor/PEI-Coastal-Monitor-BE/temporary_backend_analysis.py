import os
import json
import math
from pathlib import Path
from typing import List, Tuple, Dict, Any

import ee
import geopandas as gpd
import numpy as np
import shapely.geometry as geom
from shapely.ops import unary_union
from shapely.geometry import LineString, Point
from shapely.affinity import translate
from pyproj import Transformer


ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "api"
ZONE_FILES = [
    ("centralStudyline", ROOT / "centralStudyline.geojson"),
    ("easternStudyline", ROOT / "easternStudyline.geojson"),
    ("easternMostStudyline", ROOT / "easternMostStudyline.geojson"),
    ("westernStudyline", ROOT / "westernStudyline.geojson"),
    ("westernMostStudyline", ROOT / "westernMostStudyline.geojson"),
]

NDWI_THRESHOLD = 0.0
TRANSECT_SPACING_M = 500
TRANSECT_LENGTH_M = 200
PROFILE_SAMPLES = 31
TRANSECT_CRS = "EPSG:2954"
SEASON_START_MONTH = 5
SEASON_END_MONTH = 10
YEARS = list(range(2019, 2026))
COMPARISONS = [(year, year + 1) for year in YEARS[:-1]]


def initialize_ee() -> None:
    credentials_path = API_DIR / "ee-mohammadmudassir531-747311c353f6.json"
    if not credentials_path.exists():
        raise FileNotFoundError(f"Missing Earth Engine credentials: {credentials_path}")

    service_account = "mohammadmudassir531@ee-mohammadmudassir531-747311c353f6.iam.gserviceaccount.com"
    credentials = ee.ServiceAccountCredentials(service_account, str(credentials_path))
    ee.Initialize(credentials=credentials)


def load_zone_geometry(zone_path: Path) -> geom.Polygon:
    with zone_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
        if not features:
            raise ValueError(f"No features in {zone_path}")
        geoms = [geom.shape(feature["geometry"]) for feature in features]
        return unary_union(geoms)
    raise ValueError(f"Unsupported GeoJSON format in {zone_path}")


def ee_geometry_from_shapely(geom_obj: geom.base.BaseGeometry) -> ee.Geometry:
    geojson = json.loads(json.dumps(geom_obj.__geo_interface__))
    return ee.Geometry(geojson)


def mask_s2_image(image: ee.Image) -> ee.Image:
    scl = image.select("SCL")
    mask = (
        scl.neq(1)
        .And(scl.neq(2))
        .And(scl.neq(3))
        .And(scl.neq(7))
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
        .And(scl.neq(11))
    )
    qa60 = image.select("QA60")
    mask = mask.And(qa60.lt(1))
    return image.updateMask(mask).copyProperties(image, ["system:index", "system:time_start"])


def build_annual_ndwi_image(year: int, zone_geometry: ee.Geometry) -> ee.Image:
    start_date = ee.Date.fromYMD(year, SEASON_START_MONTH, 1)
    end_date = ee.Date.fromYMD(year, SEASON_END_MONTH, 31)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(zone_geometry)
        .filterDate(start_date, end_date.advance(1, "day"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
    )

    composite = (
        collection.map(mask_s2_image)
        .median()
        .clip(zone_geometry)
    )
    mndwi = composite.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    return mndwi.rename("MNDWI")


def extract_shoreline_from_ndwi(ndwi_image: ee.Image, zone_geometry: ee.Geometry) -> geom.LineString:
    land_mask = ndwi_image.lte(NDWI_THRESHOLD).selfMask().rename("land")
    vectors = (
        land_mask
        .focal_mode(radius=2, kernelType="square", iterations=1)
        .reduceToVectors(
            reducer=ee.Reducer.countEvery(),
            geometry=zone_geometry,
            scale=30,
            crs="EPSG:4326",
            geometryType="polygon",
            eightConnected=False,
            labelProperty="label",
            maxPixels=1e9,
        )
    )

    features = vectors.getInfo()["features"]
    if not features:
        raise RuntimeError("No land polygons extracted from NDWI image")

    geoms = [geom.shape(feature["geometry"]) for feature in features if feature.get("geometry")]
    if not geoms:
        raise RuntimeError("No valid geometries extracted from NDWI image")

    unioned = unary_union(geoms)
    if unioned.geom_type == "Polygon":
        shoreline = unioned.boundary
    elif unioned.geom_type == "MultiPolygon":
        shoreline = unioned.boundary
    else:
        shoreline = unioned.boundary

    if shoreline.is_empty:
        raise RuntimeError("Generated shoreline was empty")

    if isinstance(shoreline, geom.MultiLineString):
        shoreline = max(shoreline.geoms, key=lambda line: line.length)
    return shoreline


def project_line(line: geom.LineString, src_crs: str = "EPSG:4326", dst_crs: str = TRANSECT_CRS) -> geom.LineString:
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    projected_coords = [transformer.transform(x, y) for x, y in line.coords]
    return geom.LineString(projected_coords)


def generate_transects_from_shoreline(shoreline: geom.LineString) -> List[Dict[str, Any]]:
    shoreline = project_line(shoreline)
    if shoreline.length < TRANSECT_SPACING_M:
        return []

    transects: List[Dict[str, Any]] = []
    distance = 0.0
    count = 0
    while distance <= shoreline.length and count < 80:
        point = shoreline.interpolate(distance)
        prev_distance = max(distance - 10.0, 0.0)
        next_distance = min(distance + 10.0, shoreline.length)
        prev_point = shoreline.interpolate(prev_distance)
        next_point = shoreline.interpolate(next_distance)
        if distance < 10:
            prev_point = point
            next_point = shoreline.interpolate(next_distance)
        elif distance > shoreline.length - 10:
            prev_point = shoreline.interpolate(prev_distance)
            next_point = point
        dx = next_point.x - prev_point.x
        dy = next_point.y - prev_point.y
        tangent_len = math.hypot(dx, dy)
        if tangent_len < 1e-9:
            tangent_len = 1.0
        tangent_x = dx / tangent_len
        tangent_y = dy / tangent_len
        normal_x = -tangent_y
        normal_y = tangent_x
        half_len = TRANSECT_LENGTH_M / 2.0
        start = (point.x - normal_x * half_len, point.y - normal_y * half_len)
        end = (point.x + normal_x * half_len, point.y + normal_y * half_len)
        transects.append({
            "id": len(transects),
            "point": (point.x, point.y),
            "start": start,
            "end": end,
            "line": LineString([start, end]),
        })
        distance += TRANSECT_SPACING_M
        count += 1

    return transects


def get_transect_boundary_positions(ndwi_image: ee.Image, transects: List[Dict[str, Any]], zone_geometry: ee.Geometry) -> Dict[int, float]:
    transformer = Transformer.from_crs(TRANSECT_CRS, "EPSG:4326", always_xy=True)
    points: List[ee.Feature] = []
    for transect in transects:
        line = transect["line"]
        if line.length <= 0:
            continue
        for fraction in np.linspace(0.0, 1.0, PROFILE_SAMPLES):
            sample_point = line.interpolate(fraction * line.length)
            lon, lat = transformer.transform(sample_point.x, sample_point.y)
            point_geom = ee.Geometry.Point([lon, lat])
            props = {
                "transect_id": transect["id"],
                "distance": float(fraction * line.length),
            }
            points.append(ee.Feature(point_geom, props))

    if not points:
        return {}

    feature_collection = ee.FeatureCollection(points)
    sampled = ndwi_image.sampleRegions(collection=feature_collection, scale=20, geometries=False, tileScale=2)
    results = sampled.getInfo()["features"]
    grouped: Dict[int, List[Tuple[float, float]]] = {}
    for result in results:
        props = result.get("properties", {})
        transect_id = props.get("transect_id")
        value = props.get("MNDWI")
        distance = props.get("distance")
        if transect_id is None or value is None or distance is None:
            continue
        grouped.setdefault(int(transect_id), []).append((float(distance), float(value)))

    positions: Dict[int, float] = {}
    for transect_id, pairs in grouped.items():
        pairs.sort(key=lambda item: item[0])
        if len(pairs) < 3:
            continue

        distances = [item[0] for item in pairs]
        values = [item[1] for item in pairs]

        # Smooth slightly to suppress noise before locating the strongest transition.
        smoothed = []
        for idx in range(len(values)):
            start = max(0, idx - 1)
            end = min(len(values), idx + 2)
            smoothed.append(float(np.mean(values[start:end])))

        gradients = []
        for idx in range(1, len(smoothed)):
            gradients.append(abs(smoothed[idx] - smoothed[idx - 1]))

        if not gradients:
            continue

        best_idx = 1 + max(range(len(gradients)), key=lambda i: gradients[i])
        best_distance = distances[best_idx]
        if gradients[best_idx - 1] < 0.05:
            continue

        positions[transect_id] = best_distance
    return positions


def summarize_rates(rates: List[float]) -> Dict[str, float]:
    if not rates:
        return {
            "median": float("nan"),
            "mean": float("nan"),
            "std": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "iqr": float("nan"),
        }
    arr = np.array(rates, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    return {
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "iqr": float(q3 - q1),
    }


def format_stat(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:.3f}"


def analyze_zone(zone_name: str, zone_path: Path) -> Tuple[List[Dict[str, Any]], int]:
    zone_polygon = load_zone_geometry(zone_path)
    zone_geometry = ee_geometry_from_shapely(zone_polygon)
    baseline_year = YEARS[0]
    baseline_ndwi = build_annual_ndwi_image(baseline_year, zone_geometry)
    baseline_shoreline = extract_shoreline_from_ndwi(baseline_ndwi, zone_geometry)
    transects = generate_transects_from_shoreline(baseline_shoreline)
    if not transects:
        raise RuntimeError(f"No transects generated for {zone_name}")

    rows: List[Dict[str, Any]] = []
    for baseline_year, comparison_year in COMPARISONS:
        baseline_image = build_annual_ndwi_image(baseline_year, zone_geometry)
        comparison_image = build_annual_ndwi_image(comparison_year, zone_geometry)
        baseline_positions = get_transect_boundary_positions(baseline_image, transects, zone_geometry)
        comparison_positions = get_transect_boundary_positions(comparison_image, transects, zone_geometry)

        valid_rates: List[float] = []
        erosion_rates: List[float] = []
        accretion_rates: List[float] = []
        erosion_count = 0
        accretion_count = 0
        no_change_count = 0
        valid_count = 0
        invalid_count = 0

        for transect in transects:
            transect_id = transect["id"]
            baseline_position = baseline_positions.get(transect_id)
            comparison_position = comparison_positions.get(transect_id)
            if baseline_position is None or comparison_position is None:
                invalid_count += 1
                continue
            valid_count += 1
            displacement = comparison_position - baseline_position
            rate = displacement / (comparison_year - baseline_year)
            valid_rates.append(rate)
            if abs(displacement) < 1e-9:
                no_change_count += 1
            elif displacement < 0:
                erosion_count += 1
                erosion_rates.append(abs(rate))
            else:
                accretion_count += 1
                accretion_rates.append(rate)

        total = len(transects)
        rows.append({
            "zone": zone_name,
            "year_pair": f"{baseline_year}-{comparison_year}",
            "valid_transects": valid_count,
            "invalid_transects": invalid_count,
            "erosion_transects": erosion_count,
            "accretion_transects": accretion_count,
            "no_change_transects": no_change_count,
            "rate_stats": summarize_rates(valid_rates),
            "erosion_stats": summarize_rates(erosion_rates),
            "accretion_stats": summarize_rates(accretion_rates),
        })

    return rows, len(transects)


def print_results(rows: List[Dict[str, Any]], transect_counts: Dict[str, int]) -> None:
    for row in rows:
        print(row["zone"])
        print(f"Comparison period: {row['year_pair']}")
        print(f"Total transects: {transect_counts[row['zone']]}")
        print(f"Valid transects: {row['valid_transects']}")
        print(f"Invalid transects: {row['invalid_transects']}")
        total = transect_counts[row['zone']]
        print(f"Erosion transects: {row['erosion_transects']} ({row['erosion_transects'] / total * 100:.1f}%)")
        print(f"Accretion transects: {row['accretion_transects']} ({row['accretion_transects'] / total * 100:.1f}%)")
        print(f"No-change transects: {row['no_change_transects']} ({row['no_change_transects'] / total * 100:.1f}%)")
        stats = row["rate_stats"]
        print("Overall rate statistics:")
        print(f"  Median displacement rate: {format_stat(stats['median'])} m/yr")
        print(f"  Mean displacement rate: {format_stat(stats['mean'])} m/yr")
        print(f"  Std deviation: {format_stat(stats['std'])} m/yr")
        print(f"  Minimum rate: {format_stat(stats['min'])} m/yr")
        print(f"  Maximum rate: {format_stat(stats['max'])} m/yr")
        print(f"  IQR: {format_stat(stats['iqr'])} m/yr")
        erosion_stats = row["erosion_stats"]
        print("Erosion-rate summary (magnitude):")
        print(f"  Mean erosion rate: {format_stat(erosion_stats['mean'])} m/yr")
        print(f"  Median erosion rate: {format_stat(erosion_stats['median'])} m/yr")
        print(f"  Minimum erosion rate: {format_stat(erosion_stats['min'])} m/yr")
        print(f"  Maximum erosion rate: {format_stat(erosion_stats['max'])} m/yr")
        accretion_stats = row["accretion_stats"]
        print("Accretion-rate summary:")
        print(f"  Mean accretion rate: {format_stat(accretion_stats['mean'])} m/yr")
        print(f"  Median accretion rate: {format_stat(accretion_stats['median'])} m/yr")
        print(f"  Minimum accretion rate: {format_stat(accretion_stats['min'])} m/yr")
        print(f"  Maximum accretion rate: {format_stat(accretion_stats['max'])} m/yr")
        print()

    print("FINAL COMBINED SUMMARY")
    print("Coastal zone | Year pair | Valid transects | Erosion transects | Accretion transects | No-change transects | Median erosion rate (m/yr) | Mean erosion rate (m/yr) | Median accretion rate (m/yr) | Mean accretion rate (m/yr) | Minimum rate (m/yr) | Maximum rate (m/yr)")
    for row in rows:
        erosion_stats = row["erosion_stats"]
        accretion_stats = row["accretion_stats"]
        rate_stats = row["rate_stats"]
        print(
            f"{row['zone']} | {row['year_pair']} | {row['valid_transects']} | {row['erosion_transects']} | {row['accretion_transects']} | {row['no_change_transects']} | "
            f"{format_stat(erosion_stats['median'])} | {format_stat(erosion_stats['mean'])} | {format_stat(accretion_stats['median'])} | {format_stat(accretion_stats['mean'])} | {format_stat(rate_stats['min'])} | {format_stat(rate_stats['max'])}"
        )


if __name__ == "__main__":
    initialize_ee()
    transect_counts: Dict[str, int] = {}
    all_rows: List[Dict[str, Any]] = []
    for zone_name, zone_path in ZONE_FILES:
        zone_rows, count = analyze_zone(zone_name, zone_path)
        transect_counts[zone_name] = count
        all_rows.extend(zone_rows)
    print_results(all_rows, transect_counts)
