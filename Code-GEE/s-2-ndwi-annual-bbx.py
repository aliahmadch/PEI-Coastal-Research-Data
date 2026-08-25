/***************************************
 * 1. Bounding box for PEI
 ***************************************/
var peiBBox = ee.Geometry.Rectangle([
  
  //westernmost
//-64.4670648, 46.293464200000004, -63.95558142, 47.154219399999995

  //western
//-63.95558142, 46.193464200000004, -63.44409804, 46.754219399999995
    
  //central
  //-63.44409804, 45.993464200000004, -62.932614660000006, 46.554219399999995
  
  //eastern
  -62.932614660000006, 45.893464200000004, -62.421131280000004, 46.554219399999995
  
  //easternmost
  //-62.421131280000004, 46.143464200000004, -61.9096479, 46.554219399999995

]);

Map.setCenter(-63.13, 46.35, 9);

Map.addLayer(peiBBox, {color: 'red'}, 'PEI Bounding Box');


/***************************************
 * 2. Sentinel-2 SR cloud/snow/shadow masking (SCL-based)
 *    Robust for NDWI + year-to-year comparison
 ***************************************/
function maskS2(image) {
  var scl = image.select('SCL');

  // Mask out problematic classes:
  // 1 = saturated/defective
  // 2 = dark area pixels
  // 3 = cloud shadow
  // 8 = cloud medium probability
  // 9 = cloud high probability
  // 10 = cirrus
  // 11 = snow/ice
  
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
 * 4. Get yearly NDWI composite (stable)
 *    - Wider summer window
 *    - Less strict cloudy% filter (mask handles pixels)
 *    - Median composite (more stable than mosaic for area stats)
 *    - Safe fallback if empty
 ***************************************/
function getNDWI(year) {
  var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(peiBBox)
    .filterDate(year + '-05-01', year + '-10-31')                 // ✅ wider window
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))          // ✅ not too strict
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  // Debug: how many images you really have
  print('Image count for ' + year + ':', col.size());

  // Median is more stable year-to-year than mosaic
  var ndwi = col.median().clip(peiBBox);

  // ✅ Safety: if empty (no bands), return a constant NDWI image
  ndwi = ee.Image(
    ee.Algorithms.If(
      ndwi.bandNames().size().gt(0),
      ndwi,
      ee.Image.constant(0).rename('NDWI').clip(peiBBox)
    )
  );

  return ndwi;
}


/***************************************
 * 5. NDWI for two years (edit years here)
 ***************************************/
var ndwiA = getNDWI(2024);
var ndwiB = getNDWI(2025);

Map.addLayer(ndwiA, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI 2020');
Map.addLayer(ndwiB, {min:-1, max:1, palette:['brown','white','blue']}, 'NDWI 2022');


/***************************************
 * 6. Land masks
 *    NOTE: using threshold 0.05 is more stable along coast than 0.00
 ***************************************/
var landA = ndwiA.lt(0.05);   // ✅ more stable than lte(0)
var landB = ndwiB.lt(0.05);


/***************************************
 * 7. Land area calculation (km²)
 *    IMPORTANT: mask the image so only land pixels count
 ***************************************/
function landArea(landMask) {
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

var areaA = landArea(landA);
var areaB = landArea(landB);

/***************************************
 * NEW: Land–Water PIXEL CONVERSION MAP
 * Clear logic:
 *  - Land -> Water  (erosion / loss)
 *  - Water -> Land  (accretion / gain)
 ***************************************/

// Water masks (inverse of land)
var waterA = landA.not();
var waterB = landB.not();

// Converted pixels
var landToWater = landA.and(waterB).selfMask(); // erosion: land in A becomes water in B
var waterToLand = waterA.and(landB).selfMask(); // accretion: water in A becomes land in B

// (Optional) stable background (faint)
var stableLand  = landA.and(landB).selfMask();
var stableWater = waterA.and(waterB).selfMask();

// --- Visualization (highly highlighted + colorful) ---
// 1) (Optional) stable background first (keep light colors)
Map.addLayer(stableWater, {palette: ['9ecae1']}, 'Stable Water (A & B)', false);
Map.addLayer(stableLand,  {palette: ['c7e9c0']}, 'Stable Land (A & B)',  false);

// 2) conversions on top (very strong colors)
Map.addLayer(landToWater, {palette: ['ff00ff']}, 'CHANGE: Land → Water (Erosion)', true);
Map.addLayer(waterToLand, {palette: ['00ffff']}, 'CHANGE: Water → Land (Accretion)', true);

// 3) If you want ONE single categorical change layer (optional)
var changeClass = ee.Image(0)
  .where(landToWater.mask(), 1)   // 1 = erosion
  .where(waterToLand.mask(), 2)   // 2 = accretion
  .updateMask(landToWater.mask().or(waterToLand.mask()));

Map.addLayer(
  changeClass,
  {min: 1, max: 2, palette: ['ff00ff', '00ffff']},
  'Converted Pixels Only (1=Erosion, 2=Accretion)',
  false
);



/***************************************
 * 8. NDWI Change
 ***************************************/
var ndwiChange = ndwiB.subtract(ndwiA);
Map.addLayer(
  ndwiChange,
  {min:-0.5, max:0.5, palette:['red','white','blue']},
  'NDWI Change (B - A)'
);


/***************************************
 * 9. Print results
 ***************************************/
print('Land Area 2020 (km²):', areaA);
print('Land Area 2022 (km²):', areaB);
print('Land Area Difference (km²):', areaB.subtract(areaA));
