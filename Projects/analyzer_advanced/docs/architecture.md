# Architecture — Project Sentinel (analyzer_advanced)

## Overview

Closed-loop gameplay behavior analyzer for Super People.
Extracts 17 behavioral states from 6h gameplay footage using Audio → Vision → Logic architecture.

## Pipeline Stages

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  calibrate.py │────▶│   analyzer.py     │────▶│  report.py   │
│  (Phase 1)    │     │   (Phase 2+3)     │     │  (Phase 4)   │
│  2-min clip   │     │   Full video      │     │  NDJSON→JSON │
└──────────────┘     └──────────────────┘     └──────────────┘
calibration.json      behavior_timeline.json   final_report.json
                                                highlights.txt
```

### Phase 1: Calibration (`calibrate.py`)
- Input: `data/clip_2min.mp4` (representative gameplay clip)
- Extracts audio features → derives thresholds (RMS, ZCR, onset rate)
- Samples 10 frames → confirms HUD region bounding boxes via EasyOCR
- Output: `calibration.json`

### Phase 2+3: Closed-Loop Analysis (`analyzer.py`)
- **Audio monitor** (every 2s): RMS, ZCR, onset rate, spectral flatness
- **FPS switching**: audio energy/onset triggers HI_FPS (2 fps) vs LO_FPS (1 fps) with 4s hysteresis
- **Per-frame pipeline**: YOLO (320px) → optical flow (320×180) → OCR (throttled, every 15s) → classify_state()
- **State classifier**: priority cascade, 17 states, uses audio + vision + OCR signals
- **Output**: NDJSON (one event per line, streamable, append-friendly)

### Phase 4: Reporting (`report.py`)
- Streams NDJSON line-by-line (never loads full file)
- Produces `final_report.json` (state breakdown, engagement ratio) + `highlights.txt` (deaths, kills)

## Sensor Stack

| Sensor | Library | Purpose |
|--------|---------|---------|
| Audio features | librosa + soundfile | RMS, ZCR, onset rate, spectral flatness |
| Object detection | YOLO v11n (320px) | Person, vehicle, loot proxy counts |
| Motion | OpenCV Farneback (320×180) | Flow magnitude, camera rotation, displacement |
| HUD/OCR | EasyOCR | Menu, death, killfeed, loot, revive, crafting |
| Death screen | (MISSING — needs red tint HSV) | Red screen overlay detection |
| ADS detection | (FRAGILE — OCR-based) | Scope/aim-down-sight detection |

## Data Flow

```
data/video.mkv (11GB, 5h10m) ─┐
data/audio.opus (218MB)        │
calibration.json               │
                               ▼
                     analyzer.py (streaming)
                               │
                               ▼
                    behavior_timeline.json (NDJSON)
                               │
                               ▼
                     report.py (streaming)
                               │
                     ┌─────────┴──────────┐
                     ▼                    ▼
              final_report.json     highlights.txt
```

## Resource Constraints

- **Disk**: NO intermediate chunk files. Seek directly from source video.
- **Memory**: Single-pass streaming. Max 2 frames in memory at once.
- **Workers**: Single worker (constrained laptop).
- **OCR**: Throttled to every 15s of video time. Cached between frames.
- **YOLO**: 320px inference size. CPU-only (GPU optional).

## 17 Behavioral States (Priority Order)

| ID | State | Primary Signals |
|----|-------|-----------------|
| 1 | menu_or_lobby | OCR menu keywords |
| 2 | death_event | Death OCR / red tint / HP=0 |
| 3 | frustration | death + vocal outburst |
| 4 | success | Killfeed with player name |
| 5 | reviving | OCR "REVIV" keyword |
| 6 | hi_intensity_combat | High RMS + ZCR + enemies + onset |
| 7 | combat | Audio + motion/ADS + persons |
| 8 | panic | Camera rotation + onset + ZCR |
| 9 | aiming | ADS active |
| 10 | stealth | Low RMS + high flatness + low motion |
| 11 | looting | Loot UI + low motion |
| 12 | resource_mgmt | Crafting UI + low motion |
| 13 | confusion | Low displacement + high direction changes |
| 14 | vehicle_traversal | Vehicle detected + motion |
| 15 | exploration | Moderate motion, no other signals |
| 16 | idle | Low motion, no signals |
| 17 | hi_intensity_unk | Fallback for unmatched high-entropy events |
