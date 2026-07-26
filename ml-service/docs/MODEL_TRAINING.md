# Model Training — Milestone M4

## Purpose

M4 implements and runs the **first reproducible EfficientNet-B0 baseline**
for the approved 6-class crop-disease scope, training on `train.csv` and
selecting the best checkpoint by validation macro-F1 on `val.csv` only.
**The test manifest (`test.csv`) is not used anywhere in M4** — it stays
frozen for Milestone M5's final evaluation and threshold selection.

This document does not claim production readiness. It documents a first
baseline run, its configuration, its outputs, and its known limitations.

## Approved six classes

- Tomato Healthy
- Tomato Early Blight
- Tomato Late Blight
- Potato Healthy
- Potato Early Blight
- Potato Late Blight

Corn Healthy and Corn Common Rust remain temporarily excluded
(`training/model_scope_v1.json`). `training/class_map.json` is unchanged
and still defines all 8 original classes; the model itself has exactly 6
output units, per the approved active scope.

## Environment setup

This project uses the existing `ml-service/.venv` virtual environment
(Python 3.13.5, arm64 macOS). Training dependencies live in
`requirements-training.txt`:

```bash
cd ml-service
.venv/bin/python3 -m pip install -r requirements-training.txt
```

**Compatibility note**: `requirements.txt` (the runtime/FastAPI stack)
pins `torch==2.3.1` / `torchvision==0.18.1` / `numpy==1.26.4`, none of
which publish wheels for Python 3.13. `requirements-training.txt` restates
the dependency set with the smallest version bumps needed for a Python
3.13/arm64 wheel to exist (`torch==2.7.1`, `torchvision==0.22.1` — an
exact, verified pair — `numpy==2.5.1`, `scikit-learn==1.5.2`,
`matplotlib==3.9.2`), verified via `pip install --dry-run` on
2026-07-25. `requirements.txt` itself is unmodified; it documents the
intended stack for the not-yet-built inference service (a later
milestone) and should be revisited when that service is actually built.

Resolved training-environment versions on this machine:

| Package | Version |
|---|---|
| Python | 3.13.5 |
| torch | 2.7.1 |
| torchvision | 0.22.1 |
| Pillow | 10.4.0 |
| numpy | 2.5.1 |
| scikit-learn | 1.5.2 |
| tqdm | 4.66.4 |
| pytest | 8.2.2 |

MPS (Apple Silicon GPU acceleration) is available and used by default;
CPU fallback works (`--device cpu`).

## Training command

```bash
cd ml-service
.venv/bin/python3 training/train.py \
  --train-manifest data/splits/train.csv \
  --val-manifest data/splits/val.csv \
  --class-map training/class_map.json \
  --model-scope training/model_scope_v1.json \
  --output-dir data/training-runs/m4-efficientnet-b0-seed42 \
  --epochs 15 \
  --batch-size 16 \
  --learning-rate 0.0003 \
  --weight-decay 0.0001 \
  --num-workers 0 \
  --seed 42 \
  --device auto \
  --early-stopping-patience 4 \
  --pretrained
```

`--max-batches-per-epoch N` is an additional, optional flag (not in the
original required list) used to run fast smoke tests without touching the
real baseline's output directory.

## Validation and final-test evaluation (M5)

`training/evaluate.py` was extended in Milestone M5 with explicit
`--mode validation` / `--mode final-test` support, manifest/checkpoint
SHA-256 verification, and a required `--confirm-final-test-evaluation`
acknowledgement for the one-time frozen test evaluation. The M4-era
single-file `--output-json` interface shown in earlier revisions of this
document no longer exists. Commands, the validation-selected confidence
threshold, and the frozen test results are documented in
**[`MODEL_EVALUATION.md`](MODEL_EVALUATION.md)** — not duplicated here.

## Resume command

```bash
.venv/bin/python3 training/train.py \
  ... (same arguments as the original run) ... \
  --resume-checkpoint data/training-runs/m4-efficientnet-b0-seed42/last_model.pt
```

Before resuming, the architecture, class map, class count, manifest
hashes, and preprocessing config are checked against the checkpoint; any
mismatch raises an error rather than resuming silently. A seed mismatch is
also disclosed as an error rather than silently ignored.

## Output locations (all gitignored)

- `ml-service/data/training-runs/m4-efficientnet-b0-seed42/` — the
  baseline run: `best_model.pt`, `last_model.pt`, `training_history.json`,
  `validation_metrics_best.json`, `confusion_matrix_best.json`,
  `per_class_metrics_best.json`, `run_config.json`, `environment.json`,
  `manifest_hashes.json`, `training_summary.json`, `training.log`.
