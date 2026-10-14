/***************************************************************
 * NDWI LAND–WATER CHANGE AND THRESHOLD-SENSITIVITY ANALYSIS
 *
 * Primary threshold: 0.05
 * Sensitivity bounds: 0.00 and 0.10
 * Study period: 2019–2025
 * Seasonal window: May 1–October 31
 *
 * Optimized to avoid "Too many concurrent aggregations."
 ***************************************************************/


/***************************************************************
 * 1. USER SETTINGS
 ***************************************************************/

// Change this value to run another coastal zone.
var ZONE_KEY = 'eastern';

var ZONES = {
  westernMost: {
    name: 'WesternMost',
    asset: 'projects/ee-aliahmadch40/assets/westernMostStudyline'
  },
  western: {
    name: 'Western',
    asset: 'projects/ee-aliahmadch40/assets/westernStudyline'
  },
  central: {
    name: 'Central',
    asset: 'projects/ee-aliahmadch40/assets/centralStudyline'
  },
  eastern: {
    name: 'Eastern',
    asset: 'projects/ee-aliahmadch40/assets/easternStudyline'
  },
  easternMost: {
    name: 'EasternMost',
    asset: 'projects/ee-aliahmadch40/assets/easternMostStudyline'
  }
};

// NDWI thresholds.
var TH_LOW = 0.00;
var TH_MAIN = 0.05;
var TH_HIGH = 0.10;

// Analysis period.
var YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025];

// Map to display and export.
var MAP_START_YEAR = 2022;
var MAP_END_YEAR = 2023;

// Processing settings.
var SCALE = 10;
var OUTPUT_CRS = 'EPSG:2954';
var MAX_PIXELS = 1e13;
var DRIVE_FOLDER = 'NDWI_Threshold_Sensitivity';


/***************************************************************
 * 2. LOAD COASTAL-ZONE POLYGON
 ***************************************************************/

var zoneConfig = ZONES[ZONE_KEY];
var ZONE_NAME = zoneConfig.name;

var aoiFC = ee.FeatureCollection(zoneConfig.asset);
var AOI = aoiFC.geometry();

var AOI_AREA_KM2 = ee.Number(AOI.area(1)).divide(1e6);

Map.centerObject(AOI, 9);
Map.addLayer(aoiFC, {color: 'red'}, ZONE_NAME + ' coastal zone');

print('Selected coastal zone:', ZONE_NAME);
print('Polygon area (km²):', AOI_AREA_KM2);


/***************************************************************
 * 3. SENTINEL-2 PREPROCESSING
 ***************************************************************/

function maskS2(image) {
  var scl = image.select('SCL');

  var validMask = scl.neq(1)    // saturated or defective
    .and(scl.neq(2))            // dark-area pixels
    .and(scl.neq(3))            // cloud shadows
    .and(scl.neq(8))            // medium-probability clouds
    .and(scl.neq(9))            // high-probability clouds
    .and(scl.neq(10))           // cirrus
    .and(scl.neq(11));          // snow or ice

  return image
    .updateMask(validMask)
    .copyProperties(image, ['system:time_start']);
}


function addNDWI(image) {
  var ndwi = image
    .normalizedDifference(['B3', 'B8'])
    .rename('NDWI');

  return image.addBands(ndwi);
}


/***************************************************************
 * 4. ANNUAL NDWI COMPOSITE
 ***************************************************************/

function getAnnualNDWI(year) {
  var startDate = ee.Date.fromYMD(year, 5, 1);

  /*
   * filterDate uses an exclusive end date.
   * November 1 includes October 31.
   */
  var endDate = ee.Date.fromYMD(year, 11, 1);

  var collection = ee.ImageCollection(
    'COPERNICUS/S2_SR_HARMONIZED'
  )
    .filterBounds(AOI)
    .filterDate(startDate, endDate)
    .filter(
      ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60)
    )
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  var imageCount = collection.size();

  /*
   * Fully masked fallback image.
   * It prevents an empty collection from creating false land area.
   */
  var emptyImage = ee.Image.constant(0)
    .rename('NDWI')
    .updateMask(ee.Image.constant(0))
    .clip(AOI);

  var composite = collection
    .merge(ee.ImageCollection.fromImages([emptyImage]))
    .median()
    .rename('NDWI')
    .clip(AOI)
    .set({
      Year: year,
      Image_Count: imageCount
    });

  return {
    image: composite,
    count: imageCount
  };
}


