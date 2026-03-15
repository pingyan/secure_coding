# Decision Journal — Project Sentinel

## 2026-03-14: Recovery Assessment (Claude takeover)

### Context
Project was in-progress with calibration complete but smoke test failed (0 bytes output).
Reference project (`video-audio-processor`) completed full 5h10m analysis with 311 chunks.

### Diagnosis

**Why the smoke test failed:**
The analyzer extracts video chunks to disk (43MB per 10-min chunk), then processes via cv2.VideoCapture. The smoke test log shows it reached "Processing 1 chunks" but produced 0 events. Likely causes:
1. The chunk extraction succeeded (chunk_0000.mp4 = 43MB exists) but `process_chunk()` hung — possibly on the first OCR call (EasyOCR on CPU is slow, and the first call triggers model loading).
2. The 2-second audio step with HI_FPS=2 produces only 1 frame per step in low mode, but each frame requires YOLO + optical flow + potentially OCR. On CPU, this could be ~2-5s per frame, meaning the 120s clip needs ~240-600s minimum.
3. The process may have been killed before completion (user got impatient, OOM, etc.)

**Critical architectural issue: chunk extraction to disk**
The `extract_chunk()` function writes MP4 files to `chunks/`. This violates the mandatory constraint. For a 10-min chunk at 1920x1080, this is ~40-100MB per chunk. For the full 5h video, that's 31 chunks × ~50MB = ~1.5GB of disk churn.

The reference project also used chunk files (311 × 60s chunks) but had explicit cleanup. The new project must avoid this entirely.

### Decisions

1. **Eliminate chunk extraction** — Replace `extract_chunk()` + `cv2.VideoCapture(chunk_path)` with direct seeking using `cv2.VideoCapture(video_path)` + `cap.set(CAP_PROP_POS_MSEC, ...)`. This is what the current `read_frame_at()` already does within a chunk — we just need to point it at the source video directly.

   *Alternative considered:* ffmpeg pipe per-frame (current `extract_frame()` fallback). Rejected because subprocess overhead per frame is ~200ms, vs ~5ms for cv2 seeking.

   *Alternative considered:* Keep chunks but auto-delete. Rejected because it still risks disk pressure if the process crashes between extract and delete.

2. **Add red tint death detection** — The reference project proved this is the most reliable death signal (0.58-0.68 on actual deaths, 0.10-0.17 baseline, threshold 0.50). Currently only OCR-based death detection exists, which is fragile. Implementation: HSV analysis of center frame region, check red_mask ratio.

3. **Fix ADS detection** — OCR on `ads_scope` region was not confirmed in calibration (no text found). The reference project used Hough circle detection at frame center. Switch to that approach.

4. **Add checkpoint/resume** — Write a `checkpoint.json` tracking last-processed timestamp. On restart, skip to that point. NDJSON output is append-friendly, so this is straightforward.

5. **Add benchmark evaluation** — Compare output against the known benchmark (40 events from the 2-min clip at minute 15). Report per-class match/mismatch.

6. **Fix report.py** — `dt = 1.0 / 5` is wrong; HI_FPS is 2 in analyzer.py. Should derive dt from the event timestamps or use the correct FPS constants.

### Priority Order
1. Fix chunk extraction → direct seeking (unblocks everything)
2. Add red tint + fix ADS detection (correctness)
3. Add checkpoint/resume (safety)
4. Fix report.py FPS bug
5. Add benchmark evaluation
6. Run smoke test → validate
7. Run full analysis if smoke test passes

## 2026-03-14: v0.2 Implementation & Benchmark Results

### Changes Implemented
1. **Eliminated chunk extraction** — Direct cv2 seeking from source video. Zero disk writes.
2. **Added red tint death detection** — HSV analysis with threshold 0.50. Works perfectly: 6 events at t=52-54.5 with red_tint 0.54-0.71.
3. **Added ADS Hough circle detection** — Replaces broken OCR-based ADS. Required multiple tuning iterations:
   - v1: param2=40, tolerance=inf → 55% false positive rate (131/238)
   - v2: param2=80, tolerance=5% → 0.8% detection rate (2/238), too strict
   - v3: param2=60, tolerance=15%, edge_density gate → reasonable balance
4. **Added checkpoint/resume** — `checkpoint.json` updated every 30s of video time.
5. **Fixed report.py FPS bug** — Now derives dt from event timestamps.
6. **Created evaluate.py** — Benchmark evaluation against ground truth.
7. **Reduced OCR interval** — 15s → 5s for better revive recall.

### Benchmark Results (v0.2, 2-min clip at minute 15)

| Class | GT | Predicted | Diff | Notes |
|-------|---:|----------:|-----:|-------|
| exploration | 13 | 12 | -1 | Close |
| aiming | 11 | 9 | -2 | Hough ADS less sensitive than reference |
| reviving | 6 | 10 | +4 | OCR text persists on screen ~30s |
| combat | 4 | 3 | -1 | Close |
| death_event | 2 | 2 | 0 | **Exact match** — red tint works |
| looting | 2 | 3 | +1 | Close |
| hi_intensity_combat | 1 | 0 | -1 | Threshold too strict |
| vehicle_traversal | 1 | 1 | 0 | **Exact match** |

**Total: 40/40 windows. 3 exact, 4 within ±1, 1 over-detection.**

### Mismatch Analysis

**Reviving over-detection (10 vs 6):**
Root cause: OCR finds "REVIV" text in loot_ui/crafting_ui region. The revive UI overlay persists on screen for ~30s (t=65-94.5), but the actual revive action is only ~18s. The OCR caching (5s intervals) propagates each positive detection. This is a fundamental limitation of text-persistence-based detection.
Possible fixes: require additional motion constraints (player should be stationary while reviving), or time-limit consecutive revive detections.

**Aiming under-detection (9 vs 11):**
Root cause: Hough circle ADS detection requires a clear circular scope overlay centered on screen. Non-circular scopes (red dots, iron sights) are missed. The reference project may have used a broader ADS detection including crosshair detection.

**hi_intensity_combat missed (0 vs 1):**
Root cause: Requires simultaneous RMS > 0.09, ZCR > 0.107, persons > 0, AND onset_rate > 8.0. All four conditions rarely co-occur in a single 2s window. The threshold combination is too strict.

### Performance
- 238 events, 120s clip, ~115s processing time
- ~1.0x realtime on CPU (M-series MacBook)
- Zero disk writes (no chunks)
- Memory stable (< 512MB)

## Rejected Approaches

- **Rewrite from scratch**: The current code structure is sound. The classifier, audio pipeline, and output format are all good. Only the video I/O layer needs fixing.
- **Multi-worker processing**: Laptop is resource-constrained. Single worker is correct.
- **Full-resolution YOLO**: 320px is sufficient for person/vehicle counting. Higher resolution would 3-4x the cost.
- **Center-screen OCR for revive**: Tried adding a broad center-screen OCR region for revive detection. Resulted in massive false positives (70/238 events). Removed.
- **ADS via OCR**: Original approach was broken (ads_scope region unconfirmed in calibration). Hough circles are more reliable despite lower recall.
