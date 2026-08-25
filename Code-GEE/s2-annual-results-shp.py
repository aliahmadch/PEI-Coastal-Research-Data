/***************************************
 * 1. AOI from Shapefile (Asset)
 ***************************************/
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernMostStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/westernStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/centralStudyline');
var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternStudyline');
//var aoiFC = ee.FeatureCollection('projects/ee-aliahmadch40/assets/easternMostStudyline');
var peiAOI = aoiFC.geometry();

Map.centerObject(peiAOI, 9);
Map.addLayer(peiAOI, {color: 'red'}, 'AOI (Shapefile)');


/***************************************
 * 2. Sentinel-2 SR cloud/snow/shadow masking (SCL-based)
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
  var ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI');
  return image.addBands(ndwi);
}


/***************************************
 * 4. Get yearly NDWI composite (same logic)
 ***************************************/
function getNDWI(year) {
  var start = ee.Date.fromYMD(year, 5, 1);
  var end   = ee.Date.fromYMD(year, 10, 31);

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
      ee.Image.constant(0).rename('NDWI').clip(peiAOI)
    )
  );

  // Return both NDWI and count
  return {
    ndwi: ndwi,
    count: count
  };
}


/***************************************
 * 5. Land mask and area (same threshold = 0.05)
 ***************************************/
var TH = 0.05;

function landAreaKm2FromNDWI(ndwiImg) {
  var landMask = ndwiImg.lt(TH); // land = NDWI < 0.05
  var area = landMask.selfMask()
    .multiply(ee.Image.pixelArea())
    .reduceRegion({
      reducer: ee.Reducer.sum(),
      geometry: peiAOI,
      scale: 10,
      maxPixels: 1e13
    })
    .getNumber('NDWI')
    .divide(1e6); // m² → km²

  return area;
}


/***************************************
 * 6. Annual results table: 2019–2025
 ***************************************/
var years = ee.List.sequence(2019, 2025);

var annualFC = ee.FeatureCollection(
  years.map(function(y) {
    y = ee.Number(y).toInt();

    var out = getNDWI(y);
    var ndwi = ee.Image(out.ndwi);
    var count = ee.Number(out.count);

    var landKm2 = landAreaKm2FromNDWI(ndwi);

    return ee.Feature(null, {
      Year: y,
      ImageCount: count,
      Land_km2: landKm2
    });
  })
);

// Print as a clean table (screenshot-ready)
print('✅ Annual NDWI Land Area (2019–2025) [screenshot-ready table]', annualFC);


/***************************************
 * 7. Year-to-year change table (ΔLand)
 ***************************************/
var annualList = annualFC.sort('Year').toList(annualFC.size());

var deltaFC = ee.FeatureCollection(
  ee.List.sequence(1, annualList.size().subtract(1)).map(function(i) {
    i = ee.Number(i);

    var curr = ee.Feature(annualList.get(i));
    var prev = ee.Feature(annualList.get(i.subtract(1)));

    var year = curr.getNumber('Year');
    var delta = curr.getNumber('Land_km2').subtract(prev.getNumber('Land_km2'));

    return ee.Feature(null, {
      Year: year,
      Delta_Land_km2: delta
    });
  })
);

// Print delta table (screenshot-ready)
print('✅ Year-to-year change (ΔLand km²)', deltaFC);


/***************************************
 * 8. One-time comparison: 2019 vs 2025 + overall change
 ***************************************/
var f2019 = ee.Feature(annualFC.filter(ee.Filter.eq('Year', 2019)).first());
var f2025 = ee.Feature(annualFC.filter(ee.Filter.eq('Year', 2025)).first());

var overall = ee.Feature(null, {
  StartYear: 2019,
  EndYear: 2025,
  Land_2019_km2: f2019.getNumber('Land_km2'),
  Land_2025_km2: f2025.getNumber('Land_km2'),
  OverallChange_km2: f2025.getNumber('Land_km2').subtract(f2019.getNumber('Land_km2'))
});

print('✅ Overall change (2019 → 2025)', overall);


/***************************************
 * 9. Optional: Nice chart for paper screenshots
 ***************************************/
var chart = ui.Chart.feature.byFeature(annualFC.sort('Year'), 'Year', 'Land_km2')
  .setOptions({
    title: 'Annual Land Area (NDWI<0.05) within AOI (2019–2025)',
    hAxis: {title: 'Year'},
    vAxis: {title: 'Land area (km²)'},
    pointSize: 4,
    lineWidth: 2
  });

print(chart);


/***************************************
 * 10. Optional: visualize NDWI + change for two selected years
 *     (keeps your original map layers idea)
 ***************************************/
var yrA = 2023;
var yrB = 2024;

var ndwiA_pack = getNDWI(yrA);
var ndwiB_pack = getNDWI(yrB);
var ndwiA = ee.Image(ndwiA_pack.ndwi);
var ndwiB = ee.Image(ndwiB_pack.ndwi);

Map.addLayer(ndwiA, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI ' + yrA);
Map.addLayer(ndwiB, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI ' + yrB);

var ndwiChange = ndwiB.subtract(ndwiA);
Map.addLayer(ndwiChange, {min:-0.5, max:0.5, palette:['red','white','blue']}, 'NDWI Change (' + yrB + ' - ' + yrA + ')');

/***************************************
 * 11. EXPORT ANNUAL TABLE (CSV)
 ***************************************/
Export.table.toDrive({
  collection: annualFC,
  description: 'NDWI_Annual_Results_2019_2025',
  fileFormat: 'CSV'
});


/***************************************
 * 12. EXPORT YEAR-TO-YEAR CHANGE TABLE
 ***************************************/
Export.table.toDrive({
  collection: deltaFC,
  description: 'NDWI_Yearly_Change_2019_2025',
  fileFormat: 'CSV'
});


/***************************************
 * 13. EXPORT OVERALL COMPARISON
 ***************************************/
Export.table.toDrive({
  collection: ee.FeatureCollection([overall]),
  description: 'NDWI_Overall_Change_2019_2025',
  fileFormat: 'CSV'
});
