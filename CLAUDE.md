# AgriAI Claude Code Instructions

## Project

AgriAI is a phase-by-phase agriculture intelligence platform built with
Next.js 14, TypeScript, MongoDB, FastAPI, custom ML models, Ollama, and Qwen3 8B.

## Current Phase

Phase 1 — Local Qwen3 8B Integration.

Work only on the current approved phase. Do not implement future phases.

## Phase 1 Scope

- Inspect the existing AI chat architecture.
- Add a reusable typed Ollama client.
- Use local qwen3:8b for agriculture text chat.
- Replace Groq only in the text-chat workflow.
- Add an Ollama health-check endpoint.
- Add timeout and connection-error handling.
- Update safe example environment variables.
- Preserve Gemini image analysis temporarily.
- Preserve authentication and user-specific history.

Do not implement:

- Custom crop-disease ML models
- Weather advisory
- Disease-risk prediction
- Crop lifecycle calendar
- Voice assistant
- RAG
- Offline PWA
- User feedback and correction
- Any later phase

## Workflow

1. Inspect the repository before editing.
2. Explain the current architecture.
3. Propose a file-by-file implementation plan.
4. Wait for explicit approval before editing.
5. Modify only approved files.
6. Run validation after implementation.
7. Report changed files and unresolved limitations honestly.

## Git Rules

- Never work directly on main.
- Never commit, push, merge, rebase, reset, or rewrite Git history.
- The user performs all Git operations.
- Do not modify unrelated files.
- Do not delete branches.

## Security Rules

- Never read, print, modify, or commit .env.local.
- Never expose secrets in source code, logs, or output.
- Never place private values in NEXT_PUBLIC_ variables.
- Never disable authentication or route protection.
- Validate API input.
- Do not run destructive Docker commands.

## AI Safety Rules

- Qwen provides chat and explanations only.
- Qwen must not invent pesticide or fertilizer dosages.
- Qwen must communicate uncertainty.
- Serious agricultural decisions must recommend expert verification.
- Qwen must not silently replace structured ML predictions.

## Required Validation

Run:

- npm run lint
- npm run build
- Any tests introduced during the current phase

Before finishing, report:

- Changed files
- Commands executed
- Validation results
- Remaining limitations
- Suggested commit message
