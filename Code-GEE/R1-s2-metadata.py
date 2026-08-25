/*****************************************************
 * COMPLETE SENTINEL-2 SCENE INVENTORY
 * Study period: 2019–2025
 * Seasonal window: 1 May–31 October inclusive
 *
 * Outputs:
 * 1. Year-by-year inventory summary
 * 2. Complete candidate-scene inventory
 * 3. Processing-parameter table
 *****************************************************/


// ====================================================
// 1. STUDY AREAS
// Merge all analysis areas into one study-wide AOI
// ====================================================

var westernmostFC = ee.FeatureCollection(
  'projects/ee-aliahmadch40/assets/westernMostStudyline'
);

var westernFC = ee.FeatureCollection(
  'projects/ee-aliahmadch40/assets/westernStudyline'
);

var centralFC = ee.FeatureCollection(
  'projects/ee-aliahmadch40/assets/centralStudyline'
);

var easternFC = ee.FeatureCollection(
  'projects/ee-aliahmadch40/assets/easternStudyline'
);

var easternmostFC = ee.FeatureCollection(
  'projects/ee-aliahmadch40/assets/easternMostStudyline'
);


var allStudyAreas = westernmostFC
  .merge(westernFC)
  .merge(centralFC)
  .merge(easternFC)
  .merge(easternmostFC);


var studyAOI = allStudyAreas.geometry();


Map.centerObject(studyAOI, 8);

Map.addLayer(
  allStudyAreas,
  {color: 'red'},
  'All study areas'
);


// ====================================================
// 2. PROCESSING PARAMETERS
// ====================================================

var COLLECTION_ID =
  'COPERNICUS/S2_SR_HARMONIZED';

var START_YEAR = 2019;
var END_YEAR = 2025;

var CLOUD_THRESHOLD = 60;

// NDWI threshold used in the main analysis
var NDWI_THRESHOLD = 0.05;

var years = ee.List.sequence(
  START_YEAR,
  END_YEAR
);


// ====================================================
// 3. SENTINEL-2 SCL MASK
//
// Masked classes:
// 1  = saturated or defective
// 2  = dark area pixels
// 3  = cloud shadows
// 8  = medium-probability clouds
// 9  = high-probability clouds
// 10 = cirrus
// 11 = snow or ice
//
// Class 7, low-probability cloud/unclassified,
// remains included because it was not masked in
// the original methodology.
// ====================================================

function maskS2(image) {

  var scl = image.select('SCL');

  var mask = scl.neq(1)
    .and(scl.neq(2))
    .and(scl.neq(3))
    .and(scl.neq(8))
    .and(scl.neq(9))
    .and(scl.neq(10))
    .and(scl.neq(11));

  return image.updateMask(mask);
}


// ====================================================
// 4. ADD NDWI
// ====================================================

function addNDWI(image) {

  var ndwi = image
    .normalizedDifference(['B3', 'B8'])
    .rename('NDWI');

  return image.addBands(ndwi);
}


// ====================================================
// 5. COLLECTION BEFORE CLOUD FILTER
//
// Date window:
// Start date is inclusive.
// End date is exclusive.
//
// Therefore, 1 November is used to include
// all images acquired through 31 October.
// ====================================================

function getCandidateCollection(year) {

  year = ee.Number(year).toInt();

  var startDate = ee.Date.fromYMD(
    year,
    5,
    1
  );

  var endDateExclusive = ee.Date.fromYMD(
    year,
    11,
    1
  );

  return ee.ImageCollection(COLLECTION_ID)
    .filterBounds(studyAOI)
    .filterDate(
      startDate,
      endDateExclusive
    );
}


// ====================================================
// 6. COLLECTION AFTER CLOUD FILTER
// ====================================================

function getRetainedCollection(year) {

  return getCandidateCollection(year)
    .filter(
      ee.Filter.lt(
        'CLOUDY_PIXEL_PERCENTAGE',
        CLOUD_THRESHOLD
      )
    );
}


// ====================================================
// 7. COMPLETE SCENE INVENTORY
//
// Contains one row for every candidate scene,
// including both retained and excluded scenes.
// ====================================================

