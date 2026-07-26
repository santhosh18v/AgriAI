# Model Evaluation — Milestone M5

## Purpose

M5 has two jobs: (1) select a confidence/uncertainty threshold using
**validation predictions only**, before any test label is read, and (2)
evaluate the frozen M4 checkpoint on `test.csv` **exactly once**, as the
final, descriptive performance report for this baseline. This document does
not claim production readiness. **No M6 (FastAPI service) work has started.**

## Validation vs. test set — why the test set is used only once

`val.csv` was already used repeatedly during M4 for model/checkpoint
selection (best-epoch selection by validation macro-F1). Because of that
repeated use, validation metrics carry a small "we picked the best epoch on
this set" optimism bias. `test.csv` was never touched by M4 or by any part
of M5's threshold selection — it is the one dataset slice that has not
influenced any modeling decision, so it is evaluated exactly once, after
every decision (checkpoint, threshold) is already frozen, to give an
unbiased read of generalization. Re-evaluating `test.csv` again in a future
milestone, or changing the model/threshold in response to these numbers,
would silently reintroduce the same bias `test.csv` exists to avoid.

`ml-service/training/evaluate.py` enforces this mechanically: `--mode
final-test` requires `--confirm-final-test-evaluation` and a pre-frozen
`--apply-threshold`, refuses any manifest not literally named `test.csv`,
and verifies both the manifest and checkpoint SHA-256 before loading any
data.

## Threshold-selection rule (predeclared, validation-only)

Recorded verbatim in `training/confidence_policy_v1.json`'s
`selection_rule` field and in `training/select_threshold.py`:

Candidate grid: fixed values 0.50–0.99 in steps of 0.01 (50 candidates),
evaluated on **validation predictions only**. A candidate threshold passes
iff:

- accepted-prediction accuracy ≥ 99.0%
- overall coverage ≥ 90%
- every class retains ≥ 80% coverage
- every class retains ≥ 15 accepted validation images
- no class has zero accepted support

Among passing thresholds: (1) prefer highest overall coverage, (2) tie-break
on higher selective macro-F1, (3) then lower threshold, (4) then
deterministic numeric ordering. If no candidate passes, no threshold is
selected — the Pareto frontier over (coverage, selective accuracy) is
reported instead and `confidence_policy_v1.json` is written with
`status: "blocked_threshold_selection"`.

