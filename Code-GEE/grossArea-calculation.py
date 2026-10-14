/*******************************************************
 * GROSS LAND-WATER TRANSITIONS + NET CHANGE
 * Required only for Reviewer 3 comment
 *******************************************************/


/***************************************
 * 1. SELECT AOI
 ***************************************/
var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernMostStudyline');
var REGION = 'Westernmost';

//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernStudyline');
//var REGION = 'Western';

//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/centralStudyline');
//var REGION = 'Central';

//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternStudyline');
//var REGION = 'Eastern';

//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternMostStudyline');
//var REGION = 'Easternmost';

var peiAOI = aoiFC.geometry();


/***************************************
 * 2. SENTINEL-2 SCL MASK
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
 * 3. ANNUAL NDWI COMPOSITE
 ***************************************/
function getNDWI(year) {

  var start = ee.Date.fromYMD(year, 5, 1);
  var end   = ee.Date.fromYMD(year, 10, 31);

  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(peiAOI)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskS2)
    .map(function(image) {
      return image.normalizedDifference(['B3', 'B8'])
        .rename('NDWI');
    })
    .median()
    .clip(peiAOI);
}


/***************************************
 * 4. AREA CALCULATION
 ***************************************/
function areaKm2(maskImage) {

  var areaImage = ee.Image.pixelArea()
    .updateMask(maskImage)
    .rename('area');

  var result = areaImage.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: peiAOI,
    scale: 10,
    maxPixels: 1e13
  });

  return ee.Number(result.get('area')).divide(1e6);
}


/***************************************
 * 5. GROSS + NET TRANSITIONS
 ***************************************/
var TH = 0.10;

var startYears = ee.List.sequence(2019, 2024);

var transitionFC = ee.FeatureCollection(
  startYears.map(function(y) {

    y = ee.Number(y).toInt();
    var y2 = y.add(1);

    var ndwi1 = getNDWI(y);
    var ndwi2 = getNDWI(y2);

    // Compare only pixels valid in BOTH years
    var commonValid = ndwi1.mask().and(ndwi2.mask());

    var land1 = ndwi1.lt(TH).updateMask(commonValid);
    var land2 = ndwi2.lt(TH).updateMask(commonValid);

    // Gross land → water
    var landToWater = land1
      .and(land2.not())
      .updateMask(commonValid);

    // Gross water → land
    var waterToLand = land1.not()
      .and(land2)
      .updateMask(commonValid);

    var landToWaterKm2 = areaKm2(landToWater);
    var waterToLandKm2 = areaKm2(waterToLand);

    // Net = water→land − land→water
    var netKm2 = waterToLandKm2.subtract(landToWaterKm2);

    return ee.Feature(null, {
      Region: REGION,
      Period: y.format().cat('-').cat(y2.format()),
      Land_to_Water_km2: landToWaterKm2,
      Water_to_Land_km2: waterToLandKm2,
      Net_Change_km2: netKm2
    });
  })
);


/***************************************
 * 6. PRINT + EXPORT ONLY
 ***************************************/
print('Gross and Net Land-Water Transitions', transitionFC);

Export.table.toDrive({
  collection: transitionFC,
  description: 'NDWI_Gross_Net_Transitions_2019_2025_' + REGION,
  fileFormat: 'CSV'
});