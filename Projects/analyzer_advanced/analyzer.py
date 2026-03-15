"""
analyzer.py — Phase 2+3: Closed-loop behavioral processor (v0.2)
Input:  calibration.json, data/audio.opus, data/video.mkv
Output: behavior_timeline.json (NDJSON)

Architecture: Audio every 2s → decide FPS (1 or 2) with 4s hysteresis
              Per frame: YOLO + Optical Flow + red tint + Hough ADS + OCR → classify_state()

v0.2 changes:
  - Direct cv2 seeking from source video (no chunk files to disk)
  - Red tint death screen detection (HSV, threshold 0.50)
  - ADS detection via Hough circles (replaces broken OCR)
  - Checkpoint/resume support
  - OCR interval reduced to 5s for better revive recall
"""

import gc
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import easyocr
import librosa
import numpy as np
import soundfile as sf
from tqdm import tqdm
from ultralytics import YOLO

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
VIDEO_PATH = "data/video.mkv"
AUDIO_OPUS_PATH = "data/audio.opus"
AUDIO_WAV_PATH = "data/audio_full.wav"
CALIB_PATH = "calibration.json"
OUTPUT_PATH = "behavior_timeline.json"
CHECKPOINT_PATH = "checkpoint.json"

AUDIO_STEP_S = 2.0      # audio window step
AUDIO_WIN_S = 2.0        # audio analysis window
HI_FPS = 2               # frames/s during active events
LO_FPS = 0.5             # frames/s during calm (1 frame per 2s)
FPS_HYSTERESIS_S = 4.0   # seconds before switching FPS mode down
OCR_INTERVAL_S = 15.0    # run OCR every N seconds

# Red tint death detection
RED_TINT_THRESHOLD = 0.50  # ratio of red pixels; reference project: death=0.58-0.68, baseline=0.10-0.17

# Audio thresholds (calibrate.py may override)
DEFAULT_THRESHOLDS = {
    "rms_silence": 0.015,
    "rms_combat": 0.065,
    "rms_hi_combat": 0.110,
    "zcr_gunshot": 0.200,
    "zcr_panic": 0.250,
    "onset_rate_combat": 4.0,
    "onset_rate_hi": 8.0,
    "spectral_flat_stealth": 0.060,
    "flow_rotation_hi": 8.0,
    "flow_motion_idle": 0.5,
    "flow_motion_moderate": 3.0,
}

STATE_NAMES = {
    1:  "menu_or_lobby",
    2:  "death_event",
    3:  "frustration",
    4:  "success",
    5:  "reviving",
    6:  "hi_intensity_combat",
    7:  "combat",
    8:  "panic",
    9:  "aiming",
    10: "stealth",
    11: "looting",
    12: "resource_mgmt",
    13: "confusion",
    14: "vehicle_traversal",
    15: "exploration",
    16: "idle",
    17: "hi_intensity_unk",
}


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint(path: str) -> dict | None:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def save_checkpoint(path: str, t: float, events_written: int):
    data = {"last_t": t, "events_written": events_written, "timestamp": time.time()}
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def convert_audio(opus_path: str, wav_path: str):
    """Convert audio.opus → audio_full.wav (22050 Hz mono) if not already done."""
    if os.path.exists(wav_path):
        print(f"  Audio WAV already exists: {wav_path}")
        return
    print(f"  Converting {opus_path} → {wav_path} ...")
    subprocess.run(
        ["ffmpeg", "-y", "-i", opus_path, "-ar", "22050", "-ac", "1",
         "-f", "wav", wav_path, "-loglevel", "quiet"],
        check=True,
    )
    print(f"  Done. ({os.path.getsize(wav_path) / 1e9:.2f} GB)")


def read_audio_window(wav_path: str, t_start: float, t_end: float, sr: int = 22050) -> np.ndarray:
    """Stream-read a time window from WAV — avoids loading full 1.6 GB."""
    start_sample = int(t_start * sr)
    n_samples = int((t_end - t_start) * sr)
    if n_samples <= 0:
        return np.zeros(sr, dtype=np.float32)
    try:
        with sf.SoundFile(wav_path) as f:
            total = len(f)
            if start_sample >= total:
                return np.zeros(n_samples, dtype=np.float32)
            f.seek(start_sample)
            data = f.read(min(n_samples, total - start_sample), dtype='float32')
            if len(data) < n_samples:
                data = np.pad(data, (0, n_samples - len(data)))
            return data
    except Exception:
        return np.zeros(n_samples, dtype=np.float32)


