# AgriAI Claude Code Instructions

## Project

AgriAI is a phase-by-phase agriculture intelligence platform built with
Next.js 14, TypeScript, MongoDB, FastAPI, custom ML models, Ollama, and
Qwen3 8B.

## Current Phase

Phase 2 — Custom Crop-Disease ML Service.

Work only on Phase 2. Do not implement later phases.

## Phase 2 Objective

Build a reproducible custom crop-disease image-classification system and
integrate it into AgriAI through a Python FastAPI service.

The custom model should become the primary crop-image diagnosis provider
after validation.

## Proposed Initial Classes

- Tomato Healthy
- Tomato Early Blight
- Tomato Late Blight
- Potato Healthy
- Potato Early Blight
- Potato Late Blight
- Corn Healthy
- Corn Common Rust

Do not silently add more classes without approval.

## Phase 2 Scope

- Inspect the existing crop scanner and image-analysis flow.
- Design a reproducible image-training pipeline.
- Use transfer learning rather than training a large CNN from scratch.
- Prefer EfficientNet-B0 as the baseline model.
- Include train, validation, and test separation.
- Produce accuracy, precision, recall, F1-score, and confusion matrix.
- Add model and dataset version metadata.
- Create a Python FastAPI ML service.
- Add health, model-info, and disease-prediction endpoints.
- Validate uploaded file type, size, and image content.
- Return top predictions and confidence scores.
- Add low-confidence and unsupported-image handling.
- Integrate the service with the existing Next.js crop scanner.
- Preserve authentication and MongoDB history.
- Keep Gemini image code temporarily as an explicit fallback until the
  custom model is validated.
- Preserve Qwen3/Ollama text chat.

## Out of Scope

Do not implement:

- Pest detection
- Soil ML models
- Weather advisory
- Disease-risk prediction
- Crop calendar
- Voice assistant
- RAG
- Offline PWA
- Feedback and correction
- Automatic retraining
- IoT features
- Any later phase

## Data and Artifact Rules

- Never commit raw datasets.
- Never commit generated training caches.
- Never commit very large model artifacts without approval.
- Add dataset, checkpoint, and local model directories to .gitignore.
- Do not download a dataset until the dataset source and licence have
  been approved.
- Record dataset source, class mapping, preprocessing, and split method.
- Avoid data leakage between train, validation, and test sets.

## ML Safety Rules

- Never force a confident prediction.
- Return an uncertain result below the approved confidence threshold.
- Return unsupported or invalid when the input is not suitable.
- Do not let Qwen silently override the classifier prediction.
- Do not invent pesticide or fertilizer dosages.
- Serious cases must recommend expert verification.

## Git Rules

- Never work directly on main.
- Never commit, push, merge, rebase, reset, or rewrite Git history.
- The user performs all Git operations.
- Do not modify unrelated files.
- Do not delete branches.

## Security Rules

- Never read, print, modify, or commit .env.local.
- Never expose secrets.
- Never disable authentication.
- Validate all API and file-upload input.
- Do not run destructive Docker commands.

## Workflow

1. Inspect the existing repository.
2. Explain the current image-analysis architecture.
3. Propose a file-by-file Phase 2 plan.
4. Wait for explicit approval before editing.
5. Implement one approved milestone at a time.
6. Run validation after every milestone.
7. Report failures and limitations honestly.

## Required Validation

For Next.js changes:

- npm run lint
- npm run build

For FastAPI and ML-service changes:

- Python formatting and lint checks
- Type checks when configured
- pytest
- FastAPI endpoint tests
- Model inference smoke test

Before finishing, report:

- Changed files
- Dataset and model versions
- Commands executed
- Training and evaluation results
- API validation results
- Remaining limitations
- Suggested commit message