/***************************************************************
 * 5. CREATE ALL ANNUAL COMPOSITES ONCE
 ***************************************************************/

var annualData = {};

YEARS.forEach(function(year) {
  annualData[year] = getAnnualNDWI(year);
});


/***************************************************************
 * 6. BASIC FUNCTIONS
 ***************************************************************/

var pixelAreaKm2 = ee.Image.pixelArea().divide(1e6);


function validMask(ndwi) {
  return ndwi.mask().gt(0);
}


function areaBand(mask, bandName) {
  return pixelAreaKm2
    .updateMask(ee.Image(mask))
    .rename(bandName);
}


function dictionaryNumber(dictionary, key) {
  return ee.Number(
    ee.Dictionary(dictionary).get(key, 0)
  );
}


function safePercentage(numerator, denominator) {
  numerator = ee.Number(numerator);
  denominator = ee.Number(denominator);

  return ee.Number(
    ee.Algorithms.If(
      denominator.gt(0),
      numerator.divide(denominator).multiply(100),
      0
    )
  );
}


function directionCode(value) {
  value = ee.Number(value);

  return ee.Number(
    ee.Algorithms.If(
      value.gt(0),
      1,
      ee.Algorithms.If(value.lt(0), -1, 0)
    )
  );
}


function directionLabel(value) {
  value = ee.Number(value);

  return ee.String(
    ee.Algorithms.If(
      value.gt(0),
      'Net land increase',
      ee.Algorithms.If(
        value.lt(0),
        'Net land decrease',
        'No net change'
      )
    )
  );
}


/***************************************************************
 * 7. ANNUAL AREA STACK
 *
 * All annual statistics are calculated using one reduceRegion().
 ***************************************************************/

var emptyStack = ee.Image.constant(0)
  .rename('empty')
  .select([]);

var annualAreaStack = emptyStack;

YEARS.forEach(function(year) {
  var ndwi = ee.Image(annualData[year].image);
  var valid = validMask(ndwi);

  var prefix = 'Y' + year + '_';

  annualAreaStack = annualAreaStack
    .addBands(
      areaBand(
        valid,
        prefix + 'Valid_Area_km2'
      )
    )
    .addBands(
      areaBand(
        valid.and(ndwi.lte(TH_LOW)),
        prefix + 'Land_TH_0_00_km2'
      )
    )
    .addBands(
      areaBand(
        valid.and(ndwi.lte(TH_MAIN)),
        prefix + 'Land_TH_0_05_km2'
      )
    )
    .addBands(
      areaBand(
        valid.and(ndwi.lte(TH_HIGH)),
        prefix + 'Land_TH_0_10_km2'
      )
    );
});


var annualDictionary = annualAreaStack.reduceRegion({
  reducer: ee.Reducer.sum(),
  geometry: AOI,
  scale: SCALE,
  crs: OUTPUT_CRS,
  maxPixels: MAX_PIXELS,
  tileScale: 4
});


