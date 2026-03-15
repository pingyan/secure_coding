"""
calibrate.py — Phase 1: Compute audio thresholds + confirm HUD regions
Input:  data/clip_2min.mp4
Output: calibration.json
"""

import json
import os
import subprocess
import tempfile
import numpy as np
import librosa
import easyocr
import cv2

CLIP_PATH = "data/clip_2min.mp4"
OUTPUT_PATH = "calibration.json"
PLAYER_NAME = "Playtime11"

# Super People 1920×1080 HUD region priors [x1, y1, x2, y2]
HUD_REGIONS = {
    "hp_bar":       [680,  955, 1240, 1000],
    "level":        [840,  985, 1080, 1040],
    "killfeed":     [1380,  15, 1920,  280],
    "ads_scope":    [860,  510, 1060,  555],
    "death_screen": [560,  380, 1360,  700],
    "loot_ui":      [15,   590,  410, 1060],
    "crafting_ui":  [15,   380,  510,  910],
    "menu_nav":     [130,    0,  800,   60],
    "webcam_exclude": [0, 750,  220, 1080],  # streamer cam — never OCR this
}

# YOLO class IDs (COCO)
YOLO_CLASS_MAP = {
    "person":     0,
    "vehicle":    [2, 5, 7],   # car, bus, truck
    "loot_proxy": [24, 26],    # backpack, handbag as loot proxy
}


def extract_audio_wav(video_path: str) -> str:
    """Extract audio from video to a temp WAV file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-ar", "22050", "-ac", "1",
         "-f", "wav", tmp.name, "-loglevel", "quiet"],
        check=True,
    )
    return tmp.name


def calibrate_audio(wav_path: str) -> dict:
    """Compute audio feature statistics from calibration clip."""
    print("  Loading audio...")
    y, sr = librosa.load(wav_path, sr=22050, mono=True)

    print("  Computing RMS...")
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]

    print("  Computing ZCR...")
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=2048, hop_length=512)[0]

    print("  Computing spectral flatness...")
    sf = librosa.feature.spectral_flatness(y=y)[0]

    print("  Computing onset rate...")
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    duration_s = len(y) / sr
    onset_rate_baseline = len(onset_frames) / duration_s if duration_s > 0 else 0.0

    mean_rms = float(np.mean(rms))
    std_rms = float(np.std(rms))
    zcr_95th = float(np.percentile(zcr, 95))
    mean_sf = float(np.mean(sf))

    audio_stats = {
        "mean_rms": mean_rms,
        "std_rms": std_rms,
        "zcr_95th": zcr_95th,
        "mean_spectral_flatness": mean_sf,
        "onset_rate_baseline": onset_rate_baseline,
    }

    # Derive thresholds from signal statistics
    thresholds = {
        "rms_silence":         max(0.008, mean_rms * 0.3),
        "rms_combat":          max(0.050, mean_rms + std_rms),
        "rms_hi_combat":       max(0.090, mean_rms + 2.0 * std_rms),
        "zcr_gunshot":         zcr_95th,
        "zcr_panic":           zcr_95th * 1.25,
        "onset_rate_combat":   4.0,
        "onset_rate_hi":       8.0,
        "spectral_flat_stealth": 0.060,
        "flow_rotation_hi":    8.0,
        "flow_motion_idle":    0.5,
        "flow_motion_moderate": 3.0,
    }

    print(f"  mean_rms={mean_rms:.4f}  std_rms={std_rms:.4f}  zcr_95th={zcr_95th:.4f}")
    print(f"  onset_rate_baseline={onset_rate_baseline:.2f}/s")

    return audio_stats, thresholds


def sample_frames(video_path: str, n: int = 10) -> list:
    """Sample n evenly-spaced frames from video, returned as np arrays."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    duration = None
    width, height = 1920, 1080
    fps = 60.0
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            duration = float(s.get("duration", 0))
            width = int(s.get("width", 1920))
            height = int(s.get("height", 1080))
            fps_str = s.get("r_frame_rate", "60/1")
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
            break

    if not duration or duration <= 0:
        duration = 120.0  # assume 2 min

    frames = []
    times = np.linspace(2.0, duration - 2.0, n)
    for t in times:
        cmd = [
            "ffmpeg", "-ss", str(t), "-i", video_path,
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-", "-loglevel", "quiet"
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and len(result.stdout) == width * height * 3:
            frame = np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 3)
            frames.append(frame)
    return frames, width, height, fps


