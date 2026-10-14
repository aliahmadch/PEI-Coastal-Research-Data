# PEI Coastal Research Data

This repository contains the code, supporting data, figures, tables, supplementary results, validation datasets, and selected UAV/drone imagery associated with the study:

**An Automated Multi-Scale Framework for Land-Water Change and Shoreline Monitoring Using Remote Sensing and GIS**

The repository is intended to support transparency, review, and reproducibility of the analytical workflow reported in the manuscript.

## Repository structure

```text
PEI-Coastal-Research-Data/
├── Code-PEI-Coastal-Monitor/
│   ├── PEI-Coastal-Monitor-BE/
│   └── PEI-Coastal-Monitor-FE/
├── Code-GEE/
├── Data/
├── Figures & Tables/
└── README.md
```

### `Code-PEI-Coastal-Monitor/`
Contains the source code for the PEI Coastal Monitor web application.

- **Backend (BE):** server-side processing and application logic.
- **Frontend (FE):** user interface and visualization components.
- Application parameters and processing logic used by the portal are documented in the source code and associated configuration files.

### `Code-GEE/`
Contains the Google Earth Engine / Python scripts used for the main remote-sensing workflow, including Sentinel-2 processing, NDWI-based analysis, annual results, threshold-sensitivity analysis, interannual agreement assessment, shoreline-position validation, water-level/tidal sensitivity analysis, and related spatial processing.

### `Data/`
Contains author-generated and supporting analytical data used in the study, including:

- tile-based and coastal-zone analytical outputs;
- annual and interannual land-water results;
- annual gross Land→Water, Water→Land, and net transition results;
- threshold-sensitivity outputs for NDWI thresholds of 0.00, 0.05, and 0.10;
- valid-observation summaries after Sentinel-2 SCL masking;
- 2022-2023 interannual classification-agreement data;
- independent UAV-Sentinel-2 shoreline-position validation data;
- paired-scene water-level/tidal sensitivity data;
- representative study-point coordinates in GeoJSON format;
- selected UAV/drone imagery and supporting site-level material where available.

GeoJSON coordinates use longitude-latitude order where applicable.

### `Figures & Tables/`
Contains the final figures, main analytical tables, and supplementary tables used in the manuscript, including threshold-sensitivity results, annual gross/net transition tables, valid-observation summaries, independent UAV-Sentinel-2 validation results, water-level/tidal sensitivity results, transect parameters/intersection rules, and representative UAV-validation/threshold-sensitive shoreline examples.

Final publication figures are supplied as research outputs. Some figure-layout and cosmetic editing steps were completed separately from the core analytical workflow and are therefore not represented as fully scripted figure-reproduction code.

## Main analytical workflow

The study combines:

1. Sentinel-2 Harmonized Surface Reflectance imagery;
2. Google Earth Engine processing;
3. cloud, shadow, snow/ice, cirrus, dark-pixel, saturated-pixel, and invalid-pixel masking using Sentinel-2 SCL classes;
4. annual NDWI compositing;
5. binary land-water classification;
6. tile-based and coastal-zone area analysis;
7. threshold-sensitivity analysis using NDWI thresholds of 0.00, 0.05, and 0.10;
8. annual gross Land→Water, Water→Land, and net transition analysis;
9. interannual classification-agreement assessment;
10. independent UAV-Sentinel-2 shoreline-position validation;
11. paired-scene water-level/tidal sensitivity analysis;
12. custom DSAS-style shoreline-displacement analysis;
13. web-based visualization and reporting.

The primary operational NDWI threshold used in the manuscript is **0.05**, while **0.00** and **0.10** are used as lower and upper sensitivity bounds.

## Validation and uncertainty assessment

### Interannual classification agreement
The 2022-2023 assessment evaluates classification consistency rather than independent ground-reference accuracy. It uses **90 stratified locations per reporting unit** across five reporting units, corresponding to **450 all-context observations** and **200 shoreline-transition observations**. Reported metrics include agreement, confusion counts, precision, recall, F1 score, kappa, and Wilson 95% confidence intervals.

### Independent UAV-Sentinel-2 shoreline-position validation
Independent shoreline-position validation uses **8 same-date UAV-Sentinel-2 comparisons across 4 PEI coastal sites**, with **52 valid transects**. The reference sites are Cape Wolfe, Factory Road, Little Minminegash Pond, and Poppycock Lane.

Positional performance is summarized using valid-transect count, mean absolute error (MAE), median absolute error, root mean square error (RMSE), and 95th-percentile (P95) absolute error.

### Water-level/tidal sensitivity
Water-level/tidal sensitivity is assessed independently of the annual composites using **6 paired Sentinel-2 acquisitions across Charlottetown, Souris, and Wood Islands**, with **60 valid transects** in total. Absolute water-level differences span **0.770-1.473 m**. The analysis reports signed displacement, mean and median absolute displacement, RMSE, and P95 absolute displacement.

This analysis quantifies shoreline-position sensitivity associated with differing water levels and contemporaneous coastal conditions. It is not treated as a complete tide-normalization procedure.