var annualFeatures = YEARS.map(function(year) {
  var prefix = 'Y' + year + '_';

  var validArea = dictionaryNumber(
    annualDictionary,
    prefix + 'Valid_Area_km2'
  );

  var coverage = safePercentage(
    validArea,
    AOI_AREA_KM2
  );

  var imageCount = ee.Number(
    annualData[year].count
  );

  return ee.Feature(null, {
    Coastal_Zone: ZONE_NAME,
    Year: year,
    Image_Count: imageCount,

    Valid_Area_km2: validArea,
    Valid_Coverage_pct: coverage,

    Land_km2_TH_0_00: dictionaryNumber(
      annualDictionary,
      prefix + 'Land_TH_0_00_km2'
    ),

    Land_km2_TH_0_05: dictionaryNumber(
      annualDictionary,
      prefix + 'Land_TH_0_05_km2'
    ),

    Land_km2_TH_0_10: dictionaryNumber(
      annualDictionary,
      prefix + 'Land_TH_0_10_km2'
    ),

    Data_Status: ee.Algorithms.If(
      imageCount.gt(0).and(validArea.gt(0)),
      'Valid',
      'No valid data'
    )
  });
});


var annualFC = ee.FeatureCollection(annualFeatures);


/***************************************************************
 * 8. COMPARISON PERIODS
 ***************************************************************/

var COMPARISONS = [
  {start: 2019, end: 2020, type: 'Annual'},
  {start: 2020, end: 2021, type: 'Annual'},
  {start: 2021, end: 2022, type: 'Annual'},
  {start: 2022, end: 2023, type: 'Annual'},
  {start: 2023, end: 2024, type: 'Annual'},
  {start: 2024, end: 2025, type: 'Annual'},
  {start: 2019, end: 2025, type: 'Overall'}
];


/***************************************************************
 * 9. ADD ONE COMPARISON TO THE AREA STACK
 ***************************************************************/

function addComparisonBands(stack, startYear, endYear) {
  var ndwiStart = ee.Image(
    annualData[startYear].image
  );

  var ndwiEnd = ee.Image(
    annualData[endYear].image
  );

  var commonValid = validMask(ndwiStart)
    .and(validMask(ndwiEnd));

  var prefix = 'P' + startYear + '_' + endYear + '_';

  // Classifications at threshold 0.00.
  var landStartLow = ndwiStart.lte(TH_LOW)
    .and(commonValid);

  var waterStartLow = ndwiStart.gt(TH_LOW)
    .and(commonValid);

  var landEndLow = ndwiEnd.lte(TH_LOW)
    .and(commonValid);

  var waterEndLow = ndwiEnd.gt(TH_LOW)
    .and(commonValid);

  // Classifications at threshold 0.05.
  var landStartMain = ndwiStart.lte(TH_MAIN)
    .and(commonValid);

  var waterStartMain = ndwiStart.gt(TH_MAIN)
    .and(commonValid);

  var landEndMain = ndwiEnd.lte(TH_MAIN)
    .and(commonValid);

  var waterEndMain = ndwiEnd.gt(TH_MAIN)
    .and(commonValid);

  // Classifications at threshold 0.10.
  var landStartHigh = ndwiStart.lte(TH_HIGH)
    .and(commonValid);

  var waterStartHigh = ndwiStart.gt(TH_HIGH)
    .and(commonValid);

  var landEndHigh = ndwiEnd.lte(TH_HIGH)
    .and(commonValid);

  var waterEndHigh = ndwiEnd.gt(TH_HIGH)
    .and(commonValid);

  // Land-to-water transitions.
  var landToWaterLow = landStartLow
    .and(waterEndLow);

  var landToWaterMain = landStartMain
    .and(waterEndMain);

  var landToWaterHigh = landStartHigh
    .and(waterEndHigh);

  // Water-to-land transitions.
  var waterToLandLow = waterStartLow
    .and(landEndLow);

  var waterToLandMain = waterStartMain
    .and(landEndMain);

  var waterToLandHigh = waterStartHigh
    .and(landEndHigh);

  /*
   * Robust classes:
   * classification remains the same under all thresholds.
   */
  var unchangedLand = ndwiStart.lte(TH_LOW)
    .and(ndwiEnd.lte(TH_LOW))
    .and(commonValid);

  var unchangedWater = ndwiStart.gt(TH_HIGH)
    .and(ndwiEnd.gt(TH_HIGH))
    .and(commonValid);

  var robustLandToWater = ndwiStart.lte(TH_LOW)
    .and(ndwiEnd.gt(TH_HIGH))
    .and(commonValid);

  var robustWaterToLand = ndwiStart.gt(TH_HIGH)
    .and(ndwiEnd.lte(TH_LOW))
    .and(commonValid);

  var robustClassified = unchangedLand
    .or(unchangedWater)
    .or(robustLandToWater)
    .or(robustWaterToLand);

  /*
   * Threshold-sensitive pixels:
   * classification or transition changes among thresholds.
   */
  var thresholdSensitive = commonValid
    .and(robustClassified.not());

  var primaryTransition = landToWaterMain
    .or(waterToLandMain);

  var sensitivePrimaryTransition = primaryTransition
    .and(thresholdSensitive);

  return stack
    .addBands(
      areaBand(
        commonValid,
        prefix + 'Common_Valid_km2'
      )
    )

    // Land-to-water areas.
    .addBands(
      areaBand(
        landToWaterLow,
        prefix + 'L2W_0_00_km2'
      )
    )
    .addBands(
      areaBand(
        landToWaterMain,
        prefix + 'L2W_0_05_km2'
      )
    )
    .addBands(
      areaBand(
        landToWaterHigh,
        prefix + 'L2W_0_10_km2'
      )
    )

    // Water-to-land areas.
    .addBands(
      areaBand(
        waterToLandLow,
        prefix + 'W2L_0_00_km2'
      )
    )
    .addBands(
      areaBand(
        waterToLandMain,
        prefix + 'W2L_0_05_km2'
      )
    )
    .addBands(
      areaBand(
        waterToLandHigh,
        prefix + 'W2L_0_10_km2'
      )
    )

    // Land area used for reconciliation.
    .addBands(
      areaBand(
        landStartMain,
        prefix + 'Start_Land_0_05_km2'
      )
    )
    .addBands(
      areaBand(
        landEndMain,
        prefix + 'End_Land_0_05_km2'
      )
    )

    // Robust transitions.
    .addBands(
      areaBand(
        robustLandToWater,
        prefix + 'Robust_L2W_km2'
      )
    )
    .addBands(
      areaBand(
        robustWaterToLand,
        prefix + 'Robust_W2L_km2'
      )
    )

    // Threshold sensitivity.
    .addBands(
      areaBand(
        thresholdSensitive,
        prefix + 'Threshold_Sensitive_km2'
      )
    )
    .addBands(
      areaBand(
        sensitivePrimaryTransition,
        prefix + 'Sensitive_Primary_Transition_km2'
      )
    );
}