var sceneInventoryFC = ee.FeatureCollection(

  years.map(function(year) {

    year = ee.Number(year).toInt();

    var candidateCollection =
      getCandidateCollection(year);

    var candidateList =
      candidateCollection.toList(
        candidateCollection.size()
      );

    return ee.FeatureCollection(

      candidateList.map(function(item) {

        var image = ee.Image(item);

        var cloudPercentage = ee.Number(
          image.get(
            'CLOUDY_PIXEL_PERCENTAGE'
          )
        );

        var retained =
          cloudPercentage.lt(
            CLOUD_THRESHOLD
          );

        var retainedValue = ee.Number(
          ee.Algorithms.If(
            retained,
            1,
            0
          )
        );

        var status = ee.String(
          ee.Algorithms.If(
            retained,
            'Retained',
            'Excluded'
          )
        );

        var exclusionReason = ee.String(
          ee.Algorithms.If(
            retained,
            'None',
            'CLOUDY_PIXEL_PERCENTAGE >= 60'
          )
        );

        var acquisitionDate = ee.Date(
          image.get('system:time_start')
        );

        return ee.Feature(null, {

          year: year,

          acquisition_date_utc:
            acquisitionDate.format(
              'YYYY-MM-dd'
            ),

          acquisition_datetime_utc:
            acquisitionDate.format(
              'YYYY-MM-dd HH:mm:ss'
            ),

          system_time_start_ms:
            image.get(
              'system:time_start'
            ),

          system_index:
            image.get(
              'system:index'
            ),

          product_id:
            image.get(
              'PRODUCT_ID'
            ),

          mgrs_tile:
            image.get(
              'MGRS_TILE'
            ),

          spacecraft:
            image.get(
              'SPACECRAFT_NAME'
            ),

          processing_baseline:
            image.get(
              'PROCESSING_BASELINE'
            ),

          sensing_orbit_number:
            image.get(
              'SENSING_ORBIT_NUMBER'
            ),

          cloudy_pixel_percentage:
            cloudPercentage,

          retained_after_cloud_filter:
            retainedValue,

          scene_status:
            status,

          exclusion_reason:
            exclusionReason
        });
      })
    );
  })

).flatten();


print(
  '✅ Complete Sentinel-2 candidate-scene inventory',
  sceneInventoryFC.sort(
    'system_time_start_ms'
  )
);


// ====================================================
// 8. YEAR-BY-YEAR INVENTORY SUMMARY
// ====================================================

var yearSummaryFC = ee.FeatureCollection(

  years.map(function(year) {

    year = ee.Number(year).toInt();

    var startDate = ee.Date.fromYMD(
      year,
      5,
      1
    );

    var endDateExclusive = ee.Date.fromYMD(
      year,
      11,
      1
    );


    // --------------------------------------------
    // Collections before and after cloud filtering
    // --------------------------------------------

    var candidates =
      getCandidateCollection(year);

    var retained =
      getRetainedCollection(year);

    var candidateCount =
      candidates.size();

    var retainedCount =
      retained.size();

    var excludedCount =
      candidateCount.subtract(
        retainedCount
      );


    // --------------------------------------------
    // Unique retained acquisition dates
    // Multiple MGRS granules may occur on one date
    // --------------------------------------------

    var retainedWithDates = retained.map(
      function(image) {

        return image.set(
          'acquisition_date_text',

          ee.Date(
            image.get(
              'system:time_start'
            )
          ).format(
            'YYYY-MM-dd'
          )
        );
      }
    );


    var uniqueAcquisitionDates = ee.List(
      retainedWithDates.aggregate_array(
        'acquisition_date_text'
      )
    )
      .distinct()
      .size();


    // --------------------------------------------
    // Mask pixels and create annual NDWI composite
    // --------------------------------------------

    var maskedNDWICollection = retained
      .map(maskS2)
      .map(addNDWI)
      .select('NDWI');


    var annualComposite =
      maskedNDWICollection
        .median()
        .clip(studyAOI);


    // --------------------------------------------
    // Number of valid 10 m pixels in annual composite
    //
    // A pixel is valid when at least one retained
    // image contributed an unmasked NDWI observation.
    // --------------------------------------------

    var validPixelDictionary =
      annualComposite.reduceRegion({

        reducer: ee.Reducer.count(),

        geometry: studyAOI,

        scale: 10,

        maxPixels: 1e13,

        tileScale: 4
      });


    var compositeValidPixels = ee.Number(
      validPixelDictionary.get(
        'NDWI',
        0
      )
    );


    // --------------------------------------------
    // Valid annual composite area
    // --------------------------------------------

    var validAreaImage =
      ee.Image.pixelArea()
        .updateMask(
          annualComposite.mask()
        )
        .rename(
          'valid_area_m2'
        );


    var validAreaDictionary =
      validAreaImage.reduceRegion({

        reducer: ee.Reducer.sum(),

        geometry: studyAOI,

        scale: 10,

        maxPixels: 1e13,

        tileScale: 4
      });


    var validAreaKm2 = ee.Number(
      validAreaDictionary.get(
        'valid_area_m2',
        0
      )
    ).divide(
      1e6
    );


    var aoiAreaKm2 = ee.Number(
      studyAOI.area(1)
    ).divide(
      1e6
    );


    var validCoveragePercent =
      validAreaKm2
        .divide(aoiAreaKm2)
        .multiply(100);


    // --------------------------------------------
    // Count valid observations contributing to
    // every annual composite pixel
    // --------------------------------------------

    var observationCountImage =
      maskedNDWICollection
        .count()
        .rename(
          'valid_observation_count'
        )
        .clip(studyAOI);


    var observationReducer =
      ee.Reducer.minMax()

        .combine({
          reducer2: ee.Reducer.mean(),
          sharedInputs: true
        })

        .combine({
          reducer2: ee.Reducer.sum(),
          sharedInputs: true
        });


    var observationStatistics =
      observationCountImage.reduceRegion({

        reducer: observationReducer,

        geometry: studyAOI,

        scale: 10,

        maxPixels: 1e13,

        tileScale: 4
      });


    // --------------------------------------------
    // Year-summary row
    // --------------------------------------------

    return ee.Feature(null, {

      year: year,

      collection_id:
        COLLECTION_ID,

      start_date_inclusive:
        startDate.format(
          'YYYY-MM-dd'
        ),

      end_date_inclusive:
        endDateExclusive
          .advance(-1, 'day')
          .format('YYYY-MM-dd'),

      scene_cloud_threshold_percent:
        CLOUD_THRESHOLD,

      scenes_before_cloud_filter:
        candidateCount,

      scenes_after_cloud_filter:
        retainedCount,

      scenes_excluded_by_cloud_filter:
        excludedCount,

      unique_retained_acquisition_dates:
        uniqueAcquisitionDates,

      composite_valid_pixels_10m:
        compositeValidPixels,

      composite_valid_area_km2:
        validAreaKm2,

      composite_valid_coverage_percent:
        validCoveragePercent,

      minimum_valid_observations_per_pixel:
        observationStatistics.get(
          'valid_observation_count_min'
        ),

      mean_valid_observations_per_pixel:
        observationStatistics.get(
          'valid_observation_count_mean'
        ),

      maximum_valid_observations_per_pixel:
        observationStatistics.get(
          'valid_observation_count_max'
        ),

      total_valid_pixel_observations:
        observationStatistics.get(
          'valid_observation_count_sum'
        )
    });
  })

);


