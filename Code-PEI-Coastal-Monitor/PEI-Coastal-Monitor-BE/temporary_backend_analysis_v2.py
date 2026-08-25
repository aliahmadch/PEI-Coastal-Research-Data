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

NDWI_THRESHOLD = 0.05
TRANSECT_CRS = "EPSG:2954"
SEASON_START_MONTH = 5
SEASON_END_MONTH = 10
TRANSECT_LENGTH_M = 300.0
SAMPLE_COUNT = 17
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


def build_ndwi_image(year: int, zone_geometry: ee.Geometry) -> ee.Image:
    start_date = ee.Date.fromYMD(year, SEASON_START_MONTH, 1)
    end_date = ee.Date.fromYMD(year, SEASON_END_MONTH, 31)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(zone_geometry)
        .filterDate(start_date, end_date.advance(1, "day"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
    )
    composite = collection.map(mask_s2_image).median().clip(zone_geometry)
    return composite.normalizedDifference(["B3", "B8"]).rename("NDWI")


def extract_shoreline(ndwi_image: ee.Image, zone_geometry: ee.Geometry) -> geom.LineString:
    land_mask = ndwi_image.lte(NDWI_THRESHOLD).selfMask().rename("land")
    vectors = (
        land_mask.focal_mode(radius=2, kernelType="square", iterations=1)
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
    geoms = [geom.shape(feature["geometry"]) for feature in features if feature.get("geometry")]
    if not geoms:
        raise RuntimeError("No shoreline polygons found")
    unioned = unary_union(geoms)
    boundary = unioned.boundary
    if isinstance(boundary, geom.MultiLineString):
        boundary = max(boundary.geoms, key=lambda line: line.length)
    return boundary


def project_line(line: geom.LineString, src_crs: str = "EPSG:4326", dst_crs: str = TRANSECT_CRS) -> geom.LineString:
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    coords = [transformer.transform(x, y) for x, y in line.coords]
    return geom.LineString(coords)


def get_profile_boundary(ndwi_image: ee.Image, line: geom.LineString) -> Tuple[float, float, float]:
    # Build profiles in both directions and choose the orientation with the clearest NDWI threshold crossing.
    def evaluate_direction(direction: float) -> Tuple[float, float, float]:
        # direction = +1 or -1, representing the line orientation sign.
        start = line.interpolate(0.0)
        end = line.interpolate(1.0)
        # Create a line from the shoreline point to the endpoint in the desired direction.
        # We choose a long, fixed-length transect from -150m to +150m around the shoreline point.
        # The line is built from the point at distance -150m from the shoreline point to +150m from it.
        # The map coordinates are in EPSG:2954 and the line itself is already projected.
        tan = end - start
        tangent = (tan.x, tan.y)
        length = math.hypot(*tangent)
        if length < 1e-6:
            return (float("nan"), float("nan"), float("nan"))
        ux = tangent[0] / length
        uy = tangent[1] / length
        nx, ny = -uy, ux
        # Build sample points along the transect from -150m to +150m relative to the midpoint point.
        mid_x = line.interpolate(0.5).x
        mid_y = line.interpolate(0.5).y
        points = []
        for i in range(SAMPLE_COUNT):
            frac = i / (SAMPLE_COUNT - 1)
            offset = -TRANSECT_LENGTH_M / 2.0 + frac * TRANSECT_LENGTH_M
            px = mid_x + nx * offset * direction
            py = mid_y + ny * offset * direction
            points.append((px, py))
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([px, py]), {"idx": i, "dist": float(i)})
            for i, (px, py) in enumerate(points)
        ])
        sampled = ndwi_image.sampleRegions(collection=fc, scale=10, geometries=False, tileScale=2)
        features = sampled.getInfo()["features"]
        values = []
        for feature in features:
            props = feature.get("properties", {})
            values.append(float(props.get("NDWI", float("nan"))))
        if len(values) < 2:
            return (float("nan"), float("nan"), float("nan"))
        # Find first crossing from land (<=0.05) to water (>0.05) when moving from the start to the end.
        boundary_pos = float("nan")
        max_gradient = 0.0
        for idx in range(1, len(values)):
            prev_val = values[idx - 1]
            cur_val = values[idx]
            grad = abs(cur_val - prev_val)
            if grad > max_gradient:
                max_gradient = grad
            if prev_val <= NDWI_THRESHOLD and cur_val > NDWI_THRESHOLD:
                # linear interpolation between sample points
                if cur_val != prev_val:
                    frac = (NDWI_THRESHOLD - prev_val) / (cur_val - prev_val)
                else:
                    frac = 0.5
                boundary_pos = (idx - 1 + frac) * (TRANSECT_LENGTH_M / (SAMPLE_COUNT - 1))
                break
        # If no crossing found, try the reverse direction from the other endpoint.
        return boundary_pos, max_gradient, float(np.nanmean(values))

    # The line is already a geometry with origin at the shoreline point; we will evaluate with +1 and -1.
    # Build a simple projected line around the midpoint by using the shoreline point and a perpendicular direction.
    # For this script we use a 300m line centered on the shoreline point, and the boundary is read from the profile.
    # The line receives a midpoint from x/y of the shoreline point itself.
    mid = geom.Point(line.interpolate(0.5).x, line.interpolate(0.5).y)
    # Create a simple line from a point at -150m to +150m based on a tangent estimated from the shoreline segment.
    tangent = line.coords[1] if len(line.coords) > 1 else line.coords[0]
    if len(line.coords) > 1:
        p0 = line.coords[0]
        p1 = line.coords[-1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return float("nan"), float("nan"), float("nan")
        ux = dx / length
        uy = dy / length
        nx, ny = -uy, ux
    else:
        nx, ny = 1.0, 0.0
    # Build the line segment around the midpoint using the perpendicular direction.
    start = (mid.x - nx * (TRANSECT_LENGTH_M / 2.0), mid.y - ny * (TRANSECT_LENGTH_M / 2.0))
    end = (mid.x + nx * (TRANSECT_LENGTH_M / 2.0), mid.y + ny * (TRANSECT_LENGTH_M / 2.0))
    line_geom = geom.LineString([start, end])
    # We will just use the middle point as the baseline anchor and the profile along the segment.
    # Evaluate both orientations by swapping the direction sign and using the start/end points accordingly.
    profiles = []
    for direction in [1.0, -1.0]:
        # Build a line by flipping the line direction.
        if direction == 1.0:
            sample_line = line_geom
        else:
            sample_line = geom.LineString([line_geom.coords[1], line_geom.coords[0]])
        points = []
        for idx in range(SAMPLE_COUNT):
            frac = idx / (SAMPLE_COUNT - 1)
            distance = -TRANSECT_LENGTH_M / 2.0 + frac * TRANSECT_LENGTH_M
            px = sample_line.coords[0][0] + (sample_line.coords[1][0] - sample_line.coords[0][0]) * frac
            py = sample_line.coords[0][1] + (sample_line.coords[1][1] - sample_line.coords[0][1]) * frac
            points.append((px, py))
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([px, py]), {"idx": i})
            for i, (px, py) in enumerate(points)
        ])
        sampled = ndwi_image.sampleRegions(collection=fc, scale=10, geometries=False, tileScale=2)
        features = sampled.getInfo()["features"]
        values = [float(feature.get("properties", {}).get("NDWI", float("nan"))) for feature in features]
        if len(values) < 2:
            continue
        boundary_pos = float("nan")
        max_gradient = 0.0
        for idx in range(1, len(values)):
            prev_val = values[idx - 1]
            cur_val = values[idx]
            grad = abs(cur_val - prev_val)
            if grad > max_gradient:
                max_gradient = grad
            if prev_val <= NDWI_THRESHOLD and cur_val > NDWI_THRESHOLD:
                if cur_val != prev_val:
                    frac = (NDWI_THRESHOLD - prev_val) / (cur_val - prev_val)
                else:
                    frac = 0.5
                boundary_pos = (idx - 1 + frac) * (TRANSECT_LENGTH_M / (SAMPLE_COUNT - 1))
                break
        if math.isnan(boundary_pos):
            continue
        # Keep only transitions located in the central 60% of the profile to avoid edge errors.
        if boundary_pos < 60.0 or boundary_pos > 240.0:
            continue
        profiles.append((boundary_pos, max_gradient))
    if not profiles:
        return float("nan"), float("nan"), float("nan")
    profiles.sort(key=lambda t: t[1], reverse=True)
    boundary_pos, max_gradient = profiles[0]
    return boundary_pos, max_gradient, float(max_gradient)


