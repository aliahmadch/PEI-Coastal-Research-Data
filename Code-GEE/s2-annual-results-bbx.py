/***************************************
 * 1. Bounding box for PEI (easternmost)
 ***************************************/
var peiBBox = ee.Geometry.Rectangle([
  
  //westernmost
-64.4670648, 46.293464200000004, -63.95558142, 47.154219399999995

  //western
//-63.95558142, 46.193464200000004, -63.44409804, 46.754219399999995
    
  //central
  //-63.44409804, 45.993464200000004, -62.932614660000006, 46.554219399999995
  
  //eastern
  //-62.932614660000006, 45.893464200000004, -62.421131280000004, 46.554219399999995
  
  //easternmost
  //-62.421131280000004, 46.143464200000004, -61.9096479, 46.554219399999995

]);
var peiBBox1 = ee.Geometry.Rectangle([
  
  //westernmost
-64.4670648, 46.293464200000004, -63.95558142, 47.154219399999995
]);
var peiBBox2 = ee.Geometry.Rectangle([
  
   //western
-63.95558142, 46.193464200000004, -63.44409804, 46.754219399999995
]);
var peiBBox3 = ee.Geometry.Rectangle([
  
  //central
  -63.44409804, 45.993464200000004, -62.932614660000006, 46.554219399999995
]);
var peiBBox4 = ee.Geometry.Rectangle([
  
  //eastern
  -62.932614660000006, 45.893464200000004, -62.421131280000004, 46.554219399999995
]);

Map.setCenter(-62.15, 46.35, 9);
Map.addLayer(peiBBox, {color: 'red'}, 'PEI Bounding Box');
//Map.addLayer(peiBBox1, {color: 'red'}, 'PEI Bounding Box');
//Map.addLayer(peiBBox2, {color: 'red'}, 'PEI Bounding Box');
//Map.addLayer(peiBBox3, {color: 'red'}, 'PEI Bounding Box');
//Map.addLayer(peiBBox4, {color: 'red'}, 'PEI Bounding Box');


/***************************************
 * 2. Sentinel-2 SR cloud/snow/shadow masking (SCL-based)
 *    (same logic)
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
 * 3. NDWI band (same logic)
 ***************************************/
function addNDWI(image) {
  var ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI');
  return image.addBands(ndwi);
}


/***************************************
 * 4. Get yearly NDWI composite (same logic)
 *    IMPORTANT: NO print() inside (fixes mapped-function error)
 ***************************************/
function getNDWI(year) {
  var start = ee.Date.fromYMD(year, 5, 1);
  var end   = ee.Date.fromYMD(year, 10, 31);

  var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(peiBBox)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  var count = col.size();

  var ndwi = col.median().clip(peiBBox);

  // Safety fallback (if empty)
  ndwi = ee.Image(
    ee.Algorithms.If(
      ndwi.bandNames().size().gt(0),
      ndwi,
      ee.Image.constant(0).rename('NDWI').clip(peiBBox)
    )
  );

  return { ndwi: ndwi, count: count };
}


/***************************************
 * 5. Land mask + area (same threshold logic)
 ***************************************/
var TH = 0.05;

function landAreaKm2FromNDWI(ndwiImg) {
  var landMask = ndwiImg.lt(TH); // land = NDWI < 0.05
  return landMask.selfMask()
    .multiply(ee.Image.pixelArea())
    .reduceRegion({
      reducer: ee.Reducer.sum(),
      geometry: peiBBox,
      scale: 10,
      maxPixels: 1e13
    })
    .getNumber('NDWI')
    .divide(1e6); // m² → km²
}


/***************************************
 * 6. Annual results table: 2019–2025 (screenshot-ready)
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

print('✅ Annual NDWI Land Area (BBox, 2019–2025)', annualFC);


/***************************************
 * 7. Year-to-year change table (ΔLand km²)
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

print('✅ Year-to-year change (BBox, ΔLand km²)', deltaFC);


/***************************************
 * 8. One-time comparison: 2019 vs 2025
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

print('✅ Overall change (BBox, 2019 → 2025)', overall);


/***************************************
 * 9. Optional: chart (nice for screenshot in paper)
 ***************************************/
var chart = ui.Chart.feature.byFeature(annualFC.sort('Year'), 'Year', 'Land_km2')
  .setOptions({
    title: 'Annual Land Area (NDWI<0.05) within BBox (2019–2025)',
    hAxis: {title: 'Year'},
    vAxis: {title: 'Land area (km²)'},
    pointSize: 4,
    lineWidth: 2
  });
print(chart);


/***************************************
 * 10. Map symbology: show NDWI + NDWI change (pick any two years)
 ***************************************/
var yrA = 2019;
var yrB = 2020;

var packA = getNDWI(yrA);
var packB = getNDWI(yrB);

var ndwiA = ee.Image(packA.ndwi);
var ndwiB = ee.Image(packB.ndwi);

Map.addLayer(ndwiA, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI ' + yrA);
Map.addLayer(ndwiB, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI ' + yrB);

var ndwiChange = ndwiB.subtract(ndwiA);
Map.addLayer(
  ndwiChange,
  {min:-0.5, max:0.5, palette:['red','white','blue']},
  'NDWI Change (' + yrB + ' - ' + yrA + ')'
);

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