## Threshold and land-water transition analysis

Threshold sensitivity is evaluated at NDWI values of **0.00, 0.05, and 0.10** using a common valid-pixel footprint.

The repository includes annual and cumulative net land-water change, empirical threshold-sensitivity bounds, directional stability across tested thresholds, threshold-sensitive transition areas, and annual gross Land→Water, Water→Land, and net transitions for each reporting unit and threshold.

Net transition is defined as:

**Net = Water→Land − Land→Water**

These results distinguish net balance from opposing gross transitions that may otherwise cancel within a reporting unit.

## DSAS-style shoreline analysis

The portal implements a **custom DSAS-style transect workflow** rather than the official USGS DSAS software.

Key documented parameters include:

- analysis CRS: **EPSG:2954**;
- transect spacing: **500 m**;
- total transect length: **200 m**;
- local perpendicular orientation;
- landward-to-water sampling direction;
- first-water-pixel shoreline-intersection rule;
- signed two-date shoreline displacement;
- simple annualized displacement based on elapsed decimal years.

The workflow is intended for localized screening-level shoreline-displacement analysis. It does not claim formal equivalence with official DSAS statistics such as NSM, EPR, LRR, or uncertainty-weighted rates.

## Spatial and temporal scope

- **Study area:** Prince Edward Island, Canada
- **Study period:** 2019-2025
- **Satellite:** Sentinel-2
- **Primary spatial resolution:** 10 m
- **Seasonal processing window:** May-October
- **Reporting framework:** five broad reporting sectors with complementary coastal-zone analysis

The portal can also accept user-defined date ranges and recently available Sentinel-2 imagery, subject to Earth Engine image availability and processing constraints.

## Portal benchmark

A representative uncached benchmark separates major processing components:

- GEE imagery retrieval / NDWI processing: **median 2.39 s**;
- local shoreline vectorization: **2.99 s**;
- local transect generation: **4.22 s**;
- estimated network/interface latency: **0.5-1.0 s**;
- total user-perceived processing time: approximately **10.1-10.6 s**.

Five uncached benchmark runs completed successfully (**0/5 failures**). Processing demand varies with AOI extent, scene count, shoreline complexity, transect density, raster-to-vector conversion, Earth Engine quotas, and concurrent requests.

The manual comparison of approximately **1-2 h** is an operational estimate for an equivalent manual workflow and is not presented as a controlled time-and-motion experiment.

## Software and dependencies

The repository includes the frontend and backend application source code together with the available dependency/configuration files.

The remote-sensing workflow uses Google Earth Engine and Python-based geospatial processing. Exact software requirements should be taken from the dependency files and source-code imports included within the corresponding code folders.

Users running Google Earth Engine scripts must have access to a valid Google Earth Engine account/project. Authentication credentials are not distributed in this repository.

## Reproducibility notes

The repository provides the core analytical/application code, supporting datasets, numerical outputs, figures, tables, validation data, and supplementary results needed to inspect and reproduce the principal workflow and reported analyses.

The repository does **not** claim that every publication figure can be regenerated automatically from a single command. Some final figure assembly, annotation, and cosmetic editing were completed outside the core analytical scripts. The numerical data underlying the reported analytical figures and tables are provided where available.

The same-date UAV datasets are used as independent high-resolution reference shorelines for quantitative shoreline-position validation. A separate set of selected 2022 and 2024 UAV images is retained only as qualitative post-event context for the Hurricane Fiona discussion. These two uses should not be conflated.

## Data sources

Sentinel-2 imagery is accessed from the original public source through Google Earth Engine and is not redistributed as a complete satellite archive in this repository.

Users should consult the manuscript and the code comments/configuration for the exact processing parameters, masking rules, spatial units, validation procedures, and interpretation limits.

## Interpretation limits

The NDWI products represent spectrally detected land-water states. They should not automatically be interpreted as tide-normalized geomorphic shorelines or direct measurements of permanent erosion and accretion.

Threshold sensitivity is quantified using NDWI values of 0.00, 0.05, and 0.10. Independent UAV validation quantifies shoreline-position performance at selected sites, and paired-scene analysis quantifies water-level/tidal sensitivity at selected locations.

Remaining uncertainty sources include mixed pixels, 10 m spatial resolution, georegistration, seasonal compositing, wet sediment, turbidity, vegetation, wave conditions, shoreline morphology, and other local coastal processes.

The annual May-October composites are not tide-normalized. The water-level/tidal analysis provides an empirical sensitivity assessment and should not be interpreted as a complete hydrodynamic correction.

## Citation

If you use this repository, please cite the associated manuscript and the repository release.

A formal repository citation can be added here after the GitHub release and/or archival DOI is created.

## Licence

Please add the appropriate licence file before public release.

Recommended approach:

- source code: an open-source software licence such as MIT, if approved by the authors;
- author-generated data and figures: a suitable open-data/content licence such as CC BY 4.0, if approved by the authors.

Third-party data remain subject to the licences and terms of their original providers.

## Contact

For questions about the study or repository, please contact the corresponding author listed in the manuscript.