def analyze_audio_window(y: np.ndarray, sr: int = 22050) -> dict:
    """Compute audio features for a short window."""
    if len(y) == 0 or np.all(y == 0):
        return {
            "rms": 0.0, "zcr_mean": 0.0, "onset_rate": 0.0,
            "spectral_flatness": 0.0, "is_vocal_outburst": False,
        }

    hop = 512
    rms_arr = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    zcr_arr = librosa.feature.zero_crossing_rate(y, frame_length=2048, hop_length=hop)[0]
    sf_arr = librosa.feature.spectral_flatness(y=y)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    n_onsets = len(librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr))
    duration = len(y) / sr

    rms_val = float(np.mean(rms_arr))
    zcr_val = float(np.mean(zcr_arr))
    sf_val = float(np.mean(sf_arr))
    onset_rate = n_onsets / duration if duration > 0 else 0.0

    return {
        "rms": rms_val,
        "zcr_mean": zcr_val,
        "onset_rate": onset_rate,
        "spectral_flatness": sf_val,
        "is_vocal_outburst": False,
    }


# ---------------------------------------------------------------------------
# Vision helpers
# ---------------------------------------------------------------------------

def crop_region(frame: np.ndarray, bbox: list, height: int, width: int) -> np.ndarray:
    """Crop frame to bbox [x1,y1,x2,y2], clamped to frame dimensions."""
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    x2 = max(x1 + 1, min(x2, width))
    y1 = max(0, min(y1, height - 1))
    y2 = max(y1 + 1, min(y2, height))
    return frame[y1:y2, x1:x2]


def run_yolo(model: YOLO, frame: np.ndarray, class_map: dict) -> dict:
    """Run YOLO inference and count relevant object classes."""
    results = model(frame, verbose=False, imgsz=320)
    persons = 0
    vehicles = 0
    loot_items = 0
    for r in results:
        for cls_id in r.boxes.cls.cpu().numpy().astype(int):
            if cls_id == class_map["person"]:
                persons += 1
            elif cls_id in class_map["vehicle"]:
                vehicles += 1
            elif cls_id in class_map["loot_proxy"]:
                loot_items += 1
    return {"persons": persons, "vehicles": vehicles, "loot_items": loot_items}


def compute_optical_flow(prev_gray: np.ndarray, curr_gray: np.ndarray) -> dict:
    """Farneback optical flow → magnitude, camera_rotation, net_displacement, direction_changes."""
    if prev_gray is None or curr_gray is None:
        return {"flow_magnitude": 0.0, "camera_rotation": 0.0,
                "net_displacement": 0.0, "direction_changes": 0}

    small_prev = cv2.resize(prev_gray, (320, 180))
    small_curr = cv2.resize(curr_gray, (320, 180))

    flow = cv2.calcOpticalFlowFarneback(
        small_prev, small_curr, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
    )

    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    mean_mag = float(np.mean(mag))
    camera_rotation = float(np.std(ang))

    mean_dx = float(np.mean(flow[..., 0]))
    mean_dy = float(np.mean(flow[..., 1]))
    net_displacement = float(np.sqrt(mean_dx**2 + mean_dy**2))

    angles_flat = ang.flatten()
    quadrants = (angles_flat / (np.pi / 2)).astype(int) % 4
    n_pairs = len(quadrants) - 1
    direction_changes = float(np.sum(np.diff(quadrants) != 0)) / n_pairs if n_pairs > 0 else 0.0

    return {
        "flow_magnitude": mean_mag,
        "camera_rotation": camera_rotation,
        "net_displacement": net_displacement,
        "direction_changes": direction_changes,
    }


