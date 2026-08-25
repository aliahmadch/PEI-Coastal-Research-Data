/*****************************************************
 * VALIDATION CELL (PATCH-WISE, 2022 vs 2023) - HARD MODE
 * Internal validation = year-to-year agreement INCLUDING SHORELINE RISK ZONE
 * - SAME methodology: S2_SR_HARMONIZED + SCL mask + NDWI + TH=0.05
 * - Samples 3 strata from 2022:
 *    (1) stable land
 *    (2) stable water
 *    (3) shoreline-risk band (mixed zone)
 * - Compares 2023 classification at same points
 *****************************************************/

// ------------------------------
// Patch bounding boxes
// ------------------------------
var patches = [
  //{name: 'westernmost',     bbox: ee.Geometry.Rectangle([-64.4670648, 46.293464200000004, -63.95558142, 47.154219399999995])},
  //{name: 'western', bbox: ee.Geometry.Rectangle([-63.95558142, 46.193464200000004, -63.44409804, 46.754219399999995])
  {name: 'central',     bbox: ee.Geometry.Rectangle([-63.44409804, 45.993464200000004, -62.932614660000006, 46.554219399999995])},
  //{name: 'eastern',     bbox: ee.Geometry.Rectangle([-62.932614660000006, 45.893464200000004, -62.421131280000004, 46.554219399999995])},
  //{name: 'easternmost', bbox: ee.Geometry.Rectangle([-62.421131280000004, 46.143464200000004, -61.9096479, 46.554219399999995])},
  
];

// ------------------------------
// SAME functions (do not change methodology)
// ------------------------------
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

function addNDWI(image) {
  var ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI');
  return image.addBands(ndwi);
}

