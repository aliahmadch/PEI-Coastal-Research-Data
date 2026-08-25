import json
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple

import ee
import numpy as np
import shapely.geometry as geom
from pyproj import Transformer
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "api"
ZONE_FILES = [
    ("centralStudyline", ROOT / "centralStudyline.geojson"),
    ("easternStudyline", ROOT / "easternStudyline.geojson"),
    ("easternMostStudyline", ROOT / "easternMostStudyline.geojson"),
    ("westernStudyline", ROOT / "westernStudyline.geojson"),
    ("westernMostStudyline", ROOT / "westernMostStudyline.geojson"),
]

SEASON_START_MONTH = 5
SEASON_END_MONTH = 10
LOCATION_COUNT = 50
WINDOW_LENGTH_M = 1000.0
WINDOW_WIDTH_M = 250.0
WATER_THRESHOLD = 0.05
YEAR_PAIRS = [(2019, 2020), (2020, 2021), (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]


def initialize_ee() -> None:
    credentials_path = API_DIR / "ee-mohammadmudassir531-747311c353f6.json"
    service_account = "mohammadmudassir531@ee-mohammadmudassir531-747311c353f6.iam.gserviceaccount.com"
    credentials = ee.ServiceAccountCredentials(service_account, str(credentials_path))
    ee.Initialize(credentials=credentials)


def load_zone_geometry(zone_path: Path) -> geom.Polygon:
    with zone_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    geoms = [geom.shape(feature["geometry"]) for feature in data.get("features", [])]
    return unary_union(geoms)


def ee_geometry_from_shapely(geometry: geom.base.BaseGeometry) -> ee.Geometry:
    return ee.Geometry(json.loads(json.dumps(geometry.__geo_interface__)))


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


def build_water_image(year: int, zone_geometry: ee.Geometry) -> ee.Image:
    start_date = ee.Date.fromYMD(year, SEASON_START_MONTH, 1)
    end_date = ee.Date.fromYMD(year, SEASON_END_MONTH, 31)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(zone_geometry)
        .filterDate(start_date, end_date.advance(1, "day"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
    )
    composite = collection.map(mask_s2_image).median().clip(zone_geometry)
    mndwi = composite.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    return mndwi.gt(WATER_THRESHOLD).rename("water")


def make_windows(zone_polygon: geom.Polygon) -> List[geom.Polygon]:
    boundary = zone_polygon.boundary
    if hasattr(boundary, "geoms"):
        line = max(boundary.geoms, key=lambda item: item.length)
    else:
        line = boundary
    if line.length < 10:
        return []

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:2954", always_xy=True)
    reverse_transformer = Transformer.from_crs("EPSG:2954", "EPSG:4326", always_xy=True)
    projected_coords = [transformer.transform(x, y) for x, y in line.coords]
    projected_line = geom.LineString(projected_coords)
    if projected_line.length < 10:
        return []
    spacing = projected_line.length / max(LOCATION_COUNT - 1, 1)
    points = [projected_line.interpolate(i * spacing) for i in range(LOCATION_COUNT)]

    windows = []
    for point in points:
        half_length = WINDOW_LENGTH_M / 2.0
        half_width = WINDOW_WIDTH_M / 2.0
        corners = [
            (point.x - half_length, point.y - half_width),
            (point.x + half_length, point.y - half_width),
            (point.x + half_length, point.y + half_width),
            (point.x - half_length, point.y + half_width),
        ]
        projected_polygon = geom.Polygon(corners)
        geo_coords = [reverse_transformer.transform(x, y) for x, y in projected_polygon.exterior.coords]
        windows.append(geom.Polygon(geo_coords))
    return windows


def water_fraction(image: ee.Image, window: geom.Polygon) -> float:
    window_geometry = ee_geometry_from_shapely(window)
    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=window_geometry,
        scale=10,
        maxPixels=1e9,
    ).get("water")
    result = value.getInfo()
    if result is None:
        return float("nan")
    return float(result)


def summarize_rates(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"median": float("nan"), "mean": float("nan"), "std": float("nan"), "min": float("nan"), "max": float("nan")}
    arr = np.array(values, dtype=float)
    return {
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def format_stat(v: float) -> str:
    if math.isnan(v):
        return "n/a"
    return f"{v:.3f}"


def analyze_zone(zone_name: str, zone_path: Path) -> List[Dict[str, Any]]:
    zone_polygon = load_zone_geometry(zone_path)
    zone_geometry = ee_geometry_from_shapely(zone_polygon)
    windows = make_windows(zone_polygon)
    if len(windows) < 10:
        raise RuntimeError(f"Too few windows for {zone_name}")

    rows: List[Dict[str, Any]] = []
    for start_year, end_year in YEAR_PAIRS:
        baseline_image = build_water_image(start_year, zone_geometry)
        comparison_image = build_water_image(end_year, zone_geometry)
        rates: List[float] = []
        erosion_count = 0
        accretion_count = 0
        no_change_count = 0
        for window in windows:
            baseline_value = water_fraction(baseline_image, window)
            comparison_value = water_fraction(comparison_image, window)
            if math.isnan(baseline_value) or math.isnan(comparison_value):
                continue
            change = comparison_value - baseline_value
            rate = change / (end_year - start_year)
            rates.append(rate)
            if abs(change) <= 0.05:
                no_change_count += 1
            elif change < 0:
                erosion_count += 1
            else:
                accretion_count += 1
        rows.append({
            "zone": zone_name,
            "year_pair": f"{start_year}-{end_year}",
            "locations": len(windows),
            "valid_locations": len(rates),
            "erosion_locations": erosion_count,
            "accretion_locations": accretion_count,
            "no_change_locations": no_change_count,
            "rate_stats": summarize_rates(rates),
        })

    baseline_image = build_water_image(2019, zone_geometry)
    comparison_image = build_water_image(2025, zone_geometry)
    rates: List[float] = []
    erosion_count = 0
    accretion_count = 0
    no_change_count = 0
    for window in windows:
        baseline_value = water_fraction(baseline_image, window)
        comparison_value = water_fraction(comparison_image, window)
        if math.isnan(baseline_value) or math.isnan(comparison_value):
            continue
        change = comparison_value - baseline_value
        rate = change / 6.0
        rates.append(rate)
        if abs(change) <= 0.05:
            no_change_count += 1
        elif change < 0:
            erosion_count += 1
        else:
            accretion_count += 1
    rows.append({
        "zone": zone_name,
        "year_pair": "2019-2025 net",
        "locations": len(windows),
        "valid_locations": len(rates),
        "erosion_locations": erosion_count,
        "accretion_locations": accretion_count,
        "no_change_locations": no_change_count,
        "rate_stats": summarize_rates(rates),
    })
    return rows


def print_results(rows: List[Dict[str, Any]]) -> None:
    print("Method: 50 coastal windows sampled along the main shoreline segment; each window uses the share of water pixels from an annual Sentinel-2 MNDWI water mask as a shoreline-change proxy.")
    print()
    for row in rows:
        print(row["zone"])
        print(f"Comparison period: {row['year_pair']}")
        print(f"Locations: {row['locations']}")
        print(f"Valid locations: {row['valid_locations']}")
        print(f"Erosion locations: {row['erosion_locations']}")
        print(f"Accretion locations: {row['accretion_locations']}")
        print(f"No-change locations: {row['no_change_locations']}")
        stats = row["rate_stats"]
        print(f"Median water-change rate: {format_stat(stats['median'])} change units/yr")
        print(f"Mean water-change rate: {format_stat(stats['mean'])} change units/yr")
        print(f"Std dev: {format_stat(stats['std'])} change units/yr")
        print(f"Min rate: {format_stat(stats['min'])} change units/yr")
        print(f"Max rate: {format_stat(stats['max'])} change units/yr")
        print()


if __name__ == "__main__":
    initialize_ee()
    all_rows = []
    for zone_name, zone_path in ZONE_FILES:
        try:
            all_rows.extend(analyze_zone(zone_name, zone_path))
        except Exception as exc:
            print(zone_name, "failed", exc)
    print_results(all_rows)
