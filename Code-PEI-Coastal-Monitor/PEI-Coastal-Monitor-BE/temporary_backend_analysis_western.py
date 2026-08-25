import csv
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
ZONE_PATH = ROOT / "westernStudyline.geojson"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SEASON_START_MONTH = 5
SEASON_END_MONTH = 10
TRANSECT_LENGTH_M = 1500.0
SAMPLE_COUNT = 41
THRESHOLD = 0.0
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


def build_mndwi_image(year: int, zone_geometry: ee.Geometry) -> ee.Image:
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
    return mndwi.rename("MNDWI")


def extract_shoreline(mndwi_image: ee.Image, zone_geometry: ee.Geometry) -> geom.LineString:
    land_mask = mndwi_image.lte(THRESHOLD).selfMask().rename("land")
    vectors = (
        land_mask.focal_mode(radius=2, kernelType="square", iterations=1)
        .reduceToVectors(
            reducer=ee.Reducer.countEvery(),
            geometry=zone_geometry,
            scale=20,
            crs="EPSG:4326",
            geometryType="polygon",
            eightConnected=False,
            labelProperty="label",
            maxPixels=1e9,
        )
    )
    features = vectors.getInfo()["features"]
    geoms = [geom.shape(feature["geometry"]) for feature in features if feature.get("geometry")]
    if not geoms:
        raise RuntimeError("No shoreline polygons found")
    unioned = unary_union(geoms)
    boundary = unioned.boundary
    if isinstance(boundary, geom.MultiLineString):
        boundary = max(boundary.geoms, key=lambda line: line.length)
    return boundary


def project_line(line: geom.LineString, src_crs: str = "EPSG:4326", dst_crs: str = "EPSG:2954") -> geom.LineString:
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    coords = [transformer.transform(x, y) for x, y in line.coords]
    return geom.LineString(coords)


def generate_transects(shoreline: geom.LineString) -> List[Dict[str, Any]]:
    projected = project_line(shoreline)
    if projected.length < 100:
        return []
    spacing = projected.length / 79.0
    transects = []
    for idx in range(80):
        point = projected.interpolate((idx + 0.5) * spacing)
        if idx == 0:
            prev_point = projected.interpolate(0.0)
            next_point = projected.interpolate(min(spacing * 2.0, projected.length))
        elif idx == 79:
            prev_point = projected.interpolate(max(projected.length - spacing * 2.0, 0.0))
            next_point = projected.interpolate(projected.length)
        else:
            prev_point = projected.interpolate(max((idx + 0.5) * spacing - spacing / 2.0, 0.0))
            next_point = projected.interpolate(min((idx + 0.5) * spacing + spacing / 2.0, projected.length))
        dx = next_point.x - prev_point.x
        dy = next_point.y - prev_point.y
        tangent_length = math.hypot(dx, dy)
        if tangent_length < 1e-6:
            continue
        tangent_x = dx / tangent_length
        tangent_y = dy / tangent_length
        normal_x = -tangent_y
        normal_y = tangent_x
        half_len = TRANSECT_LENGTH_M / 2.0
        start = (point.x - normal_x * half_len, point.y - normal_y * half_len)
        end = (point.x + normal_x * half_len, point.y + normal_y * half_len)
        transects.append({"id": len(transects), "line": geom.LineString([start, end])})
    return transects


def get_profile_boundary_position(mndwi_image: ee.Image, transect_line: geom.LineString) -> Tuple[float, float]:
    transformer = Transformer.from_crs("EPSG:2954", "EPSG:4326", always_xy=True)
    if transect_line.length <= 0:
        return float("nan"), float("nan")

    points = []
    for frac in np.linspace(0.0, 1.0, SAMPLE_COUNT):
        sample_point = transect_line.interpolate(frac * transect_line.length)
        lon, lat = transformer.transform(sample_point.x, sample_point.y)
        points.append((lon, lat))

    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([lon, lat]), {"idx": i})
        for i, (lon, lat) in enumerate(points)
    ])
    sampled = mndwi_image.sampleRegions(collection=fc, scale=10, geometries=False, tileScale=2)
    features = sampled.getInfo()["features"]
    if not features:
        return float("nan"), float("nan")

    values = []
    for feature in features:
        props = feature.get("properties", {})
        values.append(float(props.get("MNDWI", float("nan"))))
    if len(values) < 3:
        return float("nan"), float("nan")

    arr = np.array(values, dtype=float)
    smooth = np.convolve(arr, np.array([1, 2, 1], dtype=float), mode="same") / 4.0
    gradients = np.abs(np.diff(smooth))
    if gradients.size == 0:
        return float("nan"), float("nan")
    max_idx = int(np.argmax(gradients)) + 1
    if gradients[max_idx - 1] < 0.05:
        return float("nan"), float("nan")
    step = transect_line.length / (SAMPLE_COUNT - 1)
    boundary_pos = max_idx * step
    return boundary_pos, float(gradients[max_idx - 1])


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