/***************************************************************
 * 10. BUILD ONE COMPARISON STACK
 *
 * All comparison statistics are calculated using one
 * reduceRegion().
 ***************************************************************/

var comparisonAreaStack = emptyStack;

COMPARISONS.forEach(function(period) {
  comparisonAreaStack = addComparisonBands(
    comparisonAreaStack,
    period.start,
    period.end
  );
});


var comparisonDictionary =
  comparisonAreaStack.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: AOI,
    scale: SCALE,
    crs: OUTPUT_CRS,
    maxPixels: MAX_PIXELS,
    tileScale: 4
  });


/***************************************************************
 * 11. CREATE COMPARISON RESULTS TABLE
 ***************************************************************/

var comparisonFeatures = COMPARISONS.map(function(period) {
  var startYear = period.start;
  var endYear = period.end;

  var prefix = 'P' + startYear + '_' + endYear + '_';

  var commonValidArea = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Common_Valid_km2'
  );

  var l2wLow = dictionaryNumber(
    comparisonDictionary,
    prefix + 'L2W_0_00_km2'
  );

  var l2wMain = dictionaryNumber(
    comparisonDictionary,
    prefix + 'L2W_0_05_km2'
  );

  var l2wHigh = dictionaryNumber(
    comparisonDictionary,
    prefix + 'L2W_0_10_km2'
  );

  var w2lLow = dictionaryNumber(
    comparisonDictionary,
    prefix + 'W2L_0_00_km2'
  );

  var w2lMain = dictionaryNumber(
    comparisonDictionary,
    prefix + 'W2L_0_05_km2'
  );

  var w2lHigh = dictionaryNumber(
    comparisonDictionary,
    prefix + 'W2L_0_10_km2'
  );

  /*
   * Net land-area change:
   * positive = net increase in classified land;
   * negative = net decrease in classified land.
   */
  var netLow = w2lLow.subtract(l2wLow);
  var netMain = w2lMain.subtract(l2wMain);
  var netHigh = w2lHigh.subtract(l2wHigh);

  var changeList = ee.List([
    netLow,
    netMain,
    netHigh
  ]);

  var minimumChange = ee.Number(
    changeList.reduce(ee.Reducer.min())
  );

  var maximumChange = ee.Number(
    changeList.reduce(ee.Reducer.max())
  );

  var sensitivityRange = maximumChange
    .subtract(minimumChange);

  var maxDeviation = ee.Number(
    ee.List([
      netLow.subtract(netMain).abs(),
      netHigh.subtract(netMain).abs()
    ]).reduce(ee.Reducer.max())
  );

  var directionStable = directionCode(netLow)
    .eq(directionCode(netMain))
    .and(
      directionCode(netMain)
        .eq(directionCode(netHigh))
    );

  var primaryTransitionArea = l2wMain
    .add(w2lMain);

  var robustL2W = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Robust_L2W_km2'
  );

  var robustW2L = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Robust_W2L_km2'
  );

  var thresholdSensitiveArea = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Threshold_Sensitive_km2'
  );

  var sensitivePrimaryArea = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Sensitive_Primary_Transition_km2'
  );

  var startLandMain = dictionaryNumber(
    comparisonDictionary,
    prefix + 'Start_Land_0_05_km2'
  );

  var endLandMain = dictionaryNumber(
    comparisonDictionary,
    prefix + 'End_Land_0_05_km2'
  );

  var landAreaDifference = endLandMain
    .subtract(startLandMain);

  var reconciliationError = netMain
    .subtract(landAreaDifference)
    .abs();

  var startCount = ee.Number(
    annualData[startYear].count
  );

  var endCount = ee.Number(
    annualData[endYear].count
  );

  var comparisonValid = startCount.gt(0)
    .and(endCount.gt(0))
    .and(commonValidArea.gt(0));

  return ee.Feature(null, {
    Coastal_Zone: ZONE_NAME,
    Comparison_Type: period.type,
    Start_Year: startYear,
    End_Year: endYear,

    Image_Count_Start: startCount,
    Image_Count_End: endCount,

    Common_Valid_Area_km2:
      commonValidArea,

    Common_Valid_Coverage_pct:
      safePercentage(
        commonValidArea,
        AOI_AREA_KM2
      ),

    Land_to_Water_TH_0_00_km2:
      l2wLow,

    Land_to_Water_TH_0_05_km2:
      l2wMain,

    Land_to_Water_TH_0_10_km2:
      l2wHigh,

    Water_to_Land_TH_0_00_km2:
      w2lLow,

    Water_to_Land_TH_0_05_km2:
      w2lMain,

    Water_to_Land_TH_0_10_km2:
      w2lHigh,

    Net_Change_TH_0_00_km2:
      netLow,

    Net_Change_TH_0_05_km2:
      netMain,

    Net_Change_TH_0_10_km2:
      netHigh,

    Minimum_Change_km2:
      minimumChange,

    Maximum_Change_km2:
      maximumChange,

    Sensitivity_Range_km2:
      sensitivityRange,

    Max_Deviation_From_0_05_km2:
      maxDeviation,

    Direction_TH_0_05:
      ee.Algorithms.If(
        comparisonValid,
        directionLabel(netMain),
        'Not evaluated'
      ),

    Direction_Stable:
      ee.Algorithms.If(
        comparisonValid,
        ee.Algorithms.If(
          directionStable,
          'Yes',
          'No'
        ),
        'Not evaluated'
      ),

    Primary_Transition_Area_km2:
      primaryTransitionArea,

    Robust_Land_to_Water_km2:
      robustL2W,

    Robust_Water_to_Land_km2:
      robustW2L,

    Robust_Transition_Area_km2:
      robustL2W.add(robustW2L),

    Threshold_Sensitive_Area_km2:
      thresholdSensitiveArea,

    Threshold_Sensitive_pct_CommonValid:
      safePercentage(
        thresholdSensitiveArea,
        commonValidArea
      ),

    Sensitive_Primary_Transition_Area_km2:
      sensitivePrimaryArea,

    Sensitive_Primary_Transition_pct:
      safePercentage(
        sensitivePrimaryArea,
        primaryTransitionArea
      ),

    Reconciliation_Error_TH_0_05_km2:
      reconciliationError,

    Comparison_Status:
      ee.Algorithms.If(
        comparisonValid,
        'Valid',
        'No common valid data'
      )
  });
});


