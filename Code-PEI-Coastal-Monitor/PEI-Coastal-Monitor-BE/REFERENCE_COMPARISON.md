# Reference vs Our Implementation (GEE → Preprocessing → True Colour/NDWI → Shorelines → Erosion → DSAS)

This document compares the **Code Reference** (sections 1–6) with **our project** (`api/app.py` and `pei/src/components/Dashboard.js`).

---

## 1. Loading imagery from GEE

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **GEE init** | Service account + `ee.Initialize(credentials)` | Same | ✅ Same |
| **Geometry helper** | `get_geometry(roi_geojson)` → ROI or PEI_BBOX | **Added** `get_geometry(roi_geojson)` in `app.py` | ✅ Aligned |
| **get_imagery** | Uses `geom = get_geometry(data.get("roi"))`, S2 filter + mask_s2 + median, clip to geom | Now uses `get_geometry(data.get("roi") or data.get("geometry"))` and clips to that AOI | ✅ Aligned |
| **Frontend** | `loadImagery` POST with `roi: getRoiForApi()` | We use `load_baseline_2016` / `load_comparison_imagery` with `polygon` (no standalone `get_imagery` + roi in Dashboard) | ⚠️ Different flow; API now supports `roi`/`geometry` for future use |

---

## 2. Preprocessing (cloud masking)

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **mask_s2** | SCL only: mask out 1,2,3,8,9,10,11 | SCL (0,1,2,3,7,8,9,10,11) **and** QA60 (opaque cloud + cirrus) | ⚠️ Stricter: we also mask 0,7 and use QA60 |
| **Intent** | Same: avoid clouds for NDWI/land | Same | ✅ Same |

---

## 3. True colour and NDWI

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **NDWI** | `normalizedDifference(["B3","B8"]).rename("NDWI")` | Same | ✅ Same |
| **True colour viz** | `min: 500, max: 2500` (unscaled reflectance) | `min: 0.05, max: 0.25` (scaled 1/10000 after composite) | ⚠️ Different numbers, correct for our pipeline (L2A scaled) |
| **NDWI viz** | `min: -1, max: 1`, palette brown/white/blue | Same | ✅ Same |

---

## 4. Shoreline extraction

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **Land mask** | `ndwi.lte(0).rename("land")` | `ndwi.lte(NDWI_LAND_THRESHOLD).rename("land")` with threshold 0 | ✅ Same |
| **Land → polygons** | focal_mode(radius=2), reduceToVectors(scale=30), **dissolve** | `land_polygons_fc_dissolved` (focal radius 3, scale 30, dissolve); `extract_shoreline_from_land_mask` tries dissolved then non-dissolved | ✅ Same idea |
| **Polygons → shoreline** | `polygons_geojson_to_shoreline_lines` (exterior boundaries → LineStrings) | Same function | ✅ Same |
| **get_shoreline_data** | Accepts `roi`, uses `get_geometry(roi)` | Accepts `roi` or `geometry`, uses `get_geometry(roi or geometry)` | ✅ Aligned |
| **Frontend** | Sends `roi: getRoiForApi()`, displays as "Current Shoreline" | Sends `geometry: polygon` in `loadCurrentShoreline`, displays as "Current Shoreline (NDWI)" | ✅ Same idea |

---

## 5. Erosion / change analysis

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **Endpoint** | `analyze_change` POST with start_date, end_date, **roi** | `analyze_change` now accepts **roi** or **geometry** | ✅ Aligned |
| **Baseline area** | `land_area_km2(BASELINE["land_mask"], geom)` for ROI | Now `land_area_km2(baseline_land_mask, geom)` when ROI provided | ✅ Aligned |
| **Erosion** | baseline land ∧ current water, then tiles | Same; erosion image clipped to geom for ROI | ✅ Aligned |
| **Frontend** | `analyzeCoastalChange` with roi in body | We use `analyze_erosion` (polygon + 4 dates) for AOI workflow; `analyze_change` with roi available for reference-style use | ⚠️ Two flows: AOI (analyze_erosion) and reference-style (analyze_change + roi) both supported |

---

## 6. DSAS

| Item | Reference | Our project | Status |
|------|-----------|-------------|--------|
| **Constants** | TRANSECT_SPACING_M=500, TRANSECT_LENGTH_M=200, TRANSECT_CRS=EPSG:2954 | Same | ✅ Same |
| **Transect generation** | `generate_transects_from_shoreline` (pyproj, interpolate, perpendicular) | Same logic in `generate_transects_from_shoreline` | ✅ Same |
| **get_baseline_transects** | Returns BASELINE polygons, shoreline, transects (no params) | Returns same; also supports optional start_date, end_date for user baseline range | ✅ Superset |
| **Frontend DSAS** | `fetchBaselineTransects`: get_shoreline_data(roi) then get_baseline_transects | We use `generate_dsas_transects` POST (polygon + 4 dates) for AOI-based transects | ⚠️ Different: we have AOI-first DSAS; reference uses PEI-wide baseline + optional current shoreline |
| **Transect click** | Min distance to current shoreline + simple rate (2016 → endDate) | We call `get_transect_change` (NDWI sampling along transect, baseline vs comparison distance) | ⚠️ Different: we use server-side NDWI sampling; reference uses client-side distance to shoreline |

---

## Summary

- **Implemented same way:** GEE init, NDWI formula, land = NDWI ≤ 0, shoreline extraction (dissolved polygons → LineStrings), transect constants and generation logic, baseline init with dissolved polygon, and (after changes) **get_geometry**, **get_imagery/get_shoreline_data/analyze_change with roi/geometry**.
- **Different by design:**  
  - **mask_s2**: we use SCL + QA60 and mask more classes (stricter).  
  - **True colour**: we use 0.05/0.25 because we scale by 1/10000 after composite.  
  - **Frontend workflow**: we are AOI-first (select/draw polygon → load baseline → comparison → analyze_erosion / generate_dsas_transects); the reference describes a PEI-wide + optional ROI flow with get_imagery, get_shoreline_data, analyze_change, get_baseline_transects. The **API** now supports the reference style (roi/geometry on get_imagery, get_shoreline_data, analyze_change) so a reference-style frontend can be added without backend changes.

---

## Note on `HAS_PYPROJ` (reference)

The reference mentions `HAS_PYPROJ`. Our code uses `PYPROJ_AVAILABLE` and a try/except on `import pyproj`; behaviour is equivalent.