print(
  '✅ Year-by-year Sentinel-2 inventory summary',
  yearSummaryFC
);


// ====================================================
// 9. PROCESSING-PARAMETER TABLE
// ====================================================

var processingParametersFC =
  ee.FeatureCollection([

    ee.Feature(null, {

      collection_id:
        COLLECTION_ID,

      product:
        'Sentinel-2 MSI Level-2A Harmonized Surface Reflectance',

      study_period:
        '2019-2025',

      annual_date_window:
        '1 May-31 October inclusive',

      spatial_selection_rule:
        'Image footprint intersects merged study AOI',

      scene_cloud_rule:
        'CLOUDY_PIXEL_PERCENTAGE < 60',

      masked_SCL_classes:
        '1, 2, 3, 8, 9, 10, 11',

      masked_SCL_descriptions:
        'Saturated/defective; dark area; cloud shadow; medium-probability cloud; high-probability cloud; cirrus; snow/ice',

      retained_SCL_classes:
        '4, 5, 6, 7',

      retained_SCL_descriptions:
        'Vegetation; bare soil; water; low-probability cloud/unclassified',

      annual_composite_method:
        'Median',

      NDWI_bands:
        'B3 and B8',

      output_resolution_m:
        10,

      NDWI_threshold:
        NDWI_THRESHOLD
    })
  ]);


print(
  '✅ Processing parameters',
  processingParametersFC
);


// ====================================================
// 10. EXPORT YEAR SUMMARY
// Supplementary Table S1a
// ====================================================

Export.table.toDrive({

  collection:
    yearSummaryFC,

  description:
    'Supplementary_Table_S1a_Sentinel2_Yearly_Inventory_2019_2025',

  fileNamePrefix:
    'Supplementary_Table_S1a_Sentinel2_Yearly_Inventory_2019_2025',

  fileFormat:
    'CSV'
});


// ====================================================
// 11. EXPORT COMPLETE SCENE INVENTORY
// Supplementary Table S1b
// ====================================================

Export.table.toDrive({

  collection:
    sceneInventoryFC.sort(
      'system_time_start_ms'
    ),

  description:
    'Supplementary_Table_S1b_Complete_Sentinel2_Scene_Inventory',

  fileNamePrefix:
    'Supplementary_Table_S1b_Complete_Sentinel2_Scene_Inventory',

  fileFormat:
    'CSV'
});


// ====================================================
// 12. EXPORT PROCESSING PARAMETERS
// ====================================================

Export.table.toDrive({

  collection:
    processingParametersFC,

  description:
    'Supplementary_Table_S1c_Sentinel2_Processing_Parameters',

  fileNamePrefix:
    'Supplementary_Table_S1c_Sentinel2_Processing_Parameters',

  fileFormat:
    'CSV'
});