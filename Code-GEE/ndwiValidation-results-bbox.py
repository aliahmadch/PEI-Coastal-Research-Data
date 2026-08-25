/*****************************************************
 * VALIDATION CELL (PATCH-WISE, 2022 vs 2023) - HARD MODE
 *
 * Metrics:
 * Accuracy, Accuracy 95% Wilson CI,
 * Precision, Recall, F1, and Kappa
 *
 * Separates:
 * ALL vs STABLE (inland) vs RISK (coastal zone)
 *
 * Original methodology unchanged.
 *****************************************************/


// ====================================================
// 1. PATCH BOUNDING BOXES
// ====================================================

var patches = [

   {
     name: 'westernmost',
     bbox: ee.Geometry.Rectangle([
       -64.4670648,
       46.293464200000004,
      -63.95558142,
       47.154219399999995
     ])
   },

  /*{
     name: 'western',
     bbox: ee.Geometry.Rectangle([
       -63.95558142,
       46.193464200000004,
      -63.44409804,
       46.754219399999995
     ])
   },

  /* {
     name: 'central',
     bbox: ee.Geometry.Rectangle([
       -63.44409804,
       45.993464200000004,
       -62.932614660000006,
       46.554219399999995
     ])
   },

  {
    name: 'eastern',
    bbox: ee.Geometry.Rectangle([
      -62.932614660000006,
      45.893464200000004,
      -62.421131280000004,
      46.554219399999995
    ])
  }*/

   /*{
    name: 'easternmost',
    bbox: ee.Geometry.Rectangle([
       -62.421131280000004,
       46.143464200000004,
       -61.9096479,
       46.554219399999995
     ])
   }*/

];


// ====================================================
// 2. SENTINEL-2 PROCESSING FUNCTIONS
// Original methodology unchanged
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


function addNDWI(image) {

  var ndwi = image
    .normalizedDifference(['B3', 'B8'])
    .rename('NDWI');

  return image.addBands(ndwi);
}


function getNDWI_forBBox(year, bbox) {

  var col = ee.ImageCollection(
      'COPERNICUS/S2_SR_HARMONIZED'
    )
    .filterBounds(bbox)
    .filterDate(
      year + '-05-01',
      year + '-10-31'
    )
    .filter(
      ee.Filter.lt(
        'CLOUDY_PIXEL_PERCENTAGE',
        60
      )
    )
    .map(maskS2)
    .map(addNDWI)
    .select('NDWI');

  print(
    'Image count ' + year + ':',
    col.size()
  );

  var ndwi = col
    .median()
    .clip(bbox);

  ndwi = ee.Image(
    ee.Algorithms.If(
      ndwi.bandNames().size().gt(0),

      ndwi,

      ee.Image
        .constant(0)
        .rename('NDWI')
        .clip(bbox)
    )
  );

  return ndwi;
}


// ====================================================
// 3. VALIDATION SETTINGS
// ====================================================

var YEAR_A = 2022;
var YEAR_B = 2023;

// Fixed NDWI threshold used in the manuscript
var TH = 0.05;

var SAFE_PIXELS = 3;
var RISK_PIXELS = 2;

var N_STABLE_LAND  = 25;
var N_STABLE_WATER = 25;
var N_RISK         = 40;


// ====================================================
// 4. CREATE SHORELINE-RISK BAND
// Original methodology unchanged
// ====================================================

function makeRiskBand(waterA) {

  var w = waterA
    .selfMask();

  var l = waterA
    .not()
    .selfMask();

  var wDil = w.focal_max(
    RISK_PIXELS
  );

  var lDil = l.focal_max(
    RISK_PIXELS
  );

  return wDil
    .and(lDil)
    .selfMask()
    .rename('risk');
}


// ====================================================
// 5. NEW: WILSON 95% CONFIDENCE INTERVAL
//
// successes = correct classifications, TP + TN
// total     = total validation samples
//
// Output example:
// [0.848, 0.962]
// ====================================================

function wilsonCI95(successes, total) {

  var k = ee.Number(successes);
  var n = ee.Number(total);

  // z-score for a 95% confidence interval
  var z = ee.Number(1.96);
  var zSquared = z.pow(2);

  var proportion = k.divide(n);

  var denominator = ee.Number(1)
    .add(
      zSquared.divide(n)
    );

  var centre = proportion
    .add(
      zSquared.divide(
        n.multiply(2)
      )
    )
    .divide(denominator);

  var insideSquareRoot = proportion
    .multiply(
      ee.Number(1)
        .subtract(proportion)
    )
    .divide(n)
    .add(
      zSquared.divide(
        ee.Number(4)
          .multiply(
            n.pow(2)
          )
      )
    );

  var halfWidth = z
    .multiply(
      insideSquareRoot.sqrt()
    )
    .divide(denominator);

  var lowerLimit = centre
    .subtract(halfWidth);

  var upperLimit = centre
    .add(halfWidth);

  // Return one screenshot-ready/export-ready value
  return ee.String('[')
    .cat(
      lowerLimit.format('%.3f')
    )
    .cat(', ')
    .cat(
      upperLimit.format('%.3f')
    )
    .cat(']');
}