**`select_threshold.py select` reads only a validation-predictions CSV — it
has no test-manifest argument of any kind.** Test labels were not used,
read, or referenced at any point during threshold selection
(`confidence_policy_v1.json`'s `test_labels_used_for_threshold_selection:
false`).

## Selected threshold (M5 result)

| | Value |
|---|---|
| Selected threshold | **0.50** (the lowest grid value) |
| Status | `approved_for_test_application` |
| Validation coverage | 0.999 (1000/1001) |
| Validation selective accuracy | 0.994 |
| Validation selective macro-F1 | 0.9949 |

At threshold 0.50 the M4 checkpoint's validation predictions already clear
every mandatory constraint (99%+ accepted accuracy, ≥90% coverage, ≥80%
per-class coverage, ≥15 accepted images per class) — the lowest grid rung
already passes because validation errors are rare (6 of 1001) and none of
them happen to sit at very low confidence. This is a legitimate outcome of
the predeclared rule, not a relaxed or hand-picked value; per-class
validation coverage was 100% for five of six classes and 99.3% for Tomato
Early Blight. Full detail: `threshold_candidates.json` (all 50 candidates),
`threshold_selection.json`.

## Raw frozen test metrics (test.csv, evaluated once)

991 samples, checkpoint epoch 5 (`best_model.pt`, SHA-256
`24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081`).

| Metric | Value |
|---|---|
| Accuracy | 0.98890 |
| Macro precision | 0.98078 |
| Macro recall | 0.98815 |
| Macro F1 | 0.98412 |
| Weighted F1 | 0.98890 |
| Loss (unweighted CE) | 0.03917 |

Per-class (precision / recall / F1 / support):

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| Tomato Healthy | 0.9958 | 1.0000 | 0.9979 | 238 |
| Tomato Early Blight | 0.9865 | 0.9865 | 0.9865 | 148 |
| Tomato Late Blight | 0.9793 | 0.9965 | 0.9878 | 285 |
| Potato Healthy | 0.9231 | 1.0000 | 0.9600 | 24 |
| Potato Early Blight | 1.0000 | 0.9865 | 0.9932 | 148 |
| Potato Late Blight | 1.0000 | 0.9595 | 0.9793 | 148 |

Confusion matrix: `test_confusion_matrix.json`. Test macro-F1 (0.984) is
modestly lower than validation macro-F1 (0.994) — expected, since validation
was used for checkpoint selection and test was not; this gap is a normal,
disclosed generalization estimate, not evidence of a pipeline error.

## Thresholded test metrics (frozen threshold = 0.50, applied once)

| Metric | Value |
|---|---|
| Coverage | 1.000 (991/991 accepted) |
| Selective accuracy | 0.98890 |
| Selective macro-F1 | 0.98412 |
| Accepted errors | 11 |
| Rejected errors | 0 |
| Rejected correct predictions | 0 |

At threshold 0.50 the model accepted every test image — coverage is 100%
and thresholded metrics are numerically identical to the raw metrics above,
because none of the 11 test errors happened to fall below 0.50 confidence
(the lowest error confidence was 0.504). **This means the 0.50 threshold
provides no actual filtering on this test set** — it does not reject any of
the model's mistakes. This is disclosed, not hidden: at this validation-only
selected threshold, low-confidence rejection is not currently doing
protective work on unseen data, and several of the test errors are
high-confidence, some extremely so (see Error analysis below). The
threshold was **not** changed after seeing this — per the predeclared rule
and standing M5 policy, the frozen threshold is applied and reported as-is.

Per-class threshold-applied coverage/accuracy: identical to the per-class
raw metrics above (100% coverage on all six classes at this threshold); see
`test_metrics_thresholded.json` for full per-class detail.

## Confidence intervals (95%, bootstrap, seed 42, 2000 resamples)

Group-aware (resamples `group_key`, the more meaningful result — images
within one physical leaf are correlated) vs. image-level (resamples rows
independently, reported for comparison only):

| Metric | Group-aware 95% CI | Image-level 95% CI |
|---|---|---|
| Raw accuracy | [0.9817, 0.9949] | [0.9818, 0.9950] |
| Raw macro-F1 | [0.9590, 0.9943] | [0.9701, 0.9945] |
| Thresholded selective accuracy | [0.9817, 0.9949] | [0.9818, 0.9950] |
| Thresholded coverage | [1.0, 1.0] | [1.0, 1.0] |

Group-aware and image-level intervals are close here because 482 leaf groups
back only 991 images (most groups are small), but the group-aware
macro-F1 interval is visibly wider on the low end (0.959 vs 0.970) — that
gap is the correlation effect the group-aware method exists to capture, and
it is the interval that should be trusted over the image-level one. Full
detail: `m5_summary.json`.

## Calibration analysis (raw softmax confidence, no calibration fitted)

Per the M5 instructions' "keep the simplest defensible approach": only raw
maximum-softmax-probability confidence was analyzed. No temperature scaling
or other calibration was fitted — the raw baseline is used unmodified as
the threshold input.

| Metric | Value |
|---|---|
| Expected calibration error (10 bins) | 0.00249 |
| Maximum calibration error | 0.1052 |
| Brier score | 0.00805 |
| Mean confidence, correct predictions | 0.9912 |
| Mean confidence, incorrect predictions | 0.7160 |

The observed in-distribution test-set ECE and Brier score were low in this
single evaluation, but this does not establish real-world calibration:
incorrect predictions are not reliably low-confidence in this sample —
several errors sit above 0.70, and the single highest-confidence error is at
0.99999976 (see below). This is exactly why the 0.50 threshold rejected none
of the errors. A single 991-image, in-distribution, non-adversarial test set
is not sufficient evidence to claim the model "is calibrated"; see
[Confidence and deployment safety notes](#confidence-and-deployment-safety-notes)
below. Full reliability-bin table: `confidence_analysis.json`.

## Error analysis

11 raw test errors out of 991 (all 11 remain accepted at the frozen 0.50
threshold; 0 were correctly rejected as uncertain; 0 correct predictions
were incorrectly rejected).

Confusion pairs (count):

| Pair | Count |
|---|---:|
| Potato Late Blight → Tomato Late Blight | 4 |
| Potato Early Blight → Tomato Early Blight | 2 |
| Potato Late Blight → Potato Healthy | 2 |
| Tomato Early Blight → Tomato Late Blight | 2 |
| Tomato Late Blight → Tomato Healthy | 1 |

Highest-confidence incorrect prediction: a Tomato Late Blight image
misclassified as Tomato Healthy at **0.9999998** confidence — the single
most concerning error in this run, since near-certain confidence gives no
usable signal to reject it. The remaining 10 errors span confidence 0.50–
0.92. Lowest-confidence correct predictions cluster around 0.50–0.73, mostly
Potato Early Blight. One leaf group (`Potato___Late_blight:::80.0`)
contributed 2 of the 11 errors — a mild concentration, not a dominant
pattern. Zero of the three approved similarity-guard groups showed
inconsistent correctness. No biological or clinical interpretation beyond
what is directly visible in these numbers is made. Full detail (including
paths, for internal review only — never copied into tracked files):
`m5_summary.json`'s `error_analysis` section.

## Confidence and deployment safety notes

- **Softmax confidence is a model score, not a guaranteed true probability.**
  A value of 0.95 does not mean "95% likely to be correct" in any calibrated,
  guaranteed sense — it is the model's own internal score, shaped by its
  training data and architecture, not an external measurement of truth.
- **High confidence does not guarantee correctness.** One frozen-test error
  had confidence approximately **0.9999998** — the model was confidently
  wrong. This is not a hypothetical concern; it is an observed result in
  this exact evaluation run.
- **The validation-selected threshold was 0.50.** It rejected **zero** of
  the 991 frozen-test predictions. Therefore, on this particular test set,
  this baseline threshold provided **no meaningful filtering** — it did not
  catch a single one of the model's 11 test errors, including the
  0.9999998-confidence one above.
- **Thresholding alone is insufficient** for out-of-distribution or real
  farm photos. This threshold was selected and evaluated entirely on
  PlantVillage-derived images (controlled backgrounds, consistent framing).
  It provides no evidence about behavior on phone photos taken in a real
  field, under real lighting, with real backgrounds, blur, or co-occurring
  conditions the training data does not represent.
- **Future API and UI work must label this value as "model confidence,"**
  never as "certainty" or "probability of truth." Presenting it as a
  probability of correctness would overstate what this number means, given
  the observed 0.9999998 counterexample above.
- **Real-world field validation is still required.** Nothing in this
  milestone substitutes for evaluating the model against real-world,
  out-of-distribution farm photography before any deployment decision.
- **This model and confidence policy are not production-calibrated.** No
  production-readiness claim is made anywhere in this milestone, or
  anywhere in this project (see the "Status" section below for what was
  later built on top of this frozen checkpoint/threshold).

## Potato Healthy limitation (test set)

Potato Healthy's test slice contains **24 images from only 6 independent
physical-leaf groups** — the same structural constraint documented for
validation in `MODEL_TRAINING.md`. Its test metrics (recall 1.0, precision
0.923, F1 0.960) are reported as-is, but with **only 6 independent leaf
groups**, a single misclassified or correctly-classified leaf group can
swing this class's precision/recall substantially. **A perfect or
near-perfect score on this class does not demonstrate production-level
generalization**, and because macro-F1 weighs all six classes equally,
overall macro-F1 remains sensitive to this one small, low-independent-count
class. This limitation is disclosed wherever Potato Healthy is reported, not
worked around.

## Reproduction commands

```bash
cd ml-service

# 1. Validation-mode evaluation (repeatable)
.venv/bin/python3 training/evaluate.py \
  --mode validation \
  --checkpoint data/training-runs/m4-efficientnet-b0-seed42/best_model.pt \
  --manifest data/splits/val.csv \
  --class-map training/class_map.json \
  --model-scope training/model_scope_v1.json \
  --expected-manifest-sha256 85f86dec9e81566b19d0654559f6b56c11d4b7086f3d5b8d244e00cae91dd91f \
  --expected-checkpoint-sha256 24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081 \
  --output-dir data/evaluation-runs/m5-efficientnet-b0-seed42

# 2. Threshold selection (validation predictions only)
.venv/bin/python3 training/select_threshold.py select \
  --validation-predictions-csv data/evaluation-runs/m5-efficientnet-b0-seed42/validation_predictions.csv \
  --checkpoint-sha256 24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081 \
  --validation-manifest-sha256 85f86dec9e81566b19d0654559f6b56c11d4b7086f3d5b8d244e00cae91dd91f \
  --output-dir data/evaluation-runs/m5-efficientnet-b0-seed42 \
  --confidence-policy-output training/confidence_policy_v1.json

# 3. Final-test evaluation -- ONE TIME ONLY, do not rerun
.venv/bin/python3 training/evaluate.py \
  --mode final-test \
  --confirm-final-test-evaluation \
  --checkpoint data/training-runs/m4-efficientnet-b0-seed42/best_model.pt \
  --manifest data/splits/test.csv \
  --class-map training/class_map.json \
  --model-scope training/model_scope_v1.json \
  --expected-manifest-sha256 3d0ee43d9edc836eefadb71bf178d55d3e60817053efa5f9f5a52cd04c284abb \
  --expected-checkpoint-sha256 24e7244ed2970ec3aac50be870f0de80f42d52baf30cd80b429ff67e9d001081 \
  --apply-threshold 0.5 \
  --output-dir data/evaluation-runs/m5-efficientnet-b0-seed42

# 4. Apply the frozen threshold + full analysis
.venv/bin/python3 training/select_threshold.py apply \
  --test-predictions-csv data/evaluation-runs/m5-efficientnet-b0-seed42/test_predictions.csv \
  --confidence-policy-json training/confidence_policy_v1.json \
  --evaluation-manifest-hashes-json data/evaluation-runs/m5-efficientnet-b0-seed42/evaluation_manifest_hashes.json \
  --output-dir data/evaluation-runs/m5-efficientnet-b0-seed42
```

## Output locations (all gitignored except `confidence_policy_v1.json`)

`ml-service/data/evaluation-runs/m5-efficientnet-b0-seed42/`:
`validation_predictions.csv`, `validation_metrics.json`,
`validation_confusion_matrix.json`, `validation_per_class_metrics.json`,
`threshold_candidates.json`, `threshold_selection.json`,
`test_predictions.csv`, `test_metrics_raw.json`,
`test_metrics_thresholded.json`, `test_confusion_matrix.json`,
`test_per_class_metrics.json`, `confidence_analysis.json`,
`m5_summary.json`, `evaluation_environment.json`,
`evaluation_manifest_hashes.json`, `evaluation.log`.

`ml-service/training/confidence_policy_v1.json` is tracked in git (the
frozen threshold decision record); no other file in this milestone's output
is committed.

## Status

**M6 built the FastAPI service foundation** (health, readiness, and
model-info endpoints — see `docs/API_FOUNDATION.md`); **M7 added the real
`POST /api/predict/disease` endpoint** (see `docs/PREDICTION_API.md`),
applying this same frozen checkpoint and threshold to live image uploads.
No production-readiness claim is made for this baseline. The frozen
threshold (0.50) currently performs no rejection at all on the observed
test set and should not be assumed to generalize to future, harder or
out-of-distribution images without further review. **M8–M10** (Next.js
integration, MongoDB persistence, and a real end-to-end validation pass)
are also complete — see `../docs/PHASE_2_CUSTOM_DISEASE_ML.md` for the
full Phase 2 picture.