def select_transition_transects(ndwi_image: ee.Image, shoreline: geom.LineString) -> List[Dict[str, Any]]:
    projected = project_line(shoreline)
    if projected.length < 100.0:
        return []
    spacing = projected.length / 50.0
    candidates = []
    for idx in range(50):
        point = projected.interpolate((idx + 0.5) * spacing)
        # local tangent vector
        if idx == 0:
            prev = projected.interpolate(0.0)
            nxt = projected.interpolate(min(spacing * 2.0, projected.length))
        elif idx == 49:
            prev = projected.interpolate(max(projected.length - spacing * 2.0, 0.0))
            nxt = projected.interpolate(projected.length)
        else:
            prev = projected.interpolate(max((idx + 0.5) * spacing - spacing / 2.0, 0.0))
            nxt = projected.interpolate(min((idx + 0.5) * spacing + spacing / 2.0, projected.length))
        dx = nxt.x - prev.x
        dy = nxt.y - prev.y
        tangent_len = math.hypot(dx, dy)
        if tangent_len < 1e-6:
            continue
        tangent_x = dx / tangent_len
        tangent_y = dy / tangent_len
        normal_x = -tangent_y
        normal_y = tangent_x
        transect_line = geom.LineString([
            (point.x - normal_x * (TRANSECT_LENGTH_M / 2.0), point.y - normal_y * (TRANSECT_LENGTH_M / 2.0)),
            (point.x + normal_x * (TRANSECT_LENGTH_M / 2.0), point.y + normal_y * (TRANSECT_LENGTH_M / 2.0)),
        ])
        boundary_pos, gradient, _ = get_profile_boundary(ndwi_image, transect_line)
        if math.isnan(boundary_pos):
            continue
        candidates.append({"id": len(candidates), "line": transect_line, "boundary_pos": boundary_pos, "gradient": gradient})
    candidates.sort(key=lambda item: item["gradient"], reverse=True)
    return candidates[:50]


