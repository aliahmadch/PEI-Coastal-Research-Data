/***************************************
 * 1. AOI from Shapefile (Asset)
 ***************************************/
var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernMostStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/centralStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternMostStudyline');

var peiAOI = aoiFC.geometry();

Map.centerObject(peiAOI, 9);
Map.addLayer(peiAOI, {color: 'red'}, 'AOI (Shapefile)');


/***************************************
 * 2. Sentinel-2 SR cloud/snow/shadow masking
 *    SCL-based
 ***************************************/
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


/***************************************
 * 3. NDWI band
 ***************************************/
function addNDWI(image) {
  var ndwi = image
    .normalizedDifference(['B3', 'B8'])
    .rename('NDWI');

  return image.addBands(ndwi);
}


/***************************************
 * 4. Get yearly NDWI composite
 ***************************************/
function getNDWI(year) {

  var start = ee.Date.fromYMD(year, 5, 1);

  // NOTE:
  // filterDate end is exclusive.
  // November 1 includes all of October.
  var end = ee.Date.fromYMD(year, 11, 1);

  var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(peiAOI)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  var count = col.size();

  var ndwi = col.median().clip(peiAOI);

  // Safety fallback
  ndwi = ee.Image(
    ee.Algorithms.If(
      ndwi.bandNames().size().gt(0),
      ndwi,
      ee.Image.constant(0)
        .rename('NDWI')
        .clip(peiAOI)
    )
  );

  return {
    ndwi: ndwi,
    count: count
  };
}


/***************************************
 * 5. Valid-observation statistics
 *    Reviewer 3 requirement
 ***************************************/