var comparisonFC = ee.FeatureCollection(
  comparisonFeatures
);

var yearlyComparisonFC = comparisonFC.filter(
  ee.Filter.eq('Comparison_Type', 'Annual')
);

var overallComparisonFC = comparisonFC.filter(
  ee.Filter.eq('Comparison_Type', 'Overall')
);


/***************************************************************
 * 12. CREATE THE SELECTED SENSITIVITY MAP
 ***************************************************************/

function createSensitivityMap(startYear, endYear) {
  var ndwiStart = ee.Image(
    annualData[startYear].image
  );

  var ndwiEnd = ee.Image(
    annualData[endYear].image
  );

  var commonValid = validMask(ndwiStart)
    .and(validMask(ndwiEnd));

  var unchangedLand = ndwiStart.lte(TH_LOW)
    .and(ndwiEnd.lte(TH_LOW))
    .and(commonValid);

  var unchangedWater = ndwiStart.gt(TH_HIGH)
    .and(ndwiEnd.gt(TH_HIGH))
    .and(commonValid);

  var robustLandToWater = ndwiStart.lte(TH_LOW)
    .and(ndwiEnd.gt(TH_HIGH))
    .and(commonValid);

  var robustWaterToLand = ndwiStart.gt(TH_HIGH)
    .and(ndwiEnd.lte(TH_LOW))
    .and(commonValid);

  var robustClassified = unchangedLand
    .or(unchangedWater)
    .or(robustLandToWater)
    .or(robustWaterToLand);

  var thresholdSensitive = commonValid
    .and(robustClassified.not());

  /*
   * Class values:
   * 0 = no common valid data
   * 1 = consistently unchanged land
   * 2 = consistently unchanged water
   * 3 = robust land-to-water
   * 4 = robust water-to-land
   * 5 = threshold-sensitive
   */
  return ee.Image.constant(0)
    .clip(AOI)
    .where(unchangedLand, 1)
    .where(unchangedWater, 2)
    .where(robustLandToWater, 3)
    .where(robustWaterToLand, 4)
    .where(thresholdSensitive, 5)
    .rename('Sensitivity_Class')
    .toByte();
}