def analyze_western() -> List[Dict[str, Any]]:
    zone_polygon = load_zone_geometry(ZONE_PATH)
    zone_geometry = ee_geometry_from_shapely(zone_polygon)
    base_shoreline = extract_shoreline(build_mndwi_image(2019, zone_geometry), zone_geometry)
    transects = generate_transects(base_shoreline)
    if len(transects) < 60:
        raise RuntimeError(f"Only {len(transects)} transects generated")

    rows = []
    for start_year, end_year in YEAR_PAIRS:
        baseline_image = build_mndwi_image(start_year, zone_geometry)
        comparison_image = build_mndwi_image(end_year, zone_geometry)
        rates = []
        erosion_count = 0
        accretion_count = 0
        no_change_count = 0
        valid_count = 0
        invalid_count = 0
        for transect in transects:
            baseline_pos, _ = get_profile_boundary_position(baseline_image, transect["line"])
            comparison_pos, _ = get_profile_boundary_position(comparison_image, transect["line"])
            if math.isnan(baseline_pos) or math.isnan(comparison_pos):
                invalid_count += 1
                continue
            valid_count += 1
            displacement = comparison_pos - baseline_pos
            rate = displacement / (end_year - start_year)
            rates.append(rate)
            if abs(displacement) <= 5.0:
                no_change_count += 1
            elif displacement < 0:
                erosion_count += 1
            else:
                accretion_count += 1
        rows.append({
            "zone": "westernStudyline",
            "year_pair": f"{start_year}-{end_year}",
            "total_transects": len(transects),
            "valid_transects": valid_count,
            "invalid_transects": invalid_count,
            "erosion_transects": erosion_count,
            "accretion_transects": accretion_count,
            "no_change_transects": no_change_count,
            "rate_stats": summarize_rates(rates),
        })

    # net summary
    baseline_image = build_mndwi_image(2019, zone_geometry)
    comparison_image = build_mndwi_image(2025, zone_geometry)
    rates = []
    erosion_count = 0
    accretion_count = 0
    no_change_count = 0
    valid_count = 0
    invalid_count = 0
    for transect in transects:
        baseline_pos, _ = get_profile_boundary_position(baseline_image, transect["line"])
        comparison_pos, _ = get_profile_boundary_position(comparison_image, transect["line"])
        if math.isnan(baseline_pos) or math.isnan(comparison_pos):
            invalid_count += 1
            continue
        valid_count += 1
        displacement = comparison_pos - baseline_pos
        rate = displacement / 6.0
        rates.append(rate)
        if abs(displacement) <= 5.0:
            no_change_count += 1
        elif displacement < 0:
            erosion_count += 1
        else:
            accretion_count += 1
    rows.append({
        "zone": "westernStudyline",
        "year_pair": "2019-2025 net",
        "total_transects": len(transects),
        "valid_transects": valid_count,
        "invalid_transects": invalid_count,
        "erosion_transects": erosion_count,
        "accretion_transects": accretion_count,
        "no_change_transects": no_change_count,
        "rate_stats": summarize_rates(rates),
    })
    return rows


def write_csv(rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "zone", "year_pair", "total_transects", "valid_transects", "invalid_transects",
        "erosion_transects", "accretion_transects", "no_change_transects",
        "median_rate_m_per_yr", "mean_rate_m_per_yr", "std_rate_m_per_yr", "min_rate_m_per_yr", "max_rate_m_per_yr",
    ]
    csv_path = OUTPUT_DIR / "westernStudyline_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "zone": row["zone"],
                "year_pair": row["year_pair"],
                "total_transects": row["total_transects"],
                "valid_transects": row["valid_transects"],
                "invalid_transects": row["invalid_transects"],
                "erosion_transects": row["erosion_transects"],
                "accretion_transects": row["accretion_transects"],
                "no_change_transects": row["no_change_transects"],
                "median_rate_m_per_yr": row["rate_stats"]["median"],
                "mean_rate_m_per_yr": row["rate_stats"]["mean"],
                "std_rate_m_per_yr": row["rate_stats"]["std"],
                "min_rate_m_per_yr": row["rate_stats"]["min"],
                "max_rate_m_per_yr": row["rate_stats"]["max"],
            })


def write_xlsx(rows: List[Dict[str, Any]]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    headers = [
        "zone", "year_pair", "total_transects", "valid_transects", "invalid_transects",
        "erosion_transects", "accretion_transects", "no_change_transects",
        "median_rate_m_per_yr", "mean_rate_m_per_yr", "std_rate_m_per_yr", "min_rate_m_per_yr", "max_rate_m_per_yr",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([
            row["zone"], row["year_pair"], row["total_transects"], row["valid_transects"], row["invalid_transects"],
            row["erosion_transects"], row["accretion_transects"], row["no_change_transects"],
            row["rate_stats"]["median"], row["rate_stats"]["mean"], row["rate_stats"]["std"], row["rate_stats"]["min"], row["rate_stats"]["max"],
        ])
    wb.save(OUTPUT_DIR / "westernStudyline_results.xlsx")


if __name__ == "__main__":
    initialize_ee()
    rows = analyze_western()
    write_csv(rows)
    write_xlsx(rows)
    print("Western analysis complete")
    for row in rows:
        print(row["year_pair"], "valid", row["valid_transects"], "invalid", row["invalid_transects"], "mean", format_stat(row["rate_stats"]["mean"]))