function getValidObservationStats(year) {

  var start = ee.Date.fromYMD(year, 5, 1);
  var end   = ee.Date.fromYMD(year, 11, 1);

  // Collection before SCL masking
  var rawCol = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(peiAOI)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60));

  // Total available observations per pixel
  var totalObs = rawCol
    .select('B3')
    .count()
    .rename('TotalObs');

  // Apply same SCL masking used in main analysis
  var validCol = rawCol.map(maskS2);

  // Valid observations per pixel after masking
  var validObs = validCol
    .select('B3')
    .count()
    .rename('ValidObs');

  // Valid observation percentage per pixel
  var validPct = validObs
    .divide(totalObs)
    .multiply(100)
    .rename('ValidObsPct')
    .updateMask(totalObs.gt(0));

  // Mean total observations per pixel
  var meanTotalObs = totalObs.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  }).getNumber('TotalObs');

  // Mean valid observations per pixel
  var meanValidObs = validObs.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  }).getNumber('ValidObs');

  // Mean valid observation percentage
  var meanValidPct = validPct.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  }).getNumber('ValidObsPct');

  // Minimum valid observation percentage
  var minValidPct = validPct.reduceRegion({
    reducer: ee.Reducer.min(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  }).getNumber('ValidObsPct');

  // Maximum valid observation percentage
  var maxValidPct = validPct.reduceRegion({
    reducer: ee.Reducer.max(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  }).getNumber('ValidObsPct');

  return {
    totalObsImage: totalObs,
    validObsImage: validObs,
    validPctImage: validPct,

    meanTotalObs: meanTotalObs,
    meanValidObs: meanValidObs,
    meanValidPct: meanValidPct,
    minValidPct: minValidPct,
    maxValidPct: maxValidPct
  };
}


/***************************************
 * 6. Land mask and area
 *    Threshold = 0.05
 ***************************************/
var TH = 0.05;

function landAreaKm2FromNDWI(ndwiImg) {

  var landMask = ndwiImg.lt(TH);

  var area = landMask
    .selfMask()
    .multiply(ee.Image.pixelArea())
    .reduceRegion({
      reducer: ee.Reducer.sum(),
      geometry: peiAOI,
      scale: 10,
      maxPixels: 1e13
    })
    .getNumber('NDWI')
    .divide(1e6);

  return area;
}


/***************************************
 * 7. Annual results table: 2019–2025
 ***************************************/
var years = ee.List.sequence(2019, 2025);

var annualFC = ee.FeatureCollection(
  years.map(function(y) {

    y = ee.Number(y).toInt();

    var ndwiOut = getNDWI(y);
    var ndwi = ee.Image(ndwiOut.ndwi);
    var imageCount = ee.Number(ndwiOut.count);

    var landKm2 = landAreaKm2FromNDWI(ndwi);

    // Valid observation statistics
    var obs = getValidObservationStats(y);

    return ee.Feature(null, {

      Year: y,

      ImageCount: imageCount,

      Mean_Available_Obs_per_Pixel:
        obs.meanTotalObs,

      Mean_Valid_Obs_per_Pixel:
        obs.meanValidObs,

      Valid_Observation_Percent:
        obs.meanValidPct,

      Min_Valid_Observation_Percent:
        obs.minValidPct,

      Max_Valid_Observation_Percent:
        obs.maxValidPct,

      Land_km2: landKm2
    });
  })
);

print(
  '✅ Annual NDWI + Valid Observation Coverage (2019–2025)',
  annualFC
);


/***************************************
 * 8. Year-to-year change table
 ***************************************/
var annualList = annualFC
  .sort('Year')
  .toList(annualFC.size());

var deltaFC = ee.FeatureCollection(
  ee.List
    .sequence(1, annualList.size().subtract(1))
    .map(function(i) {

      i = ee.Number(i);

      var curr = ee.Feature(
        annualList.get(i)
      );

      var prev = ee.Feature(
        annualList.get(i.subtract(1))
      );

      var year = curr.getNumber('Year');

      var delta = curr
        .getNumber('Land_km2')
        .subtract(
          prev.getNumber('Land_km2')
        );

      return ee.Feature(null, {
        Year: year,
        Delta_Land_km2: delta
      });
    })
);

print(
  '✅ Year-to-year change (ΔLand km²)',
  deltaFC
);


/***************************************
 * 9. Overall comparison: 2019 vs 2025
 ***************************************/
var f2019 = ee.Feature(
  annualFC
    .filter(ee.Filter.eq('Year', 2019))
    .first()
);

var f2025 = ee.Feature(
  annualFC
    .filter(ee.Filter.eq('Year', 2025))
    .first()
);

var overall = ee.Feature(null, {

  StartYear: 2019,

  EndYear: 2025,

  Land_2019_km2:
    f2019.getNumber('Land_km2'),

  Land_2025_km2:
    f2025.getNumber('Land_km2'),

  OverallChange_km2:
    f2025
      .getNumber('Land_km2')
      .subtract(
        f2019.getNumber('Land_km2')
      )
});

print(
  '✅ Overall change (2019 → 2025)',
  overall
);


/***************************************
 * 10. Land area chart
 ***************************************/
var chart = ui.Chart.feature.byFeature(
  annualFC.sort('Year'),
  'Year',
  'Land_km2'
)
.setOptions({

  title:
    'Annual Land Area (NDWI < 0.05) within AOI (2019–2025)',

  hAxis: {
    title: 'Year'
  },

  vAxis: {
    title: 'Land area (km²)'
  },

  pointSize: 4,

  lineWidth: 2
});

print(chart);


/***************************************
 * 11. Valid observation % chart
 ***************************************/
var validChart = ui.Chart.feature.byFeature(
  annualFC.sort('Year'),
  'Year',
  'Valid_Observation_Percent'
)
.setOptions({

  title:
    'Annual Valid Sentinel-2 Observation Coverage (2019–2025)',

  hAxis: {
    title: 'Year'
  },

  vAxis: {
    title: 'Valid observations (%)',
    viewWindow: {
      min: 0,
      max: 100
    }
  },

  pointSize: 5,

  lineWidth: 2
});

print(validChart);


/***************************************
 * 12. Visualize NDWI + change
 ***************************************/
var yrA = 2023;
var yrB = 2024;

var ndwiA_pack = getNDWI(yrA);
var ndwiB_pack = getNDWI(yrB);

var ndwiA = ee.Image(
  ndwiA_pack.ndwi
);

var ndwiB = ee.Image(
  ndwiB_pack.ndwi
);

Map.addLayer(
  ndwiA,
  {
    min: -1,
    max: 1,
    palette: [
      'brown',
      'white',
      'blue'
    ]
  },
  'NDWI ' + yrA
);

Map.addLayer(
  ndwiB,
  {
    min: -1,
    max: 1,
    palette: [
      'brown',
      'white',
      'blue'
    ]
  },
  'NDWI ' + yrB
);

var ndwiChange =
  ndwiB.subtract(ndwiA);

Map.addLayer(
  ndwiChange,
  {
    min: -0.5,
    max: 0.5,
    palette: [
      'red',
      'white',
      'blue'
    ]
  },
  'NDWI Change (' +
    yrB +
    ' - ' +
    yrA +
    ')'
);


/***************************************
 * 13. Valid observation coverage map
 ***************************************/
var checkYear = 2023;

var obsCheck =
  getValidObservationStats(
    checkYear
  );

Map.addLayer(
  ee.Image(
    obsCheck.validPctImage
  ),
  {
    min: 0,
    max: 100,
    palette: [
      'red',
      'yellow',
      'green'
    ]
  },
  'Valid Observation % ' +
    checkYear
);


/***************************************
 * 14. EXPORT ANNUAL TABLE
 ***************************************/
Export.table.toDrive({

  collection: annualFC,

  description:
    'NDWI_Annual_Results_ValidObs_2019_2025',

  fileFormat: 'CSV'
});


/***************************************
 * 15. EXPORT YEAR-TO-YEAR CHANGE TABLE
 ***************************************/
Export.table.toDrive({

  collection: deltaFC,

  description:
    'NDWI_Yearly_Change_2019_2025',

  fileFormat: 'CSV'
});


/***************************************
 * 16. EXPORT OVERALL COMPARISON
 ***************************************/
Export.table.toDrive({

  collection:
    ee.FeatureCollection([
      overall
    ]),

  description:
    'NDWI_Overall_Change_2019_2025',

  fileFormat: 'CSV'
});