// ====================================================
// 6. COMPUTE METRICS FROM CONFUSION MATRIX
//
// Positive class = WATER (1)
//
// ConfusionMatrix:
// rows    = truth
// columns = prediction
//
// [[TN, FP],
//  [FN, TP]]
//
// Added output:
// accuracy_ci95
// ====================================================

function metricsFromCM(cm) {

  cm = ee.ConfusionMatrix(cm);

  var arr = ee.Array(
    cm.array()
  );

  var tn = ee.Number(
    arr.get([0, 0])
  );

  var fp = ee.Number(
    arr.get([0, 1])
  );

  var fn = ee.Number(
    arr.get([1, 0])
  );

  var tp = ee.Number(
    arr.get([1, 1])
  );

  var precision = tp.divide(
    tp.add(fp)
  );

  var recall = tp.divide(
    tp.add(fn)
  );

  var f1 = precision
    .multiply(recall)
    .multiply(2)
    .divide(
      precision.add(recall)
    );

  // Handle divide-by-zero safely
  precision = ee.Number(
    ee.Algorithms.If(
      tp.add(fp).neq(0),
      precision,
      0
    )
  );

  recall = ee.Number(
    ee.Algorithms.If(
      tp.add(fn).neq(0),
      recall,
      0
    )
  );

  f1 = ee.Number(
    ee.Algorithms.If(
      precision.add(recall).neq(0),
      f1,
      0
    )
  );

  // ------------------------------------------
  // NEW: accuracy/agreement 95% Wilson CI
  // ------------------------------------------

  var correct = tp.add(tn);

  var total = tp
    .add(tn)
    .add(fp)
    .add(fn);

  var accuracyCI95 = wilsonCI95(
    correct,
    total
  );

  return ee.Dictionary({

    tn: tn,
    fp: fp,
    fn: fn,
    tp: tp,

    precision: precision,
    recall: recall,
    f1: f1,

    // One additional output column
    accuracy_ci95: accuracyCI95
  });
}


// ====================================================
// 7. VALIDATE ONE PATCH
// ====================================================