- `ml-service/models/` — reserved for a promoted/exported model (not used
  by M4 directly; the run directory above is the source of truth for this
  milestone).

No model weights are committed or pushed.

## Baseline hyperparameters (selected defaults)

| Setting | Value |
|---|---|
| Architecture | EfficientNet-B0 (torchvision, ImageNet-pretrained) |
| Seed | 42 |
| Epochs (max) | 15 |
| Batch size | 16 |
| Learning rate | 0.0003 |
| Weight decay | 0.0001 |
| Optimizer | AdamW |
| Scheduler | ReduceLROnPlateau (mode=max on val macro-F1, factor=0.5, patience=2) |
| Loss | CrossEntropyLoss, inverse-frequency-balanced class weights |
| Early-stopping patience | 4 epochs without macro-F1 improvement |
| num_workers | 0 (macOS-safe default) |
| Device | auto (MPS → CPU fallback) |

## Augmentation

Conservative, disease-symptom-preserving. Train: `RandomResizedCrop(224,
scale=[0.85,1.0])`, horizontal flip (p=0.5), rotation (±15°), mild color
jitter (brightness/contrast 0.15, saturation 0.1, hue 0.02), ImageNet
normalization. No vertical flip (a leaf has no natural vertical-flip
symmetry and it risks distorting gravity-influenced lesion-spread cues).
Validation: `Resize(256)` → `CenterCrop(224)` → ImageNet normalization,
fully deterministic. Full config recorded in every run's `run_config.json`
under `transforms`.

## Class-imbalance strategy

Potato Healthy has only 104 training images vs 700–1,331 for the other 5
classes. The single selected baseline strategy is **weighted
cross-entropy** using inverse-frequency-balanced weights
(`total / (num_classes * class_count)`), computed once from `train.csv`
and recorded in `run_config.json` under `class_weights` (both the
unweighted-1.0 baseline and the selected weighted values are recorded).
No oversampling is combined with the weighting, to keep the first
baseline's imbalance handling simple and attributable.

## Checkpoint format

`best_model.pt` / `last_model.pt` are plain `torch.save` dictionaries
(never a pickled full model object), containing: `model_state_dict`,
`optimizer_state_dict`, `scheduler_state_dict`, `epoch`,
`best_val_macro_f1`, `val_loss`, `class_names`, `class_to_index`,
`architecture`, `preprocessing_config`, `training_config`,
`manifest_hashes`, `seed`, `agriai_repo_commit`, `torch_version`.

## Metrics

Every epoch: loss, accuracy, macro precision/recall/F1, weighted F1 —
computed with `zero_division=0` (never raises/NaNs on an unpredicted
class). Validation additionally gets per-class precision/recall/F1/support
and a confusion matrix. **Model selection**: highest validation macro-F1;
ties broken by lower validation loss, then by earlier epoch. Validation
accuracy alone is never used to select the model.

## Potato Healthy limitation (disclose in every result)

The approved validation set contains only **24 Potato Healthy images from
6 independent physical-leaf groups**. Image-level support (24) overstates
the number of independent examples (6). Potato Healthy precision, recall,
and F1 carry **high uncertainty**, and **macro-F1 is sensitive to this
small class**. No claim of production-level generalization is made for
Potato Healthy. Potato Healthy is not removed or changed because of this —
the limitation is disclosed, not worked around.

## Test set status

**`test.csv` was not loaded anywhere in M4** — not for training, not for
validation, not for early stopping, not for model selection, not for
threshold selection. Milestone M5 subsequently performed the one-time final
test evaluation and validation-only threshold selection; see
[`MODEL_EVALUATION.md`](MODEL_EVALUATION.md). `test.csv` has now been
evaluated exactly once and must not be evaluated again.

## Reproducibility disclosure

Python `random`, NumPy, and `torch` (including MPS/CUDA where available)
are seeded. `torch.use_deterministic_algorithms(True, warn_only=True)` is
enabled so unsupported/nondeterministic MPS ops warn instead of crashing.
**Full bit-for-bit determinism across runs on MPS is not claimed** — some
EfficientNet-B0 MPS kernels (depthwise/SE blocks) have no deterministic
implementation in torch 2.7.1. Seeded initialization, data ordering, and
augmentation are reproducible; exact floating-point reduction order in
MPS matmul/conv may still vary run to run. CPU runs are expected to be
closer to fully deterministic.