def detect_red_tint(frame: np.ndarray) -> float:
    """Detect death screen red tint via HSV analysis.
    Returns ratio of red pixels (0.0-1.0).
    Reference: death screens = 0.58-0.68, baseline gameplay = 0.10-0.17.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    # Red hue wraps around: H<10 or H>170, with S>50 to exclude gray
    red_mask = ((h < 10) | (h > 170)) & (s > 50)
    return float(np.sum(red_mask)) / red_mask.size


def detect_ads_hough(frame: np.ndarray, height: int, width: int) -> bool:
    """Detect ADS (aim-down-sight) via Hough circle at frame center.
    Scope overlays produce a strong circular edge pattern centered on screen.
    Uses strict parameters: high edge threshold (param1=150), high accumulator
    threshold (param2=80), and requires circle center within 5% of frame center.
    """
    cx, cy = width // 2, height // 2
    rx, ry = width // 5, height // 5  # crop center 40%
    y1, y2 = max(0, cy - ry), min(height, cy + ry)
    x1, x2 = max(0, cx - rx), min(width, cx + rx)
    center_crop = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(center_crop, cv2.COLOR_BGR2GRAY)

    # Apply edge detection first to verify strong circular edges
    edges = cv2.Canny(gray, 100, 200)
    edge_density = float(np.sum(edges > 0)) / edges.size
    if edge_density < 0.02:  # not enough edges for a scope overlay
        return False

    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT,
        dp=1.5, minDist=80,
        param1=120, param2=60,  # moderate: require clear circular evidence
        minRadius=int(min(rx, ry) * 0.5),
        maxRadius=int(min(rx, ry) * 1.2),
    )
    if circles is None:
        return False

    # Verify circle is centered (within 15% of crop center)
    crop_h, crop_w = gray.shape
    crop_cx, crop_cy = crop_w / 2, crop_h / 2
    tolerance = min(crop_w, crop_h) * 0.15
    for circle in circles[0]:
        dist = np.sqrt((circle[0] - crop_cx)**2 + (circle[1] - crop_cy)**2)
        if dist < tolerance:
            return True
    return False


def run_ocr(reader, frame: np.ndarray, hud_regions: dict, height: int, width: int,
            player_name: str) -> dict:
    """Run EasyOCR on relevant HUD crops and parse results."""
    ocr_out = {
        "hp": None,
        "ads_active": False,
        "death_screen": False,
        "loot_ui_open": False,
        "crafting_ui_open": False,
        "killfeed_snippet": "",
        "is_menu": False,
        "revive_detected": False,
    }

    def ocr_region(region_name: str) -> list:
        info = hud_regions.get(region_name, {})
        bbox = info.get("bbox") if isinstance(info, dict) else info
        if not bbox:
            return []
        crop = crop_region(frame, bbox, height, width)
        if crop.size == 0:
            return []
        return reader.readtext(crop, detail=1)

    # Menu detection
    for _, text, conf in ocr_region("menu_nav"):
        if conf > 0.5 and any(k in text.upper() for k in ["PLAY", "ARMORY", "PERSONAL SUPPLY"]):
            ocr_out["is_menu"] = True
            break

    # HP bar
    for _, text, conf in ocr_region("hp_bar"):
        if conf > 0.4:
            nums = re.findall(r'\d+', text)
            if nums:
                ocr_out["hp"] = int(nums[0])
                break

    # Death screen OCR (supplements red tint detection)
    for _, text, conf in ocr_region("death_screen"):
        if conf > 0.4 and any(k in text.upper() for k in ["ELIMINAT", "YOU DIED", "KILLED", "KNOCKED"]):
            ocr_out["death_screen"] = True
            break

    # Loot UI
    for _, text, conf in ocr_region("loot_ui"):
        if conf > 0.4 and len(text.strip()) > 2:
            ocr_out["loot_ui_open"] = True
            break

    # Crafting UI
    for _, text, conf in ocr_region("crafting_ui"):
        if conf > 0.4 and "CRAFT" in text.upper():
            ocr_out["crafting_ui_open"] = True
            break

    # Killfeed — look for player name as killer
    for _, text, conf in ocr_region("killfeed"):
        if conf > 0.4 and len(text.strip()) > 1:
            if player_name.lower() in text.lower():
                ocr_out["killfeed_snippet"] = text.strip()

    # Revive detection — check targeted HUD regions only (not death_screen, too broad)
    for region in ["loot_ui", "crafting_ui"]:
        if ocr_out["revive_detected"]:
            break
        for _, text, conf in ocr_region(region):
            if conf > 0.4 and "REVIV" in text.upper():
                ocr_out["revive_detected"] = True
                break

    return ocr_out


# ---------------------------------------------------------------------------
# State classifier
# ---------------------------------------------------------------------------

def classify_state(audio: dict, vision: dict, ocr: dict, thr: dict) -> int:
    """Priority cascade → returns state_id 1-17."""
    rms = audio["rms"]
    zcr = audio["zcr_mean"]
    onset_rate = audio["onset_rate"]
    sf_val = audio["spectral_flatness"]

    flow_mag = vision.get("flow_magnitude", 0.0)
    cam_rot = vision.get("camera_rotation", 0.0)
    net_disp = vision.get("net_displacement", 0.0)
    dir_chg = vision.get("direction_changes", 0)
    persons = vision.get("persons", 0)
    vehicles = vision.get("vehicles", 0)
    red_tint = vision.get("red_tint_ratio", 0.0)

    hp = ocr.get("hp")
    ads = ocr.get("ads_active", False) or vision.get("ads_hough", False)
    death_screen = ocr.get("death_screen", False) or (red_tint > RED_TINT_THRESHOLD)
    loot_ui = ocr.get("loot_ui_open", False)
    crafting_ui = ocr.get("crafting_ui_open", False)
    killfeed = ocr.get("killfeed_snippet", "")
    is_menu = ocr.get("is_menu", False)
    revive = ocr.get("revive_detected", False)

    # 1. Menu / lobby
    if is_menu:
        return 1

    # 2. Death event
    is_dead = death_screen or (hp is not None and hp == 0)
    if is_dead:
        # 3. Frustration = death + vocal outburst
        if rms > thr["rms_hi_combat"] and zcr > thr["zcr_panic"]:
            return 3
        return 2

    # 4. Success (player made a kill)
    if killfeed:
        return 4

    # 5. Reviving
    if revive:
        return 5

    # 8. Panic
    if cam_rot > thr["flow_rotation_hi"] and onset_rate > thr["onset_rate_hi"] and zcr > thr["zcr_gunshot"]:
        return 8

    # 6. Hi-intensity combat
    if (rms > thr["rms_hi_combat"] and zcr > thr["zcr_gunshot"]
            and persons > 0 and onset_rate > thr["onset_rate_hi"]):
        return 6

    # 7. Combat
    high_audio = rms > thr["rms_combat"]
    has_motion = flow_mag > thr["flow_motion_moderate"]
    if high_audio and (has_motion or ads) and (persons >= 2 or ads):
        return 7

    # 9. Aiming
    if ads:
        return 9

    # 12. Resource management
    if crafting_ui and flow_mag < thr["flow_motion_moderate"]:
        return 12

    # 11. Looting
    if loot_ui and flow_mag < thr["flow_motion_moderate"]:
        return 11

    # 10. Stealth
    if (rms < thr["rms_silence"] and sf_val > thr["spectral_flat_stealth"]
            and flow_mag < thr["flow_motion_moderate"]):
        return 10

    # 14. Vehicle traversal
    if vehicles > 0 and flow_mag > thr["flow_motion_moderate"]:
        return 14

    # 13. Confusion (dir_chg normalized 0-1; >0.12 = significant)
    if net_disp < thr["flow_motion_moderate"] and dir_chg > 0.12:
        return 13

    # 15. Exploration
    if flow_mag > thr["flow_motion_idle"]:
        return 15

    # 16. Idle
    if flow_mag < thr["flow_motion_idle"] and rms < thr["rms_combat"]:
        return 16

    # 17. High-intensity unknown fallback
    if rms > thr["rms_combat"] or flow_mag > thr["flow_motion_moderate"]:
        return 17

    return 16  # default idle


# ---------------------------------------------------------------------------
# Stream processor (no chunk files)
# ---------------------------------------------------------------------------

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe. Handles MKV (duration in tags)."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", video_path],
        capture_output=True, text=True
    )
    info = json.loads(result.stdout)

    # Try format-level duration first (most reliable)
    fmt_dur = info.get("format", {}).get("duration")
    if fmt_dur:
        return float(fmt_dur)

    # Try stream-level duration, then tags (MKV stores it in tags)
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            dur = s.get("duration")
            if dur:
                return float(dur)
            tag_dur = s.get("tags", {}).get("DURATION", "")
            if tag_dur:
                parts = tag_dur.split(":")
                if len(parts) == 3:
                    h, m, sec = parts
                    return float(h) * 3600 + float(m) * 60 + float(sec)
    return 0.0


def process_video(
    video_path: str,
    t_start: float,
    t_end: float,
    width: int,
    height: int,
    model: YOLO,
    reader,
    calib: dict,
    out_file,
    events_offset: int = 0,
) -> int:
    """Process video range by seeking directly — no chunk files written to disk.

    Opens cv2.VideoCapture on the source video and seeks to each frame time.
    """
    thr = calib["thresholds"]
    hud = calib["hud_regions"]
    player_name = calib["player_name"]
    class_map = dict(calib["yolo_class_map"])
    class_map["vehicle"] = [int(x) for x in class_map["vehicle"]]
    class_map["loot_proxy"] = [int(x) for x in class_map["loot_proxy"]]

    wav_path = AUDIO_WAV_PATH
    sr = 22050

    # Webcam exclusion bbox
    webcam_entry = hud.get("webcam_exclude", {})
    webcam_bbox = webcam_entry.get("bbox") if isinstance(webcam_entry, dict) else webcam_entry
    if not webcam_bbox:
        webcam_bbox = None

    # Open source video directly — no chunk extraction
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"    ERROR: could not open {video_path}")
        return 0

    # FPS mode state machine
    current_fps = LO_FPS
    fps_mode = "lo"
    fps_switch_timer = 0.0

    prev_gray = None
    step = AUDIO_STEP_S
    events_written = events_offset
    t = t_start

    # OCR state
    last_ocr_t = t_start - OCR_INTERVAL_S  # force OCR on first frame
    cached_ocr = {
        "hp": None, "ads_active": False, "death_screen": False,
        "loot_ui_open": False, "crafting_ui_open": False,
        "killfeed_snippet": "", "is_menu": False, "revive_detected": False,
    }

    checkpoint_interval = 30.0  # save checkpoint every 30s of video time
    last_checkpoint_t = t_start

    pbar = tqdm(total=int(t_end - t_start), desc="Processing", unit="s", initial=0)

    while t < t_end:
        # Audio window
        y_win = read_audio_window(wav_path, t, t + AUDIO_WIN_S, sr)
        audio_feat = analyze_audio_window(y_win, sr)

        # Decide FPS based on audio energy
        audio_active = (audio_feat["rms"] > thr["rms_combat"] or
                        audio_feat["onset_rate"] > thr["onset_rate_combat"])
        if audio_active:
            fps_switch_timer = FPS_HYSTERESIS_S
        else:
            fps_switch_timer = max(0.0, fps_switch_timer - step)

        new_fps = HI_FPS if fps_switch_timer > 0 else LO_FPS
        if new_fps != current_fps:
            current_fps = new_fps
            fps_mode = "hi" if current_fps == HI_FPS else "lo"

        # Frame timestamps within this audio step
        frame_interval = 1.0 / current_fps
        frame_times = np.arange(t, min(t + step, t_end), frame_interval)

        for ft in frame_times:
            # Seek directly in source video
            cap.set(cv2.CAP_PROP_POS_MSEC, ft * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            # Optical flow
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            flow_feat = compute_optical_flow(prev_gray, gray)
            prev_gray = gray

            # Red tint death detection
            red_tint = detect_red_tint(frame)

            # ADS via Hough circles
            ads_hough = detect_ads_hough(frame, height, width)

            # Blank webcam region before YOLO
            if webcam_bbox:
                x1, y1, x2, y2 = webcam_bbox
                frame[y1:y2, x1:x2] = 0

            # YOLO
            vision_feat = run_yolo(model, frame, class_map)
            vision_feat.update(flow_feat)
            vision_feat["red_tint_ratio"] = red_tint
            vision_feat["ads_hough"] = ads_hough

            # OCR — every OCR_INTERVAL_S seconds of video time
            if ft - last_ocr_t >= OCR_INTERVAL_S:
                cached_ocr = run_ocr(reader, frame, hud, height, width, player_name)
                last_ocr_t = ft

            ocr_feat = cached_ocr

            # Classify
            state_id = classify_state(audio_feat, vision_feat, ocr_feat, thr)
            audio_feat["is_vocal_outburst"] = (state_id == 3)

            event = {
                "t": round(ft, 3),
                "state_id": state_id,
                "state_name": STATE_NAMES[state_id],
                "audio": {
                    "rms": round(audio_feat["rms"], 5),
                    "zcr_mean": round(audio_feat["zcr_mean"], 5),
                    "onset_rate": round(audio_feat["onset_rate"], 3),
                    "spectral_flatness": round(audio_feat["spectral_flatness"], 5),
                    "is_vocal_outburst": audio_feat["is_vocal_outburst"],
                },
                "vision": {
                    "persons": vision_feat["persons"],
                    "vehicles": vision_feat["vehicles"],
                    "loot_items": vision_feat["loot_items"],
                    "flow_magnitude": round(vision_feat["flow_magnitude"], 3),
                    "camera_rotation": round(vision_feat["camera_rotation"], 3),
                    "net_displacement": round(vision_feat["net_displacement"], 3),
                    "direction_changes": round(vision_feat["direction_changes"], 4),
                    "red_tint_ratio": round(red_tint, 4),
                    "ads_hough": ads_hough,
                },
                "ocr": {
                    "hp": ocr_feat["hp"],
                    "ads_active": ocr_feat["ads_active"],
                    "death_screen": ocr_feat["death_screen"],
                    "loot_ui_open": ocr_feat["loot_ui_open"],
                    "crafting_ui_open": ocr_feat["crafting_ui_open"],
                    "killfeed_snippet": ocr_feat["killfeed_snippet"],
                    "revive_detected": ocr_feat["revive_detected"],
                },
                "fps_mode": fps_mode,
            }

            out_file.write(json.dumps(event) + "\n")
            out_file.flush()
            events_written += 1

        # Update progress
        pbar.update(int(step))

        # Checkpoint
        if t - last_checkpoint_t >= checkpoint_interval:
            save_checkpoint(CHECKPOINT_PATH, t, events_written)
            last_checkpoint_t = t

        t += step

    pbar.close()
    cap.release()

    # Final checkpoint
    save_checkpoint(CHECKPOINT_PATH, t_end, events_written)

    return events_written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    # Load calibration
    if not os.path.exists(CALIB_PATH):
        print(f"ERROR: {CALIB_PATH} not found. Run calibrate.py first.")
        sys.exit(1)

    with open(CALIB_PATH) as f:
        calib = json.load(f)

    width = calib["video"]["width"]
    height = calib["video"]["height"]

    print("==> Project Sentinel — Behavioral Analyzer v0.2")
    print(f"    Player: {calib['player_name']}")
    print(f"    Video:  {VIDEO_PATH}")
    print(f"    Resolution: {width}x{height}")

    # Convert audio
    print("\n[1/3] Preparing audio...")
    if not os.path.exists(AUDIO_OPUS_PATH):
        print(f"ERROR: {AUDIO_OPUS_PATH} not found.")
        sys.exit(1)
    convert_audio(AUDIO_OPUS_PATH, AUDIO_WAV_PATH)

    # Video duration
    print("\n[2/3] Getting video info...")
    total_duration = get_video_duration(VIDEO_PATH)
    if total_duration <= 0:
        print("ERROR: Could not read video duration.")
        sys.exit(1)
    print(f"    Duration: {total_duration:.1f}s ({total_duration/3600:.2f}h)")

    # Check for resume
    resume_t = 0.0
    resume_events = 0
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    file_mode = "w"
    if checkpoint and checkpoint.get("last_t", 0) > 0:
        resume_t = checkpoint["last_t"]
        resume_events = checkpoint.get("events_written", 0)
        if resume_t < total_duration:
            print(f"    Resuming from t={resume_t:.1f}s ({resume_events} events already written)")
            file_mode = "a"
        else:
            print(f"    Previous run completed. Starting fresh.")
            resume_t = 0.0
            resume_events = 0

    # Initialize models
    print("\n[3/3] Loading models...")
    model = YOLO("yolo11n.pt")
    print("    YOLO loaded.")
    reader = easyocr.Reader(['en'], gpu=False)
    print("    EasyOCR loaded.")

    # Process video — direct seeking, no chunk files
    print(f"\n    Processing {VIDEO_PATH} → {OUTPUT_PATH}")
    print(f"    Range: [{resume_t:.0f}, {total_duration:.0f}]s")
    print(f"    FPS: lo={LO_FPS}, hi={HI_FPS}, hysteresis={FPS_HYSTERESIS_S}s")
    print(f"    OCR interval: {OCR_INTERVAL_S}s")
    print(f"    Red tint threshold: {RED_TINT_THRESHOLD}")

    with open(OUTPUT_PATH, file_mode) as out_file:
        n_events = process_video(
            video_path=VIDEO_PATH,
            t_start=resume_t,
            t_end=total_duration,
            width=width,
            height=height,
            model=model,
            reader=reader,
            calib=calib,
            out_file=out_file,
            events_offset=resume_events,
        )

    elapsed = time.time() - start_time
    print(f"\n==> Done. {n_events} events written to {OUTPUT_PATH}")
    print(f"    Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"    Rate: {total_duration / elapsed:.1f}x realtime" if elapsed > 0 else "")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        VIDEO_PATH = "data/clip_15min.mp4"
        AUDIO_OPUS_PATH = "data/clip_15min_audio.opus"
        AUDIO_WAV_PATH = "data/clip_15min_audio.wav"
        OUTPUT_PATH = "behavior_timeline_smoke.json"
        CHECKPOINT_PATH = "checkpoint_smoke.json"
        print("==> SMOKE TEST MODE: using clip_15min.mp4")

    main()
