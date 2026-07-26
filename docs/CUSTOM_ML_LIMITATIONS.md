# Custom ML Limitations

This document collects, in one place, every known limitation of Phase 2's
custom disease-ML feature — dataset, metrics, confidence, system, and
safety. It exists so no one has to hunt through milestone-by-milestone docs
to understand what this feature does and does not prove. Nothing here is
new information; every item is already documented at its source milestone
and is repeated here for visibility.

## Dataset

- **PlantVillage-derived controlled images.** Leaves photographed against a plain background under lab-style conditions — not real farm-field photographs (varied lighting, backgrounds, occlusion, multiple leaves/diseases in frame, phone-camera artifacts, etc.).
- **Limited real-farm diversity.** No claim is made that this dataset represents the diversity of real-world field conditions a farmer's photo will show.
- **Corn excluded from this first model.** No authoritative physical-leaf grouping metadata exists for either Corn class in this source data, so a defensible, leakage-free split could not be produced — Corn was excluded from active scope entirely rather than risk data leakage. This may be revisited in a future phase if better grouping metadata becomes available.
- **Six supported classes only**: Tomato Healthy/Early Blight/Late Blight, Potato Healthy/Early Blight/Late Blight. Any other crop, disease, or condition is out of scope — the model has no opinion on them and the system is designed to never silently guess at an unsupported class.
- **Potato Healthy has only 38 leaf groups** (authoritative `leaf_id`-based grouping only; no Tomato-style filename-family or perceptual-hash grouping was approved for this class). Validation and test **each contain only 6 independent leaf groups** for Potato Healthy — meaningfully thinner support than the other five classes, all of which have hundreds of groups.

## Metrics

- **High results on a controlled dataset.** 98.89% accuracy / 0.9841 macro-F1 on the frozen `test.csv` split describes performance on **this specific controlled-image dataset** — it is not evidence of, and must not be read as, real-field generalization performance.
- **No production-generalization claim is made anywhere in this project.**
- **Macro-F1 is sensitive to Potato Healthy's thin support.** With only 6 independent test-set leaf groups for that class, a single misclassified leaf-group can move the macro-F1 by a visible amount — the metric is real, but its per-class stability varies significantly by class.
- **Test metrics are not evidence of real-field performance** — they describe one 991-image, in-distribution, non-adversarial evaluation, run exactly once (Milestone M5), never re-run to "improve" the reported numbers.

## Confidence

- **Threshold: 0.50**, selected using validation predictions only, before test labels were ever read.
- **Rejected zero of 991 frozen test samples** — on this dataset, at this threshold, the model accepted every test prediction; thresholding provided no additional filtering.
- **Softmax confidence is a model score, not certainty** — it is not a calibrated probability that the prediction is correct, and must never be presented to a user as such.
- **One frozen-test error had confidence near 1.0** (0.99999976) — the single highest-confidence prediction in the entire frozen test set was, in fact, wrong. This is direct, concrete evidence that high confidence does not guarantee correctness for this model.
- **Not production-calibrated** — `confidence_policy_v1.json`'s `production_calibrated` field is `false`, and no calibration study (temperature scaling, Platt scaling, or similar) has been performed.
- **Threshold alone is insufficient for out-of-distribution detection** — a photo of an unsupported crop, a non-leaf object, or a real farm photo very different from this dataset's style could still receive a high-confidence, "accepted" prediction. The threshold guards against low raw softmax scores, not against inputs that are simply outside what the model has ever seen.

## System

- **The model checkpoint is stored locally and is not committed to Git** — a developer must obtain or regenerate it separately (see [`CUSTOM_ML_RUNBOOK.md`](CUSTOM_ML_RUNBOOK.md)).
- **FastAPI must be run as a separate process** from the Next.js app — there is no single combined server, and no process-supervision/orchestration (e.g. systemd unit, Docker Compose) is provided by this repository for either service.
- **No cloud deployment has been completed** — both services have only been run and validated on local development machines.
- **Gemini fallback depends on valid Gemini credentials** being configured — if the configured key is invalid or missing, a fallback attempt fails with a safe, sanitized error rather than succeeding (verified directly during M10, where this environment's own credential was in fact invalid).
- **Uncertain-result live end-to-end behavior was not naturally observed** — every real prediction made during M10's validation was accepted (consistent with the 0-rejection frozen-test result); the uncertain-result UI/persistence path is verified via the automated test suite, not a live "accepted: false" example.
- **Real browser visual verification was not completed during M10** — the JSON data and persisted documents were verified directly (API + database), and React Testing Library component tests assert the rendering logic against that same data shape, but no one visually confirmed the rendered page in an actual browser during that milestone.
- **Performance numbers recorded in M10/M7 docs are informal, single-machine observations** — not a benchmark, not load-tested, and not representative of any particular production hardware or concurrency level.

## Safety

- **This is not agricultural diagnosis.** It is an image-classification model's output, not a substitute for a trained plant pathologist or agricultural extension agent.
- **Expert consultation is required for important decisions.** Any decision with real financial or crop-health consequences (e.g. whether to apply a treatment, destroy a plant, or write off a crop) should involve a human expert, not just this tool's output.
- **No automatic pesticide/treatment action should ever be taken solely from this model's output.** The application deliberately does not generate disease-specific treatment or dosage recommendations from the custom model — custom-ml results include only safe, generic disclaimer text directing the user to consult an extension service or Gemini for general guidance, never a specific chemical/dosage claim.
