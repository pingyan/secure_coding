# Runbook — Project Sentinel

## Prerequisites

- macOS (ARM64)
- Python 3.13 (via system python3)
- ffmpeg + ffprobe installed
- ~15GB free disk (11GB video + outputs)

## Setup

```bash
cd /Users/ping.yan/Projects/analyzer_advanced
./setup_env.sh          # creates .venv, installs deps
source .venv/bin/activate
```

## Data Requirements

Place in `data/`:
- `video.mkv` — full gameplay recording (~11GB, 5h10m)
- `audio.opus` — extracted audio track (~218MB)
- `clip_2min.mp4` — 2-min calibration clip (any representative gameplay segment)
- `clip_15min.mp4` — 2-min benchmark clip (starts at minute 15 of video.mkv)

Extract clips from source video if needed:
```bash
# Calibration clip (first 2 minutes of gameplay, skip menu)
ffmpeg -ss 300 -i data/video.mkv -t 120 -c:v libx264 -crf 18 data/clip_2min.mp4

# Benchmark clip (minute 15-17)
ffmpeg -ss 900 -i data/video.mkv -t 120 -c:v libx264 -crf 18 data/clip_15min.mp4

# Extract audio for benchmark clip
ffmpeg -i data/clip_15min.mp4 -ar 22050 -ac 1 -c:a opus data/clip_15min_audio.opus
```

## Running

### Full pipeline
```bash
./run_all.sh
```

### Step by step
```bash
# 1. Calibration (uses clip_2min.mp4, ~2-3 min)
python calibrate.py

# 2. Analysis (uses video.mkv, ~9h for full video)
python analyzer.py

# 3. Reporting
python report.py
```

### Smoke test (benchmark clip only)
```bash
python analyzer.py --smoke
# Uses clip_15min.mp4, outputs behavior_timeline_smoke.json
# Expected: ~120s of events, ~40 behavioral windows
```

## Outputs

| File | Format | Description |
|------|--------|-------------|
| `calibration.json` | JSON | Audio thresholds + HUD regions |
| `behavior_timeline.json` | NDJSON | One event per line, full video |
| `behavior_timeline_smoke.json` | NDJSON | Smoke test output |
| `final_report.json` | JSON | State breakdown + engagement ratio |
| `highlights.txt` | Text | Human-readable death/kill highlights |

## Monitoring a Run

- Watch NDJSON grow: `wc -l behavior_timeline.json`
- Check last event: `tail -1 behavior_timeline.json | python -m json.tool`
- Disk usage: `du -sh chunks/ data/` (chunks/ should stay empty after v0.2)

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 bytes output | Process hung on first OCR/YOLO | Check model loading, increase timeout |
| OOM | Too many frames in memory | Ensure single-pass streaming, workers=1 |
| Chunks dir growing | Chunk extraction not cleaned up | v0.2 eliminates chunks entirely |
| Audio WAV missing | ffmpeg conversion failed | Check ffmpeg installation, audio.opus exists |
| Calibration fails | clip_2min.mp4 missing or corrupt | Re-extract from video.mkv |

## Benchmark Validation

Expected results for the 2-min clip at minute 15:
```
exploration:          13 windows
aiming:              11 windows
reviving:             6 windows
combat:               4 windows
death_event:          2 windows
looting:              2 windows
high_intensity_combat: 1 window
vehicle_traversal:    1 window
total:               40 windows
```

## Resource Budgets

| Resource | Budget | Notes |
|----------|--------|-------|
| Disk (temp) | 0 MB | No chunk files in v0.2+ |
| Memory | < 512 MB | Single-pass, 2 frames max |
| CPU | 1 worker | No parallelism on laptop |
| OCR calls | 1 per 15s video | Cached between frames |
| YOLO inference | 320px input | CPU-only, ~50ms/frame |