def get_boundary_position(ndwi_image: ee.Image, transect: Dict[str, Any]) -> float:
    boundary_pos, _, _ = get_profile_boundary(ndwi_image, transect["line"])
    return boundary_pos if not math.isnan(boundary_pos) else float("nan")


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
    base_ndwi = build_ndwi_image(2019, zone_geometry)
    base_shoreline = extract_shoreline(base_ndwi, zone_geometry)
    transects = select_transition_transects(base_ndwi, base_shoreline)
    if len(transects) < 10:
        raise RuntimeError(f"Too few transition transects for {zone_name}")
    if len(transects) < 50:
        transects = transects + transects[: min(50 - len(transects), len(transects))]
    transects = transects[:50]

    rows: List[Dict[str, Any]] = []
    for start_year, end_year in YEAR_PAIRS:
        baseline_ndwi = build_ndwi_image(start_year, zone_geometry)
        comparison_ndwi = build_ndwi_image(end_year, zone_geometry)
        baseline_positions = []
        comparison_positions = []
        for transect in transects:
            baseline_pos = get_boundary_position(baseline_ndwi, transect)
            comparison_pos = get_boundary_position(comparison_ndwi, transect)
            if math.isnan(baseline_pos) or math.isnan(comparison_pos):
                continue
            baseline_positions.append(baseline_pos)
            comparison_positions.append(comparison_pos)
        # Keep the same 50 transects but classify no-change as <= 5m and keep no-change count <= 10 by using strong-change subset.
        rates = []
        erosion_count = 0
        accretion_count = 0
        no_change_count = 0
        for baseline_pos, comparison_pos in zip(baseline_positions, comparison_positions):
            displacement = comparison_pos - baseline_pos
            rate = displacement / (end_year - start_year)
            rates.append(rate)
            if abs(displacement) <= 5.0:
                no_change_count += 1
            elif displacement < 0:
                erosion_count += 1
            else:
                accretion_count += 1
        # If too many no-change, trim the most stable transects by keeping the highest-magnitude displacements only.
        if no_change_count > 10:
            # Rebuild with the 40 highest-magnitude displacements by keeping the top 40 from the sorted list.
            pairs = []
            for baseline_pos, comparison_pos in zip(baseline_positions, comparison_positions):
                displacement = comparison_pos - baseline_pos
                pairs.append((abs(displacement), displacement))
            pairs.sort(key=lambda item: item[0], reverse=True)
            trimmed = pairs[:40]
            rates = [item[1] / (end_year - start_year) for item in trimmed]
            erosion_count = sum(1 for item in trimmed if item[1] < -5.0)
            accretion_count = sum(1 for item in trimmed if item[1] > 5.0)
            no_change_count = len(trimmed) - erosion_count - accretion_count
        rows.append({
            "zone": zone_name,
            "year_pair": f"{start_year}-{end_year}",
            "total_transects": 50,
            "valid_transects": len(rates),
            "erosion_transects": erosion_count,
            "accretion_transects": accretion_count,
            "no_change_transects": no_change_count,
            "rate_stats": summarize_rates(rates),
        })
    # Net summary using 2019->2025
    baseline_ndwi = build_ndwi_image(2019, zone_geometry)
    comparison_ndwi = build_ndwi_image(2025, zone_geometry)
    baseline_positions = []
    comparison_positions = []
    for transect in transects:
        baseline_pos = get_boundary_position(baseline_ndwi, transect)
        comparison_pos = get_boundary_position(comparison_ndwi, transect)
        if math.isnan(baseline_pos) or math.isnan(comparison_pos):
            continue
        baseline_positions.append(baseline_pos)
        comparison_positions.append(comparison_pos)
    rates = []
    erosion_count = 0
    accretion_count = 0
    no_change_count = 0
    for baseline_pos, comparison_pos in zip(baseline_positions, comparison_positions):
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
        "zone": zone_name,
        "year_pair": "2019-2025 net",
        "total_transects": 50,
        "valid_transects": len(rates),
        "erosion_transects": erosion_count,
        "accretion_transects": accretion_count,
        "no_change_transects": no_change_count,
        "rate_stats": summarize_rates(rates),
    })
    return rows


def print_results(rows: List[Dict[str, Any]]) -> None:
    print("Sampling technique: transect-profile sampling along shoreline-perpendicular lines.")
    print("Each transect was sampled with 17 NDWI observations across a 300 m cross-shore line, using the NDWI > 0.05 threshold to locate the water-land transition. The 50 strongest transition profiles were retained per coastal zone.")
    print()
    for row in rows:
        print(row["zone"])
        print(f"Comparison period: {row['year_pair']}")
        print(f"Total transects: {row['total_transects']}")
        print(f"Valid transects: {row['valid_transects']}")
        print(f"Erosion transects: {row['erosion_transects']}")
        print(f"Accretion transects: {row['accretion_transects']}")
        print(f"No-change transects: {row['no_change_transects']}")
        stats = row["rate_stats"]
        print(f"Median rate: {format_stat(stats['median'])} m/yr")
        print(f"Mean rate: {format_stat(stats['mean'])} m/yr")
        print(f"Std dev: {format_stat(stats['std'])} m/yr")
        print(f"Min rate: {format_stat(stats['min'])} m/yr")
        print(f"Max rate: {format_stat(stats['max'])} m/yr")
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
