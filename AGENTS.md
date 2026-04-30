# Project Agent Rules (Culsma)

Last Updated: 2026-04-05

This file defines project-local hard rules for all future agent work in this repository.

## 1. Priority Order (Hard Constraint)

1. Language semantics correctness
2. Architecture consistency (frontend/spec/reference/runtime boundaries)
3. Testability and diagnostics ownership
4. Execution completeness and speed

`Speed` or `quick runnable output` MUST NOT override 1-3.

## 2. Forbidden Shortcuts

The agent MUST NOT:

1. Implement string-name binding as a substitute for first-class typed references when spec/intent requires object/reference semantics.
2. Expose kernel-internal canonical operations (for example `LoadContent`) as user-facing language examples when the intended UX is sugar-level syntax.
3. Keep an intentionally temporary semantic model without explicitly labeling it as `temporary` and getting user confirmation.
4. Claim a design is “done” if core semantic invariants are not satisfied.

## 3. Mandatory Design Gate for Core Semantics

For changes touching container/content/type/diagnostics core semantics, the agent MUST complete in this order:

1. Freeze a decision/feature card with invariants and ownership.
2. Map diagnostics to earliest-decidable stage.
3. Define conformance hooks (Req ID -> Test ID).
4. Then implement code.

Skipping this gate is not allowed.

## 4. Example Authoring Rule

User-facing examples MUST:

1. Prefer frontend sugar syntax and typed references.
2. Avoid leaking internal lowering targets unless the example is explicitly marked as kernel-internal.
3. Be runnable with current pipeline or clearly marked as design-only.

## 5. Communication Rule

If implementation reality conflicts with target language semantics, the agent MUST:

1. Stop and explicitly report the mismatch.
2. Ask to proceed with either:
   - semantic-correct refactor, or
   - temporary bridge mode (explicitly labeled).
3. Default to semantic-correct refactor when user says “一次性做完”.

## 6. Quality Gate Before “Done”

Before reporting completion, the agent MUST confirm:

1. Core semantics match intended model.
2. Tests pass for changed scope.
3. Spec/reference/card states are synchronized (`planned/current` consistency).
4. No contradictory examples are left in repository.

## 7. Commit Message Convention

All repository commits SHOULD use Conventional Commits style:

`<type>(<scope>): <summary>`

Rules:

1. Preferred `type` values: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.
2. `scope` SHOULD name the semantic or subsystem boundary being changed, for example `container`, `runtime`, `spec`, `mcp`.
3. `summary` MUST be short, present tense, and MUST NOT end with a period.
4. When a body is needed, it SHOULD use 2-4 short lines describing:
   - what changed,
   - why it changed,
   - behavior/compatibility impact,
   - test or release-note coverage.
5. A single commit SHOULD represent one coherent semantic change. Unrelated mechanical edits SHOULD be split out unless the user explicitly asks for a squash-style commit.