function validatePatch(
  patchName,
  bbox
) {

  var ndwiA = getNDWI_forBBox(
    YEAR_A,
    bbox
  );

  var ndwiB = getNDWI_forBBox(
    YEAR_B,
    bbox
  );

  // 2022 = truth/reference classification
  var waterA = ndwiA
    .gt(TH)
    .rename('classA');

  // 2023 = predicted/comparison classification
  var waterB = ndwiB
    .gt(TH)
    .rename('classB');


  // ------------------------------------------
  // Stable inland land and water
  // ------------------------------------------

  var stableWaterA = waterA
    .selfMask()
    .focal_min(SAFE_PIXELS)
    .rename('stableWaterA');

  var stableLandA = waterA
    .not()
    .selfMask()
    .focal_min(SAFE_PIXELS)
    .rename('stableLandA');


  // ------------------------------------------
  // Coastal-risk band
  // ------------------------------------------

  var riskBand = makeRiskBand(
    waterA
  ).rename('riskBand');


  // ------------------------------------------
  // Strata:
  //
  // 0 = stable land
  // 1 = stable water
  // 2 = risk shoreline
  // ------------------------------------------

  var strata = ee.Image(0)
    .rename('strata')

    .where(
      stableWaterA.mask(),
      1
    )

    .where(
      riskBand.mask(),
      2
    )

    .updateMask(
      stableLandA.mask()
        .or(
          stableWaterA.mask()
        )
        .or(
          riskBand.mask()
        )
    );


  // ------------------------------------------
  // Stratified samples
  // Original methodology unchanged
  // ------------------------------------------

  var samples = strata

    .addBands(waterA)
    .addBands(waterB)

    .stratifiedSample({

      numPoints: 0,

      classBand: 'strata',

      classValues: [
        0,
        1,
        2
      ],

      classPoints: [
        N_STABLE_LAND,
        N_STABLE_WATER,
        N_RISK
      ],

      region: bbox,

      scale: 10,

      geometries: true,

      seed: 1
    })

    .map(function(feature) {

      var stratum = ee.Number(
        feature.get('strata')
      );

      var label = ee.String(

        ee.Algorithms.If(

          stratum.eq(0),

          'stable_land',

          ee.Algorithms.If(

            stratum.eq(1),

            'stable_water',

            'risk_shoreline'
          )
        )
      );

      return feature.set({

        patch: patchName,

        yearA: YEAR_A,

        yearB: YEAR_B,

        strata_label: label
      });
    });


  // ==================================================
  // METRICS: ALL
  // 90 samples:
  // 25 stable land + 25 stable water + 40 risk
  // ==================================================

  var emAll = samples.errorMatrix(
    'classA',
    'classB'
  );

  var accAll = emAll.accuracy();

  var kapAll = emAll.kappa();

  var mAll = metricsFromCM(
    emAll
  );


  // ==================================================
  // METRICS: RISK COASTAL
  // Stratum 2 only: 40 samples
  // ==================================================

  var riskOnly = samples.filter(
    ee.Filter.eq(
      'strata',
      2
    )
  );

  var emRisk = riskOnly.errorMatrix(
    'classA',
    'classB'
  );

  var accRisk = emRisk.accuracy();

  var kapRisk = emRisk.kappa();

  var mRisk = metricsFromCM(
    emRisk
  );


  // ==================================================
  // METRICS: STABLE INLAND
  // Strata 0 and 1: 50 samples
  // ==================================================

  var stableOnly = samples.filter(
    ee.Filter.inList(
      'strata',
      [0, 1]
    )
  );

  var emStable = stableOnly.errorMatrix(
    'classA',
    'classB'
  );

  var accStable = emStable.accuracy();

  var kapStable = emStable.kappa();

  var mStable = metricsFromCM(
    emStable
  );


  // ==================================================
  // SCREENSHOT-READY TABLE ROWS
  //
  // New output property:
  // accuracy_ci95
  // ==================================================

  var rowAll = ee.Feature(

    null,

    ee.Dictionary({

      patch: patchName,

      zone: 'ALL',

      yearA: YEAR_A,

      yearB: YEAR_B,

      n_samples: samples.size(),

      accuracy: accAll,

      kappa: kapAll

    }).combine(
      mAll,
      true
    )
  );


  var rowStable = ee.Feature(

    null,

    ee.Dictionary({

      patch: patchName,

      zone: 'STABLE (inland)',

      yearA: YEAR_A,

      yearB: YEAR_B,

      n_samples: stableOnly.size(),

      accuracy: accStable,

      kappa: kapStable

    }).combine(
      mStable,
      true
    )
  );


  var rowRisk = ee.Feature(

    null,

    ee.Dictionary({

      patch: patchName,

      zone: 'RISK (coastal)',

      yearA: YEAR_A,

      yearB: YEAR_B,

      n_samples: riskOnly.size(),

      accuracy: accRisk,

      kappa: kapRisk

    }).combine(
      mRisk,
      true
    )
  );


  var metricsTable = ee.FeatureCollection([

    rowAll,

    rowStable,

    rowRisk
  ]);


  // ==================================================
  // PRINT TABLES AND MATRICES
  // ==================================================

  print(
    '=============================='
  );

  print(
    '✅ Validation metrics table with accuracy 95% CI: '
      + patchName,
    metricsTable
  );

  print(
    'Confusion matrix ALL '
      + '(truth rows vs predicted columns):',
    emAll
  );

  print(
    'Confusion matrix STABLE:',
    emStable
  );

  print(
    'Confusion matrix RISK:',
    emRisk
  );

  print(
    '=============================='
  );


  return {

    metricsTable: metricsTable,

    samples: samples,

    riskBand: riskBand,

    bbox: bbox
  };
}


// ====================================================
// 8. RUN ENABLED PATCHES
// ====================================================

var allTables = [];

var allSamples = [];


patches.forEach(function(patch) {

  var output = validatePatch(

    patch.name,

    patch.bbox
  );


  allTables.push(

    output.metricsTable
  );


  allSamples.push(

    output.samples
  );


  // Visualization unchanged

  Map.addLayer(

    patch.bbox,

    {
      color: 'yellow'
    },

    'Patch bbox: ' + patch.name
  );


  Map.addLayer(

    output.riskBand,

    {
      palette: ['magenta']
    },

    'Risk band (shoreline zone): '
      + patch.name
  );


  Map.addLayer(

    output.samples,

    {
      color: 'lime'
    },

    'Validation points: '
      + patch.name
  );
});


// ====================================================
// 9. COMBINE TABLES
// ====================================================

var metricsFC = ee.FeatureCollection(
  allTables
).flatten();


var samplesFC = ee.FeatureCollection(
  allSamples
).flatten();


print(

  '✅ Combined metrics tables '
    + '(ALL, STABLE, and RISK) '
    + 'with 95% confidence intervals',

  metricsFC
);


// ====================================================
// 10. EXPORT METRICS TABLE
//
// CSV will now include:
// accuracy_ci95
// ====================================================

Export.table.toDrive({

  collection: metricsFC,

  description:
    'pei_internal_validation_metrics_all_stable_risk_2022_vs_2023_with_95CI',

  fileNamePrefix:
    'pei_internal_validation_metrics_all_stable_risk_2022_vs_2023_with_95CI',

  fileFormat: 'CSV'
});


// ====================================================
// OPTIONAL: EXPORT VALIDATION POINTS
// ====================================================

// Export.table.toDrive({
//
//   collection: samplesFC,
//
//   description:
//     'pei_internal_validation_points_hardmode_2022_vs_2023',
//
//   fileNamePrefix:
//     'pei_internal_validation_points_hardmode_2022_vs_2023',
//
//   fileFormat: 'CSV'
// });