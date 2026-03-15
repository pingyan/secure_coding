# Changelog — Project Sentinel

## v0.1.0 — Initial Implementation (2026-03-14)

- Calibration pipeline (`calibrate.py`): audio threshold derivation + HUD region confirmation
- Closed-loop analyzer (`analyzer.py`): audio-triggered FPS switching, YOLO + optical flow + OCR
- Report generator (`report.py`): streaming NDJSON → JSON + highlights
- Orchestration script (`run_all.sh`)
- Calibration completed successfully (`calibration.json`)
- Smoke test attempted on `clip_15min.mp4` — failed (0 bytes output)

### Known issues at v0.1.0
- Writes intermediate chunk files to disk (violates resource constraint)
- No resume/checkpoint support
- No red tint death screen detection
- ADS detection via OCR is non-functional (region unconfirmed)
- report.py has FPS constant mismatch (hardcodes 1/5, should be 1/2)
- No benchmark evaluation code

---

## v0.2.0 — Recovery & Stabilization (2026-03-14)

### Completed
- [x] Eliminate chunk extraction → direct cv2 seeking from source video (zero disk writes)
- [x] Add red tint death screen detection (HSV analysis, threshold 0.50)
- [x] Fix ADS detection (Hough circles with edge density gate, centered circle verification)
- [x] Add checkpoint/resume support (checkpoint.json, 30s intervals)
- [x] Fix report.py FPS mismatch (derive dt from timestamps)
- [x] Add benchmark evaluation (evaluate.py) against known ground truth
- [x] Successful smoke test on 2-min benchmark clip (238 events, 40/40 windows)
- [x] OCR interval reduced from 15s to 5s for better revive recall

### Benchmark (v0.2.0)
- 3 exact class matches (death_event, vehicle_traversal, + total=40)
- 4 classes within ±1 window (exploration, combat, looting, + near for aiming)
- Revive over-detection: 10 vs 6 (OCR text persists on screen longer than actual action)

### Remaining tuning opportunities
- Revive: add motion constraint or duration cap to reduce over-detection
- ADS: consider adding crosshair/red-dot detection alongside Hough circles
- hi_intensity_combat: relax threshold combination (currently requires 4 simultaneous signals)
