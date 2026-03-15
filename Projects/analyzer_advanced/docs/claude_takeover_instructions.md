# claude_takeover_instructions.md

## Purpose

These instructions are for Claude to take over and continue the **existing** project at:

`/Users/ping.yan/Projects/analyzer_advanced`

This is **not** a greenfield project. Claude should treat `analyzer_advanced` as an in-progress system, recover context from what already exists, and continue autonomously.

## Mission

Continue building an optimized, resource-aware gameplay behavior analyzer using a closed-loop architecture.

### Closed-loop architecture goals

1. **Trigger Loop (Audio -> Vision)**
- Audio monitors the stream for high-entropy events such as gunshots, vehicle engines, and explosions.
- When audio detects a likely event, vision sampling should temporarily increase.
- Example:
  - low baseline sampling: 2 FPS
  - burst mode during triggered windows: 30 FPS for ~5 seconds

2. **Verification Loop (YOLO / Vision -> OCR / HUD)**
- Vision detections should trigger targeted OCR / HUD verification.
- OCR / HUD should focus on:
  - killfeed
  - revive text
  - elimination / killed-by text
  - player HP / status if available
  - level-up / win text if available

3. **Logic Layer / Behavioral Judge**
- Convert low-level signals into structured behavior events.
- If practical, use a lightweight local reasoning model or an abstraction that could later be swapped with an LLM.
- Structured output example:
  - `{"behavior": "Skirmish-Flee", "confidence": 0.92, "evidence": {...}}`

## Important clarification

This project already exists and is underway.

Claude must:
- inspect the current repo state first
- reuse existing code where it is sound
- reuse and adapt existing docs / architecture where useful
- avoid recreating the project from scratch
- avoid unnecessary churn or wholesale rewrites unless justified

## Autonomy requirements

Claude should proceed autonomously and should **not ask for routine guidance**.

Claude should:
- inspect current files and architecture
- infer the current implementation stage
- identify what is reusable
- identify what needs refactoring
- make reasonable engineering decisions
- checkpoint often
- keep the system recoverable
- document decisions, trade-offs, and failures

Claude should only ask for input if there is a true hard blocker such as:
- missing files
- permission failures
- environment failures that cannot be worked around

## Resource and pipeline health requirements

Claude must be extremely mindful of:
- memory pressure
- disk pressure
- temp file growth
- resumability
- system stability

### Prior failure modes from the old pipeline

The earlier naive pipeline failed because of:
- large chunk video files written to disk
- excessive disk usage (`data/chunks` ballooned)
- over-aggressive full-video runs
- multiple workers on a constrained laptop
- OCR / detection / decode combined too aggressively
- insufficient checkpoint discipline

### Mandatory constraints

Claude must:
- **not write intermediate chunk video files to disk**
- stream or seek directly from source video
- prefer `workers = 1` unless safety is proven
- use low-memory defaults
- keep outputs lightweight
- avoid frame dumps or annotated video by default
- avoid launching long full-video runs without checkpoints
- implement and preserve resume support
- log runtime / resource usage / output sizes

## Reference materials from prior project

Claude may and should reference useful material from:

`/Users/ping.yan/Projects/video-audio-processor/`

Especially:
- `docs/signal_layer_spec.md`
- `docs/behavior_layer_spec.md`

These should be treated as useful prior design references, not as something to clone blindly.

## Validation benchmark requirement

Use the following benchmark validation target:

### Benchmark clip
- 2-minute clip starting at minute 15 of `video.mkv`

### Benchmark findings
- exploration: 13
- aiming: 11
- reviving: 6
- combat: 4
- death_event: 2
- looting: 2
- high_intensity_combat: 1
- vehicle_traversal: 1
- total: 40

Claude must:
- build evaluation logic against this benchmark
- report per-class matches / mismatches
- analyze likely causes of mismatch
- explicitly analyze **reviving recall**, since revive detection is sensitive to OCR sampling
- treat this as a practical validation set

## Expectations for working with the existing project

Claude should begin by doing these things in order:

1. Inspect the current repository structure of `analyzer_advanced`
2. Summarize what already exists
3. Identify:
   - completed components
   - unstable components
   - duplicated / legacy code
   - resource-risky code
4. Inspect the old reference project and extract reusable lessons
5. Propose a continuation plan that preserves good existing work

Claude should **not** restart the project from zero.

## Required project hygiene

Claude must maintain strong engineering hygiene inside the existing repo.

### Versioning
- clearly track analyzer versions or milestones
- preserve change history

### Checkpoints
- checkpoint major milestones
- store resumable metadata
- make long runs restartable

### Recovery strategy
- design for interruption recovery
- avoid recomputing finished work unnecessarily

### Decision journal
Maintain a running decision journal that includes:
- diagnosis of issues
- design decisions
- trade-offs considered
- why decisions were made
- rejected alternatives
- failure analyses

Suggested files:
- `docs/journal.md`
- `docs/changelog.md`
- `docs/runbook.md`
- `docs/architecture.md`

If these already exist, update them rather than recreating them.

## Architecture direction

Claude should evolve the project toward this architecture:

1. **Cheap global scan**
- sparse baseline FPS
- audio entropy detection
- lightweight motion / scene-change analysis

2. **Triggered refinement**
- denser vision only in high-value windows
- targeted OCR / HUD verification
- richer behavior extraction only where justified

3. **Behavior judge**
- structured event inference
- explainable evidence
- machine-readable JSON output

4. **Evaluation**
- compare against benchmark clip
- summarize mismatch by class
- summarize resource trade-offs

5. **Reporting**
- clear technical report
- concise executive summary
- operational notes

## Implementation priorities

### Priority 1
- recover context from the existing project
- understand current repo state
- understand what already works
- understand where the current pipeline is fragile

### Priority 2
- make the pipeline resource-safe
- eliminate any remaining disk-heavy chunking behavior
- enforce streaming / seeking behavior
- preserve or improve resume support

### Priority 3
- implement or improve the audio-trigger loop
- implement or improve targeted OCR / HUD verification
- tighten the behavior judge

### Priority 4
- add / improve benchmark evaluation
- make reporting clean and reproducible

## Deliverables Claude should maintain or produce

1. Updated codebase in `analyzer_advanced`
2. Updated docs:
   - `docs/architecture.md`
   - `docs/journal.md`
   - `docs/changelog.md`
   - `docs/runbook.md`
3. Evaluation artifacts for the benchmark clip
4. Final report:
   - `reports/final_report.md`
5. Executive summary:
   - `reports/executive_summary.md`

If equivalent files already exist, Claude should update them rather than duplicating them.

## Required working style

Before any heavy processing, Claude should first:
1. recover state
2. inspect current code and docs
3. summarize current architecture and risks
4. propose low-risk next steps
5. only then run small controlled tests

Claude should not launch a long full-video run without first proving:
- memory safety
- disk safety
- resumability
- output correctness on a small validation run