var sensitivityMap = createSensitivityMap(
  MAP_START_YEAR,
  MAP_END_YEAR
);

Map.addLayer(
  sensitivityMap.updateMask(sensitivityMap.neq(0)),
  {
    min: 1,
    max: 5,
    palette: [
      '8c6d31',  // unchanged land
      '2b8cbe',  // unchanged water
      'd73027',  // robust land-to-water
      '1a9850',  // robust water-to-land
      'ffd92f'   // threshold-sensitive
    ]
  },
  ZONE_NAME + ' threshold sensitivity ' +
    MAP_START_YEAR + '–' +
    MAP_END_YEAR
);


/***************************************************************
 * 13. RESULTS PREVIEW
 *
 * Only two aggregated tables are printed.
 ***************************************************************/

print(
  '1. Annual area and threshold sensitivity',
  annualFC.sort('Year')
);

print(
  '2. Yearly and overall change sensitivity',
  comparisonFC.sort('Start_Year')
);

print(
  'Sensitivity-map classes',
  {
    0: 'No common valid data',
    1: 'Consistently unchanged land',
    2: 'Consistently unchanged water',
    3: 'Robust land-to-water transition',
    4: 'Robust water-to-land transition',
    5: 'Threshold-sensitive classification/change'
  }
);


/***************************************************************
 * 14. EXPORT ANNUAL AREA TABLE
 ***************************************************************/