def confirm_hud_regions(frames: list, reader, width: int, height: int) -> dict:
    """Run EasyOCR on sampled frames to confirm which HUD regions have content."""
    confirmed = {}
    total_frames = len(frames)
    print(f"  Sampling {total_frames} frames for HUD confirmation...")

    for region_name, bbox in HUD_REGIONS.items():
        if region_name == "webcam_exclude":
            confirmed[region_name] = {"bbox": bbox, "confirmed": False, "note": "excluded"}
            continue

        x1, y1, x2, y2 = bbox
        # Clamp to actual frame dimensions
        x1 = max(0, min(x1, width - 1))
        x2 = max(0, min(x2, width))
        y1 = max(0, min(y1, height - 1))
        y2 = max(0, min(y2, height))

        found_text = False
        for frame in frames:
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            results = reader.readtext(crop, detail=1)
            for (_, text, conf) in results:
                if conf > 0.5 and len(text.strip()) > 0:
                    found_text = True
                    break
            if found_text:
                break

        confirmed[region_name] = {
            "bbox": bbox,
            "confirmed": found_text,
        }
        status = "OK" if found_text else "unconfirmed (using prior)"
        print(f"    {region_name}: {status}")

    return confirmed


def get_video_meta(video_path: str) -> dict:
    """Get video width, height, fps, duration."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            fps_str = s.get("r_frame_rate", "60/1")
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
            return {
                "width": int(s.get("width", 1920)),
                "height": int(s.get("height", 1080)),
                "fps": fps,
                "duration": float(s.get("duration", 0)),
            }
    return {"width": 1920, "height": 1080, "fps": 60.0, "duration": 0.0}


def main():
    print(f"==> Calibrating from {CLIP_PATH}")

    if not os.path.exists(CLIP_PATH):
        raise FileNotFoundError(f"Calibration clip not found: {CLIP_PATH}")

    # --- Video metadata ---
    print("\n[1/4] Reading video metadata...")
    meta = get_video_meta(CLIP_PATH)
    print(f"  {meta['width']}x{meta['height']} @ {meta['fps']:.1f} fps, {meta['duration']:.1f}s")

    # --- Audio calibration ---
    print("\n[2/4] Calibrating audio...")
    wav_path = extract_audio_wav(CLIP_PATH)
    try:
        audio_stats, thresholds = calibrate_audio(wav_path)
    finally:
        os.unlink(wav_path)

    # --- Frame sampling ---
    print("\n[3/4] Sampling frames from clip...")
    frames, width, height, fps = sample_frames(CLIP_PATH, n=10)
    print(f"  Got {len(frames)} frames at {width}x{height}")

    # --- HUD confirmation ---
    print("\n[4/4] Confirming HUD regions with EasyOCR...")
    reader = easyocr.Reader(['en'], gpu=False)
    hud_confirmed = confirm_hud_regions(frames, reader, width, height)
    confirmed_count = sum(1 for v in hud_confirmed.values() if v.get("confirmed"))
    print(f"  Confirmed {confirmed_count}/{len(hud_confirmed)} HUD regions")

    # --- Save calibration ---
    calibration = {
        "player_name": PLAYER_NAME,
        "video": meta,
        "audio": audio_stats,
        "thresholds": thresholds,
        "hud_regions": hud_confirmed,
        "yolo_class_map": YOLO_CLASS_MAP,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\n==> Calibration saved to {OUTPUT_PATH}")
    print(f"    mean_rms={audio_stats['mean_rms']:.4f}, rms_silence={thresholds['rms_silence']:.4f}")
    print(f"    zcr_gunshot={thresholds['zcr_gunshot']:.4f}, onset_rate_combat={thresholds['onset_rate_combat']}")


if __name__ == "__main__":
    main()
