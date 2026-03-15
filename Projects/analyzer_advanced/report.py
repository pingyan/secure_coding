"""
report.py — Generate final_report.json + highlights.txt
Input:  behavior_timeline.json (NDJSON)
Output: final_report.json, highlights.txt

Streams input line-by-line — never loads full file into memory.
"""

import json
import os
import sys

TIMELINE_PATH = "behavior_timeline.json"
REPORT_PATH = "final_report.json"
HIGHLIGHTS_PATH = "highlights.txt"

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

HIGHLIGHT_STATES = {2, 3, 4}  # death, frustration, success


def fmt_timestamp(t: float) -> str:
    """Format seconds to HH:MM:SS.f"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:05.1f}"


def main():
    if not os.path.exists(TIMELINE_PATH):
        print(f"ERROR: {TIMELINE_PATH} not found. Run analyzer.py first.")
        sys.exit(1)

    # Accumulators
    state_seconds = {sid: 0.0 for sid in STATE_NAMES}
    highlights = {2: [], 3: [], 4: []}
    total_seconds = 0.0
    prev_t = None
    prev_fps_mode = "lo"
    line_count = 0

    print(f"==> Streaming {TIMELINE_PATH} ...")

    with open(TIMELINE_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = event.get("t", 0.0)
            state_id = event.get("state_id", 16)
            fps_mode = event.get("fps_mode", "lo")

            # dt = time represented by this event
            if prev_t is not None and t > prev_t:
                dt = t - prev_t
            elif fps_mode == "hi":
                dt = 1.0 / 2    # HI_FPS = 2
            else:
                dt = 1.0 / 1    # LO_FPS = 1

            if state_id in state_seconds:
                state_seconds[state_id] += dt
            total_seconds += dt

            # Collect highlights
            if state_id in HIGHLIGHT_STATES:
                ocr = event.get("ocr", {})
                highlights[state_id].append({
                    "t": t,
                    "state_name": STATE_NAMES[state_id],
                    "hp": ocr.get("hp"),
                    "killfeed": ocr.get("killfeed_snippet", ""),
                })

            prev_t = t
            line_count += 1

    print(f"    Processed {line_count} events, {total_seconds:.1f}s total represented")

    if total_seconds == 0:
        print("WARNING: No events found — timeline may be empty.")
        total_seconds = 1.0  # avoid division by zero

    # --- Build final_report.json ---
    dominant_state = max(state_seconds, key=state_seconds.get)
    combat_seconds = state_seconds[6] + state_seconds[7] + state_seconds[8]
    engagement_ratio = combat_seconds / total_seconds if total_seconds > 0 else 0.0

    states_out = {}
    for sid, name in STATE_NAMES.items():
        secs = state_seconds[sid]
        states_out[str(sid)] = {
            "name": name,
            "seconds": round(secs, 2),
            "pct": round(100.0 * secs / total_seconds, 2),
        }

    report = {
        "total_duration_seconds": round(total_seconds, 2),
        "events_processed": line_count,
        "states": states_out,
        "dominant_state": STATE_NAMES[dominant_state],
        "engagement_ratio": round(engagement_ratio, 4),
        "combat_seconds": round(combat_seconds, 2),
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"==> Saved {REPORT_PATH}")

    # --- Build highlights.txt ---
    with open(HIGHLIGHTS_PATH, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("  Project Sentinel — Gameplay Highlights\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Total duration analyzed: {total_duration_fmt(total_seconds)}\n")
        f.write(f"Dominant state:          {STATE_NAMES[dominant_state]}\n")
        f.write(f"Engagement ratio:        {engagement_ratio:.1%}\n\n")

        # State breakdown
        f.write("STATE BREAKDOWN\n")
        f.write("-" * 40 + "\n")
        for sid in sorted(STATE_NAMES.keys()):
            name = STATE_NAMES[sid]
            secs = state_seconds[sid]
            pct = 100.0 * secs / total_seconds
            if secs > 0:
                f.write(f"  [{sid:2d}] {name:<22s}  {secs:8.1f}s  ({pct:5.1f}%)\n")
        f.write("\n")

        # Death events
        deaths = highlights[2] + highlights[3]
        deaths.sort(key=lambda x: x["t"])
        f.write(f"== DEATH EVENTS ({len(deaths)}) ==\n")
        for ev in deaths:
            ts = fmt_timestamp(ev["t"])
            hp_str = f"hp={ev['hp']}" if ev["hp"] is not None else "hp=?"
            f.write(f"  [{ts}]  t={ev['t']:.1f}   state={ev['state_name']:<14s}  {hp_str}\n")
        f.write("\n")

        # Success / kill events
        kills = highlights[4]
        kills.sort(key=lambda x: x["t"])
        f.write(f"== SUCCESS / KILL EVENTS ({len(kills)}) ==\n")
        for ev in kills:
            ts = fmt_timestamp(ev["t"])
            feed = ev["killfeed"] or ""
            f.write(f"  [{ts}]  t={ev['t']:.1f}   killfeed=\"{feed}\"\n")
        f.write("\n")

    print(f"==> Saved {HIGHLIGHTS_PATH}")
    print(f"\n    dominant_state = {STATE_NAMES[dominant_state]}")
    print(f"    engagement_ratio = {engagement_ratio:.1%}")
    print(f"    deaths detected = {len(deaths)},  kills detected = {len(kills)}")


def total_duration_fmt(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{h}h {m}m {sec}s"


if __name__ == "__main__":
    main()