var annualExportName =
  'NDWI_' + ZONE_NAME +
  '_Annual_Area_Sensitivity_2019_2025';

Export.table.toDrive({
  collection: annualFC.sort('Year'),
  description: annualExportName,
  folder: DRIVE_FOLDER,
  fileNamePrefix: annualExportName,
  fileFormat: 'CSV',
  selectors: [
    'Coastal_Zone',
    'Year',
    'Image_Count',
    'Valid_Area_km2',
    'Valid_Coverage_pct',
    'Land_km2_TH_0_00',
    'Land_km2_TH_0_05',
    'Land_km2_TH_0_10',
    'Data_Status'
  ]
});


/***************************************************************
 * 15. EXPORT ALL CHANGE AND SENSITIVITY RESULTS
 ***************************************************************/

var comparisonExportName =
  'NDWI_' + ZONE_NAME +
  '_Change_Sensitivity_2019_2025';

Export.table.toDrive({
  collection: comparisonFC.sort('Start_Year'),
  description: comparisonExportName,
  folder: DRIVE_FOLDER,
  fileNamePrefix: comparisonExportName,
  fileFormat: 'CSV',
  selectors: [
    'Coastal_Zone',
    'Comparison_Type',
    'Start_Year',
    'End_Year',

    'Image_Count_Start',
    'Image_Count_End',

    'Common_Valid_Area_km2',
    'Common_Valid_Coverage_pct',

    'Land_to_Water_TH_0_00_km2',
    'Land_to_Water_TH_0_05_km2',
    'Land_to_Water_TH_0_10_km2',

    'Water_to_Land_TH_0_00_km2',
    'Water_to_Land_TH_0_05_km2',
    'Water_to_Land_TH_0_10_km2',

    'Net_Change_TH_0_00_km2',
    'Net_Change_TH_0_05_km2',
    'Net_Change_TH_0_10_km2',

    'Minimum_Change_km2',
    'Maximum_Change_km2',
    'Sensitivity_Range_km2',
    'Max_Deviation_From_0_05_km2',

    'Direction_TH_0_05',
    'Direction_Stable',

    'Primary_Transition_Area_km2',

    'Robust_Land_to_Water_km2',
    'Robust_Water_to_Land_km2',
    'Robust_Transition_Area_km2',

    'Threshold_Sensitive_Area_km2',
    'Threshold_Sensitive_pct_CommonValid',

    'Sensitive_Primary_Transition_Area_km2',
    'Sensitive_Primary_Transition_pct',

    'Reconciliation_Error_TH_0_05_km2',
    'Comparison_Status'
  ]
});


/***************************************************************
 * 16. EXPORT THE SELECTED SENSITIVITY MAP
 ***************************************************************/

var mapExportName =
  'NDWI_' + ZONE_NAME + '_' +
  MAP_START_YEAR + '_' +
  MAP_END_YEAR +
  '_Threshold_Sensitivity';

Export.image.toDrive({
  image: sensitivityMap,
  description: mapExportName,
  folder: DRIVE_FOLDER,
  fileNamePrefix: mapExportName,
  region: AOI,
  scale: SCALE,
  crs: OUTPUT_CRS,
  maxPixels: MAX_PIXELS,
  fileFormat: 'GeoTIFF',
  formatOptions: {
    cloudOptimized: true
  }
});