function getNDWI_forBBox(year, bbox) {
  var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(bbox)
    .filterDate(year + '-05-01', year + '-10-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  print('Image count ' + year + ':', col.size());

  var ndwi = col.median().clip(bbox);

  ndwi = ee.Image(
    ee.Algorithms.If(
      ndwi.bandNames().size().gt(0),
      ndwi,
      ee.Image.constant(0).rename('NDWI').clip(bbox)
    )
  );

  return ndwi;
}

// ------------------------------
// Validation settings
// ------------------------------
var YEAR_A = 2022;
var YEAR_B = 2023;
var TH = 0.05;

// Pixels for "stable" erosion away from edge (optional)
var SAFE_PIXELS = 3;      // ~30m
// Pixels for shoreline risk band thickness around shoreline
var RISK_PIXELS = 2;      // ~20m band each side (increase to 3-5 for harder)

// Points per stratum per patch
var N_STABLE_LAND  = 25;
var N_STABLE_WATER = 25;
var N_RISK         = 40;  // more points near shoreline = harder validation

// ------------------------------
// Helper: build risk band around 2022 shoreline boundary
// shoreline boundary ≈ where water/land changes in 2022 classification
// We'll approximate boundary by dilating water and land and intersecting.
// ------------------------------
function makeRiskBand(waterA) {
  // waterA is 0/1 image (not masked)
  var w = waterA.selfMask();
  var l = waterA.not().selfMask();

  // Dilate both; overlap zone approximates shoreline mixing band
  var wDil = w.focal_max(RISK_PIXELS);
  var lDil = l.focal_max(RISK_PIXELS);

  // Overlap region = near the boundary
  var risk = wDil.and(lDil).selfMask().rename('risk');
  return risk;
}

// ------------------------------
// Validate one patch
// ------------------------------
function validatePatch(patchName, bbox) {
  var ndwiA = getNDWI_forBBox(YEAR_A, bbox);
  var ndwiB = getNDWI_forBBox(YEAR_B, bbox);

  // Water classification (same threshold)
  var waterA = ndwiA.gt(TH).rename('classA');  // 1=water, 0=land
  var waterB = ndwiB.gt(TH).rename('classB');  // prediction

  // Stable zones (still included, but we ALSO add risky shoreline points)
  var stableWaterA = waterA.selfMask().focal_min(SAFE_PIXELS).rename('stableWaterA');
  var stableLandA  = waterA.not().selfMask().focal_min(SAFE_PIXELS).rename('stableLandA');

  // Risk band near shoreline (mixed zone)
  var riskBand = makeRiskBand(waterA).rename('riskBand');

  // Build ONE sampling-class band for stratified sampling:
  // 0 = stable land, 1 = stable water, 2 = risk band
  var strata = ee.Image(0).rename('strata')
    .where(stableWaterA.mask(), 1)
    .where(riskBand.mask(), 2)
    .updateMask(stableLandA.mask().or(stableWaterA.mask()).or(riskBand.mask()));

  // Sample points from each stratum (2022-based strata)
  var samples = strata
    .addBands(waterA)  // truth classA (2022 water/land)
    .addBands(waterB)  // predicted classB (2023 water/land)
    .stratifiedSample({
      numPoints: 0,
      classBand: 'strata',
      classValues: [0, 1, 2],
      classPoints: [N_STABLE_LAND, N_STABLE_WATER, N_RISK],
      region: bbox,
      scale: 10,
      geometries: true,
      seed: 1
    })
    .map(function(f) {
      // Add readable label
      var s = ee.Number(f.get('strata'));
      var label = ee.String(
        ee.Algorithms.If(s.eq(0), 'stable_land',
          ee.Algorithms.If(s.eq(1), 'stable_water', 'risk_shoreline')
        )
      );
      return f.set({patch: patchName, yearA: YEAR_A, yearB: YEAR_B, strata_label: label});
    });

  // Confusion matrix for ALL samples: truth=2022 classA, predicted=2023 classB
  var emAll = samples.errorMatrix('classA', 'classB');
  var accAll = emAll.accuracy();
  var kappaAll = emAll.kappa();

  // Accuracy ONLY within risk band (optional, very useful)
  var riskOnly = samples.filter(ee.Filter.eq('strata', 2));
  var emRisk = riskOnly.errorMatrix('classA', 'classB');
  var accRisk = emRisk.accuracy();

  // Summary feature
  var summary = ee.Feature(null, {
    patch: patchName,
    yearA: YEAR_A,
    yearB: YEAR_B,
    n_total: samples.size(),
    n_risk: riskOnly.size(),
    accuracy_all: accAll,
    kappa_all: kappaAll,
    accuracy_risk_only: accRisk
  });

  // Print per patch
  print('--- ' + patchName + ' (2022 vs 2023, includes shoreline risk) ---');
  print('Counts:', summary);
  print('Confusion matrix ALL:', emAll);
  print('Accuracy ALL:', accAll, 'Kappa:', kappaAll);
  print('Confusion matrix RISK only:', emRisk);
  print('Accuracy RISK only:', accRisk);

  return {summary: summary, samples: samples, riskBand: riskBand};
}

// ------------------------------
// Run patch-by-patch and combine
// ------------------------------
var summaries = [];
var allSamples = [];

patches.forEach(function(p) {
  var out = validatePatch(p.name, p.bbox);
  summaries.push(out.summary);
  allSamples.push(out.samples);

  // Visualize only for easternmost patch
  if (p.name === 'easternmost') {
    Map.addLayer(p.bbox, {color: 'yellow'}, 'Patch bbox: ' + p.name);
    Map.addLayer(out.riskBand, {palette:['magenta']}, 'Risk band (shoreline zone)');
    Map.addLayer(out.samples, {color: 'lime'}, 'Validation points: ' + p.name);
  }
  if (p.name === 'central') {
    Map.addLayer(p.bbox, {color: 'yellow'}, 'Patch bbox: ' + p.name);
    Map.addLayer(out.riskBand, {palette:['magenta']}, 'Risk band (shoreline zone)');
    Map.addLayer(out.samples, {color: 'lime'}, 'Validation points: ' + p.name);
  }
});

var summariesFC = ee.FeatureCollection(summaries);
var samplesFC = ee.FeatureCollection(allSamples).flatten();

print('✅ Combined validation summaries:', summariesFC);

// Export summary table
Export.table.toDrive({
  collection: summariesFC,
  description: 'pei_internal_validation_hardmode_2022_vs_2023_patchwise',
  fileFormat: 'CSV'
});

// Optional: export sample points (bigger file)
// Export.table.toDrive({
//   collection: samplesFC,
//   description: 'pei_internal_validation_points_hardmode_2022_vs_2023_patchwise',
//   fileFormat: 'CSV'
// });
