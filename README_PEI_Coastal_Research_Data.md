# PEI Coastal Research Data

This repository contains the code, supporting data, figures, tables, supplementary results, and selected UAV/drone imagery associated with the study:

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
Contains the Google Earth Engine / Python scripts used for the main remote-sensing workflow, including Sentinel-2 processing, NDWI-based analysis, annual results, validation/agreement analysis, and related spatial processing.

### `Data/`
Contains author-generated and supporting analytical data used in the study, including:

- tile-based and coastal-zone analytical outputs;
- annual and interannual land-water results;
- validation/agreement-related data;
- representative study-point coordinates in GeoJSON format;
- selected UAV/drone imagery and supporting site-level material where available.

GeoJSON coordinates use longitude-latitude order where applicable.

### `Figures & Tables/`
Contains the final figures, main analytical tables, and supplementary tables used in the revised manuscript, including the threshold-sensitivity results reported in Supplementary Tables S1-S5.

Final publication figures are supplied as research outputs. Some figure-layout and cosmetic editing steps were completed separately from the core analytical workflow and are therefore not represented as fully scripted figure-reproduction code.

## Main analytical workflow

The study combines:

1. Sentinel-2 Harmonized Surface Reflectance imagery;
2. Google Earth Engine processing;
3. cloud, shadow, snow, and invalid-pixel masking;
4. annual NDWI compositing;
5. binary land-water classification;
6. tile-based and coastal-zone area analysis;
7. threshold-sensitivity analysis using NDWI thresholds of 0.00, 0.05, and 0.10;
8. interannual agreement assessment;
9. DSAS-style shoreline-displacement analysis;
10. web-based visualization and reporting.

The primary operational NDWI threshold used in the manuscript is **0.05**, while **0.00** and **0.10** are used as sensitivity bounds.

## Spatial and temporal scope

- **Study area:** Prince Edward Island, Canada
- **Study period:** 2019-2025
- **Satellite:** Sentinel-2
- **Primary spatial resolution:** 10 m
- **Seasonal processing window:** May-October
- **Reporting framework:** five broad reporting sectors with complementary coastal-zone analysis

## Software and dependencies

The repository includes the frontend and backend application source code together with the available dependency/configuration files.

The remote-sensing workflow uses Google Earth Engine and Python-based geospatial processing. Exact software requirements should be taken from the dependency files and source-code imports included within the corresponding code folders.

Users running Google Earth Engine scripts must have access to a valid Google Earth Engine account/project. Authentication credentials are not distributed in this repository.

## Reproducibility notes

The repository provides the core analytical/application code, supporting datasets, numerical outputs, figures, tables, and supplementary results needed to inspect and reproduce the principal workflow and reported analyses.

The repository does **not** claim that every publication figure can be regenerated automatically from a single command. Some final figure assembly, annotation, and cosmetic editing were completed outside the core analytical scripts. The numerical data underlying the reported analytical figures and tables are provided where available.

The UAV/drone material is used as supporting qualitative context as described in the manuscript and should not be interpreted as an independently sampled, tide-normalized quantitative validation dataset.

## Data sources

Sentinel-2 imagery is accessed from the original public source through Google Earth Engine and is not redistributed as a complete satellite archive in this repository.

Users should consult the manuscript and the code comments/configuration for the exact processing parameters, masking rules, spatial units, and interpretation limits.

## Interpretation limits

The NDWI products represent spectrally detected land-water states. They should not automatically be interpreted as tide-normalized geomorphic shorelines or direct measurements of permanent erosion and accretion.

Threshold sensitivity is quantified using the tested NDWI values of 0.00, 0.05, and 0.10. Other sources of uncertainty include water level, tidal stage, mixed pixels, spatial resolution, georegistration, seasonal compositing, wet sediment, turbidity, and shoreline-position uncertainty.

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
